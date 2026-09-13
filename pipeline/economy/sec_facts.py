"""SEC companyfacts extraction shared by the economic viability model.

Uses USD facts, latest filings, prioritized tags, and FY/YTD reconstruction.
Annualized YTD is an explicit fallback, not a fully observed trailing year.
"""
from datetime import date


PREDECESSOR_CIKS = {"XOM": [34088]}


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

