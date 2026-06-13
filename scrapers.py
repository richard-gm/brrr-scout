"""
Listing collectors for BRRR Scout.

Scraping layer (in order of reliability):
  1. crawl4ai + cookies  — headless Chromium with your browser cookies injected.
                           Bypasses bot detection because Rightmove/Zoopla see
                           a trusted, known session. Best option.
  2. crawl4ai (no cookies) — stealth headless Chromium, no session. Works from
                           residential IPs; may be blocked on cloud/VPS.
  3. requests            — plain HTTP fallback. Fast but easily blocked.
  4. inbox               — browser-saved HTML files in data/inbox/. Always works.

Cookie setup (one-time, takes 2 minutes):
  See COOKIES.md for step-by-step instructions.
  TL;DR: install 'Cookie-Editor' extension → visit rightmove.co.uk and
  zoopla.co.uk → export cookies as JSON → save to data/cookies/.

Optional proxy (set SCRAPER_PROXY_URL env var):
  Routes crawl4ai + requests through a residential proxy if cookies alone
  aren't enough (rare). Supports ScraperAPI, Bright Data etc.
"""

import asyncio, json, logging, os, pathlib, re, time
import requests as _requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RATE_SECONDS  = 6
CRAWL_TIMEOUT = 60_000   # ms — allow time for JS + any challenge pages
PROXY_URL     = os.environ.get("SCRAPER_PROXY_URL")

# Cookie files — drop exports from Cookie-Editor here
COOKIES_DIR   = pathlib.Path(os.environ.get("COOKIES_DIR", "data/cookies"))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")

