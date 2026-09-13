"""Financial health & viability screen for S&P 500 constituents.

Usage: python3 financial_health.py <companyfacts_dir>
(populate the directory first with fetch_sec_facts.py)

Uses the newest SEC XBRL data per company: the latest 10-K, trailing twelve
months (TTM = last fiscal year + current YTD - prior-year YTD from 10-Qs) and
the latest balance sheet. Writes financial_health.csv with ratios, a 0-100
score and a viability rating.

Ratings are backward-looking proxies for future viability (profitability,
cash generation, growth, leverage) - not forecasts.
"""
import csv
import json
import os
import sys
from datetime import date

CONSTITUENTS = "constituents.csv"
OUT = "financial_health.csv"
STALE_BEFORE = "2025-06-30"  # latest period older than this = no recent filings

# companies that re-registered under a new CIK; older filings live under the predecessor
PREDECESSOR_CIKS = {"XOM": [34088]}

# candidate XBRL tags per concept, in order of preference
FLOW_TAGS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                "RevenuesNetOfInterestExpense", "ifrs:Revenue"],
    "net": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss",
            "ifrs:ProfitLossAttributableToOwnersOfParent", "ifrs:ProfitLoss"],
    "op_income": ["OperatingIncomeLoss", "ifrs:ProfitLossFromOperatingActivities"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
            "ifrs:CashFlowsFromUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsForCapitalImprovements", "PaymentsToAcquireRealEstate",
              "ifrs:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
    "rnd": ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
            "ifrs:ResearchAndDevelopmentExpense"],
    "interest": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt",
                 "InterestPaidNet", "ifrs:FinanceCosts"],
}
INSTANT_TAGS = {
    "assets": ["Assets", "ifrs:Assets"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
               "ifrs:EquityAttributableToOwnersOfParent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "ifrs:CashAndCashEquivalents"],
}
DEBT_TOTAL = ["LongTermDebt", "DebtLongtermAndShorttermCombinedAmount", "ifrs:Borrowings"]
DEBT_PARTS = [("LongTermDebtNoncurrent", "LongTermDebtCurrent"),
              ("LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent")]
# fallbacks for filers that tag balance-sheet debt with custom elements; each
# matched LongTermDebt within +-15% for >80% of companies reporting both
DEBT_FALLBACK = ["LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
                 "DebtInstrumentCarryingAmount", "DebtAndCapitalLeaseObligations"]
DEBT_MATURITIES = ["LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
                   "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
                   "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
                   "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
                   "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
                   "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive"]
FALLBACK_MAX_AGE_DAYS = 400  # fallbacks are often annual-only disclosures
SHORT_TERM = ["ShortTermBorrowings", "CommercialPaper"]


def d(s):
    return date.fromisoformat(s)


def facts_for(data, tag):
    ns, name = ("ifrs-full", tag[5:]) if tag.startswith("ifrs:") else ("us-gaap", tag)
    concept = data.get("facts", {}).get(ns, {}).get(name)
    return concept["units"].get("USD", []) if concept else []


def merge_facts(data, extra):
    """Append a predecessor registrant's facts; latest_by_period resolves overlaps."""
    for ns, concepts in extra.get("facts", {}).items():
        target = data.setdefault("facts", {}).setdefault(ns, {})
        for name, concept in concepts.items():
            units = target.setdefault(name, {"units": {}})["units"]
            for unit, facts in concept["units"].items():
                units.setdefault(unit, []).extend(facts)


def latest_by_period(facts):
    """One value per (start, end): the most recently filed, skipping the zero
    placeholders some filers tag in predecessor/successor columns.

    Any form counts - the newest copy of a 10-K figure is often in a proxy
    statement (pay-vs-performance) or an 8-K recast."""
    best = {}
    for f in facts:
        key = (f.get("start"), f["end"])
        cur = best.get(key)
        if cur is None or ((cur["val"] == 0, cur["filed"]) < (f["val"] == 0, f["filed"])
                           if (cur["val"] == 0) == (f["val"] == 0) else cur["val"] == 0):
            best[key] = f
    return best.values()


def length(f):
    return (d(f["end"]) - d(f["start"])).days


def flow(data, tag):
    """Latest fiscal year, prior fiscal year and TTM for a duration concept."""
    facts = [f for f in latest_by_period(facts_for(data, tag)) if f.get("start")]
    # 10-Qs can carry trailing-twelve-month figures (e.g. Amazon) - not fiscal years
    annual = {f["end"]: f for f in facts if 350 <= length(f) <= 380 and not f["form"].startswith("10-Q")}
    partial = [f for f in facts if 80 <= length(f) <= 300]
    newest = max((f["end"] for f in partial), default=None)

    if not annual or (newest and (d(newest) - d(max(annual))).days > 400):
        # no usable fiscal year (spin-off, new registrant): annualise the latest year-to-date
        if not newest:
            return None
        ytd = max((f for f in partial if f["end"] == newest), key=length)
        return {"fy": None, "fy_end": None, "prior_fy": None, "ttm": ytd["val"] * 365 / length(ytd),
                "ttm_end": newest, "accn": ytd["accn"], "method": "annualised YTD"}

    fy_end = max(annual)
    fy = annual[fy_end]
    prior = next((annual[e] for e in annual if 350 <= (d(fy_end) - d(e)).days <= 380), None)
    res = {"fy": fy["val"], "fy_end": fy_end, "prior_fy": prior["val"] if prior else None,
           "ttm": fy["val"], "ttm_end": fy_end, "accn": fy["accn"], "method": "fiscal year"}

    # year-to-date periods that start right after the last fiscal year
    ytd = [f for f in partial if f["end"] > fy_end and abs((d(f["start"]) - d(fy_end)).days - 1) <= 7]
    if ytd:
        cur = max(ytd, key=lambda f: f["end"])
        comp = next((f for f in facts if abs((d(cur["end"]) - d(f["end"])).days - 365) <= 10
                     and abs(length(f) - length(cur)) <= 10), None)
        if comp:
            res.update(ttm=fy["val"] + cur["val"] - comp["val"], ttm_end=cur["end"], accn=cur["accn"],
                       method="FY + YTD")
    return res


def best_flow(data, concept, tags=None):
    options = []
    for i, tag in enumerate(tags or FLOW_TAGS[concept]):
        r = flow(data, tag)
        if r:
            # newest data wins; revenue ties go to the largest line (partial tags are smaller)
            tie = abs(r["ttm"]) if concept == "revenue" else -i
            options.append(((r["ttm_end"], r["method"] != "annualised YTD", r["fy_end"] or "", tie), r))
    return max(options, key=lambda o: o[0])[1] if options else None


def instants(data, tag):
    return {f["end"]: f["val"] for f in sorted(latest_by_period(facts_for(data, tag)), key=lambda f: f["filed"])
            if not f.get("start")}


def best_instant(data, tags, not_before):
    options = []
    for i, tag in enumerate(tags):
        vals = instants(data, tag)
        if vals:
            end = max(vals)
            if end >= not_before:
                options.append(((end, -i), vals[end]))
    return max(options, key=lambda o: o[0])[1] if options else None


def total_debt(data, bs_end):
    """Long-term debt (incl. current portion) plus short-term borrowings at the balance-sheet date."""
    lt = None
    for tag in DEBT_TOTAL:
        lt = instants(data, tag).get(bs_end)
        if lt is not None:
            break
    if lt is None:
        for non, cur in DEBT_PARTS:
            a, b = instants(data, non).get(bs_end), instants(data, cur).get(bs_end)
            if a is not None:
                lt = a + (b or 0)
                break
    if lt is None:
        lt = recent_fallback_debt(data, bs_end)
    if lt is None:
        # a current portion or commercial paper alone would understate debt
        return None
    return lt + sum(v for v in (instants(data, t).get(bs_end) for t in SHORT_TERM) if v is not None)


def recent_fallback_debt(data, bs_end):
    """Newest fallback debt figure no older than FALLBACK_MAX_AGE_DAYS before the balance sheet."""
    def fresh(end):
        return 0 <= (d(bs_end) - d(end)).days <= FALLBACK_MAX_AGE_DAYS

    for tag in DEBT_FALLBACK:
        vals = {e: v for e, v in instants(data, tag).items() if fresh(e)}
        if vals:
            return vals[max(vals)]
    schedules = [instants(data, t) for t in DEBT_MATURITIES]
    ends = [e for e in set.intersection(*(set(s) for s in schedules)) if fresh(e)] if all(schedules) else []
    return sum(s[max(ends)] for s in schedules) if ends else None


def ratio(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def score(r, financial):
    """Weighted 0-100 score; missing inputs are dropped and weights renormalised."""
    parts = []  # (points 0..1, weight)

    def add(value, fn, weight):
        if value is not None:
            parts.append((clamp(fn(value), 0, 1), weight))

    if financial:
        add(r["net_margin"], lambda v: (v + 0.05) / 0.35, 35)
        add(r["roa"], lambda v: v / 0.02, 35)  # banks/insurers run on thin ROA
        add(r["growth"], lambda v: (v + 0.10) / 0.25, 20)
        add(r["ocf_margin"], lambda v: v / 0.25, 10)
    else:
        add(r["net_margin"], lambda v: (v + 0.05) / 0.30, 25)
        add(r["fcf_margin"], lambda v: (v + 0.05) / 0.25, 20)
        add(r["roa"], lambda v: v / 0.12, 15)
        if r["debt_to_ocf"] is not None:
            add(r["debt_to_ocf"], lambda v: (8 - v) / 7, 15)  # <=1y to repay = full, >=8y = zero
        elif r["ocf"] is not None and r["ocf"] <= 0:
            parts.append((0, 15))
        add(r["growth"], lambda v: (v + 0.10) / 0.25, 10)  # -10% = zero, +15% = full
        add(r["coverage"], lambda v: (v - 1) / 9, 10)  # 1x = zero, 10x = full
        add(r["debt_to_assets"], lambda v: (0.7 - v) / 0.6, 5)
    if not parts:
        return None
    return round(100 * sum(p * w for p, w in parts) / sum(w for _, w in parts), 1)


def rating(r, s, financial, stale):
    if stale:
        return "No recent filings"
    if s is None:
        return "Insufficient data"
    net, fcf = r["net"], r["fcf"]
    if net < 0 and (financial or fcf is None or fcf < 0):
        return "Distressed"
    if net < 0:
        return "Loss-making, cash-positive"
    if s >= 70:
        return "Strong"
    if s >= 50:
        return "Solid"
    if s >= 35:
        return "Watch"
    return "Weak"


def bn(v):
    return None if v is None else round(v / 1e9, 2)


def pct(v, digits=1):
    return None if v is None else round(100 * v, digits)


def rnd(v, digits):
    return None if v is None else round(v, digits)


def analyse(member, data):
    financial = member["GICS Sector"] == "Financials"
    flows = {c: best_flow(data, c) for c in FLOW_TAGS}
    ttm = {c: (f["ttm"] if f else None) for c, f in flows.items()}
    rev, net, ocf, capex = ttm["revenue"], ttm["net"], ttm["ocf"], ttm["capex"]

    period_end = max((f["ttm_end"] for f in flows.values() if f), default=None)
    bs_end = max(instants(data, "Assets") or instants(data, "ifrs:Assets") or {"": 0})
    recent = bs_end or "0000"
    assets = best_instant(data, INSTANT_TAGS["assets"], recent)
    equity = best_instant(data, INSTANT_TAGS["equity"], recent)
    cash = best_instant(data, INSTANT_TAGS["cash"], recent)
    debt = total_debt(data, bs_end) if bs_end else None

    # a revenue tag smaller than profit or cash flow is a partial line
    # (common for REITs/banks) - margins built on it would be meaningless
    rev_flow = flows["revenue"]
    if rev is not None and (rev <= 0 or any(v is not None and v > rev for v in (net, ocf))):
        rev, rev_flow = None, None
    growth = None
    if rev_flow and rev_flow["prior_fy"] and rev_flow["prior_fy"] > 0:
        growth = rev_flow["fy"] / rev_flow["prior_fy"] - 1

    fcf = ocf - abs(capex) if ocf is not None and capex is not None else None
    interest = ttm["interest"]
    r = {
        "net": net, "ocf": ocf, "fcf": fcf, "growth": growth,
        "net_margin": ratio(net, rev),
        "roa": ratio(net, assets),
        "ocf_margin": ratio(ocf, rev),
        "fcf_margin": ratio(fcf, rev),
        "debt_to_assets": ratio(debt, assets),
        "debt_to_ocf": ratio(debt, ocf) if ocf and ocf > 0 else None,
        "coverage": ratio(ttm["op_income"], abs(interest)) if interest else None,
    }
    available = sum(v is not None for v in (rev, net, assets, debt, ocf, capex))
    stale = period_end is None or period_end < STALE_BEFORE
    s = score(r, financial) if net is not None and available >= 4 else None
    net_fy = flows["net"]
    return {
        "fy_end": flows["net"]["fy_end"] if flows["net"] else None,
        "ttm_end": period_end,
        "ttm_method": flows["net"]["method"] if flows["net"] else None,
        "balance_sheet_date": bs_end or None,
        "revenue_ttm_usd_bn": bn(rev),
        "revenue_growth_last_fy_pct": pct(growth),
        "operating_income_ttm_usd_bn": bn(ttm["op_income"]),  # far below net income = gains-driven profit
        "net_income_ttm_usd_bn": bn(net),
        "net_income_last_fy_usd_bn": bn(net_fy["fy"]) if net_fy else None,
        "net_income_prior_fy_usd_bn": bn(net_fy["prior_fy"]) if net_fy else None,
        "fcf_ttm_usd_bn": bn(fcf),
        "cash_usd_bn": bn(cash),
        "debt_usd_bn": bn(debt),
        "equity_usd_bn": bn(equity),
        "net_margin_pct": pct(r["net_margin"]),
        "fcf_margin_pct": pct(r["fcf_margin"]),
        "roa_pct": pct(r["roa"], 2),
        "debt_to_assets": rnd(r["debt_to_assets"], 2),
        "debt_payback_years": rnd(r["debt_to_ocf"], 1),
        "interest_coverage_x": rnd(r["coverage"], 1),
        "rnd_pct_revenue": pct(ratio(ttm["rnd"], rev)),
        "profitable_ttm": "" if net is None else ("Yes" if net > 0 else "No"),
        "fields_available_of_6": available,
        "health_score": s,
        "viability_rating": rating(r, s, financial, stale),
        "latest_accession": flows["net"]["accn"] if flows["net"] else None,
    }


def main():
    facts_dir = sys.argv[1]
    with open(CONSTITUENTS, newline="") as f:
        members = list(csv.DictReader(f))

    out = []
    for m in members:
        path = os.path.join(facts_dir, f"{int(m['CIK'])}.json")
        base = {"ticker": m["Symbol"], "company": m["Security"], "sector": m["GICS Sector"], "cik": m["CIK"]}
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            for cik in PREDECESSOR_CIKS.get(m["Symbol"], []):
                with open(os.path.join(facts_dir, f"{cik}.json")) as f:
                    merge_facts(data, json.load(f))
            base.update(analyse(m, data))
        else:
            base["viability_rating"] = "No SEC data"
        out.append(base)

    fields = list(max(out, key=len))
    out.sort(key=lambda x: -(x.get("health_score") if x.get("health_score") is not None else -1))
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} constituents written to {OUT}")


if __name__ == "__main__":
    main()
