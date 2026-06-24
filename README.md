# BRRR Scout

A self-hosted web app for UK Buy–Refurbish–Refinance–Rent investors. Finds and tracks cheap listings, prices deals against official Land Registry data, screens auction legal packs with AI, and counts down refinance windows on the properties you own.

---

## Quick start

### Option A — Docker Compose (recommended)

```bash
# 1. Copy the env template and fill in your API keys
cp .env.example .env

# 2. Start the app
docker compose up
```

Open **http://localhost:5000**

The `data/` folder is mounted as a Docker volume so your database, saved HTML files, and legal pack PDFs survive container restarts.

### Option B — Local Python

```bash
pip install -r requirements.txt
crawl4ai-setup           # one-time: downloads Playwright/Chromium

cp .env.example .env     # fill in your keys
python wsgi.py
```

---

## Environment variables  (`.env`)

Copy `.env.example` and fill in the values you need. All are optional — the app runs without any of them, with reduced functionality.

| Variable | What it enables |
|---|---|
| `ANTHROPIC_API_KEY` | AI deal verdict, floorplan 1→2 bed check, legal pack red-flag analysis |
| `EPC_API_KEY` | EPC data on deal cards (register free at epc.opendatacommunities.org) |
| `SCRAPER_PROXY_URL` | Routes portal scraping through a residential proxy (ScraperAPI, Bright Data…) |

---

## Pages and features

### 1 · Deal ledger  `/`  ← start here

Every tracked listing ranked by ROI, most attractive first.

**How to get deals in:**
- **Run live scan** (nav bar) — scrapes your configured Rightmove/Zoopla searches directly
- **Import inbox** (nav bar) — saves from your browser into `data/inbox/` (see Scraping section)
- **Add a listing** (panel at the top of the deal list, open by default) — paste a Rightmove or Zoopla URL or fill the form manually

**What each deal card shows:**

| Element | Where it appears |
|---|---|
| Asking price + price-drop tracker | Top of card |
| Land Registry comp value (HIGH/MEDIUM/LOW confidence) | Top of card — click the **N · basis** link to expand the full comp table |
| Tiered SDLT, 75% LTV refi, cashflow, ROI, verdict | Gauge bar |
| **EPC badge** (A–G, colour coded) | Address line — requires `EPC_API_KEY` in `.env` |
| **Owner intelligence** (purple strip) | Below address — last sale date/price, years held, flags (RECENT BUYER, LONG HOLD, HIGH TURNOVER) |
| **Claude AI verdict** (blue box) — BUY / WATCH / PASS with pros, cons, flags, next action | Below owner strip — requires `ANTHROPIC_API_KEY` |
| 1→2 bed conversion result | Tags row — appears on 1-bed listings with a floorplan URL |
| Live rental comp count | Gauge bar label — shows how many Rightmove rental listings informed the rent estimate |

**Max bid calculator** (dark panel at the top of the page): enter end value, refurb and rent → prints the max you can pay and still hit your target ROI. The URL preserves all inputs for saving/sharing.

**Tiered SDLT** is applied automatically inside every deal valuation at the additional-dwelling rates (3% on first £125k, 5% to £250k, 8% to £925k). It is not a standalone page — it feeds directly into the cash-in and ROI figures on each card.

**URL auto-fill**: in the "Add a listing" panel, paste any Rightmove or Zoopla property URL into the blue box and click **Auto-fill →** to scrape the address, price, beds, type, postcode, and floorplan URL automatically. The panel is open by default.

**Real rental comps**: when you add or scan a listing, the app fetches live Rightmove rental listings for that outcode and uses the median as the rent estimate. The number of live comps used is shown as a small annotation on the gauge bar (e.g. `(12 live comps)`). If Rightmove blocks the scrape, it falls back to a 1.15%-of-value heuristic.

**Owner intelligence**: every deal card shows a purple "Owner intel" strip with the last recorded sale date and price, how many years the current owner has held the property, and flags for notable patterns (RECENT BUYER, LONG HOLD, HIGH TURNOVER). Data comes from the HM Land Registry Price Paid dataset — public records, no buyer names. It only appears after a deal has been analysed.

