# BRRR Scout — Architecture

## Overview

BRRR Scout is a Flask web application with a SQLite backend. It is designed to be self-hosted as a single container with zero external service dependencies beyond optional third-party APIs.

```
Browser
  └─ Flask (routes.py)
       ├─ analyzer.py       ← deal maths, AI verdict, EPC, owner intel
       ├─ scrapers.py       ← crawl4ai / requests / inbox / rental comps
       ├─ calcs.py          ← standalone calculators (Flip, HMO, SDLT re-export)
       ├─ signals.py        ← deal signal/tag computation
       ├─ db.py             ← SQLite schema, rolling migrations, all queries
       └─ config.py         ← hardcoded defaults (overridden by settings table)
```

## Request flow

1. User adds a listing URL → `POST /add_manual` or `GET /api/scrape?url=…`
2. `scrapers.py` fetches the portal page (crawl4ai → requests → inbox fallback)
3. `analyzer.py` runs deal maths: SDLT, deposit, loan, cashflow, ROI
4. Land Registry API provides sold comps; Rightmove rental scrape provides rent estimate
5. Optional: Claude API provides AI deal verdict; EPC API provides energy data
6. Result written to SQLite; signals computed at render time via `signals.py`

## Module responsibilities

### `routes.py`
All Flask route handlers. No business logic — delegates to analyzer/calcs/db/scrapers. Follows the Flask app-factory pattern: all routes registered inside `init_app(app)`.

### `analyzer.py`
Core deal maths:
- `calc_sdlt(price)` — tiered SDLT at additional-dwelling rates
- `analyse_deal(…)` — full deal pipeline: comps → rent → cashflow → ROI → verdict
- `get_ai_verdict(deal)` — Claude API call (optional)
- `get_epc(postcode)` — EPC Open Data Communities API
- `get_owner_intel(address, postcode)` — Land Registry Price Paid history

### `calcs.py`
Standalone calculator functions (no DB, no scraping):
- `calc_flip(buy_price, refurb, …)` — flip deal economics
- `calc_hmo(buy_price, rooms, rent_per_room, refurb, …)` — HMO cashflow + BRRR refi

### `signals.py`
Stateless signal tagging:
- `compute_signals(d)` — returns list of `{label, cls, detail}` dicts for a deal row
- Tags: RECENTLY REDUCED, PRICE HISTORY, STALE LISTING, BRRR CANDIDATE, GOOD YIELD, AUCTION, LEASEHOLD

### `db.py`
- Rolling migrations v1–v6 via chained `conn()` redefinitions
- All SQL queries as named functions (no raw SQL in routes)
- Settings stored in key-value `settings` table, overriding `config.py` defaults

### `config.py`
Hardcoded defaults for financial assumptions, scraping config, target areas. All values overridable at runtime via the Settings page.

## Database schema (v6)

| Table | Purpose |
|---|---|
| `deals` | All tracked listings — price, comp, analysis results |
| `price_history` | Per-deal price-drop tracking |
| `comps` | Cached Land Registry transactions per outcode |
| `rental_comps` | Cached Rightmove rental listings per outcode |
| `auction_lots` | Auction tracker lots |
| `portfolio` | Owned properties with refi tracking |
| `settings` | Key-value overrides for financial assumptions |

## Colour design system

All templates share a consistent CSS custom property set:

| Variable | Hex | Role |
|---|---|---|
| `--ink` | `#0B1F3A` | Deep navy — text, header, borders |
| `--mortar` | `#FAF6EC` | Warm cream — page background |
| `--card` | `#FFFFFF` | Card / panel background |
| `--brick` | `#A8402C` | Terracotta — accent, price drops |
| `--pass` | `#0E6B4E` | Forest green — good deals, pass |
| `--thin` | `#C39A3C` | Amber — thin deals, warning |
| `--walk` | `#A7343A` | Deep red — walk away, fail |
| `--line` | `#DDD8CC` | Warm grey — borders, dividers |
| `--indigo` | `#3B2FB3` | Indigo — BRRR/yield highlights |

## Deployment

See `deployment.md` for Docker and local setup instructions.
