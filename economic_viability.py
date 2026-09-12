"""Economic viability: can a company keep paying its workforce and its
obligations out of its own operations - also through a bad year?

Usage: python3 economic_viability.py <companyfacts_dir>
(populate the directory first with fetch_sec_facts.py)

Three principles:

1. **Capacity, not size or profit.** Every measure is a ratio against the
   company's own obligations or its own history, and every score saturates at
   a level that counts as "sufficient". Earning ten times more than needed
   scores the same as earning just enough. There is no margin, return or
   growth metric.

2. **Observed, not forecast.** Only figures from 10-K/10-Q filings: up to ten
   fiscal years of history plus the latest balance sheet and trailing twelve
   months. The stress case is not an assumption but a repeat of the worst
   year the company itself has already been through.

3. **Weakest link.** Dimensions are combined with a geometric mean, and the
   level is set by the weakest dimension: a large cash pile does not buy back
   a decade of negative cash flow.

Dimensions
- cash generation: in how many of the last ten years did operations bring in
  cash, did that cash at least cover the wear of the asset base
  (depreciation), and is it cash-positive now (last three fiscal years and
  trailing twelve months)? A company that fails this lives on outside money;
  the recent part keeps an old cash-burn phase from outweighing years of
  self-funding since.
- shock absorption: take the largest one-year fall in operating cash flow in
  the company's own history (scaled by total assets, so it transfers to
  today's size). If it happened again now, would operating cash flow stay
  positive - and if not, how much of the gap does cash on hand cover?
  This is the direct question "could it keep paying staff and suppliers
  through its worst year without new money".
- debt service: share of operating cash eaten by interest, and debt due within
  twelve months versus cash plus a year of operating cash flow.

Not scored, on purpose
- Revenue swings: spin-offs, divestitures and commodity prices move revenue
  without threatening payroll, and revenue tags break across years. The
  cash-flow history already shows the swings that mattered.
- Banks and insurers: deposits, trading assets and premiums make operating
  cash flow, liquidity and debt ratios mean something else. They need
  regulatory capital data (FFIEC call reports, NAIC), so they are marked not
  assessable instead of being scored with the wrong yardstick.

The thresholds below are set, not estimated. They are here to be argued with.
"""
import csv
import json
import math
import os
import sys

import financial_health as fh

OUT = "economic_viability.csv"
HEALTH_CSV = "financial_health.csv"  # optional, only for the bias check
HISTORY_YEARS = 10
RECENT_YEARS = 3
MIN_YEARS = 3
STALE_BEFORE = "2024-06-30"

# (zero_at, full_at): linear in between, clamped to 0..1 outside
THRESHOLDS = {
    "ocf_positive_share": (0.5, 1.0),   # cash-positive every year = full; half the years or fewer = zero
    "reinvestment_share": (0.5, 0.9),   # one year in ten may fall short of depreciation
    "shock_cash_coverage": (0.25, 1.0), # cash covers the whole gap of a repeated worst year = full
    "interest_share": (0.5, 0.1),       # interest up to 10% of operating cash = full; half = zero
    "due_to_available": (1.5, 0.5),     # maturities up to half of cash + a year's OCF = full
}
SCORE_FLOOR = 0.02  # keeps the geometric mean defined when a dimension scores zero
LEVELS = [(0.6, "viable"), (0.25, "strained"), (0.0, "at risk")]  # judged on the weakest dimension
MIN_DIMENSIONS = 2

DNA_TAGS = ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
            "DepreciationAmortizationAndAccretionNet", "Depreciation"]
COST_TAGS = ["CostsAndExpenses", "OperatingCostsAndExpenses"]
INTEREST_PAID_TAGS = ["InterestPaidNet", "InterestPaid"]
SHORT_INVESTMENT_TAGS = ["ShortTermInvestments", "MarketableSecuritiesCurrent",
                         "AvailableForSaleSecuritiesDebtSecuritiesCurrent"]
LABOR_TAGS = ["LaborAndRelatedExpense"]


def ramp(value, zero_at, full_at):
    if value is None:
        return None
    return max(0.0, min(1.0, (value - zero_at) / (full_at - zero_at)))


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def annual_series(data, tags):
    """[(fiscal year end, value)] for the last HISTORY_YEARS fiscal years; per year the first tag in `tags` wins."""
    years = {}
    for rank, tag in enumerate(tags):
        for f in fh.latest_by_period(fh.facts_for(data, tag)):
            if f.get("start") and 350 <= fh.length(f) <= 380 and not f["form"].startswith("10-Q"):
                if f["end"] not in years or -rank > years[f["end"]][0]:
                    years[f["end"]] = (-rank, f["val"])
    series = []
    for end in sorted(years):
        if series and (fh.d(end) - fh.d(series[-1][0])).days < 300:
            series[-1] = (end, years[end][1])  # changed fiscal year end: keep the newer
        else:
            series.append((end, years[end][1]))
    return series[-HISTORY_YEARS:]


def first_instant(data, tags, when):
    for tag in tags:
        v = fh.instants(data, tag).get(when)
        if v is not None:
            return v
    return None


