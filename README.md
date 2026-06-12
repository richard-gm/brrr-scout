# BRRR Scout

A local web app for UK Buy–Refurbish–Refinance–Rent investors. It finds and
tracks cheap listings, prices deals against official sold data, locks your
auction max bids, screens legal packs, and counts down refinance windows on
the properties you own.

Everything runs on your machine. Data lives in one SQLite file
(`data/brrr_scout.db`) so you can compare prices and deals over time.

## Quick start
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...   # optional: enables floorplan + legal pack AI analysis
    python app.py                          # open http://127.0.0.1:5000

## The four pages

### 1. Deal ledger (/)
Every listing the app has seen, ranked by ROI. Each card shows asking price
(with price-drop tracking across scans), the comp value with a HIGH/MEDIUM/LOW
confidence badge, end value used, the pull-out gauge (cash out vs cash left
in after refinancing at 75% LTV), annual cashflow, lender stress test, and a
verdict: FULL RECYCLE / GOOD DEAL / ON TARGET (7–12% ROI) / THIN / WALK AWAY.

The dark **Max bid calculator** panel works backwards: enter end value,
refurb, rent and target ROI and it prints the most you're allowed to pay.

Three ways to feed it deals:
- **Run live scan** — scrapes the searches in `config.py`. Rightmove and
  Zoopla prohibit scraping and run bot protection, so this can fail at any
  time. Personal research only; the 5s/request rate limit is deliberate.
- **Import inbox (reliable)** — save listing or search pages from your
  browser (Ctrl+S) into `data/inbox/` and click Import inbox.
- **Add manually** — paste lots from auction catalogues into the form.

### 2. Auction tracker (/auctions)
Per lot: countdown to auction day, guide price vs your **locked max bid**
(warns when the guide already exceeds it), a 10-point bid-day checklist that
stamps BID READY only at 10/10, and **legal pack PDF analysis** — upload the
pack and the AI flags short leases, buyer-pays-seller-fees special
conditions, title issues, knotweed and tight completions, with a
LOW/MEDIUM/HIGH risk verdict. See CLAUDE.md for exactly what the AI checks.

### 3. Portfolio (/portfolio)
The "repeat" in BRRR. Per owned property: the 6-month refinance countdown
(183 days from completion — the common lender seasoning rule), refurb spend
vs budget with an OVER flag, current value (manual or one-click revalue from
Land Registry comps), and the headline: **how much a refinance releases
today**. When a property passes 6 months with releasable equity, it gets a
red REFI WINDOW OPEN banner. Totals strip: cash deployed, cash recycled, net
cash still in the market, portfolio cashflow, aggregate LTV.

### 4. Max bid (part of the ledger)
GET /maxbid — bookmarkable, so you can save calculations per lot.

## Data sources
- **HM Land Registry Price Paid Data** (free, official) for sold comps —
  the same data refinance surveyors use. Comps are tiered: same street
  (recency-weighted) > same property type in outcode > outcode median.
- **Rightmove/Zoopla** for live listings, best effort (see above).
- **Claude API** for floorplan and legal pack analysis (optional).

## Assumptions (edit in analyzer.py, dict `A`)
5.25% interest-only BTL rate · 75% refinance LTV · 5% investor SDLT ·
£2,500 legal/sourcing per deal · 10% management · 8% maintenance · 4% voids ·
£350/yr insurance · stress test: rent ≥ 125% of mortgage at 7%.

## Files
    app.py        Flask routes and the deal pipeline
    analyzer.py   Deal maths, max-bid, comps scoring, AI prompts
    scrapers.py   Portal parsers + browser-save inbox importer
    db.py         SQLite schema, migrations, queries
    config.py     Your target areas and price ceiling
    CLAUDE.md     Instructions for the AI tasks (floorplans, legal packs)
    data/         Database, inbox/ for saved pages, packs/ for legal packs

## Honest limitations
- End values are comp baselines capped at asking +45%. Before bidding or
  refinancing, verify with same-street solds — the valuer will.
- Rent estimates are heuristic (~1.15% of value pcm). Use real rental comps.
- AI floorplan and legal pack outputs are screening aids. Conversions need
  freeholder consent and Building Regs; packs need a solicitor. The person
  liable on completion day is you.
