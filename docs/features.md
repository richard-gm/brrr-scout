# BRRR Scout — Feature Reference

## 1 · Deal Ledger (`/`)

**Purpose:** Central dashboard — every tracked listing ranked by ROI.

### Adding listings
| Method | How |
|---|---|
| URL auto-fill | Paste Rightmove/Zoopla URL into the blue box → click Auto-fill |
| Manual | Fill the form fields directly |
| Live scan | Click "Run live scan" in the nav bar |
| Inbox import | Save portal search pages as HTML to `data/inbox/`, click "Import inbox" |

### Deal card elements

| Element | What it shows |
|---|---|
| Asking price + price-drop | Top left — tracks price history, shows drop since first seen |
| Comp value + confidence | Land Registry median for outcode — click the `N · basis` link to expand comps |
| End value | Comp median capped at asking +45%, or override in max-bid calculator |
| ROI on cash left | Annual cashflow ÷ cash left in after refi |
| Verdict stamp | FULL RECYCLE / GOOD DEAL / ON TARGET / THIN / WALK |
| Gauge bar | Visual split: pulled-out vs left-in on a £ basis |
| EPC badge | Energy rating A–G (requires `EPC_API_KEY`) |
| Owner intel strip | Purple — last sale date, years held, RECENT BUYER / LONG HOLD / HIGH TURNOVER flags |
| Claude AI box | Blue — BUY / WATCH / PASS with pros, cons, flags, next action (requires `ANTHROPIC_API_KEY`) |
| Signal tags | Coloured badges — BRRR CANDIDATE, RECENTLY REDUCED, STALE LISTING, etc. |
| 1→2 bed tag | Floorplan conversion check result (requires floorplan URL + `ANTHROPIC_API_KEY`) |

### Signal tags

| Tag | Trigger |
|---|---|
| BRRR CANDIDATE | ROI ≥ 10% + stress pass + ≥ 70% cash recycled |
| GOOD YIELD | ROI ≥ 10% + stress pass (but < 70% recycled) |
| RECENTLY REDUCED | Any tracked price drop |
| PRICE HISTORY | 3+ price points recorded |
| STALE LISTING | 45+ days on market |
| AUCTION | Flagged as auction lot |
| LEASEHOLD | Tenure contains "leasehold" |

### Max bid calculator

Enter end value, refurb, rent, target ROI → get the max you can pay and still hit your target. URL is shareable/bookmarkable.

---

## 2 · Postcode Lookup (`/lookup`)

- **EPC record** — rating, floor area, construction age, fuel type
- **Sold comps table** — last 15 Land Registry sales in outcode, sortable by date or price
- **Map view** — Leaflet/OpenStreetMap with price-quartile colour pins (green = cheapest, red = most expensive). Click any pin for address, price, date, type.
- **Pre-fill form** — jump straight to deal analysis from any postcode

---

## 3 · Auction Tracker (`/auctions`)

Per lot:
- Countdown to auction day (red when < 7 days, amber < 14)
- Guide price vs locked max bid — warning when guide exceeds max
- Legal pack AI analysis — upload PDF, Claude extracts: lease length, seller fee traps, title issues, tenancy, searches, environmental. Risk: LOW / MEDIUM / HIGH.
- 10-point bid-day checklist — BID READY only when all 10 items are ticked

---

## 4 · Portfolio (`/portfolio`)

For each owned property:
- **Refinance countdown** — days until 6-month seasoning window opens from completion date
- **REFI WINDOW OPEN** banner when equity available and window is open
- Refurb spend vs budget (red when over)
- **One-click revalue** — fresh Land Registry comps
- Cashflow at current rent and mortgage
- **Record refinance** — logs released amount, updates loan balance

Portfolio totals: cash deployed, cash recycled, net cash in market, aggregate LTV.

---

## 5 · Calculators (`/calculators`)

Three standalone calculators accessible via tab nav:

### SDLT / Stamp Duty
Calculates SDLT at additional-dwelling rates for any purchase price. Shows band breakdown and effective rate.

### Flip Calculator
Buy → refurb → sell economics:
- Inputs: buy price, refurb cost, target profit, agent fee %
- Outputs: total money in, break-even sale price, target sale price, ROI on cash in

### HMO Calculator
House in Multiple Occupation:
- Inputs: buy price, refurb, rooms, rent/room, bills/room, mortgage rate, LTV
- Outputs: gross yield, net yield, monthly cashflow, ROI on cash in, stress test PASS/FAIL
- BRRR section: refi loan, extra cash released, left in after refi
- Costs assumed: 12% mgmt, 8% maint, 5% voids, £700 insurance

---

## 6 · Settings (`/settings`)

All financial assumptions are editable at runtime — no code changes needed:

- Price range & refurb budgets
- BTL rate, refi LTV, fees, management %, maintenance %, voids %, insurance
- Deal strategy thresholds (ROI bands for verdict tiers)
- Comparable settings (lookback period, price cap, recency weighting)
- Scraping settings (rate limits, property types, exclusions)
- Claude AI model and token limits
- Target search areas (JSON — Rightmove/Zoopla location IDs)

---

## 7 · Comps drill-down (deal ledger)

On any deal card, click the **"N · basis"** link next to the comp value to expand an inline Land Registry transaction table (date, address, type, price). Click again to collapse. Results are cached in the browser session.
