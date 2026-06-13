# BRRR Scout

A local web app for UK Buy–Refurbish–Refinance–Rent investors. Finds and
tracks cheap listings, prices deals against official Land Registry sold data,
locks auction max bids, screens legal packs with AI, and counts down refinance
windows on the properties you own.

All data lives in one SQLite file (`data/brrr_scout.db`) so you can compare
deals and prices over time.

---

## Quick start

### Option A — Docker (recommended)
```bash
docker build -t brrr-scout .
docker run -p 5000:5000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e SCRAPER_PROXY_URL=http://scraperapi:<key>@proxy-server.scraperapi.com:8001 \
  -v $(pwd)/data:/app/data \
  brrr-scout
```
Open http://localhost:5000

### Option B — local Python
```bash
pip install -r requirements.txt
crawl4ai-setup                  # downloads Playwright/Chromium (once)
export ANTHROPIC_API_KEY=sk-ant-...
export SCRAPER_PROXY_URL=...    # optional, see Scraping section
python app.py
```

---

## The four pages

### 1  Deal ledger  `/`
Every listing ranked by ROI. Each card shows:
- Asking price with price-drop tracking across scans
- Comp value with HIGH / MEDIUM / LOW confidence badge (same street → same
  type → outcode, recency-weighted)
- End value, pull-out gauge (cash out vs cash left in at 75% LTV)
- Annual cashflow, lender stress test, verdict:
  **FULL RECYCLE / GOOD DEAL / ON TARGET / THIN / WALK AWAY**

The dark **Max bid calculator** panel at the top works backwards: enter end
value, refurb and rent → prints the most you can pay and still hit your ROI.

### 2  Auction tracker  `/auctions`
Per lot: countdown to auction day, guide price vs **locked max bid** (red
warning when guide already exceeds it), 10-point bid-day checklist (stamps
BID READY only at 10/10), and legal pack PDF analysis (see CLAUDE.md).

### 3  Portfolio  `/portfolio`
Per owned property: 6-month refinance countdown from completion date, refurb
spend vs budget, one-click revalue from Land Registry comps, and how much a
refinance releases today. Red **REFI WINDOW OPEN** banner when the window is
open and equity is available. Totals: cash deployed, cash recycled, net cash
in market, portfolio cashflow, aggregate LTV.

### 4  Max bid  `/maxbid`
Bookmarkable — URL preserves all inputs for sharing / saving per lot.

---

## Scraping — how it works

Property portals actively block bots. The app uses a three-layer approach:

```
crawl4ai (headless Chromium, JS-rendered)
    ↓ fails
requests (plain HTTP, spoofed UA)
    ↓ fails
inbox (browser-saved HTML — always works)
```

**Layer 1 — crawl4ai (primary)**
Headless Chromium with stealth settings, networkidle wait, JS scroll, and a
3.5 s settle delay so listing data has time to land in the DOM. This beats
most bot-protection that blocks plain HTTP but passes JS-rendered clients.

**Layer 2 — requests fallback**
Fast plain-HTTP attempt. Catches pages where the portal serves the full JSON
payload without requiring JavaScript.

**Layer 3 — inbox (always reliable)**
Save the search page from your browser into `data/inbox/`:
1. Run your search on Rightmove or Zoopla and scroll to load all results
2. `Ctrl+S` (or `Cmd+S`) → **Webpage, HTML Only**
3. Save the file into `data/inbox/` (any filename; `.html` or `.htm`)
4. Click **Import inbox** in the app

The app auto-detects which portal the file came from.

**Optional proxy — greatly improves live success rate**
Set `SCRAPER_PROXY_URL` to route all traffic through a residential proxy:
```bash
# ScraperAPI (cheapest for this use case, ~$49/mo for 100k requests)
export SCRAPER_PROXY_URL=http://scraperapi:<API_KEY>@proxy-server.scraperapi.com:8001

# Bright Data
export SCRAPER_PROXY_URL=http://<user>:<pass>@zproxy.lum-superproxy.io:22225
```
Both crawl4ai and the requests fallback route through it automatically.

**Rate limit:** 8 seconds between requests. Do not lower this. Rightmove and
Zoopla prohibit automated access in their T&Cs — this tool is for personal
research only.

---

## Data sources
| Data | Source | Notes |
|---|---|---|
| Listings | Rightmove, Zoopla | live scrape or inbox |
| Sold comps | HM Land Registry Price Paid API | free, official, same data surveyors use |
| Floorplan check | Claude API (claude-sonnet) | optional, see CLAUDE.md |
| Legal pack | Claude API (claude-sonnet) | optional, see CLAUDE.md |

---

## Model assumptions  (edit in `analyzer.py`, dict `A`)
| Setting | Default | Notes |
|---|---|---|
| BTL interest rate | 5.25% | interest-only; check current deals |
| Refinance LTV | 75% | standard BTL max |
| Investor SDLT | 5% | England additional-property surcharge |
| Legal/sourcing per deal | £2,500 | solicitor + survey + auction entry |
| Management fee | 10% of rent | full management |
| Maintenance | 8% of rent | older stock allowance |
| Voids | 4% of rent | ~2 weeks/year |
| Insurance | £350/yr | typical low-value terrace/flat |
| Stress test | rent ≥ 125% × mortgage @ 7% | standard BTL lender requirement |

---

## Files
```
app.py          Flask routes + deal pipeline
analyzer.py     Deal maths, max-bid, comp scoring, AI prompts
scrapers.py     crawl4ai + requests + inbox importer
db.py           SQLite schema, migrations, all queries
config.py       Your target areas and price ceiling
CLAUDE.md       AI task contracts (floorplans + legal packs)
Dockerfile      Production container with Chromium pre-installed
data/           Database, inbox/ for HTML saves, packs/ for legal PDFs
```

---

## Honest limitations
- End values default to the Land Registry outcode comp median (capped at
  asking +45%). Always verify with same-street solds before bidding — the
  valuer will.
- Rent estimates are heuristic (~1.15% of value/month). Use real rental comps.
- AI floorplan and legal pack outputs are **screening aids only**. Conversions
  need freeholder consent and Building Regulations sign-off. Legal packs need
  a solicitor to read before you bid. The person liable on completion day is you.
