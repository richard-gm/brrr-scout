"""SQLite storage for BRRR Scout."""
import sqlite3, json, time, pathlib

DB_PATH = pathlib.Path(__file__).parent / "data" / "brrr_scout.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,              -- rightmove | zoopla | manual
  source_id TEXT,                    -- portal listing id
  url TEXT UNIQUE,
  address TEXT, postcode TEXT, outcode TEXT,
  prop_type TEXT, bedrooms INTEGER, tenure TEXT,
  is_auction INTEGER DEFAULT 0,
  floorplan_url TEXT,
  first_seen REAL, last_seen REAL
);
CREATE TABLE IF NOT EXISTS price_snapshots (
  id INTEGER PRIMARY KEY,
  property_id INTEGER REFERENCES properties(id),
  price INTEGER, seen_at REAL
);
CREATE TABLE IF NOT EXISTS sold_comps (
  id INTEGER PRIMARY KEY,
  outcode TEXT, postcode TEXT, address TEXT,
  price INTEGER, sold_date TEXT, prop_type TEXT,
  fetched_at REAL
);
CREATE TABLE IF NOT EXISTS analyses (
  id INTEGER PRIMARY KEY,
  property_id INTEGER UNIQUE REFERENCES properties(id),
  refurb_estimate INTEGER, end_value INTEGER, monthly_rent INTEGER,
  comp_count INTEGER, comp_median INTEGER,
  total_cash_in INTEGER, refi_loan INTEGER, pulled_out INTEGER, left_in INTEGER,
  net_cashflow_yr INTEGER, roi REAL, gross_yield REAL,
  stress_pass INTEGER, verdict TEXT,
  conversion_json TEXT,              -- floorplan 1->2 bed assessment
  analysed_at REAL
);
"""

def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c

def upsert_property(c, p):
    """p: dict with url/source/address/... Returns property id, records price snapshot."""
    now = time.time()
    row = c.execute("SELECT id FROM properties WHERE url=?", (p["url"],)).fetchone()
    if row:
        pid = row["id"]
        c.execute("UPDATE properties SET last_seen=?, floorplan_url=COALESCE(?,floorplan_url) WHERE id=?",
                  (now, p.get("floorplan_url"), pid))
    else:
        c.execute("""INSERT INTO properties(source,source_id,url,address,postcode,outcode,prop_type,
                     bedrooms,tenure,is_auction,floorplan_url,first_seen,last_seen)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (p["source"], p.get("source_id"), p["url"], p.get("address"), p.get("postcode"),
                   p.get("outcode"), p.get("prop_type"), p.get("bedrooms"), p.get("tenure"),
                   int(p.get("is_auction", 0)), p.get("floorplan_url"), now, now))
        pid = c.execute("SELECT last_insert_rowid() i").fetchone()["i"]
    if p.get("price"):
        last = c.execute("SELECT price FROM price_snapshots WHERE property_id=? ORDER BY seen_at DESC LIMIT 1",
                         (pid,)).fetchone()
        if not last or last["price"] != p["price"]:
            c.execute("INSERT INTO price_snapshots(property_id,price,seen_at) VALUES(?,?,?)", (pid, p["price"], now))
    c.commit()
    return pid

def save_comps(c, outcode, comps):
    c.execute("DELETE FROM sold_comps WHERE outcode=?", (outcode,))
    now = time.time()
    for x in comps:
        c.execute("INSERT INTO sold_comps(outcode,postcode,address,price,sold_date,prop_type,fetched_at) VALUES(?,?,?,?,?,?,?)",
                  (outcode, x.get("postcode"), x.get("address"), x["price"], x.get("sold_date"), x.get("prop_type"), now))
    c.commit()

def save_analysis(c, pid, a):
    a = dict(a); a["conversion_json"] = json.dumps(a.get("conversion") or {})
    c.execute("""INSERT INTO analyses(property_id,refurb_estimate,end_value,monthly_rent,comp_count,comp_median,
                 total_cash_in,refi_loan,pulled_out,left_in,net_cashflow_yr,roi,gross_yield,stress_pass,verdict,
                 conversion_json,analysed_at,comp_confidence,comp_basis)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(property_id) DO UPDATE SET
                 refurb_estimate=excluded.refurb_estimate, end_value=excluded.end_value,
                 monthly_rent=excluded.monthly_rent, comp_count=excluded.comp_count, comp_median=excluded.comp_median,
                 total_cash_in=excluded.total_cash_in, refi_loan=excluded.refi_loan, pulled_out=excluded.pulled_out,
                 left_in=excluded.left_in, net_cashflow_yr=excluded.net_cashflow_yr, roi=excluded.roi,
                 gross_yield=excluded.gross_yield, stress_pass=excluded.stress_pass, verdict=excluded.verdict,
                 conversion_json=excluded.conversion_json, analysed_at=excluded.analysed_at,
                 comp_confidence=excluded.comp_confidence, comp_basis=excluded.comp_basis""",
              (pid, a.get("refurb_estimate"), a.get("end_value"), a.get("monthly_rent"), a.get("comp_count"),
               a.get("comp_median"), a.get("total_cash_in"), a.get("refi_loan"), a.get("pulled_out"),
               a.get("left_in"), a.get("net_cashflow_yr"), a.get("roi"), a.get("gross_yield"),
               int(bool(a.get("stress_pass"))), a.get("verdict"), a["conversion_json"], time.time(),
               a.get("comp_confidence"), a.get("comp_basis")))
    c.commit()

