"""All Flask routes for BRRR Scout."""
import json, os, pathlib, datetime as _dt
from flask import render_template, redirect, url_for, request, flash, jsonify
from werkzeug.utils import secure_filename
from . import db, config, scrapers, analyzer

_DATA = pathlib.Path(__file__).parent.parent / "data"


def run_pipeline(app, listings):
    """Store listings, fetch comps + EPC per property, analyse each deal."""
    c = db.conn()
    outcode_cache = {}
    rental_cache = {}
    n = 0
    for p in listings:
        if not p.get("price") or not p.get("outcode"):
            continue
        if p.get("postcode") and not p.get("epc_rating"):
            epc = analyzer.fetch_epc(p["postcode"])
            if epc:
                p.update(epc_rating=epc.get("epc_rating"), floor_area=epc.get("floor_area"))
        pid = db.upsert_property(c, p)
        oc = p["outcode"]
        if oc not in outcode_cache:
            comps = analyzer.fetch_sold_comps(oc)
            db.save_comps(c, oc, comps)
            outcode_cache[oc] = comps
        count, median, conf, basis = analyzer.score_comps(outcode_cache[oc], p.get("address"), p.get("prop_type"))
        end_value = min(median, int(p["price"] * 1.45)) if median else int(p["price"] * 1.30)
        refurb = config.REFURB_HEAVY if (p.get("is_auction") and p["price"] < 45000) else config.REFURB_DEFAULT
        if oc not in rental_cache:
            cached = db.get_rental_comps(c, oc)
            if cached is None:
                fresh = scrapers.fetch_rental_comps(oc)
                if fresh:
                    db.save_rental_comps(c, oc, fresh)
                    cached = fresh
                else:
                    cached = []
            rental_cache[oc] = cached
        rent_live = analyzer.median_rent_from_comps(rental_cache[oc], beds=p.get("bedrooms"))
        rent = rent_live or analyzer.estimate_rent(end_value, oc)
        a = analyzer.analyse_deal(p["price"], end_value, refurb, rent)
        a.update(comp_count=count, comp_median=median, comp_confidence=conf, comp_basis=basis,
                 rental_comp_count=len(rental_cache[oc]) if rental_cache[oc] else 0,
                 rental_comp_median=rent_live)
        if p.get("floorplan_url") and (p.get("bedrooms") or 0) == 1:
            a["conversion"] = analyzer.check_conversion(p["floorplan_url"])
        a["owner"] = analyzer.fetch_address_history(p.get("address"), p.get("postcode"))
        a["ai"] = analyzer.analyse_deal_ai(a, p.get("address"), p.get("postcode"))
        db.save_analysis(c, pid, a)
        n += 1
    c.close()
    return n


