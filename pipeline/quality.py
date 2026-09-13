"""Quality rules produce evidence packets for hard constraints, known data failure mechanisms, and sector outliers. Hard-rule errors and requests for review are distinct. Extreme values can be real; the rule sets severity independently of model advice."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from .config import OUT, RAW
from .resolve import OVERRIDES, master_prefix, normalize, override_prefix, resolve_owners

CURRENT_YEAR = 2026
CO2_PROGRAMS = {"ARP", "RGGI", "NSPS4T"}  # Configured CO2-reporting programs; SIPNOX alone reports NOx, not CO2.
CORE_METRICS = {"scope1_t", "co2_intensity", "intensity_cagr", "absolute_cagr"}


@dataclass
class Flag:
    rule: str
    severity: str           # error or review.
    ticker: str
    metric: str
    year: int | None
    value: float | None
    message: str
    impact_t: float = 0.0
    ranking_relevant: bool = False
    evidence: dict = field(default_factory=dict)


class Context:
    """Load shared inputs once for all quality rules."""

    def __init__(self) -> None:
        self.long = pd.read_parquet(OUT / "dataset_long.parquet")
        self.master = pd.read_parquet(RAW / "sp500_master.parquet")
        self.names = self.master.set_index("ticker")[["company", "gics_sector"]]
        self.cy = pd.read_csv(OUT / "company_year.csv")
        self.bands = pd.read_csv(OUT / "climate_bands.csv")
        self.ranked = set(self.bands["ticker"])
        self.lookup = {normalize(r.company): r.ticker for r in self.master.itertuples()}
        fac = pd.read_parquet(RAW / "epa_facility.parquet")
        emi = pd.read_parquet(RAW / "epa_emission.parquet")
        self.fac_year = fac.merge(emi, on=["facility_id", "year"], how="left")
        own = resolve_owners(self.fac_year[["facility_id", "year", "parent_company"]], self.master)
        self.attrib = self.fac_year.merge(own, on=["facility_id", "year"])
        self.attrib["att_t"] = self.attrib["scope1_t"] * self.attrib["share"]

    def to_ticker(self, name) -> str | None:
        k = normalize(name)
        if not k:
            return None
        if k in self.lookup:
            return self.lookup[k]
        if k in OVERRIDES:
            return OVERRIDES[k]
        return override_prefix(k) or master_prefix(k, self.lookup)

    def series(self, ticker: str, metric: str) -> dict:
        s = self.long[(self.long.ticker == ticker) & (self.long.metric == metric)]
        return {int(y): round(float(v), 4) for y, v in zip(s.year, s.value)}

    def sector_stats(self, ticker: str, metric: str) -> dict:
        sector = self.names.gics_sector.get(ticker)
        s = self.long[(self.long.metric == metric) & (self.long.gics_sector == sector)]
        s = s.sort_values("year").groupby("ticker").value.last()
        if s.empty:
            return {}
        return {"sector": sector, "n": int(len(s)), "median": float(s.median()),
                "p90": float(s.quantile(0.9)), "max": float(s.max())}


# Quality rules.

def r_duplicate_cik(c: Context) -> list[Flag]:
    """Find repeated issuer CIKs in observations. Multiple share classes belong in the index membership file, but consolidated issuer observations should appear once."""
    out = []
    in_dataset = set(c.long.ticker)
    for cik, g in c.master.groupby("cik"):
        if len(g) < 2:
            continue
        included = sorted(set(g.ticker) & in_dataset)
        if len(included) < 2:
            continue
        keep, *dups = included
        for t in dups:
            out.append(Flag("F01_duplicate_cik", "error", t, "*", None, None,
                            f"Shares CIK {cik} with {keep}: issuer observations are duplicated.",
                            evidence={"cik": int(cik), "share_classes": sorted(g.ticker)}))
    return out


def r_zero_emissions(c: Context) -> list[Flag]:
    out = []
    z = c.cy[c.cy.scope1_t == 0]
    for r in z.itertuples(index=False):
        rows = c.attrib[(c.attrib.ticker == r.ticker) & (c.attrib.year == r.year)]
        supplied = float(rows.supplied_t.fillna(0).sum())
        prev = c.cy[(c.cy.ticker == r.ticker) & (c.cy.year < r.year)].sort_values("year").tail(1)
        prev_t = float(prev.scope1_t.iloc[0]) if len(prev) else None
        kind = ("supplier only (fuel supplied, not emitted by the reporting facility)" if supplied > 0
                else "Facility recorded without an emissions quantity; nonreporting needs investigation")
        out.append(Flag("F02_zero_instead_of_missing", "error", r.ticker, "scope1_t", int(r.year), 0.0,
                        f"Exactly 0 tonnes despite a matched facility: {kind}. This zero does not establish an emissions-free operation.",
                        impact_t=prev_t or 0.0, ranking_relevant=r.ticker in c.ranked,
                        evidence={"facilities": int(rows.facility_id.nunique()),
                                  "facility_types": sorted(set(rows.facility_types.dropna()))[:4],
                                  "supplied_t": supplied, "previous_year_t": prev_t,
                                  "scope1_history": c.series(r.ticker, "scope1_t")}))
    return out


def r_campd_program(c: Context) -> list[Flag]:
    out = []
    ep, fp = RAW / "campd_emission.parquet", RAW / "campd_facility.parquet"
    if not (ep.exists() and fp.exists()):
        return out
    emi, fac = pd.read_parquet(ep), pd.read_parquet(fp)
    if "programCodeInfo" not in fac.columns:
        return out
    from .sources.epa_campd import split_owner_operator
    link = []
    for fid, yr, raw, prog, name in fac[["facilityId", "year", "ownerOperator", "programCodeInfo", "facilityName"]].itertuples(index=False):
        for nm, role in split_owner_operator(raw):
            t = c.to_ticker(nm) if role == "owner" else None
            if t:
                link.append((fid, yr, t, str(prog or ""), name))
    L = pd.DataFrame(link, columns=["facilityId", "year", "ticker", "programs", "facilityName"]).drop_duplicates()
    j = L.merge(emi, on=["facilityId", "year"], how="left")
    # Check exported CAMPD observations only; the
    # program filter already excludes non-CO2
    # program records.
    exported = c.long[c.long.metric == "campd_co2_t"]
    present_keys = {(r.ticker, int(r.year)) for r in exported.itertuples(index=False)}
    for (t, yr), g in j.groupby(["ticker", "year"]):
        if g.co2_t.fillna(0).sum() > 0 or (t, int(yr)) not in present_keys:
            continue
        progs = sorted({p.strip() for s in g.programs for p in s.split(",") if p.strip()})
        measures = bool(set(progs) & CO2_PROGRAMS)
        out.append(Flag("F03_campd_non_co2_program", "review" if measures else "error", t, "campd_co2_t", int(yr), 0.0,
                        ("Zero CO2 in a CO2-reporting program: investigate shutdown, biomass, or attribution."
                         if measures else
                         f"Zero CO2 from plants reporting only to non-CO2 programs ({', '.join(progs)}). The program does not measure this quantity."),
                        ranking_relevant=False,
                        evidence={"facilities": sorted(set(g.facilityName))[:5], "programs": progs,
                                  "last_mwh": float(g.gross_load_mwh.fillna(0).sum())}))
    return out


def r_echo_quarters(c: Context) -> list[Flag]:
    out = []
    p = OUT / "echo_by_company.csv"
    if not p.exists():
        return out
    e = pd.read_csv(p)
    e = e[e.noncompliance_quarters > 12 * e.facilities]
    for r in e.itertuples(index=False):
        out.append(Flag("F04_echo_impossible_quarters", "error", r.ticker, "echo_nc_quarters", 2025, float(r.noncompliance_quarters),
                        "More than 12 noncompliance quarters per facility cannot occur in a three-year window. Possible cause: duplicate facility rows when "
                        "joining EPA data through multiple parent-name variants.",
                        evidence={"facilities": int(r.facilities), "noncompliance_quarters": float(r.noncompliance_quarters),
                                  "note": "History: 12 characters, _ no recorded violation, V violation, S significant, U unresolved"}))
    return out


def r_egrid_attribution(c: Context) -> list[Flag]:
    """Flag large plant attributions outside Utilities for investigation. A non-utility can operate real captive generation, so this is an attribution review, not a physical impossibility."""
    out = []
    e = pd.read_csv(OUT / "egrid_by_company.csv") if (OUT / "egrid_by_company.csv").exists() else pd.DataFrame()
    in_dataset = set(c.long[c.long.metric == "egrid_mwh"].ticker)
    for r in e.itertuples(index=False):
        if r.ticker not in in_dataset or r.plants > 2 or r.mwh < 1e6:
            continue
        if c.names.gics_sector.get(r.ticker) == "Utilities":
            continue
        out.append(Flag("F06_egrid_attribution", "review", r.ticker, "egrid_mwh", 2023, float(r.mwh),
                        f"A matched plant with {r.mwh/1e6:.1f} TWh at a company outside Utilities: "
                        "review name-based attribution.",
                        evidence={"plants": int(r.plants), "mwh": float(r.mwh),
                                  "co2_t": float(r.co2_t), "sector": c.names.gics_sector.get(r.ticker)}))
    return out


TEMPORAL = {
    # Subsidiary key maps to ticker, first year, last year, and explanation.
    "talen energy": ("VST", None, None, "Talen is independent of Vistra"),
    "westrock": ("SW", 2024, None, "Merger into Smurfit Westrock in July 2024"),
    "pioneer natural resources": ("XOM", 2024, None, "Acquisition by ExxonMobil in May 2024"),
    "calpine": ("CEG", 2026, None, "Acquisition by Constellation after 2023"),
    "exelon generation": ("EXC", None, 2021, "Constellation Energy since February 2022"),
    "anadarko petroleum": ("OXY", 2019, None, "Acquisition by Occidental in August 2019"),
}


def r_temporal(c: Context) -> list[Flag]:
    out = []
    a = c.attrib.copy()
    a["key"] = a.parent_company.astype(str).str.split(";").str[0].str.replace(r"\([^)]*\)", "", regex=True).map(normalize)
    for key, (t, start, end, why) in TEMPORAL.items():
        rows = a[a.key.str.startswith(key) & (a.ticker == t)]
        for yr, g in rows.groupby("year"):
            wrong = (start is None and end is None) or (start is not None and yr < start) or (end is not None and yr > end)
            if not wrong or g.att_t.sum() <= 0:
                continue
            out.append(Flag("F08_temporal_attribution", "error", t, "scope1_t", int(yr), float(g.att_t.sum()),
                            f"'{key}' is {t} attributed, but the mapping is invalid for {yr}: {why}.",
                            impact_t=float(g.att_t.sum()), ranking_relevant=t in c.ranked,
                            evidence={"raw_owner": sorted(set(g.parent_company))[:3],
                                      "facilities": int(g.facility_id.nunique())}))
    return out


def r_osha_denominator(c: Context) -> list[Flag]:
    """Flag implausible reported working hours. Preserve the source values and request investigation instead of silently replacing the denominator or calculating a reassuring injury rate."""
    out = []
    o = pd.read_parquet(RAW / "osha_ita.parquet")
    o["ticker"] = o.company_name.map(c.to_ticker)
    o = o.dropna(subset=["ticker"])
    o["hours"] = pd.to_numeric(o.total_hours_worked, errors="coerce")
    o["emp"] = pd.to_numeric(o.annual_average_employees, errors="coerce")
    o["hpe"] = o.hours / o.emp
    used_tickers = set(c.long[c.long.metric == "osha_hours"].ticker)
    for t, g in o.groupby("ticker"):
        if t not in used_tickers or g.hpe.notna().sum() == 0:
            continue
        med = float(g.hpe.median())
        implaus = float(((g.hpe < 200) | (g.hpe > 4000)).mean())
        if not (med < 500 or med > 3500 or implaus > 0.3):
            continue
        out.append(Flag("F09_osha_implausible_hours", "review", t, "osha_hours", 2025,
                        float(g.hours.sum()),
                        f"Implausible reported hours: median {med:,.0f} hours per employee "
                        f"(full-time reference around 2,000), {implaus:.0%} of reports outside 200-4,000 hours.",
                        evidence={"reports": int(len(g)), "median_hours_per_employee": med,
                                  "implausible_share": implaus,
                                  "company_names": g.company_name.value_counts().head(3).to_dict()}))
    return out


def r_whd(c: Context) -> list[Flag]:
    """Flag wage cases attributed mainly through trade names. A brand can refer to independent franchise employers. Legal-name matching and franchise documentation are needed to establish the actual employer."""
    out = []
    w = pd.read_parquet(RAW / "dol_whd.parquet")
    w["t_legal"] = w.legal_name.map(c.to_ticker)
    w["t_trade"] = w.trade_nm.map(c.to_ticker)
    w["t"] = w.t_legal.fillna(w.t_trade)
    hit = w.dropna(subset=["t"])
    in_dataset = set(c.long[c.long.metric == "whd_cases"].ticker)
    for t, g in hit.groupby("t"):
        if t not in in_dataset:
            continue
        cases = int(g.case_id.nunique())
        trade_only = int(g.t_legal.isna().sum())
        proportion = trade_only / max(len(g), 1)
        if cases < 5 or proportion < 0.5:
            continue
        out.append(Flag("F10_whd_franchise", "review", t, "whd_cases", 2024, float(cases),
                        f"{cases} cases, including {trade_only} matched only by trade name "
                        f"({proportion:.0%}). Franchisees may be independent employers; "
                        "franchise evidence is needed to resolve attribution.",
                        evidence={"cases": cases, "trade_name_only": trade_only,
                                  "legal_names": g.legal_name.value_counts().head(4).to_dict(),
                                  "trade_names": g.trade_nm.value_counts().head(4).to_dict(),
                                  "backwages_usd": float(g.bw_atp_amt.fillna(0).sum())}))
    return out


def r_sbti(c: Context) -> list[Flag]:
    out = []
    val = c.long[c.long.metric == "sbti_validated"].set_index("ticker").value
    rem = c.long[c.long.metric == "sbti_commitment_removed"].set_index("ticker").value
    for t in set(val.index) & set(rem.index):
        if val[t] == 1 and rem[t] == 1:
            out.append(Flag("F12_sbti_target_type", "error", t, "sbti_commitment_removed", CURRENT_YEAR, 1.0,
                            "Validated and removed simultaneously: statuses may belong to different target types "
                            "(near-term target set, net-zero commitment removed). Check the target-type mapping.",
                            evidence={"rule": "Commitment removed: target not submitted within the required period"}))
    # Expired near-term targets have their own
    # status metric and are excluded from the
    # current validated-target flag.
    return out


def r_extremes(c: Context) -> list[Flag]:
    """Flag high robust log-scale z-scores within sectors; retain real extremes for review."""
    out = []
    latest = c.long.sort_values("year").groupby(["ticker", "metric"]).last().reset_index()
    for m in ["scope1_t", "campd_co2_t", "tri_releases_lbs", "echo_penalties_usd",
              "whd_backwages_usd", "osha_deaths"]:
        s = latest[latest.metric == m]
        for sector, g in s.groupby("gics_sector"):
            v = g.value[g.value > 0]
            if len(v) < 6:
                continue
            lv = np.log10(v)
            med, mad = lv.median(), (lv - lv.median()).abs().median() or 1e-9
            z = (lv - med) / (1.4826 * mad)
            for idx in z[z > 3.5].index:
                r = g.loc[idx]
                out.append(Flag("P01_sector_extreme", "review", r.ticker, m, int(r.year), float(r.value),
                                f"Sector extreme (robust z-score {z[idx]:.1f} on log scale). The value may be real.",
                                ranking_relevant=r.ticker in c.ranked and m in CORE_METRICS,
                                evidence={**c.sector_stats(r.ticker, m), "history": c.series(r.ticker, m)}))
    return out


RULES = [r_duplicate_cik, r_zero_emissions, r_campd_program, r_echo_quarters, r_egrid_attribution,
         r_temporal, r_osha_denominator, r_whd, r_sbti, r_extremes]


def run() -> pd.DataFrame:
    c = Context()
    flags: list[Flag] = []
    for rule in RULES:
        got = rule(c)
        print(f"  {rule.__name__:24s} {len(got):4d}")
        flags.extend(got)
    df = pd.DataFrame([asdict(f) for f in flags], columns=list(Flag.__dataclass_fields__))
    df["company"] = df.ticker.map(c.names.company)
    df["gics_sector"] = df.ticker.map(c.names.gics_sector)
    df["evidence"] = df.evidence.map(lambda e: json.dumps(e, ensure_ascii=False, default=str))
    df.insert(0, "flag_id", pd.Series([stable_flag_id(row) for _, row in df.iterrows()], index=df.index, dtype="str"))
    return df


def stable_flag_id(row):
    """Bind review decisions to the finding and its evidence, not its row position."""
    evidence = row.get("evidence", {})
    if isinstance(evidence, str):
        evidence = json.loads(evidence)
    year, value = row.get("year"), row.get("value")
    key = [row["rule"], row["ticker"], row["metric"],
           int(year) if pd.notna(year) else None,
           float(value) if pd.notna(value) else None, evidence]
    return "Q-" + hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()[:16]


def packet(row: pd.Series) -> dict:
    """Build a model-review packet from the available dataset evidence."""
    return {
        "case": f"Rule {row['rule']} ({row['severity']}): {row['message']}",
        "company": {"ticker": row["ticker"], "name": row.get("company"), "sector": row.get("gics_sector")},
        "metric": {"id": row["metric"], "year": row["year"], "value": row["value"]},
        "evidence": json.loads(row["evidence"]),
        "task": "Assess whether the rule is supported and which cause the evidence supports.",
    }
