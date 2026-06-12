"""Sold comps (HM Land Registry, official + free), BRRR deal maths, and the
1-bed -> 2-bed floorplan conversion check via the Claude API."""
import os, json, statistics, base64, requests

LR_URL = "https://landregistry.data.gov.uk/data/ppi/transaction-record.json"

# ---- assumptions (mirror the spreadsheet) ----
A = dict(rate=0.0525, ltv=0.75, sdlt=0.05, fees=2500,
         mgmt=0.10, maint=0.08, voids=0.04, insurance=350,
         stress_rate=0.07, stress_cover=1.25)

def fetch_sold_comps(postcode_or_outcode, max_pages=3):
    """HM Land Registry Price Paid Data. Filter to recent sales client-side."""
    comps, page = [], 0
    while page < max_pages:
        try:
            r = requests.get(LR_URL, params={
                "propertyAddress.postcode": postcode_or_outcode,
                "_pageSize": 200, "_page": page}, timeout=25)
            r.raise_for_status()
            items = r.json().get("result", {}).get("items", [])
        except (requests.RequestException, ValueError):
            break
        if not items:
            break
        for it in items:
            ad = it.get("propertyAddress", {})
            comps.append({
                "postcode": ad.get("postcode"),
                "address": ", ".join(x for x in [ad.get("paon"), ad.get("street"), ad.get("town")] if x),
                "price": it.get("pricePaid"),
                "sold_date": (it.get("transactionDate") or "")[:10],
                "prop_type": (it.get("propertyType", {}).get("label", [""]) or [""])[0],
            })
        page += 1
    comps = [c for c in comps if c["price"]]
    comps.sort(key=lambda c: c["sold_date"], reverse=True)
    return comps

def comp_stats(comps, since="2024-01-01", price_cap=200000):
    recent = [c["price"] for c in comps if c["sold_date"] >= since and c["price"] <= price_cap]
    if not recent:
        return 0, None
    return len(recent), int(statistics.median(recent))

# ---- Feature 5: street-level comp scoring ----
import re as _re

def extract_street(address):
    """'12 Brick Terrace, Middlesbrough' -> 'BRICK TERRACE'."""
    if not address:
        return None
    first = address.split(",")[0]
    street = _re.sub(r"^\s*(flat|apartment|apt|unit)?\s*[\d\-/]+[a-z]?\s*", "", first, flags=_re.I).strip()
    return street.upper() or None

def _recency_weight(sold_date):
    yr = int(sold_date[:4]) if sold_date[:4].isdigit() else 2020
    return {2026: 3.0, 2025: 2.0, 2024: 1.0}.get(yr, 0.5)

def _wmedian(pairs):
    """pairs: [(price, weight)] -> weighted median."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    acc = 0
    for p, w in pairs:
        acc += w
        if acc >= total / 2:
            return int(p)
    return int(pairs[-1][0]) if pairs else None

def score_comps(comps, address, prop_type=None, since="2024-01-01", price_cap=200000):
    """Tiered matching: same street > same type in outcode > outcode.
    Returns (count, value, confidence, basis)."""
    recent = [c for c in comps if (c.get("sold_date") or "") >= since and c.get("price") and c["price"] <= price_cap]
    street = extract_street(address)
    tiers = []
    if street:
        tiers.append(("same street", [c for c in recent if street in (c.get("address") or "").upper()]))
    if prop_type:
        t = prop_type.lower()
        key = "terr" if "terr" in t else ("flat" if "flat" in t or "apart" in t else t[:4])
        tiers.append(("same type, outcode", [c for c in recent if key in (c.get("prop_type") or "").lower()]))
    tiers.append(("outcode", recent))
    for basis, pool in tiers:
        if basis == "same street" and len(pool) >= 2:
            conf = "HIGH" if len(pool) >= 3 else "MEDIUM"
        elif basis == "same type, outcode" and len(pool) >= 5:
            conf = "MEDIUM"
        elif basis == "outcode" and pool:
            conf = "LOW"
        else:
            continue
        val = _wmedian([(c["price"], _recency_weight(c["sold_date"])) for c in pool])
        return len(pool), val, conf, basis
    return 0, None, "NONE", "no recent comps"

# ---- Feature 2: max-bid reverse calculator ----
def max_bid(end_value, refurb, monthly_rent, target_roi=0.12):
    """Work backwards: given end value, refurb and rent, what's the most you can pay?
    Returns dict with bid for full recycle, bid for target ROI, and the binding numbers."""
    loan = end_value * A["ltv"]
    mortgage_pm = loan * A["rate"] / 12
    opex_pm = monthly_rent * (A["mgmt"] + A["maint"] + A["voids"]) + A["insurance"] / 12
    cashflow_yr = (monthly_rent - mortgage_pm - opex_pm) * 12
    stress = monthly_rent >= loan * A["stress_rate"] / 12 * A["stress_cover"]
    out = dict(loan=int(loan), cashflow_yr=int(cashflow_yr), stress_pass=stress,
               bid_full_recycle=None, bid_target_roi=None, max_bid=None,
               note="")
    if cashflow_yr <= 0:
        out["note"] = "Negative cashflow at this rent/value — no bid works. Walk away."
        return out
    bid_recycle = (0.80 * end_value - refurb - A["fees"]) / (1 + A["sdlt"])
    max_left_in = cashflow_yr / target_roi
    bid_roi = (max_left_in + loan - refurb - A["fees"]) / (1 + A["sdlt"])
    out["bid_full_recycle"] = max(int(bid_recycle // 250 * 250), 0)
    out["bid_target_roi"] = max(int(bid_roi // 250 * 250), 0)
    out["max_bid"] = out["bid_target_roi"]
    if not stress:
        out["note"] = ("Rent fails the lender stress test at this loan size — "
                       "the refinance will be cut. Treat the recycle bid as optimistic.")
    return out

def estimate_rent(price, outcode=""):
    """Crude fallback: ~1.15% of value pcm in high-yield northern postcodes.
    Always override with real Rightmove/Zoopla rental comps before bidding."""
    return int(round(price * 0.0115 / 25) * 25)

def analyse_deal(price, end_value, refurb, monthly_rent):
    sdlt = price * A["sdlt"]
    total_in = price + refurb + sdlt + A["fees"]
    loan = end_value * A["ltv"]
    pulled = min(loan, total_in)
    left_in = max(total_in - loan, 0)
    mortgage_pm = loan * A["rate"] / 12
    opex_pm = monthly_rent * (A["mgmt"] + A["maint"] + A["voids"]) + A["insurance"] / 12
    cashflow_yr = (monthly_rent - mortgage_pm - opex_pm) * 12
    roi = cashflow_yr / left_in if left_in > 0 else float("inf")
    stress = monthly_rent >= loan * A["stress_rate"] / 12 * A["stress_cover"]
    if not stress or cashflow_yr <= 0:
        verdict = "WALK AWAY"
    elif total_in <= 0.80 * end_value:
        verdict = "FULL RECYCLE"      # pull ~all cash out and repeat
    elif roi >= 0.12:
        verdict = "GOOD DEAL"         # beats your 7-12% target
    elif roi >= 0.07:
        verdict = "ON TARGET"
    elif roi >= 0.04:
        verdict = "THIN"
    else:
        verdict = "WALK AWAY"
    return dict(total_cash_in=int(total_in), refi_loan=int(loan), pulled_out=int(pulled),
                left_in=int(left_in), net_cashflow_yr=int(cashflow_yr),
                roi=round(roi, 4) if roi != float("inf") else 9.99,
                gross_yield=round(monthly_rent * 12 / price, 4),
                stress_pass=stress, verdict=verdict,
                end_value=int(end_value), refurb_estimate=int(refurb), monthly_rent=int(monthly_rent))

# ---- floorplan conversion check (Claude vision) ----
CONVERSION_PROMPT = """You are assessing a UK property floorplan for an investor strategy:
convert a 1-bed flat/house into a 2-bed by moving the kitchen into the open-plan
living room and turning the old kitchen into a bedroom.