---

### 2 · Postcode lookup  `/lookup`  ← "Postcode lookup" in nav

Look up any UK postcode to see:
- **EPC record** — energy rating, floor area, property type, construction age
- **Land Registry sold prices** — last 15 sales in the outcode with median + confidence band, sortable by date or price
- **Map view** — sold comps plotted as colour-coded pins on an OpenStreetMap (no API key needed). Pins are coloured by price quartile (green = cheapest, red = most expensive). Click any pin to see address, price, date, and type.
- **Pre-filled add form** — click "Add this property to the deal ledger" to run the full analysis

---

### 3 · Auction tracker  `/auctions`  ← "Auction tracker" in nav

Per lot:
- Countdown to auction day
- Guide price vs your **locked max bid** (red warning when guide already exceeds it)
- **Legal pack PDF analysis** (Claude AI) — upload the PDF, get a structured red-flag screen: lease length, seller fee traps, title issues, tenancy, searches, environmental. Risk rated LOW / MEDIUM / HIGH.
- **10-point bid-day checklist** — stamps BID READY only when all 10 items are ticked
- Delete a lot when no longer relevant

---

### 4 · Portfolio  `/portfolio`  ← "Portfolio" in nav

For every property you own:
- **Refinance countdown** — days until the 6-month seasoning window opens from completion date
- **REFI WINDOW OPEN** banner when equity is available and the window is open
- Refurb spend vs budget (red when over)
- **One-click revalue** — pulls fresh Land Registry comps and updates the estimated value
- Cashflow per month at current rent and mortgage
- **Record refinance** — logs the released amount and updates the loan balance

Portfolio totals: cash deployed, cash recycled, net cash in market, aggregate LTV.

---

### 5 · Settings  `/settings`  ← "Settings" in nav

Adjust every assumption that drives the deal maths — no code editing needed:

- **Price range & refurb**: min/max price ceiling, standard and heavy refurb budgets
- **Financial assumptions**: BTL interest rate, refinance LTV, fees, management %, maintenance %, voids %, insurance, stress test rate and cover ratio
- **Deal strategy**: end-value caps, verdict ROI thresholds (GOOD DEAL / ON TARGET / THIN / WALK), full-recycle ratios, seasoning days
- **Comparable settings**: how far back to look, price cap, recency weighting
- **Scraping settings**: rate limits, timeouts, Rightmove property types / tenure / sort / exclusions
- **Claude AI**: model name, token limits per task
- **Search areas**: the list of Rightmove/Zoopla location IDs to scan (JSON)

All settings are saved to the database and override the hardcoded defaults in `config.py`. Click **Reset to defaults** to wipe them and revert.

---

### 6 · Comps drill-down (deal ledger)

On any deal card, click the **"N · basis"** link (e.g. "4 · postcode") next to the comp value to expand an inline table of the actual Land Registry transactions that informed the median — showing address, date, type, and price. Click again to collapse.

---

## Adding listings

### Paste a portal URL (fastest)

1. The **"+ Add a listing"** panel is open by default at the bottom of the Deal ledger page
2. Paste a Rightmove or Zoopla property URL into the blue "Auto-fill" box
3. Click **Auto-fill →** — address, price, beds, type, postcode, and floorplan URL fill automatically
4. Review the form and click **Analyse deal**

### Scraping — how it works

Property portals actively block bots. The app uses a three-layer approach:

```
Layer 1 · crawl4ai  (headless Chromium, JS-rendered, stealth)
          ↓ fails
Layer 2 · requests  (plain HTTP, spoofed UA — fast, often blocked)
          ↓ fails
Layer 3 · inbox     (browser-saved HTML — always works)
```

**Inbox import (always reliable):**
1. Run your search on Rightmove or Zoopla and scroll to load all results
2. `Ctrl+S` → **Webpage, HTML Only**
3. Save into `data/inbox/` (any filename, `.html` or `.htm`)
4. Click **Import inbox** in the nav bar

**Optional: browser cookies** — greatly improve live-scan success rate. Install the Cookie-Editor browser extension, visit rightmove.co.uk and zoopla.co.uk while logged in, export cookies as JSON, save to `data/cookies/rightmove.json` and `data/cookies/zoopla.json`.

