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
| `EPC_API_EMAIL` | EPC data on deal cards (register free at epc.opendatacommunities.org) |
| `EPC_API_KEY` | Paired with `EPC_API_EMAIL` |
| `SCRAPER_PROXY_URL` | Routes portal scraping through a residential proxy (ScraperAPI, Bright Data…) |

---

## Pages and features

### 1 · Deal ledger  `/`  ← start here

Every tracked listing ranked by ROI, most attractive first.

**How to get deals in:**
- **Run live scan** (nav bar) — scrapes your configured Rightmove/Zoopla searches directly
- **Import inbox** (nav bar) — saves from your browser into `data/inbox/` (see Scraping section)
- **Add a listing** (panel at the bottom of the page) — paste a Rightmove or Zoopla URL or fill the form manually

**What each deal card shows:**
| Element | Where it appears |
|---|---|
| Asking price + price-drop tracker | Top of card |
| Land Registry comp value (HIGH/MEDIUM/LOW confidence) | Top of card |
| Tiered SDLT, 75% LTV refi, cashflow, ROI, verdict | Gauge bar |
| **EPC badge** (A–G, colour coded) | Address line — requires `EPC_API_EMAIL` |
| **Owner intelligence** (purple strip) | Below address — last sale date/price, years held, flags (RECENT BUYER, LONG HOLD, HIGH TURNOVER) |
| **Claude AI verdict** (blue box) — BUY / WATCH / PASS with pros, cons, flags, next action | Below owner strip — requires `ANTHROPIC_API_KEY` |
| 1→2 bed conversion result | Tags row — appears on 1-bed listings with a floorplan URL |
| Live rental comp count | Gauge bar label — shows how many Rightmove rental listings informed the rent estimate |

**Max bid calculator** (dark panel at the top of the page): enter end value, refurb and rent → prints the max you can pay and still hit your target ROI. The URL preserves all inputs for saving/sharing.

---

### 2 · Postcode lookup  `/lookup`  ← "Postcode lookup" in nav

Look up any UK postcode to see:
- **EPC record** — energy rating, floor area, property type, construction age
- **Land Registry sold prices** — last 15 sales in the outcode with median + confidence band
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

## Adding listings

### Paste a portal URL (fastest)

1. Open the **"+ Add a listing"** panel at the bottom of the Deal ledger page
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
| AI analysis | Claude API (claude-sonnet) | deal verdict, floorplans, legal packs — needs `ANTHROPIC_API_KEY` |

---

## Model assumptions  (edit in `brrr_scout/config.py` and `brrr_scout/analyzer.py`)

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

---

## Project layout

```
brrr-scout/
├── brrr_scout/              # Python application package
│   ├── __init__.py          # Flask app factory + template filters
│   ├── routes.py            # All route handlers (deals, auctions, portfolio, lookup, API)
│   ├── analyzer.py          # Deal maths, AI prompts, EPC, owner intelligence
│   ├── scrapers.py          # crawl4ai + requests + inbox + rental comp scraper
│   ├── db.py                # SQLite schema, rolling migrations, all queries
│   ├── config.py            # Target areas, price ceiling, refurb defaults
│   └── templates/           # Jinja2 HTML templates
│       ├── index.html       # Deal ledger
│       ├── auctions.html    # Auction tracker + legal pack upload
│       ├── portfolio.html   # Owned properties + refinance tracker
│       └── lookup.html      # Postcode lookup
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
