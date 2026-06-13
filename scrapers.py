"""
Listing collectors for BRRR Scout.

Scraping layer (in order of reliability):
  1. crawl4ai   — headless Chromium, JS-rendered, stealth mode. Primary.
  2. requests   — plain HTTP with spoofed UA. Fast fallback for pages that
                  serve full JSON without JS.
  3. inbox      — browser-saved HTML files in data/inbox/. Always works.

Rightmove & Zoopla prohibit automated scraping in their T&Cs and deploy bot
protection (Cloudflare, Akamai, DataDome). Even crawl4ai can be blocked.
The inbox is the dependable path for personal research. Live scraping is
best-effort and rate-limited to 8 s/request — do not lower it.

Optional proxy (beats most bot-protection):
  Set SCRAPER_PROXY_URL in your environment, e.g.:
    ScraperAPI:   http://scraperapi:<API_KEY>@proxy-server.scraperapi.com:8001
    Bright Data:  http://user:pass@zproxy.lum-superproxy.io:22225
  crawl4ai will route all traffic through it when set.
"""

import asyncio, json, logging, os, pathlib, re, time
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RATE_SECONDS  = 8        # minimum gap between live requests; be respectful
CRAWL_TIMEOUT = 60_000   # ms — Cloudflare challenges can take ~10 s
PROXY_URL     = os.environ.get("SCRAPER_PROXY_URL")  # optional

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")

