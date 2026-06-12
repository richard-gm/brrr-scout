"""Listing collectors: live scrape (best effort) + local HTML inbox (reliable).

Rightmove & Zoopla prohibit automated scraping in their T&Cs and use bot
protection, so live mode may fail at any time. The inbox is the dependable
path: save listing/search pages from your browser into data/inbox/ and run
the importer. Keep rates low; this tool is for personal research only.
"""
import json, re, time, pathlib, requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en-GB,en;q=0.9"}
RATE_SECONDS = 5
PC_RE = re.compile(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*(\d[A-Z]{2})\b")

def _get(url):
    time.sleep(RATE_SECONDS)
    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    return r.text

def _postcode(text):
    m = PC_RE.search(text or "")
    return (f"{m.group(1)} {m.group(2)}", m.group(1)) if m else (None, None)

def _outcode_only(text):
    m = re.search(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\b", text or "")
    return m.group(1) if m else None

# ---------- Rightmove ----------
def rightmove_search_url(location_id, max_price, min_price=20000):
    return (f"https://www.rightmove.co.uk/property-for-sale/find.html?"
            f"locationIdentifier={location_id}&maxPrice={max_price}&minPrice={min_price}"
            f"&sortType=1&propertyTypes=flat%2Cterraced&includeSSTC=false")

def parse_rightmove(html, url="rightmove"):
    """Works on both search-result and single-listing pages (live or saved)."""
    out = []
    m = re.search(r"window\.jsonModel\s*=\s*(\{.*?\})\s*</script>", html, re.S)
    if m:
        try:
            model = json.loads(m.group(1))
            for p in model.get("properties", []):
                addr = p.get("displayAddress", "")
                pc, oc = _postcode(addr)
                out.append({
                    "source": "rightmove", "source_id": str(p.get("id")),
                    "url": f"https://www.rightmove.co.uk/properties/{p.get('id')}",
                    "address": addr, "postcode": pc, "outcode": oc or _outcode_only(addr),
                    "price": int(p.get("price", {}).get("amount") or 0) or None,
                    "bedrooms": p.get("bedrooms"),
                    "prop_type": p.get("propertySubType"),
                    "is_auction": int("auction" in (p.get("displayStatus") or "").lower()
                                      or "auction" in (p.get("summary") or "").lower()),
                    "floorplan_url": None,
                })
        except json.JSONDecodeError:
            pass
    if out:
        return out
    # Single listing page: PAGE_MODEL / __NEXT_DATA__
    m = re.search(r"(?:window\.PAGE_MODEL\s*=|id=\"__NEXT_DATA__\"[^>]*>)\s*(\{.*?\})\s*(?:</script>)", html, re.S)
    if m:
        try:
            blob = json.loads(m.group(1))
            pd = (blob.get("propertyData")
                  or blob.get("props", {}).get("pageProps", {}).get("propertyData") or {})
            if pd:
                addr = (pd.get("address") or {}).get("displayAddress", "")
                pc = (pd.get("address") or {}).get("outcode", "") + " " + (pd.get("address") or {}).get("incode", "")
                fps = pd.get("floorplans") or []
                out.append({
                    "source": "rightmove", "source_id": str(pd.get("id")),
                    "url": url if url.startswith("http") else f"https://www.rightmove.co.uk/properties/{pd.get('id')}",
                    "address": addr, "postcode": pc.strip() or None,
                    "outcode": (pd.get("address") or {}).get("outcode") or _outcode_only(addr),
                    "price": (pd.get("prices") or {}).get("primaryPrice") and
                             int(re.sub(r"[^\d]", "", pd["prices"]["primaryPrice"]) or 0) or None,
                    "bedrooms": pd.get("bedrooms"),
                    "prop_type": pd.get("propertySubType"),
                    "tenure": (pd.get("tenure") or {}).get("tenureType"),
                    "is_auction": int(bool(pd.get("auctionOnly"))),
                    "floorplan_url": fps[0].get("url") if fps else None,
                })
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    return out

# ---------- Zoopla ----------
def zoopla_search_url(area_slug, max_price, min_price=20000):
    return (f"https://www.zoopla.co.uk/for-sale/property/{area_slug}/"
            f"?price_max={max_price}&price_min={min_price}&results_sort=lowest_price")

def parse_zoopla(html, url="zoopla"):
    out = []
    soup = BeautifulSoup(html, "html.parser")
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd:
        try:
            blob = json.loads(nd.string)
            def walk(node):
                if isinstance(node, dict):
                    if {"listingId", "price"} <= node.keys() or {"listingId", "pricing"} <= node.keys():
                        yield node
                    for v in node.values():
                        yield from walk(v)
                elif isinstance(node, list):
                    for v in node:
                        yield from walk(v)
            seen = set()
            for n in walk(blob):
                lid = str(n.get("listingId"))
                if lid in seen:
                    continue
                seen.add(lid)
                addr = n.get("address") or (n.get("location") or {}).get("displayAddress", "") or ""
                price_raw = n.get("price") or (n.get("pricing") or {}).get("label", "")
                price = int(re.sub(r"[^\d]", "", str(price_raw)) or 0) or None
                pc, oc = _postcode(addr)
                fp = None
                for f in (n.get("floorPlan") or {}).get("links", []) or []:
                    fp = f.get("url") or fp
                out.append({
                    "source": "zoopla", "source_id": lid,
                    "url": f"https://www.zoopla.co.uk/for-sale/details/{lid}/",
                    "address": addr, "postcode": pc, "outcode": oc or _outcode_only(addr),
                    "price": price, "bedrooms": (n.get("counts") or {}).get("numBedrooms") or n.get("numBeds"),
                    "prop_type": n.get("propertyType"),
                    "is_auction": int("auction" in json.dumps(n.get("flag", "")).lower()),
                    "floorplan_url": fp,
                })
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    return out

# ---------- entry points ----------
def scrape_live(searches):
    """searches: list of dicts {portal, url}. Returns (listings, errors)."""
    listings, errors = [], []
    for s in searches:
        try:
            html = _get(s["url"])
            parser = parse_rightmove if s["portal"] == "rightmove" else parse_zoopla
            found = parser(html, s["url"])
            if not found:
                errors.append(f"{s['portal']}: page fetched but no listings parsed (layout change or bot block)")
            listings += found
        except requests.RequestException as e:
            errors.append(f"{s['portal']}: {e} — likely bot protection. Use the inbox fallback.")
    return listings, errors

def import_inbox(folder="data/inbox"):
    """Parse every .html file saved from a browser. Reliable, ToS-friendly path."""
    listings, errors = [], []
    for f in pathlib.Path(folder).glob("*.htm*"):
        html = f.read_text(errors="ignore")
        found = parse_rightmove(html, url=f"file://{f.name}") if "rightmove" in html.lower()[:5000] \
            else parse_zoopla(html, url=f"file://{f.name}")
        if not found:
            found = parse_rightmove(html, url=f"file://{f.name}") or parse_zoopla(html, url=f"file://{f.name}")
        if found:
            listings += found
        else:
            errors.append(f"{f.name}: could not parse — is it a full saved page?")
    return listings, errors