Assess from the floorplan and respond ONLY with JSON, no markdown fences:
{
 "convertible": true/false/"maybe",
 "kitchen_has_window": true/false/"unclear",
 "kitchen_size_ok": true/false/"unclear",     // new bedroom should be >= ~7 sqm
 "living_room_fits_kitchen": true/false/"unclear",
 "fire_escape_ok": true/false/"unclear",      // new bedroom must not exit only through kitchen
 "estimated_kitchen_sqm": number or null,
 "concerns": ["..."],
 "summary": "one sentence"
}"""

def check_conversion(floorplan_url):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"convertible": "unknown", "summary": "Set ANTHROPIC_API_KEY to enable floorplan analysis."}
    if not floorplan_url:
        return {"convertible": "unknown", "summary": "No floorplan published for this listing."}
    try:
        img = requests.get(floorplan_url, timeout=20)
        img.raise_for_status()
        media = img.headers.get("Content-Type", "image/jpeg").split(";")[0]
        if media == "image/gif":
            media = "image/jpeg"
        b64 = base64.b64encode(img.content).decode()
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json={"model": "claude-sonnet-4-20250514", "max_tokens": 600,
                                "messages": [{"role": "user", "content": [
                                    {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
                                    {"type": "text", "text": CONVERSION_PROMPT}]}]},
                          timeout=60)
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        return json.loads(text.replace("```json", "").replace("```", "").strip())
    except (requests.RequestException, ValueError) as e:
        return {"convertible": "unknown", "summary": f"Floorplan analysis failed: {e}"}

# ---- Feature 1: legal pack red-flag analysis (Claude API, PDF) ----
PACK_PROMPT = """You are a UK property solicitor's assistant reviewing an auction legal pack
for a buy-refurbish-refinance investor. Identify red flags. Respond ONLY with JSON:
{
 "tenure": "freehold/leasehold/unclear",
 "lease_years_remaining": number or null,
 "tenanted": true/false/"unclear",
 "buyer_pays_seller_fees": true/false/"unclear",   // special conditions making buyer pay seller's costs
 "extra_buyer_costs_estimate": number or null,      // GBP, from special conditions
 "title_issues": ["..."],                           // restrictions, covenants, missing title, possessory title
 "searches_included": true/false/"unclear",
 "japanese_knotweed_or_environmental": true/false/"unclear",
 "completion_days": number or null,
 "red_flags": ["each serious issue, one line"],
 "risk": "LOW/MEDIUM/HIGH",
 "summary": "two sentences max"
}"""

def analyse_legal_pack(pdf_path):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"risk": "UNKNOWN", "summary": "Set ANTHROPIC_API_KEY to enable legal pack analysis."}
    try:
        with open(pdf_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json={"model": "claude-sonnet-4-20250514", "max_tokens": 1200,
                                "messages": [{"role": "user", "content": [
                                    {"type": "document", "source": {"type": "base64",
                                     "media_type": "application/pdf", "data": b64}},
                                    {"type": "text", "text": PACK_PROMPT}]}]},
                          timeout=120)
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        return json.loads(text.replace("```json", "").replace("```", "").strip())
    except (OSError, requests.RequestException, ValueError) as e:
        return {"risk": "UNKNOWN", "summary": f"Pack analysis failed: {e}"}