PC_RE = re.compile(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*(\d[A-Z]{2})\b")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _postcode(text):
    m = PC_RE.search(text or "")
    return (f"{m.group(1)} {m.group(2)}", m.group(1)) if m else (None, None)

def _outcode_only(text):
    m = re.search(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)\b", text or "")
    return m.group(1) if m else None


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
# HTML parsers (portal-specific; called by both live scrapers and inbox)
# ---------------------------------------------------------------------------
def parse_rightmove(html, url="rightmove"):
    """Parse Rightmove search-results or single-listing page HTML."""
    out = []

    # Search results embed window.jsonModel
    m = re.search(r"window\.jsonModel\s*=\s*(\{.*?\})\s*</script>", html, re.S)
    if m:
        try:
            model = json.loads(m.group(1))
            for p in model.get("properties", []):
                addr = p.get("displayAddress", "")
                pc, oc = _postcode(addr)
                out.append({
                    "source":       "rightmove",
                    "source_id":    str(p.get("id")),
                    "url":          f"https://www.rightmove.co.uk/properties/{p.get('id')}",
                    "address":      addr,
                    "postcode":     pc,
                    "outcode":      oc or _outcode_only(addr),
                    "price":        int(p.get("price", {}).get("amount") or 0) or None,
                    "bedrooms":     p.get("bedrooms"),
                    "prop_type":    p.get("propertySubType"),
                    "is_auction":   int("auction" in (p.get("displayStatus") or "").lower()
                                       or "auction" in (p.get("summary") or "").lower()),
                    "floorplan_url": None,
                })
        except (json.JSONDecodeError, KeyError):
            pass

    if out:
        return out

    # Single listing page: __NEXT_DATA__ or PAGE_MODEL
    m = re.search(
        r'(?:window\.PAGE_MODEL\s*=|id="__NEXT_DATA__"[^>]*>)\s*(\{.*?\})\s*(?:</script>)',
        html, re.S,
    )
    if m:
        try:
            blob = json.loads(m.group(1))
            pd = (
                blob.get("propertyData")
                or blob.get("props", {}).get("pageProps", {}).get("propertyData")
                or {}
            )
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
    """Parse Zoopla search-results page HTML (__NEXT_DATA__)."""
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
                     or (n.get("location") or {}).get("displayAddress", "")
                     or "")
        price_raw = n.get("price") or (n.get("pricing") or {}).get("label", "")
        price     = int(re.sub(r"[^\d]", "", str(price_raw)) or 0) or None
        pc, oc    = _postcode(addr)
        fp        = None
        for f in ((n.get("floorPlan") or {}).get("links") or []):
            fp = f.get("url") or fp
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
# Layer 1: crawl4ai (headless Chromium, JS-rendered, stealth)
# ---------------------------------------------------------------------------
async def _crawl4ai_fetch(url: str) -> str | None:
    """
    Fetch a URL with crawl4ai. Returns rendered HTML string or None on failure.
    Applies stealth UA, waits for JS data to land, optionally routes via proxy.
    """
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig  # type: ignore
    except ImportError:
        log.warning("crawl4ai not installed — falling back to requests")
        return None

    browser_kwargs: dict = dict(
        headless=True,
        browser_type="chromium",
        verbose=False,
        user_agent=UA,
        extra_args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    if PROXY_URL:
        browser_kwargs["proxy"] = PROXY_URL
        log.info("crawl4ai: routing via proxy")

    run_kwargs: dict = dict(
        page_timeout=CRAWL_TIMEOUT,
        wait_until="networkidle",
        delay_before_return_html=3.5,
        # Scroll to trigger lazy-load of listing cards
        js_code="window.scrollTo(0, document.body.scrollHeight);",
        # Wait for Rightmove's jsonModel or Zoopla's __NEXT_DATA__ to appear
        wait_for="js:() => !!(window.jsonModel || document.getElementById('__NEXT_DATA__'))",
    )

    try:
        bc = BrowserConfig(**browser_kwargs)
        rc = CrawlerRunConfig(**run_kwargs)
        async with AsyncWebCrawler(config=bc) as crawler:
            result = await crawler.arun(url, config=rc)
        if result.success and result.html and len(result.html) > 5000:
            return result.html
        log.warning("crawl4ai: %s — status %s, html_len %d",
                    url, result.status_code, len(result.html or ""))
        return None
    except Exception as exc:
        log.warning("crawl4ai exception on %s: %s", url, exc)
        return None


def _crawl4ai_fetch_sync(url: str) -> str | None:
    """Sync wrapper around the async crawl4ai fetcher."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If called from within an async context (e.g. Flask with async support)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(asyncio.run, _crawl4ai_fetch(url))
                return future.result(timeout=90)
        return loop.run_until_complete(_crawl4ai_fetch(url))
    except Exception as exc:
        log.warning("crawl4ai sync wrapper failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Layer 2: requests fallback (plain HTTP)
# ---------------------------------------------------------------------------
def _requests_fetch(url: str) -> str | None:
    headers = {
        "User-Agent":      UA,
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT":             "1",
    }
    proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
    try:
        resp = requests.get(url, headers=headers, proxies=proxies, timeout=25)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        log.warning("requests fallback failed for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Combined live fetch with automatic fallback
# ---------------------------------------------------------------------------
def _fetch_with_fallback(url: str, portal: str) -> tuple[str | None, str]:
    """
    Try crawl4ai first, then requests. Returns (html, method_used).
    Enforces RATE_SECONDS between calls.
    """
    time.sleep(RATE_SECONDS)

    log.info("Trying crawl4ai for %s (%s)", portal, url)
    html = _crawl4ai_fetch_sync(url)
    if html:
        log.info("crawl4ai succeeded for %s (%d chars)", portal, len(html))
        return html, "crawl4ai"

    log.info("crawl4ai failed — trying requests fallback for %s", portal)
    html = _requests_fetch(url)
    if html:
        log.info("requests fallback succeeded for %s (%d chars)", portal, len(html))
        return html, "requests"

    return None, "failed"


# ---------------------------------------------------------------------------
# Public: live scrape
# ---------------------------------------------------------------------------
def scrape_live(searches: list[dict]) -> tuple[list, list]:
    """
    searches: list of dicts with keys {portal, url}.
    Returns (listings, errors).
    """
    listings, errors = [], []

    for s in searches:
        portal = s["portal"]
        url    = s["url"]
        parser = parse_rightmove if portal == "rightmove" else parse_zoopla

        html, method = _fetch_with_fallback(url, portal)

        if not html:
            errors.append(
                f"{portal} ({url}): both crawl4ai and requests failed. "
                "If you have a SCRAPER_PROXY_URL set, check it's valid. "
                "Otherwise use the inbox: save the page from your browser into data/inbox/."
            )
            continue

        found = parser(html, url)
        if not found:
            errors.append(
                f"{portal}: page fetched via {method} ({len(html):,} chars) "
                "but no listings parsed — the portal may have changed its HTML structure, "
                "or bot detection is serving a CAPTCHA page. "
                "Save the page from your browser into data/inbox/ as a reliable alternative."
            )
        else:
            log.info("%s: %d listings via %s", portal, len(found), method)
            listings += found

    return listings, errors


# ---------------------------------------------------------------------------
# Public: browser-save inbox (always reliable)
# ---------------------------------------------------------------------------
def import_inbox(folder: str = "data/inbox") -> tuple[list, list]:
    """
    Parse every .html / .htm file saved from a browser.
    Reliable, ToS-friendly alternative to live scraping.

    How to save:
      Rightmove/Zoopla: run your search, scroll to load all results,
      then Ctrl+S (or Cmd+S) → 'Webpage, HTML Only' → save into data/inbox/.
      Name the file so it's clear which portal it came from, e.g.
      'rightmove_ne4_2026-06-13.html'.
    """
    listings, errors = [], []
    inbox = pathlib.Path(folder)

    for f in sorted(inbox.glob("*.htm*")):
        html = f.read_text(errors="ignore")
        if not html.strip():
            errors.append(f"{f.name}: empty file — skipped.")
            continue

        # Pick parser by sniffing the content
        is_rm = "rightmove" in html.lower()[:8000] or "window.jsonModel" in html
        is_zp = "zoopla" in html.lower()[:8000] or '"listingId"' in html

        if is_rm:
            found = parse_rightmove(html, url=f"file://{f.name}")
        elif is_zp:
            found = parse_zoopla(html, url=f"file://{f.name}")
        else:
            # Try both
            found = parse_rightmove(html, url=f"file://{f.name}") or \
                    parse_zoopla(html, url=f"file://{f.name}")

        if found:
            listings += found
            log.info("inbox: %s → %d listings", f.name, len(found))
        else:
            errors.append(
                f"{f.name}: could not parse — is it a full saved page? "
                "Make sure you saved as 'Webpage, HTML Only' (not PDF or plain text)."
            )

    return listings, errors