**Rate limit:** 6 seconds between requests. Rightmove and Zoopla prohibit automated access in their T&Cs — this tool is for personal research only.

---

## Data sources

| Data | Source | Notes |
|---|---|---|
| Listing prices | Rightmove, Zoopla | live scrape, URL scrape, or inbox HTML |
| Sold comps | HM Land Registry Price Paid API | free, official, same data surveyors use |
| Rental comps | Rightmove rental search | scraped per outcode; falls back to 1.15% heuristic |
| Owner history | HM Land Registry Price Paid API | address-level sale history, no buyer names |
| EPC data | EPC Open Data Communities API | free, needs registration |
| Postcode geocoding | postcodes.io | free, no key, used for the map on postcode lookup |
| AI analysis | Claude API (claude-sonnet) | deal verdict, floorplans, legal packs — needs `ANTHROPIC_API_KEY` |

---

## Model assumptions  (edit in Settings page or `brrr_scout/analyzer.py`)

| Setting | Default | Notes |
|---|---|---|
| BTL interest rate | 5.25% | interest-only; check current product rates |
| Refinance LTV | 75% | standard BTL max |
| SDLT | tiered | 3% on first £125k, 5% to £250k, 8% to £925k (additional-dwelling rates) |
| Legal/sourcing per deal | £2,500 | solicitor + survey + auction entry |
| Management fee | 10% of rent | full management |
| Maintenance | 8% of rent | older stock allowance |
| Voids | 4% of rent | ~2 weeks/year |
| Insurance | £350/yr | typical low-value terrace/flat |
| Stress test | rent ≥ 125% × mortgage @ 7% | standard BTL lender requirement |

All of these can now be changed in the **Settings** page without touching code.

---

## Project layout

```
brrr-scout/
├── brrr_scout/              # Python application package
│   ├── __init__.py          # Flask app factory + template filters
│   ├── routes.py            # All route handlers (deals, auctions, portfolio, lookup, settings, API)
│   ├── analyzer.py          # Deal maths, AI prompts, EPC, owner intelligence
│   ├── scrapers.py          # crawl4ai + requests + inbox + rental comp scraper
│   ├── db.py                # SQLite schema, rolling migrations v1–v6, all queries
│   ├── config.py            # Default target areas, price ceiling, refurb defaults
│   └── templates/           # Jinja2 HTML templates
│       ├── index.html       # Deal ledger + URL auto-fill + comps drill-down
│       ├── auctions.html    # Auction tracker + legal pack upload
│       ├── portfolio.html   # Owned properties + refinance tracker
│       ├── lookup.html      # Postcode lookup + sold comps map
│       └── settings.html    # All financial and scraping assumptions
├── data/                    # Runtime data — mounted as Docker volume, not in git
│   ├── inbox/               # Drop browser-saved HTML search pages here
│   ├── packs/               # Uploaded legal pack PDFs
│   └── cookies/             # Browser cookie exports for portal scraping
├── docs/
│   └── CLAUDE.md            # AI analysis contracts (floorplans + legal packs)
├── .env                     # Your secrets — copy from .env.example (gitignored)
├── .env.example             # Template: all supported env vars with descriptions
├── Dockerfile               # Production image with Chromium pre-installed
├── docker-compose.yml       # One-command start with volume + env file wired up
├── requirements.txt
├── wsgi.py                  # Entry point: `python wsgi.py` or `gunicorn wsgi:app`
└── README.md
```

---

## Honest limitations

- End values default to the Land Registry outcode comp median, capped at asking +45%. Always verify with same-street solds before bidding — the valuer will.
- Rental comps come from Rightmove's live search; if the portal blocks the scrape, the app falls back to ~1.15% of value/month. Confirm with a local agent before bidding.
- Owner intelligence uses the public Price Paid dataset — it shows when a property sold and for how much, but not buyer names (those are in the private Title Register).
- AI floorplan and legal pack outputs are **screening aids only**. Floorplan conversions need freeholder consent and Building Regulations sign-off. Legal packs need a solicitor to read before you bid. The person liable on completion day is you.
