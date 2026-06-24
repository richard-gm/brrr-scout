"""Standalone investment calculators — Flip and HMO.

SDLT is in analyzer.calc_sdlt() and re-exported here for convenience.
All functions return plain dicts suitable for JSON or template rendering.
"""
from .analyzer import calc_sdlt  # noqa: re-export

# ---- Flip calculator --------------------------------------------------------

_FLIP_AGENT_PCT = 0.015    # estate agent selling fee
_FLIP_LEGAL_BUY = 1_500    # buyer solicitor
_FLIP_LEGAL_SELL = 1_500   # seller solicitor


def calc_flip(buy_price, refurb, agent_pct=None, legal_buy=None, legal_sell=None, target_profit=15_000):
    """Calculate flip deal economics.

    Returns dict with total costs, break-even sale price, target sale price,
    profit at break-even, and gross ROI on cash invested.
    """
    if agent_pct is None:
        agent_pct = _FLIP_AGENT_PCT
    if legal_buy is None:
        legal_buy = _FLIP_LEGAL_BUY
    if legal_sell is None:
        legal_sell = _FLIP_LEGAL_SELL

    sdlt = calc_sdlt(buy_price)
    total_buy_costs = buy_price + refurb + sdlt + legal_buy

    # Sale proceeds net of selling costs:
    #   net_proceeds = sale_price × (1 − agent_pct) − legal_sell
    # Break-even: net_proceeds = total_buy_costs
    #   sale_price = (total_buy_costs + legal_sell) / (1 − agent_pct)
    breakeven_sale = int((total_buy_costs + legal_sell) / (1 - agent_pct))
    target_sale = int((total_buy_costs + legal_sell + target_profit) / (1 - agent_pct))

    # Selling costs at target sale price
    selling_costs_at_target = int(target_sale * agent_pct + legal_sell)
    actual_profit = target_sale - selling_costs_at_target - total_buy_costs
    roi = actual_profit / total_buy_costs if total_buy_costs > 0 else 0

    return {
        "buy_price": buy_price,
        "refurb": refurb,
        "sdlt": sdlt,
        "legal_buy": legal_buy,
        "legal_sell": legal_sell,
        "agent_pct": agent_pct,
        "total_buy_costs": total_buy_costs,
        "breakeven_sale": breakeven_sale,
        "target_sale": target_sale,
        "target_profit": target_profit,
        "actual_profit": int(actual_profit),
        "roi_pct": round(roi * 100, 1),
        "selling_costs": selling_costs_at_target,
    }


# ---- HMO calculator ---------------------------------------------------------

_HMO_MGMT = 0.12     # higher than BTL — specialist HMO management
_HMO_MAINT = 0.08
_HMO_VOIDS = 0.05    # slightly higher void allowance for HMO
_HMO_INSURANCE = 700  # HMO-rated landlord policy
_HMO_RATE = 0.0525
_HMO_LTV = 0.75
_HMO_FEES = 3_500    # higher legal/licensing costs


def calc_hmo(
    buy_price, rooms, rent_per_room, refurb,
    rate=None, ltv=None, bills_per_room=0,
    mgmt_pct=None, maint_pct=None, voids_pct=None,
    insurance=None, fees=None,
):
    """Calculate HMO deal economics.

    bills_per_room: monthly bills included in rent (common for HMO), £/room.
    Returns dict with gross/net rent, cashflow, ROI, stress test, and refi numbers.
    """
    if rate is None:
        rate = _HMO_RATE
    if ltv is None:
        ltv = _HMO_LTV
    if mgmt_pct is None:
        mgmt_pct = _HMO_MGMT
    if maint_pct is None:
        maint_pct = _HMO_MAINT
    if voids_pct is None:
        voids_pct = _HMO_VOIDS
    if insurance is None:
        insurance = _HMO_INSURANCE
    if fees is None:
        fees = _HMO_FEES

    gross_rent_yr = rooms * rent_per_room * 12
    mgmt = gross_rent_yr * mgmt_pct
    maint = gross_rent_yr * maint_pct
    voids = gross_rent_yr * voids_pct
    bills_yr = rooms * bills_per_room * 12
    net_rent_yr = gross_rent_yr - mgmt - maint - voids - bills_yr - insurance

    sdlt = calc_sdlt(buy_price)
    deposit = buy_price * (1 - ltv)
    total_cash_in = deposit + refurb + sdlt + fees

    loan = buy_price * ltv
    mortgage_yr = loan * rate
    cashflow_yr = net_rent_yr - mortgage_yr
    cashflow_pm = cashflow_yr / 12

    gross_yield = gross_rent_yr / buy_price if buy_price else 0
    net_yield = net_rent_yr / buy_price if buy_price else 0
    roi = cashflow_yr / total_cash_in if total_cash_in > 0 else 0

    # Stress test: rent ≥ 125 % × mortgage @ 7 %
    stress_mortgage = loan * 0.07
    stress_pass = gross_rent_yr >= 1.25 * stress_mortgage

    # Refi: borrow 75 % of (buy + refurb), assume value lifts to buy + refurb
    gdc = buy_price + refurb
    refi_loan = gdc * ltv
    pulled_out = max(0, refi_loan - loan)  # extra cash released vs initial loan
    left_in = max(0, total_cash_in - pulled_out)

    return {
        "buy_price": buy_price,
        "rooms": rooms,
        "rent_per_room": rent_per_room,
        "refurb": refurb,
        "sdlt": sdlt,
        "total_cash_in": int(total_cash_in),
        "gross_rent_yr": int(gross_rent_yr),
        "gross_rent_pm": int(gross_rent_yr / 12),
        "net_rent_yr": int(net_rent_yr),
        "mortgage_yr": int(mortgage_yr),
        "cashflow_yr": int(cashflow_yr),
        "cashflow_pm": int(cashflow_pm),
        "gross_yield_pct": round(gross_yield * 100, 2),
        "net_yield_pct": round(net_yield * 100, 2),
        "roi_pct": round(roi * 100, 1),
        "stress_pass": stress_pass,
        "gdc": int(gdc),
        "refi_loan": int(refi_loan),
        "pulled_out": int(pulled_out),
        "left_in": int(left_in),
    }
