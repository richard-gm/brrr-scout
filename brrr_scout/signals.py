"""Deal signal computation — labels applied to each deal card.

Each signal is a dict: { label, cls, detail }.
  label  – short uppercase tag shown on the card
  cls    – CSS class for colour coding
  detail – optional explanatory string (shown as tooltip / subtitle)
"""
import time as _time

_STALE_DAYS = 45   # listing is "stale" after this many days on market
_BRRR_MIN_ROI = 0.10  # 10 % ROI to qualify as BRRR candidate
_BRRR_MIN_RECYCLE = 0.70  # ≥70 % of cash pulled back out


def compute_signals(d):
    """Return list of signal dicts for a deals-query row (sqlite3.Row or dict)."""
    if not isinstance(d, dict):
        d = dict(d)

    sigs = []
    now = _time.time()

    # --- price signals -------------------------------------------------------
    price_drop = d.get("price_drop") or 0
    n_prices = d.get("n_prices") or 0

    if price_drop > 0:
        sigs.append({
            "label": "RECENTLY REDUCED",
            "cls": "sig-reduced",
            "detail": f"£{price_drop:,} drop tracked",
        })

    if n_prices >= 3 and price_drop > 0:
        sigs.append({
            "label": "PRICE HISTORY",
            "cls": "sig-history",
            "detail": f"{n_prices} price points — still falling",
        })

    # --- time on market ------------------------------------------------------
    first_seen = d.get("first_seen")
    if first_seen and (now - first_seen) > _STALE_DAYS * 86400:
        days = int((now - first_seen) / 86400)
        sigs.append({
            "label": "STALE LISTING",
            "cls": "sig-stale",
            "detail": f"{days} days on market",
        })

    # --- strategy signals ----------------------------------------------------
    roi = d.get("roi")
    stress_pass = d.get("stress_pass")
    pulled_out = d.get("pulled_out") or 0
    total_cash_in = d.get("total_cash_in") or 0
    recycle_ratio = (pulled_out / total_cash_in) if total_cash_in > 0 else 0

    if roi and roi >= _BRRR_MIN_ROI and stress_pass and recycle_ratio >= _BRRR_MIN_RECYCLE:
        sigs.append({
            "label": "BRRR CANDIDATE",
            "cls": "sig-brrr",
            "detail": f"{roi * 100:.1f}% ROI · {recycle_ratio * 100:.0f}% recycled",
        })
    elif roi and roi >= _BRRR_MIN_ROI and stress_pass:
        sigs.append({
            "label": "GOOD YIELD",
            "cls": "sig-yield",
            "detail": f"{roi * 100:.1f}% ROI · stress PASS",
        })

    # --- property type signals -----------------------------------------------
    if d.get("is_auction"):
        sigs.append({"label": "AUCTION", "cls": "sig-auction", "detail": None})

    tenure = (d.get("tenure") or "").lower()
    if "leasehold" in tenure:
        sigs.append({"label": "LEASEHOLD", "cls": "sig-leasehold", "detail": None})

    return sigs