def init_app(app):

    # ---- Deal ledger --------------------------------------------------------

    @app.route("/")
    def index():
        c = db.conn()
        rows = db.deals(c)
        hist = {r["pid"]: [(h["seen_at"], h["price"]) for h in db.price_history(c, r["pid"])] for r in rows}
        c.close()
        parsed = []
        for r in rows:
            d = dict(r)
            d["conversion"] = json.loads(r["conversion_json"]) if r["conversion_json"] else None
            d["ai"] = json.loads(r["ai_json"]) if r.get("ai_json") and r["ai_json"] not in ("{}", "null") else None
            raw_owner = r["owner_json"] if r.get("owner_json") else None
            d["owner"] = json.loads(raw_owner) if raw_owner and raw_owner not in ("{}", "null") else None
            d["history"] = hist.get(r["pid"], [])
            parsed.append(d)
        return render_template("index.html", deals=parsed, cfg=config)

    @app.route("/maxbid")
    def maxbid():
        q = request.args
        try:
            ev = int(q["end_value"]); refurb = int(q.get("refurb") or 20000)
            rent = int(q["rent"]); roi = float(q.get("target_roi") or 12) / 100
        except (KeyError, ValueError):
            return redirect(url_for("index"))
        res = analyzer.max_bid(ev, refurb, rent, roi)
        res.update(end_value=ev, refurb=refurb, rent=rent, target_roi=roi)
        c = db.conn(); rows = db.deals(c); c.close()
        parsed = []
        for r in rows:
            d = dict(r)
            d["conversion"] = json.loads(r["conversion_json"]) if r["conversion_json"] else None
            parsed.append(d)
        return render_template("index.html", deals=parsed, cfg=config, maxbid=res)

    # ---- Scanning -----------------------------------------------------------

    @app.route("/scan/live")
    def scan_live():
        searches = []
        for s in config.SEARCHES:
            url = scrapers.rightmove_search_url(s["location_id"], config.MAX_PRICE, config.MIN_PRICE) \
                if s["portal"] == "rightmove" else \
                scrapers.zoopla_search_url(s["area_slug"], config.MAX_PRICE, config.MIN_PRICE)
            searches.append({"portal": s["portal"], "url": url})
        listings, errors = scrapers.scrape_live(searches)
        n = run_pipeline(app, listings)
        flash(f"Live scan: {n} listings analysed." + (f" Issues: {'; '.join(errors)}" if errors else ""))
        return redirect(url_for("index"))

    @app.route("/scan/inbox")
    def scan_inbox():
        listings, errors = scrapers.import_inbox()
        n = run_pipeline(app, listings)
        flash(f"Inbox import: {n} listings analysed." + (f" Issues: {'; '.join(errors)}" if errors else ""))
        return redirect(url_for("index"))

    # ---- Manual add + API scrape -------------------------------------------

    @app.route("/add", methods=["POST"])
    def add_manual():
        f = request.form
        listing = {
            "source": "manual", "url": f.get("url") or f"manual-{f['address']}",
            "address": f["address"], "postcode": f.get("postcode"),
            "outcode": (f.get("postcode") or "").split()[0] or None,
            "price": int(f["price"]), "bedrooms": int(f.get("bedrooms") or 0),
            "prop_type": f.get("prop_type"), "is_auction": int(bool(f.get("is_auction"))),
            "floorplan_url": f.get("floorplan_url") or None,
        }
        run_pipeline(app, [listing])
        flash("Listing added and analysed.")
        return redirect(url_for("index"))

    @app.route("/api/scrape")
    def api_scrape():
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "url required"}), 400
        if "rightmove" in url:
            portal = "rightmove"
        elif "zoopla" in url:
            portal = "zoopla"
        else:
            return jsonify({"error": "Only Rightmove and Zoopla URLs are supported"}), 400
        html, _ = scrapers._fetch_with_fallback(url, portal)
        if not html:
            return jsonify({"error": "Could not fetch listing — save the page and use inbox import instead"}), 502
        parser = scrapers.parse_rightmove if portal == "rightmove" else scrapers.parse_zoopla
        listings = parser(html, url)
        if not listings:
            return jsonify({"error": "Page fetched but no listing data found — portal may be blocking scraping"}), 404
        return jsonify(listings[0])

    # ---- Postcode lookup ----------------------------------------------------

    @app.route("/lookup")
    def lookup():
        pc = request.args.get("postcode", "").strip().upper()
        if not pc:
            return render_template("lookup.html", postcode=None)
        epc = analyzer.fetch_epc(pc)
        outcode = pc.split()[0] if " " in pc else pc
        comps = analyzer.fetch_sold_comps(outcode)[:20]
        _, median, conf, basis = analyzer.score_comps(comps, None, None)
        return render_template("lookup.html", postcode=pc, epc=epc, comps=comps,
                               comp_median=median, comp_confidence=conf, comp_basis=basis,
                               outcode=outcode)

    # ---- Auction tracker ----------------------------------------------------

    @app.route("/auctions")
    def auctions():
        c = db.conn()
        rows = [dict(r) for r in db.lots(c)]
        c.close()
        today = _dt.date.today()
        for r in rows:
            r["checklist"] = json.loads(r["checklist_json"] or "{}")
            r["pack"] = json.loads(r["pack_json"]) if r["pack_json"] else None
            try:
                r["days_left"] = (_dt.date.fromisoformat(r["auction_date"]) - today).days
            except (TypeError, ValueError):
                r["days_left"] = None
            done = sum(1 for k, _ in db.CHECKLIST_ITEMS if r["checklist"].get(k))
            r["checklist_done"] = done
            r["bid_ready"] = done == len(db.CHECKLIST_ITEMS)
        return render_template("auctions.html", lots=rows, items=db.CHECKLIST_ITEMS, today=today)

    @app.route("/auctions/add", methods=["POST"])
    def auctions_add():
        f = request.form
        ev = int(f["end_value"]); refurb = int(f.get("refurb") or 20000); rent = int(f["rent"])
        roi = float(f.get("target_roi") or 12) / 100
        mb = analyzer.max_bid(ev, refurb, rent, roi)
        c = db.conn()
        db.add_lot(c, dict(lot_no=f.get("lot_no"), auction_house=f.get("auction_house"),
                           auction_date=f.get("auction_date"), url=f.get("url"),
                           address=f["address"], postcode=f.get("postcode"),
                           guide_price=int(f["guide_price"]), end_value=ev, refurb=refurb, rent=rent,
                           max_bid=mb["max_bid"], max_bid_recycle=mb["bid_full_recycle"],
                           target_roi=roi, notes=f.get("notes")))
        c.close()
        flash(f"Lot added. MAX BID locked at £{mb['max_bid']:,}." + (f" ⚠ {mb['note']}" if mb["note"] else ""))
        return redirect(url_for("auctions"))

    @app.route("/auctions/<int:lot_id>/check", methods=["POST"])
    def auctions_check(lot_id):
        c = db.conn()
        row = c.execute("SELECT checklist_json FROM auction_lots WHERE id=?", (lot_id,)).fetchone()
        if row:
            cl = {k: bool(request.form.get(k)) for k, _ in db.CHECKLIST_ITEMS}
            db.update_lot(c, lot_id, checklist_json=json.dumps(cl))
        c.close()
        return redirect(url_for("auctions"))

    @app.route("/auctions/<int:lot_id>/pack", methods=["POST"])
    def auctions_pack(lot_id):
        f = request.files.get("pack")
        if not f or not f.filename.lower().endswith(".pdf"):
            flash("Upload the legal pack as a single PDF.")
            return redirect(url_for("auctions"))
        dest = _DATA / "packs" / f"lot{lot_id}_{secure_filename(f.filename)}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        f.save(dest)
        result = analyzer.analyse_legal_pack(dest)
        c = db.conn()
        db.update_lot(c, lot_id, pack_json=json.dumps(result), pack_file=str(dest))
        c.close()
        flash(f"Legal pack analysed — risk: {result.get('risk','?')}. Screening aid only — your solicitor still reads the pack.")
        return redirect(url_for("auctions"))

    @app.route("/auctions/<int:lot_id>/delete", methods=["POST"])
    def auctions_delete(lot_id):
        c = db.conn(); db.delete_lot(c, lot_id); c.close()
        return redirect(url_for("auctions"))

    # ---- Portfolio ----------------------------------------------------------

    SIX_MONTH_DAYS = 183

    def _portfolio_view(c):
        rows = [dict(r) for r in db.portfolio_all(c)]
        today = _dt.date.today()
        for r in rows:
            try:
                comp = _dt.date.fromisoformat(r["completion_date"])
                r["refi_eligible_date"] = comp + _dt.timedelta(days=SIX_MONTH_DAYS)
                r["refi_days_left"] = (r["refi_eligible_date"] - today).days
            except (TypeError, ValueError):
                r["refi_eligible_date"], r["refi_days_left"] = None, None
            ev = r["est_value"] or 0
            new_loan = int(ev * analyzer.A["ltv"])
            r["refi_pull"] = max(new_loan - (r["mortgage_loan"] or 0), 0)
            sdlt = analyzer.calc_sdlt(r["purchase_price"] or 0)
            r["all_in"] = (r["purchase_price"] or 0) + (r["refurb_spent"] or 0) + sdlt + analyzer.A["fees"]
            r["equity"] = max(ev - (r["mortgage_loan"] or 0), 0)
            r["ltv"] = (r["mortgage_loan"] / ev) if ev and r["mortgage_loan"] else 0
            rate = r["mortgage_rate"] or analyzer.A["rate"]
            r["mortgage_pm"] = int((r["mortgage_loan"] or 0) * rate / 12)
            opex = (r["rent_actual"] or 0) * (analyzer.A["mgmt"] + analyzer.A["maint"] + analyzer.A["voids"]) \
                   + analyzer.A["insurance"] / 12
            r["cashflow_pm"] = int((r["rent_actual"] or 0) - r["mortgage_pm"] - opex) if r["rent_actual"] else 0
            r["refurb_over"] = (r["refurb_spent"] or 0) > (r["refurb_budget"] or 0) > 0
            r["window_open"] = (r["refi_days_left"] is not None and r["refi_days_left"] <= 0
                                and r["status"] != "refinanced" and r["refi_pull"] > 0)
        totals = dict(
            n=len(rows),
            deployed=sum(r["all_in"] for r in rows),
            recycled=sum(r["refinanced_amount"] or 0 for r in rows),
            cashflow=sum(r["cashflow_pm"] for r in rows),
            value=sum(r["est_value"] or 0 for r in rows),
            debt=sum(r["mortgage_loan"] or 0 for r in rows),
        )
        totals["agg_ltv"] = totals["debt"] / totals["value"] if totals["value"] else 0
        totals["cash_in_market"] = totals["deployed"] - totals["recycled"]
        return rows, totals

    @app.route("/portfolio")
    def portfolio():
        c = db.conn()
        rows, totals = _portfolio_view(c)
        c.close()
        return render_template("portfolio.html", props=rows, t=totals)

    @app.route("/portfolio/add", methods=["POST"])
    def portfolio_add():
        f = request.form
        c = db.conn()
        db.portfolio_add(c, dict(
            address=f["address"], postcode=f.get("postcode"),
            outcode=(f.get("postcode") or "").split()[0] or None, prop_type=f.get("prop_type"),
            purchase_price=int(f["purchase_price"]), completion_date=f["completion_date"],
            refurb_budget=int(f.get("refurb_budget") or 0), refurb_spent=int(f.get("refurb_spent") or 0),
            rent_actual=int(f.get("rent_actual") or 0), mortgage_loan=int(f.get("mortgage_loan") or 0),
            mortgage_rate=float(f["mortgage_rate"]) / 100 if f.get("mortgage_rate") else None,
            est_value=int(f.get("est_value") or 0) or None, notes=f.get("notes")))
        c.close()
        flash("Property added to portfolio.")
        return redirect(url_for("portfolio"))

    @app.route("/portfolio/<int:pid>/update", methods=["POST"])
    def portfolio_update(pid):
        f = request.form
        kw = {}
        for field, cast in (("refurb_spent", int), ("rent_actual", int), ("est_value", int),
                            ("mortgage_loan", int), ("status", str), ("notes", str)):
            if f.get(field) not in (None, ""):
                kw[field] = cast(f[field])
        c = db.conn()
        db.portfolio_update(c, pid, **kw)
        c.close()
        flash("Updated.")
        return redirect(url_for("portfolio"))

    @app.route("/portfolio/<int:pid>/revalue", methods=["POST"])
    def portfolio_revalue(pid):
        c = db.conn()
        r = c.execute("SELECT * FROM portfolio WHERE id=?", (pid,)).fetchone()
        if r and r["outcode"]:
            comps = analyzer.fetch_sold_comps(r["outcode"])
            db.save_comps(c, r["outcode"], comps)
            n, val, conf, basis = analyzer.score_comps(comps, r["address"], r["prop_type"])
            if val:
                db.portfolio_update(c, pid, est_value=val, est_value_basis=basis, est_value_confidence=conf)
                flash(f"Revalued from Land Registry: £{val:,} ({conf} confidence, {basis}, {n} comps). "
                      f"A post-refurb valuation may be higher — this is the unimproved comp baseline.")
            else:
                flash("No recent sold comps found for that outcode — keep your manual estimate.")
        c.close()
        return redirect(url_for("portfolio"))

    @app.route("/portfolio/<int:pid>/refinance", methods=["POST"])
    def portfolio_refinance(pid):
        f = request.form
        amount = int(f["amount"])
        c = db.conn()
        db.portfolio_update(c, pid, refinanced_amount=amount,
                            refinance_date=f.get("date") or _dt.date.today().isoformat(),
                            mortgage_loan=amount, status="refinanced",
                            mortgage_rate=float(f["rate"]) / 100 if f.get("rate") else None)
        c.close()
        flash(f"Refinance recorded: £{amount:,} released back into the war chest.")
        return redirect(url_for("portfolio"))

    @app.route("/portfolio/<int:pid>/delete", methods=["POST"])
    def portfolio_delete(pid):
        c = db.conn(); db.portfolio_delete(c, pid); c.close()
        return redirect(url_for("portfolio"))
