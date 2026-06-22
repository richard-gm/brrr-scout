# BRRR Scout — Session Changelog (22 Jun 2026)

## Bugs Fixed

### 1. Port mismatch (docker-compose.yml)
- **Issue**: Flask ran on port 5000 but docker-compose mapped `8080:8080`
- **Fix**: Changed to `8080:5000` so host port 8080 reaches the container's Flask

### 2. `sqlite3.Row` has no `.get()` (routes.py:72-73)
- **Issue**: `r.get("ai_json")` crashed because `sqlite3.Row` doesn't support `.get()`
- **Fix**: Changed to `d.get("ai_json")` where `d = dict(r)`

### 3. Land Registry API returns empty for outcodes (routes.py:164-165)
- **Issue**: Lookup route stripped full postcode to outcode (`SE21 8PU` → `SE21`) before querying; LR API requires full postcodes
- **Fix**: Query with full postcode first, fall back to outcode only if no results. Same fix applied to `run_pipeline`.

### 4. Land Registry date format (analyzer.py)
- **Issue**: `transactionDate` is `"Tue, 14 Sep 1999"` (RFC 2822), not ISO. Code did `[:10]` giving `"Tue, 14 S"`
- **Fix**: Added `_parse_lr_date()` helper to parse to `YYYY-MM-DD`, displayed as DD/MM/YYYY

### 5. Land Registry property type is a dict (analyzer.py)
- **Issue**: `propertyType` returns `{'_value': 'Flat-maisonette', ...}` instead of a string
- **Fix**: Extract `_value` from nested dict structure

### 6. Flat/unit numbers missing from addresses (analyzer.py)
- **Issue**: Address only used `paon` (building name), missing `saon` (flat number)
- **Fix**: Added `saon` to address construction: `FLAT 10, MELLOR HOUSE, KINGSWOOD ESTATE, LONDON`

### 7. EPC API broken (analyzer.py)
- **Issue**: Old `epc.opendatacommunities.org` API now returns 301 redirect to a GOV.UK web page
- **Fix**: Migrated to new API at `api.get-energy-performance-data.communities.gov.uk` with Bearer token auth. Two-step flow: search by postcode → fetch full certificate by number.

## New Features

### 1. Full logging system
- **Files changed**: `__init__.py`, `routes.py`, `analyzer.py`, `db.py`
- Rotating file log at `data/logs.txt` (5MB, 3 backups) — DEBUG level
- Stream handler to stdout — INFO level (visible in `docker compose logs`)
- Every route hit, API call, pipeline step, and error now logged
- Added `data/logs.txt` to `.gitignore`

### 2. Expanded EPC data
- **Fields now fetched**: floor area (m²), heated rooms, potential rating, energy consumption (kWh/m²/yr), CO₂ emissions, main fuel, double glazing %, EPC lodgement date
- Displayed in lookup page EPC panel

### 3. Sortable table columns (lookup.html)
- Date and Price columns are clickable to sort ascending/descending
- Visual sort indicators (↑/↓)

### 4. Date formatting
- Sold comp dates now display as DD/MM/YYYY (e.g. `14/09/1999`)

## Configuration Changes

### `.env` variables
| Old | New | Notes |
|---|---|---|
| `EPC_API_EMAIL` + `EPC_API_KEY` | `EPC_API_KEY` only | Bearer token from new GOV.UK platform |

To get the new token:
1. Go to https://get-energy-performance-data.communities.gov.uk/
2. Log in → My Account → copy Bearer token
3. Set `EPC_API_KEY=<token>` in `.env`

## Files Modified
- `.env.example` — updated EPC instructions
- `.gitignore` — added `data/logs.txt`
- `brrr_scout/__init__.py` — logging setup
- `brrr_scout/analyzer.py` — EPC API migration, LR date/type parsing, address fix, expanded fields
- `brrr_scout/db.py` — migration logging
- `brrr_scout/routes.py` — `sqlite3.Row` fix, postcode fallback, logging, revalue fix
- `brrr_scout/templates/lookup.html` — expanded EPC display, sortable columns, date format
- `docker-compose.yml` — port mapping fix