PC_RE = re.compile(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*(\d[A-Z]{2})\b")


# ---------------------------------------------------------------------------
# Cookie loader
# ---------------------------------------------------------------------------
def _load_cookies(domain_hint: str) -> list[dict]:
    """
    Load cookies for a given domain from data/cookies/.
    Accepts two formats:
      - Cookie-Editor JSON export (list of cookie objects)
      - Playwright storage_state JSON (has a 'cookies' key)

    Files are matched by domain_hint in the filename, e.g.:
      data/cookies/rightmove.json  →  matched by 'rightmove'
      data/cookies/zoopla.json     →  matched by 'zoopla'
      data/cookies/all.json        →  used as fallback for any domain

    Returns a list of Playwright-compatible cookie dicts.
    """
    if not COOKIES_DIR.exists():
        return []

    candidates = []
    for f in COOKIES_DIR.glob("*.json"):
        fname = f.stem.lower()
        if domain_hint.lower() in fname or fname == "all":
            candidates.append(f)

    if not candidates:
        return []

    # Prefer most-specific match (longest filename overlap)
    candidates.sort(key=lambda f: (domain_hint.lower() in f.stem.lower(), len(f.stem)), reverse=True)
    cookie_file = candidates[0]

    try:
        raw = json.loads(cookie_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Cookie file %s could not be read: %s", cookie_file, e)
        return []

    # Playwright storage_state format: {"cookies": [...], "origins": [...]}
    if isinstance(raw, dict) and "cookies" in raw:
        cookies = raw["cookies"]
    # Cookie-Editor / Netscape JSON format: plain list
    elif isinstance(raw, list):
        cookies = raw
    else:
        log.warning("Unrecognised cookie format in %s", cookie_file)
        return []

    # Normalise to Playwright cookie format
    normalised = []
    for c in cookies:
        entry: dict = {
            "name":   c.get("name", ""),
            "value":  c.get("value", ""),
            "domain": c.get("domain", f".{domain_hint}.co.uk"),
            "path":   c.get("path", "/"),
        }
        if "expires" in c:
            entry["expires"] = int(c["expires"])
        if "httpOnly" in c:
            entry["httpOnly"] = bool(c["httpOnly"])
        if "secure" in c:
            entry["secure"] = bool(c["secure"])
        if "sameSite" in c and c["sameSite"] in ("Strict", "Lax", "None"):
            entry["sameSite"] = c["sameSite"]
        if entry["name"] and entry["value"]:
            normalised.append(entry)

    log.info("Loaded %d cookies for %s from %s", len(normalised), domain_hint, cookie_file.name)
    return normalised

def _cookies_as_header(cookies: list[dict]) -> str:
    """Convert cookie list to a Cookie: header string for requests fallback."""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _postcode(text):
    m = PC_RE.search(text or "")
    return (f"{m.group(1)} {m.group(2)}", m.group(1)) if m else (None, None)

def _outcode_only(text):
    m = re.search(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\b", text or "")
    return m.group(1) if m else None

def _domain(portal: str) -> str:
    return "rightmove" if portal == "rightmove" else "zoopla"


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------
def rightmove_search_url(location_id, max_price, min_price=20000):
    return (
        f"https://www.rightmove.co.uk/property-for-sale/find.html?"
        f"locationIdentifier={location_id}&maxPrice={max_price}"
        f"&minPrice={min_price}&sortType=1"
        f"&propertyTypes=flat%2Cterraced&includeSSTC=false"
    )

def zoopla_search_url(area_slug, max_price, min_price=20000):
    return (
        f"https://www.zoopla.co.uk/for-sale/property/{area_slug}/?"
        f"price_max={max_price}&price_min={min_price}&results_sort=lowest_price"
    )


# ---------------------------------------------------------------------------
# HTML parsers
# ---------------------------------------------------------------------------
def parse_rightmove(html, url="rightmove"):
    out = []
    m = re.search(r"window\.jsonModel\s*=\s*(\{.*?\})\s*</script>", html, re.S)
    if m:
        try:
            model = json.loads(m.group(1))
            for p in model.get("properties", []):
                addr = p.get("displayAddress", "")
                pc, oc = _postcode(addr)
                out.append({
                    "source":        "rightmove",
                    "source_id":     str(p.get("id")),
                    "url":           f"https://www.rightmove.co.uk/properties/{p.get('id')}",
                    "address":       addr,
                    "postcode":      pc,
                    "outcode":       oc or _outcode_only(addr),
                    "price":         int(p.get("price", {}).get("amount") or 0) or None,
                    "bedrooms":      p.get("bedrooms"),
                    "prop_type":     p.get("propertySubType"),
                    "is_auction":    int("auction" in (p.get("displayStatus") or "").lower()
                                        or "auction" in (p.get("summary") or "").lower()),
                    "floorplan_url": None,
                })
        except (json.JSONDecodeError, KeyError):
            pass
    if out:
        return out

    m = re.search(
        r'(?:window\.PAGE_MODEL\s*=|id="__NEXT_DATA__"[^>]*>)\s*(\{.*?\})\s*(?:</script>)',
        html, re.S,
    )
    if m:
        try:
            blob = json.loads(m.group(1))
            pd = (blob.get("propertyData")
                  or blob.get("props", {}).get("pageProps", {}).get("propertyData") or {})
            if pd:
                addr = (pd.get("address") or {}).get("displayAddress", "")
                oc   = (pd.get("address") or {}).get("outcode", "")
                inc  = (pd.get("address") or {}).get("incode", "")
                fps  = pd.get("floorplans") or []
                price_raw = (pd.get("prices") or {}).get("primaryPrice", "")
                out.append({
                    "source":        "rightmove",
                    "source_id":     str(pd.get("id")),
                    "url":           url if url.startswith("http")
                                     else f"https://www.rightmove.co.uk/properties/{pd.get('id')}",
                    "address":       addr,
                    "postcode":      f"{oc} {inc}".strip() or None,
                    "outcode":       oc or _outcode_only(addr),
                    "price":         int(re.sub(r"[^\d]", "", price_raw) or 0) or None,
                    "bedrooms":      pd.get("bedrooms"),
                    "prop_type":     pd.get("propertySubType"),
                    "tenure":        (pd.get("tenure") or {}).get("tenureType"),
                    "is_auction":    int(bool(pd.get("auctionOnly"))),
                    "floorplan_url": fps[0].get("url") if fps else None,
                })
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    return out


def parse_zoopla(html, url="zoopla"):
    out  = []
    soup = BeautifulSoup(html, "html.parser")
    nd   = soup.find("script", id="__NEXT_DATA__")
    if not nd:
        return out
    try:
        blob = json.loads(nd.string)
    except (json.JSONDecodeError, TypeError):
        return out

    def _walk(node):
        if isinstance(node, dict):
            if {"listingId", "price"} <= node.keys() or {"listingId", "pricing"} <= node.keys():
                yield node
            for v in node.values():
                yield from _walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from _walk(v)

    seen = set()
    for n in _walk(blob):
        lid = str(n.get("listingId", ""))
        if not lid or lid in seen:
            continue
        seen.add(lid)
        addr      = (n.get("address")
                     or (n.get("location") or {}).get("displayAddress", "") or "")
        price_raw = n.get("price") or (n.get("pricing") or {}).get("label", "")
        price     = int(re.sub(r"[^\d]", "", str(price_raw)) or 0) or None
        pc, oc    = _postcode(addr)
        fp        = None
        for lnk in ((n.get("floorPlan") or {}).get("links") or []):
            fp = lnk.get("url") or fp
        out.append({
            "source":        "zoopla",
            "source_id":     lid,
            "url":           f"https://www.zoopla.co.uk/for-sale/details/{lid}/",
            "address":       addr,
            "postcode":      pc,
            "outcode":       oc or _outcode_only(addr),
            "price":         price,
            "bedrooms":      (n.get("counts") or {}).get("numBedrooms") or n.get("numBeds"),
            "prop_type":     n.get("propertyType"),
            "is_auction":    int("auction" in json.dumps(n.get("flag", "")).lower()),
            "floorplan_url": fp,
        })
    return out


# ---------------------------------------------------------------------------
# Layer 1: crawl4ai (headless Chromium, cookies injected, stealth)
# ---------------------------------------------------------------------------
async def _crawl4ai_fetch(url: str, cookies: list[dict]) -> str | None:
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    except ImportError:
        log.warning("crawl4ai not installed — skipping to requests fallback")
        return None

    browser_kwargs: dict = dict(
        headless=True,
        browser_type="chromium",
        verbose=False,
        user_agent=UA,
        enable_stealth=True,
        extra_args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    if cookies:
        browser_kwargs["cookies"] = cookies
        log.info("crawl4ai: injecting %d cookies", len(cookies))
    if PROXY_URL:
        browser_kwargs["proxy"] = PROXY_URL

    run_kwargs: dict = dict(
        page_timeout=CRAWL_TIMEOUT,
        wait_until="networkidle",
        delay_before_return_html=3.5,
        js_code="window.scrollTo(0, document.body.scrollHeight);",
        wait_for="js:() => !!(window.jsonModel || document.getElementById('__NEXT_DATA__'))",
    )

    try:
        bc = BrowserConfig(**browser_kwargs)
        rc = CrawlerRunConfig(**run_kwargs)
        async with AsyncWebCrawler(config=bc) as crawler:
            result = await crawler.arun(url, config=rc)
        if result.success and result.html and len(result.html) > 5000:
            return result.html
        log.warning("crawl4ai: status %s, html_len %d — insufficient content",
                    result.status_code, len(result.html or ""))
        return None
    except Exception as exc:
        log.warning("crawl4ai exception: %s", exc)
        return None


def _crawl4ai_fetch_sync(url: str, cookies: list[dict]) -> str | None:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(asyncio.run, _crawl4ai_fetch(url, cookies)).result(timeout=90)
        return loop.run_until_complete(_crawl4ai_fetch(url, cookies))
    except Exception as exc:
        log.warning("crawl4ai sync wrapper: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Layer 2: requests fallback (cookies passed as header)
# ---------------------------------------------------------------------------
def _requests_fetch(url: str, cookies: list[dict]) -> str | None:
    headers = {
        "User-Agent":      UA,
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT":             "1",
    }
    if cookies:
        headers["Cookie"] = _cookies_as_header(cookies)
        log.info("requests: sending %d cookies", len(cookies))

    proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
    try:
        resp = _requests.get(url, headers=headers, proxies=proxies, timeout=25)
        resp.raise_for_status()
        return resp.text
    except _requests.RequestException as exc:
        log.warning("requests fallback failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Combined fetch: cookies → crawl4ai → requests → fail
# ---------------------------------------------------------------------------
def _fetch_with_fallback(url: str, portal: str) -> tuple[str | None, str]:
    time.sleep(RATE_SECONDS)
    cookies  = _load_cookies(_domain(portal))
    has_ck   = bool(cookies)
    ck_label = f" (+{len(cookies)} cookies)" if has_ck else " (no cookies)"

    log.info("crawl4ai%s → %s", ck_label, url)
    html = _crawl4ai_fetch_sync(url, cookies)
    if html:
        log.info("crawl4ai succeeded (%d chars)", len(html))
        return html, f"crawl4ai{ck_label}"

    log.info("crawl4ai failed → requests%s", ck_label)
    html = _requests_fetch(url, cookies)
    if html:
        log.info("requests succeeded (%d chars)", len(html))
        return html, f"requests{ck_label}"

    return None, "failed"


# ---------------------------------------------------------------------------
# Public: live scrape
# ---------------------------------------------------------------------------
def scrape_live(searches: list[dict]) -> tuple[list, list]:
    listings, errors = [], []
    for s in searches:
        portal, url = s["portal"], s["url"]
        parser = parse_rightmove if portal == "rightmove" else parse_zoopla
        html, method = _fetch_with_fallback(url, portal)
        if not html:
            has_cookies = bool(_load_cookies(_domain(portal)))
            errors.append(
                f"{portal}: scraping failed (tried crawl4ai + requests"
                f"{', with cookies' if has_cookies else ' — no cookies found'}).\n"
                f"  → Add cookies: see data/cookies/COOKIES.md\n"
                f"  → Or use inbox: save the search page from your browser "
                f"into data/inbox/ and click 'Import inbox'."
            )
            continue
        found = parser(html, url)
        if not found:
            errors.append(
                f"{portal}: page fetched via {method} but no listings parsed. "
                f"The portal may be serving a CAPTCHA or has changed its layout. "
                f"Try refreshing your cookies (see data/cookies/COOKIES.md) "
                f"or use the inbox fallback."
            )
        else:
            log.info("%s: %d listings via %s", portal, len(found), method)
            listings += found
    return listings, errors


# ---------------------------------------------------------------------------
# Public: inbox
# ---------------------------------------------------------------------------
def import_inbox(folder: str = "data/inbox") -> tuple[list, list]:
    """
    Parse every .html/.htm file saved from a browser.
    Rightmove/Zoopla: run search, scroll, Ctrl+S → 'Webpage, HTML Only'
    → save into data/inbox/ → click 'Import inbox' in the app.
    """
    listings, errors = [], []
    inbox = pathlib.Path(folder)
    for f in sorted(inbox.glob("*.htm*")):
        html = f.read_text(errors="ignore")
        if not html.strip():
            errors.append(f"{f.name}: empty file — skipped.")
            continue
        is_rm = "rightmove" in html.lower()[:8000] or "window.jsonModel" in html
        is_zp = "zoopla" in html.lower()[:8000] or '"listingId"' in html
        if is_rm:
            found = parse_rightmove(html, url=f"file://{f.name}")
        elif is_zp:
            found = parse_zoopla(html, url=f"file://{f.name}")
        else:
            found = (parse_rightmove(html, url=f"file://{f.name}")
                     or parse_zoopla(html, url=f"file://{f.name}"))
        if found:
            listings += found
            log.info("inbox: %s → %d listings", f.name, len(found))
        else:
            errors.append(
                f"{f.name}: no listings parsed. Save as 'Webpage, HTML Only' "
                f"(not PDF or plain text), and make sure you scrolled to load all results first."
            )
    return listings, errors