def deals(c):
    return c.execute("""
      SELECT p.*, a.*, p.id AS pid,
        (SELECT price FROM price_snapshots s WHERE s.property_id=p.id ORDER BY seen_at DESC LIMIT 1) AS price,
        (SELECT COUNT(*) FROM price_snapshots s WHERE s.property_id=p.id) AS n_prices,
        (SELECT MAX(price)-MIN(price) FROM price_snapshots s WHERE s.property_id=p.id) AS price_drop
      FROM properties p LEFT JOIN analyses a ON a.property_id=p.id
      ORDER BY a.roi DESC NULLS LAST""").fetchall()

def price_history(c, pid):
    return c.execute("SELECT price, seen_at FROM price_snapshots WHERE property_id=? ORDER BY seen_at", (pid,)).fetchall()

# ---- v2 migration: comp confidence + auction lots ----
MIGRATION_V2 = """
CREATE TABLE IF NOT EXISTS auction_lots (
  id INTEGER PRIMARY KEY,
  lot_no TEXT, auction_house TEXT, auction_date TEXT, url TEXT,
  address TEXT, postcode TEXT,
  guide_price INTEGER, end_value INTEGER, refurb INTEGER, rent INTEGER,
  max_bid INTEGER, max_bid_recycle INTEGER, target_roi REAL,
  checklist_json TEXT DEFAULT '{}', pack_json TEXT, pack_file TEXT,
  notes TEXT, created REAL
);
"""
CHECKLIST_ITEMS = [
    ("legal_pack_read", "Legal pack read by solicitor"),
    ("lease_80y", "Lease ≥ 80 years (or freehold)"),
    ("no_seller_fee_traps", "No buyer-pays-seller-fees special conditions"),
    ("searches_ok", "Searches present & clean"),
    ("title_clean", "Title absolute, no odd covenants"),
    ("tenancy_verified", "Tenancy/vacant possession verified"),
    ("knotweed_clear", "No knotweed / environmental flags"),
    ("builder_walked", "Builder walked it, quote + 15% in budget"),
    ("max_bid_locked", "Max bid locked & written down"),
    ("funds_ready", "10% deposit + 28-day completion funds ready"),
]

def _migrate(c):
    c.executescript(MIGRATION_V2)
    for col in ("comp_confidence TEXT", "comp_basis TEXT"):
        try:
            c.execute(f"ALTER TABLE analyses ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    c.commit()

_old_conn = conn
def conn():
    c = _old_conn()
    _migrate(c)
    return c

def add_lot(c, d):
    c.execute("""INSERT INTO auction_lots(lot_no,auction_house,auction_date,url,address,postcode,
                 guide_price,end_value,refurb,rent,max_bid,max_bid_recycle,target_roi,notes,created)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (d.get("lot_no"), d.get("auction_house"), d.get("auction_date"), d.get("url"),
               d.get("address"), d.get("postcode"), d.get("guide_price"), d.get("end_value"),
               d.get("refurb"), d.get("rent"), d.get("max_bid"), d.get("max_bid_recycle"),
               d.get("target_roi"), d.get("notes"), time.time()))
    c.commit()
    return c.execute("SELECT last_insert_rowid() i").fetchone()["i"]

def lots(c):
    return c.execute("SELECT * FROM auction_lots ORDER BY auction_date ASC, id ASC").fetchall()

def update_lot(c, lot_id, **kw):
    sets = ", ".join(f"{k}=?" for k in kw)
    c.execute(f"UPDATE auction_lots SET {sets} WHERE id=?", (*kw.values(), lot_id))
    c.commit()

def delete_lot(c, lot_id):
    c.execute("DELETE FROM auction_lots WHERE id=?", (lot_id,))
    c.commit()

# ---- v3: portfolio (owned properties) ----
MIGRATION_V3 = """
CREATE TABLE IF NOT EXISTS portfolio (
  id INTEGER PRIMARY KEY,
  address TEXT, postcode TEXT, outcode TEXT, prop_type TEXT,
  purchase_price INTEGER, completion_date TEXT,
  refurb_budget INTEGER DEFAULT 0, refurb_spent INTEGER DEFAULT 0,
  rent_actual INTEGER DEFAULT 0,
  mortgage_loan INTEGER DEFAULT 0, mortgage_rate REAL,
  est_value INTEGER, est_value_basis TEXT, est_value_confidence TEXT,
  status TEXT DEFAULT 'refurbing',      -- refurbing | let | refinanced
  refinanced_amount INTEGER, refinance_date TEXT,
  notes TEXT, created REAL
);
"""

def _migrate_v3(c):
    c.executescript(MIGRATION_V3)
    c.commit()

_conn_v2 = conn
def conn():
    c = _conn_v2()
    _migrate_v3(c)
    return c

def portfolio_add(c, d):
    c.execute("""INSERT INTO portfolio(address,postcode,outcode,prop_type,purchase_price,completion_date,
                 refurb_budget,refurb_spent,rent_actual,mortgage_loan,mortgage_rate,est_value,status,notes,created)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (d["address"], d.get("postcode"), d.get("outcode"), d.get("prop_type"),
               d["purchase_price"], d["completion_date"], d.get("refurb_budget", 0), d.get("refurb_spent", 0),
               d.get("rent_actual", 0), d.get("mortgage_loan", 0), d.get("mortgage_rate"),
               d.get("est_value"), d.get("status", "refurbing"), d.get("notes"), time.time()))
    c.commit()
    return c.execute("SELECT last_insert_rowid() i").fetchone()["i"]

def portfolio_all(c):
    return c.execute("SELECT * FROM portfolio ORDER BY completion_date ASC").fetchall()

def portfolio_update(c, pid, **kw):
    sets = ", ".join(f"{k}=?" for k in kw)
    c.execute(f"UPDATE portfolio SET {sets} WHERE id=?", (*kw.values(), pid))
    c.commit()

def portfolio_delete(c, pid):
    c.execute("DELETE FROM portfolio WHERE id=?", (pid,))
    c.commit()
