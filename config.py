"""Target areas. Edit freely. Rightmove locationIdentifiers can be found in the
URL after searching manually on rightmove.co.uk (e.g. OUTCODE^1234 or REGION^...)."""

MAX_PRICE = 70000
MIN_PRICE = 20000

# The shortlist from our research: Newcastle flats + Teesside/Sunderland houses
SEARCHES = [
    {"portal": "rightmove", "label": "Newcastle NE4", "location_id": "OUTCODE^1759"},
    {"portal": "rightmove", "label": "Newcastle NE6", "location_id": "OUTCODE^1761"},
    {"portal": "rightmove", "label": "Sunderland SR1", "location_id": "OUTCODE^2473"},
    {"portal": "rightmove", "label": "Middlesbrough TS1", "location_id": "OUTCODE^2670"},
    {"portal": "rightmove", "label": "Middlesbrough TS3", "location_id": "OUTCODE^2683"},
    {"portal": "zoopla", "label": "Newcastle", "area_slug": "newcastle-upon-tyne"},
    {"portal": "zoopla", "label": "Middlesbrough", "area_slug": "middlesbrough"},
    {"portal": "zoopla", "label": "Sunderland", "area_slug": "sunderland"},
]

# Refurb defaults by stock type (your plan: ~20k standard, ~30k heavy)
REFURB_DEFAULT = 20000
REFURB_HEAVY = 30000