def ttm(data, tags, concept=""):
    r = fh.best_flow(data, concept, tags)
    return r["ttm"] if r else None


def worst_cash_shortfall(ocf_hist, assets):
    """Largest one-year fall in operating cash flow as a share of total assets at the start of that year.

    Returns ((fiscal year end, share), number of comparable year pairs)."""
    worst, pairs = None, 0
    for (prev_end, prev), (end, cur) in zip(ocf_hist, ocf_hist[1:]):
        base = assets.get(prev_end)
        if base and base > 0 and 330 <= (fh.d(end) - fh.d(prev_end)).days <= 400:
            pairs += 1
            share = max(prev - cur, 0) / base
            if worst is None or share > worst[1]:
                worst = (end, share)
    return worst, pairs


def due_within_year(data, bs_end):
    """Debt that has to be repaid or refinanced within twelve months."""
    total = first_instant(data, ["DebtCurrent"], bs_end)
    if total is not None:
        return total
    lt = first_instant(data, ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"], bs_end)
    if lt is None:
        schedule = {e: v for e, v in fh.instants(
            data, "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths").items()
            if 0 <= (fh.d(bs_end) - fh.d(e)).days <= fh.FALLBACK_MAX_AGE_DAYS}
        lt = schedule[max(schedule)] if schedule else None
    short = [first_instant(data, [t], bs_end) for t in fh.SHORT_TERM]
    if lt is None and all(v is None for v in short):
        return None
    return (lt or 0) + sum(v for v in short if v is not None)


def analyse(member, data):
    ocf_hist = annual_series(data, fh.FLOW_TAGS["ocf"])
    last_fy = ocf_hist[-1][0] if ocf_hist else None
    base = {"fiscal_years": len(ocf_hist), "history_from": ocf_hist[0][0] if ocf_hist else None,
            "last_fy_end": last_fy}
    if member["GICS Sector"] == "Financials":
        return {**base, "viability_level": "not assessable",
                "notes": "bank/insurer: needs regulatory capital data, cash-flow ratios do not apply"}
    if last_fy is None:
        return {**base, "viability_level": "not assessable", "notes": "no fiscal-year history yet (new registrant)"}
    if last_fy < STALE_BEFORE:
        return {**base, "viability_level": "no recent filings"}

    notes = []
    assets_hist = fh.instants(data, "Assets") or fh.instants(data, "ifrs:Assets")
    bs_end = max(assets_hist) if assets_hist else None
    ocf = ttm(data, fh.FLOW_TAGS["ocf"])
    cash = None
    if bs_end:
        cash = first_instant(data, fh.INSTANT_TAGS["cash"], bs_end)
        if cash is not None:
            cash += first_instant(data, SHORT_INVESTMENT_TAGS, bs_end) or 0

    # ---- cash generation: track record -------------------------------------
    enough_history = len(ocf_hist) >= MIN_YEARS
    positive_years = sum(v > 0 for _, v in ocf_hist)
    dna_hist = dict(annual_series(data, DNA_TAGS))
    paired = [(v, dna_hist[e]) for e, v in ocf_hist if e in dna_hist]
    covered_years = sum(o >= dep for o, dep in paired)
    if not enough_history:
        notes.append(f"only {len(ocf_hist)} fiscal year(s) of history")
    if ocf is None:
        recent = None
    elif ocf <= 0:
        recent = 0.0
    else:
        recent = 1.0 if all(v > 0 for _, v in ocf_hist[-RECENT_YEARS:]) else 0.5
    cash_generation = mean([
        ramp(positive_years / len(ocf_hist), *THRESHOLDS["ocf_positive_share"]) if enough_history else None,
        ramp(covered_years / len(paired), *THRESHOLDS["reinvestment_share"]) if len(paired) >= MIN_YEARS else None,
        recent,
    ])

    # ---- shock absorption: a repeat of the company's own worst year --------
    worst, pairs = worst_cash_shortfall(ocf_hist, assets_hist)
    shock_ocf = coverage = shock_absorption = None
    if worst and pairs >= MIN_YEARS - 1 and ocf is not None and bs_end:
        shock_ocf = ocf - worst[1] * assets_hist[bs_end]
        if shock_ocf >= 0:
            shock_absorption = 1.0
        elif cash is not None:
            coverage = cash / -shock_ocf
            shock_absorption = ramp(coverage, *THRESHOLDS["shock_cash_coverage"])

    # ---- debt service --------------------------------------------------------
    interest_share = due = due_ratio = None
    paid = ttm(data, INTEREST_PAID_TAGS)
    if paid is not None and ocf is not None:
        before_interest = ocf + abs(paid)
        interest_share = abs(paid) / before_interest if before_interest > 0 else 1.0
    if bs_end:
        due = due_within_year(data, bs_end)
    if due is not None and cash is not None:
        available = cash + max(ocf or 0, 0)
        due_ratio = due / available if available > 0 else (0.0 if due == 0 else math.inf)
    debt_service = mean([
        ramp(interest_share, *THRESHOLDS["interest_share"]),
        ramp(min(due_ratio, 10.0), *THRESHOLDS["due_to_available"]) if due_ratio is not None else None,
    ])

    # ---- info only: months of cash operating costs held in cash --------------
    cash_months = None
    rev, op_inc, dna = ttm(data, fh.FLOW_TAGS["revenue"], "revenue"), ttm(data, fh.FLOW_TAGS["op_income"]), ttm(data, DNA_TAGS)
    costs = rev - op_inc if rev is not None and op_inc is not None else ttm(data, COST_TAGS)
    if costs is not None and cash is not None:
        costs -= dna or 0
        if costs > 0:
            cash_months = cash / (costs / 12)

    # ---- combine ---------------------------------------------------------------
    dims = {"cash_generation": cash_generation, "shock_absorption": shock_absorption, "debt_service": debt_service}
    have = {k: v for k, v in dims.items() if v is not None}
    index = weakest = None
    if len(have) < MIN_DIMENSIONS:
        level = "not assessable"
    else:
        index = round(100 * math.exp(mean([math.log(max(v, SCORE_FLOOR)) for v in have.values()])), 1)
        weakest = min(have, key=have.get)
        level = next(label for bound, label in LEVELS if have[weakest] >= bound)
        if len(have) < len(dims):
            notes.append("missing: " + ", ".join(k for k in dims if k not in have))

    def r(v, n=2):
        return None if v is None else round(v, n)

    def bn(v):
        return None if v is None else round(v / 1e9, 2)

    return {
        **base,
        "balance_sheet_date": bs_end,
        "ocf_positive_years": f"{positive_years}/{len(ocf_hist)}",
        "ocf_covers_depreciation_years": f"{covered_years}/{len(paired)}" if paired else None,
        "cash_positive_now": {1.0: "yes", 0.5: "partly", 0.0: "no"}.get(recent),
        "worst_ocf_fall_pct_of_assets": r(100 * worst[1], 1) if worst else None,
        "worst_ocf_fall_fy_end": worst[0] if worst else None,
        "ocf_ttm_usd_bn": bn(ocf),
        "ocf_if_worst_year_repeats_usd_bn": bn(shock_ocf),
        "cash_and_st_investments_usd_bn": bn(cash),
        "cash_covers_shock_gap_x": r(coverage),
        "interest_share_of_op_cash_pct": r(100 * interest_share, 1) if interest_share is not None else None,
        "debt_due_12m_usd_bn": bn(due),
        "debt_due_to_cash_plus_ocf": "inf" if due_ratio == math.inf else r(due_ratio),
        "info_cash_months_of_costs": r(cash_months, 1),
        "info_labor_expense_ttm_usd_bn": bn(ttm(data, LABOR_TAGS)),  # tagged by few filers
        **{f"score_{k}": r(v) for k, v in dims.items()},
        "viability_index": index,
        "weakest_dimension": weakest,
        "viability_level": level,
        "notes": "; ".join(notes),
    }


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2
        i = j + 1
    return out


def spearman(pairs):
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    if len(pairs) < 10:
        return None, len(pairs)
    ra, rb = ranks([a for a, _ in pairs]), ranks([b for _, b in pairs])
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    var = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return round(cov / var, 2), len(pairs)


def bias_check(out):
    """Does the index just re-measure size or profit? It should not."""
    if not os.path.exists(HEALTH_CSV):
        return
    with open(HEALTH_CSV, newline="") as f:
        health = {r["ticker"]: r for r in csv.DictReader(f)}

    def num(ticker, key):
        v = health.get(ticker, {}).get(key)
        return float(v) if v not in (None, "") else None

    for label, key in [("revenue (size)", "revenue_ttm_usd_bn"), ("net income (absolute profit)", "net_income_ttm_usd_bn"),
                       ("net margin (profitability)", "net_margin_pct"), ("profit-weighted health score", "health_score")]:
        rho, n = spearman([(r.get("viability_index"), num(r["ticker"], key)) for r in out])
        print(f"Spearman viability_index vs {label}: rho={rho} (n={n})")


def main():
    facts_dir = sys.argv[1]
    with open(fh.CONSTITUENTS, newline="") as f:
        members = list(csv.DictReader(f))

    out = []
    for m in members:
        row = {"ticker": m["Symbol"], "company": m["Security"], "sector": m["GICS Sector"]}
        path = os.path.join(facts_dir, f"{int(m['CIK'])}.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            for cik in fh.PREDECESSOR_CIKS.get(m["Symbol"], []):
                with open(os.path.join(facts_dir, f"{cik}.json")) as f:
                    fh.merge_facts(data, json.load(f))
            row.update(analyse(m, data))
        else:
            row["viability_level"] = "no SEC data"
        out.append(row)

    fields = list(max(out, key=len))
    out.sort(key=lambda x: -(x.get("viability_index") if x.get("viability_index") is not None else -1))
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} constituents written to {OUT}")
    bias_check(out)


if __name__ == "__main__":
    main()
