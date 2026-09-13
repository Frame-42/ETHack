"""Combine observations in long format: one row per issuer, year, and metric. Attach source metadata, units, and value type to every row. Derived intensities, trends, and ranks remain separate from reported figures and company-level aggregates. Source links identify the source family and do not always identify an individual filing or facility record."""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from .config import OUT, RAW

BUILD_DATE = date.today().isoformat()

# Source registry. Each metric refers to a
# source identifier.
SOURCES = {'epa_ghgrp': {'name': 'EPA Greenhouse Gas Reporting Program',
               'url': 'https://data.epa.gov/efservice/PUB_DIM_FACILITY/',
               'access': 'Open, no account',
               'license': 'US government data',
               'coverage': 'US reporting facilities; study years 2018-2023',
               'measurement': 'Reported, including calculations from fuel use',
               'caveat': 'Partial US facility footprint. Keep direct emitters separate from suppliers and '
                         'injection; 2023 is the configured study cutoff.'},
 'epa_campd': {'name': 'EPA Clean Air Markets Program Data',
               'url': 'https://api.epa.gov/easey/emissions-mgmt/emissions/apportioned/annual',
               'access': 'Free API key',
               'license': 'US government data',
               'coverage': 'Participating US power facilities; 2019 onward',
               'measurement': 'Power-sector emissions reports, including continuous monitoring',
               'caveat': 'Power-sector coverage only. Current-year observations may be partial; the '
                         'owner-name allocation does not apply equity shares.'},
 'egrid': {'name': 'EPA eGRID',
           'url': 'https://www.epa.gov/egrid/download-data',
           'access': 'Open',
           'license': 'US government data',
           'coverage': 'US power plants; retained snapshot labeled 2023',
           'measurement': 'Reported plant emissions and generation',
           'caveat': 'Only matched plants are included. Operator/utility attribution differs from equity '
                     'ownership; do not add overlapping GHGRP and CAMPD totals.'},
 'sec_xbrl': {'name': 'SEC EDGAR XBRL frames',
              'url': 'https://data.sec.gov/api/xbrl/frames/',
              'access': 'Open; identifying User-Agent required',
              'license': 'Public filings',
              'coverage': 'Configured calendar frames 2016-2025',
              'measurement': 'Mandatory financial filings',
              'caveat': 'Revenue tags and fiscal periods differ. Revenue is global while the emissions '
                        'numerator is a partial US footprint.'},
 'sbti': {'name': 'Science Based Targets initiative',
          'url': 'https://sciencebasedtargets.org/download/excel',
          'access': 'Published Excel download',
          'license': 'Attribution required; verify source terms for reuse',
          'coverage': 'Participating organizations; snapshot statuses',
          'measurement': 'Company commitments and externally validated targets',
          'caveat': 'A target is not an achieved reduction. Statuses are evaluated against the build year '
                    'and differ by target type.'},
 'epa_tri': {'name': 'EPA Toxics Release Inventory',
             'url': 'https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/2023_US/csv/',
             'access': 'Open',
             'license': 'US government data',
             'coverage': 'US reporting facilities; configured year 2023',
             'measurement': 'Reported releases',
             'caveat': 'Mass totals do not account for toxicity or exposure. Reporting thresholds and '
                       'parent-name matching limit coverage.'},
 'osha_ita': {'name': 'OSHA Injury Tracking Application, Form 300A',
              'url': 'https://www.osha.gov/itadata',
              'access': 'Open; HTTP headers may be required',
              'license': 'US government data',
              'coverage': 'US reporting establishments; configured 2023-2025 releases',
              'measurement': 'Mandatory employer reports',
              'caveat': 'Hours and cases can contain reporting errors. Retain denominators and review flags; '
                        'industry exposure differs.'},
 'epa_echo': {'name': 'EPA ECHO Enforcement and Compliance History',
              'url': 'https://echo.epa.gov/files/echodownloads/echo_exporter.zip',
              'access': 'Open',
              'license': 'US government data',
              'coverage': 'Matched US facilities; rolling three-year compliance history',
              'measurement': 'Official enforcement and compliance records',
              'caveat': 'Linked through GHGRP FRS IDs. Detection and enforcement differ; absence of a '
                        'matched record does not establish compliance.'},
 'eia_923': {'name': 'EIA Form 923, via PUDL and API',
             'url': 'https://www.eia.gov/electricity/data/eia923/',
             'access': 'Open PUDL mirror; API key for EIA',
             'license': 'US government data',
             'coverage': 'US power plants; configured 2021-2025 window',
             'measurement': 'Reported fuel consumption and generation',
             'caveat': 'Useful for physical denominators and cross-checks. Boundaries and reporting periods '
                       'must align.'},
 'esg_snapshot': {'name': 'Historical Sustainalytics ESG risk ratings via Yahoo mirror',
                  'url': 'https://raw.githubusercontent.com/sburstein/ESG-Stock-Data/main/sp_esg_stock_data.csv',
                  'access': 'Public mirror',
                  'license': 'Unclear; historical comparison only',
                  'coverage': 'Historical 2021 snapshot',
                  'measurement': 'Third-party assessment',
                  'caveat': 'Never used in the climate score. Not contemporaneous with 2023 results; its '
                            'presence does not establish redistribution rights.'},
 'sp500_master': {'name': 'S&P 500 constituents',
                  'url': 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
                  'access': 'Open',
                  'license': 'CC BY-SA',
                  'coverage': '503 securities / 500 CIKs in the retained snapshot',
                  'measurement': 'Index membership and company metadata',
                  'caveat': 'Membership is a snapshot, not a historical index universe. Multiple share '
                            'classes share a CIK.'},
 'pudl': {'name': 'PUDL, Catalyst Cooperative',
          'url': 'https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/stable/',
          'access': 'Open',
          'license': 'Public domain',
          'coverage': 'Processed EIA, EPA, and SEC data',
          'measurement': 'Processed official data',
          'caveat': 'An additional processing layer can introduce errors. Pin releases for reproducibility.'},
 'pudl_sec_ex21': {'name': 'SEC 10-K Exhibit 21 ownership, via PUDL',
                   'url': 'https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/stable/core_sec10k__quarterly_exhibit_21_company_ownership.parquet',
                   'access': 'Open',
                   'license': 'Public domain',
                   'coverage': 'Subsidiary records in the configured PUDL release',
                   'measurement': 'Subsidiary disclosures in mandatory filings',
                   'caveat': 'Names may be abbreviated and ownership percentages incomplete. The active '
                             'resolver uses curated mappings; this catalog entry is not proof of a complete '
                             'historical crosswalk.'},
 'sec_dera': {'name': 'SEC companyfacts FY2024, prepared by Janis',
              'url': 'https://data.sec.gov/api/xbrl/companyfacts/',
              'access': 'Open; identifying User-Agent required',
              'license': 'Public filings',
              'coverage': 'Team FY2024 financial snapshot',
              'measurement': 'Mandatory financial filings',
              'caveat': 'Debt tags vary; missing research and development expense does not mean zero. '
                        'Detailed filing references are retained in the team input.'},
 'dol_whd': {'name': 'DOL Wage and Hour Division enforcement',
             'url': 'https://data.dol.gov/data-catalog/WHD/enforcement/WHD_enforcement.zip',
             'access': 'Open',
             'license': 'US government data',
             'coverage': 'Cases with findings ending in 2022-2024',
             'measurement': 'Official enforcement findings',
             'caveat': 'No CIK. Legal/trade-name attribution can include independent franchises. No match is '
                       'missing evidence, not zero violations.'},
 'sec_sd': {'name': 'SEC Form SD conflict-minerals filings, prepared by Janis',
            'url': 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=SD',
            'access': 'Open',
            'license': 'Public filings',
            'coverage': 'Team filing-status snapshot; see original filing dates',
            'measurement': 'Mandatory filing status',
            'caveat': 'Filing alone says nothing about responsible sourcing. The historical 2025 output '
                      'label covers an input window containing later filing dates.'},
 'wba': {'name': 'World Benchmarking Alliance company profiles, prepared by Janis',
         'url': 'https://www.worldbenchmarkingalliance.org/company-scoreboard',
         'access': 'Open public profiles',
         'license': 'CC BY 4.0; credit World Benchmarking Alliance',
         'coverage': 'Team 2026 assessment snapshot',
         'measurement': 'Assessment of disclosed company information',
         'caveat': 'Disclosure-dependent and not independent across benchmarks. Near-constant fields provide '
                   'little ranking information.'}}

# Metric registry: label, unit, direction,
# axis, source, and value type. Direction -1
# means lower is better; +1 means higher; 0 is
# contextual. Reported values and aggregated
# source observations remain distinct from
# derived ratios, trends, and rankings. Status
# flags are encoded transformations of source
# categories.
METRICS = {'scope1_t': ('Attributed US facility greenhouse-gas emissions',
              't CO2e',
              -1,
              'A',
              'epa_ghgrp',
              'aggregated'),
 'n_facilities': ('Matched GHGRP facilities', 'count', 0, 'meta', 'epa_ghgrp', 'aggregated'),
 'campd_co2_t': ('Attributed power-sector CO2 emissions', 't CO2', -1, 'A', 'epa_campd', 'aggregated'),
 'campd_plants': ('Matched CAMPD plants', 'count', 0, 'meta', 'epa_campd', 'aggregated'),
 'egrid_co2_t': ('Matched eGRID plant CO2 emissions', 't CO2', -1, 'A', 'egrid', 'aggregated'),
 'egrid_mwh': ('Net electricity generation', 'MWh', 0, 'meta', 'egrid', 'aggregated'),
 'egrid_plants': ('Matched eGRID plants', 'count', 0, 'meta', 'egrid', 'aggregated'),
 'tri_releases_lbs': ('Reported toxic releases', 'lbs', -1, 'A', 'epa_tri', 'aggregated'),
 'tri_carcinogen_lbs': ('Releases classified as carcinogenic', 'lbs', -1, 'A', 'epa_tri', 'aggregated'),
 'tri_facilities': ('Matched TRI facilities', 'count', 0, 'meta', 'epa_tri', 'aggregated'),
 'osha_dafw_cases': ('Cases with days away from work', 'count', -1, 'S', 'osha_ita', 'aggregated'),
 'osha_djtr_cases': ('Cases with job transfer or restriction', 'count', -1, 'S', 'osha_ita', 'aggregated'),
 'osha_hours': ('Reported working hours', 'hours', 0, 'meta', 'osha_ita', 'aggregated'),
 'osha_deaths': ('Reported workplace deaths', 'count', -1, 'S', 'osha_ita', 'aggregated'),
 'osha_sites': ('Matched reporting establishments', 'count', 0, 'meta', 'osha_ita', 'aggregated'),
 'echo_penalties_usd': ('Environmental penalties', 'USD', -1, 'G', 'epa_echo', 'aggregated'),
 'echo_nc_quarters': ('Noncompliance facility-quarters', 'quarters', -1, 'G', 'epa_echo', 'aggregated'),
 'echo_facilities': ('Matched ECHO facilities', 'count', 0, 'meta', 'epa_echo', 'aggregated'),
 'echo_significant': ('Facilities with significant violations', 'count', -1, 'G', 'epa_echo', 'aggregated'),
 'whd_cases': ('Wage enforcement cases, 2022-2024', 'count', -1, 'S', 'dol_whd', 'aggregated'),
 'whd_backwages_usd': ('Back wages assessed', 'USD', -1, 'S', 'dol_whd', 'aggregated'),
 'whd_employees': ('Affected employees', 'count', -1, 'S', 'dol_whd', 'aggregated'),
 'whd_violations': ('Recorded wage-law violations', 'count', -1, 'S', 'dol_whd', 'aggregated'),
 'whd_penalties_usd': ('Wage-law penalties', 'USD', -1, 'S', 'dol_whd', 'aggregated'),
 'sbti_validated': ('Set and unexpired near-term target', 'yes/no', 1, 'B', 'sbti', 'reported'),
 'sbti_near_term_year': ('Near-term target year', 'year', 0, 'B', 'sbti', 'reported'),
 'sbti_net_zero_year': ('Net-zero target year', 'year', 0, 'B', 'sbti', 'reported'),
 'sbti_commitment_removed': ('Near-term commitment removed', 'yes/no', -1, 'B', 'sbti', 'reported'),
 'sbti_net_zero_removed': ('Net-zero commitment removed', 'yes/no', -1, 'B', 'sbti', 'reported'),
 'sbti_near_term_expired': ('Near-term target year elapsed', 'yes/no', -1, 'B', 'sbti', 'reported'),
 'revenue_musd': ('Revenue', 'million USD', 0, 'meta', 'sec_xbrl', 'reported'),
 'net_income_usd': ('Net income', 'USD', 0, 'meta', 'sec_dera', 'reported'),
 'total_assets_usd': ('Total assets', 'USD', 0, 'meta', 'sec_dera', 'reported'),
 'total_debt_usd': ('Financial debt', 'USD', 0, 'meta', 'sec_dera', 'reported'),
 'operating_cf_usd': ('Operating cash flow', 'USD', 0, 'meta', 'sec_dera', 'reported'),
 'capex_usd': ('Capital expenditure', 'USD', 0, 'meta', 'sec_dera', 'reported'),
 'rnd_usd': ('Research and development expense', 'USD', 0, 'meta', 'sec_dera', 'reported'),
 'sd_conflict_minerals_filer': ('Conflict-minerals filing status, Form SD',
                                'yes/no',
                                0,
                                'meta',
                                'sec_sd',
                                'reported'),
 'wba_tpq': ('WBA transition plan quality', '0-5', 1, 'B', 'wba', 'reported'),
 'wba_ctt': ('WBA contribution to transition', '0-2', 1, 'B', 'wba', 'reported'),
 'wba_social': ('WBA Social Benchmark', '0-100', 1, 'S', 'wba', 'reported'),
 'wba_nature': ('WBA Nature Benchmark', '0-100', 1, 'B', 'wba', 'reported'),
 'wba_just_transition': ('WBA Just Transition', '0-100', 1, 'S', 'wba', 'reported'),
 'esg_risk_total': ('Historical commercial ESG risk', 'points', -1, 'comparison', 'esg_snapshot', 'reported')}


def _read(path, **kw) -> pd.DataFrame:
    return pd.read_csv(path, **kw) if path.exists() else pd.DataFrame()


def _add(rows: list, df: pd.DataFrame, mapping: dict[str, str], year=None) -> None:
    """Append finite numeric observations in long format."""
    if df.empty:
        return
    year_col = "year" if "year" in df.columns else None
    for col, metric in mapping.items():
        if col not in df.columns:
            continue
        sub = df[["ticker", col] + ([year_col] if year_col else [])].dropna(subset=[col])
        for rec in sub.itertuples(index=False):
            val = getattr(rec, col if col.isidentifier() else "_1")
            if isinstance(val, (np.bool_, bool)):
                val = float(bool(val))
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(val):
                continue
            rows.append(
                {
                    "ticker": rec.ticker,
                    "year": int(getattr(rec, year_col)) if year_col else year,
                    "metric": metric,
                    "value": val,
                }
            )


def dedupe_cik(master: pd.DataFrame) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Map share classes with a common CIK to one primary ticker and aliases. Use the longest symbol, then alphabetical order, as a deterministic naming convention; this is not an ownership or voting-rights rule."""
    primary: dict[str, str] = {}
    alias: dict[str, list[str]] = {}
    for cik, g in master.dropna(subset=["cik"]).groupby("cik"):
        if len(g) < 2:
            continue
        tickers = sorted(g["ticker"], key=lambda t: (-len(t), t))
        primary_ticker, rest = tickers[0], tickers[1:]
        alias[primary_ticker] = rest
        for t in rest:
            primary[t] = primary_ticker
    return primary, alias


def build() -> pd.DataFrame:
    master = pd.read_parquet(RAW / "sp500_master.parquet")
    rows: list[dict] = []

    # The climate panel and ranking bands are derived analysis. Do not insert calculated intensities, trends, or simulated scores into the observation table.
    cy = _read(OUT / "company_year.csv")
    if not cy.empty:
        _add(rows, cy, {"scope1_t": "scope1_t", "revenue_musd": "revenue_musd",
                        "n_facilities": "n_facilities"})

    egrid = _read(OUT / "egrid_by_company.csv")
    if not egrid.empty:
        # Retain the source numerator and denominator separately.
        _add(rows, egrid,
             {"co2_t": "egrid_co2_t", "mwh": "egrid_mwh", "plants": "egrid_plants"})

    tri = _read(OUT / "tri_by_company.csv")
    if not tri.empty:
        _add(rows, tri.assign(year=2023),
             {"releases_lbs": "tri_releases_lbs", "carcinogen_lbs": "tri_carcinogen_lbs",
              "facilities": "tri_facilities"})

    osha = _read(OUT / "osha_by_company.csv")
    if not osha.empty:
        _add(rows, osha.assign(year=2025), {
            "dafw": "osha_dafw_cases", "djtr": "osha_djtr_cases", "hours": "osha_hours",
            "deaths": "osha_deaths", "sites": "osha_sites",
        })

    echo = _read(OUT / "echo_by_company.csv")
    if not echo.empty:
        # Accept the two historical ECHO aggregate
        # column variants.
        _add(rows, echo.assign(year=2025), {
            "penalties": "echo_penalties_usd",
            "penalties_usd": "echo_penalties_usd",
            "noncompliance_quarters": "echo_nc_quarters",
            "facilities": "echo_facilities",
            "sv": "echo_significant",
            "significant_violations": "echo_significant",
        })

    # Team cross-section prepared by Janis: SEC financial figures, wage cases, and Form SD.
    hv_path = RAW / "team_hard_variables.parquet"
    if hv_path.exists():
        hv = pd.read_parquet(hv_path)
        _add(rows, hv.assign(year=2024), {
            "net_usd_fy24": "net_income_usd", "assets_usd_fy24": "total_assets_usd",
            "debt_usd_fy24": "total_debt_usd", "ocf_usd_fy24": "operating_cf_usd",
            "capex_usd_fy24": "capex_usd", "rnd_usd_fy24": "rnd_usd",
        })
        sd = hv.assign(year=2025, sd_flag=(hv["sd_filer_22_25"] == "Yes").astype(float))
        _add(rows, sd, {"sd_flag": "sd_conflict_minerals_filer"})

    # Department of Labor wage enforcement cases.
    whd = _whd_by_company(master)
    if not whd.empty:
        _add(rows, whd.assign(year=2024), {
            "cases": "whd_cases", "violations": "whd_violations",
            "backwages_usd": "whd_backwages_usd", "employees": "whd_employees",
            "penalties_usd": "whd_penalties_usd",
        })

    # Team WBA assessments (CC BY 4.0).
    wba_path = RAW / "team_wba.parquet"
    if wba_path.exists():
        wba = pd.read_parquet(wba_path).assign(year=2026)
        _add(rows, wba, {"tpq": "wba_tpq", "ctt": "wba_ctt", "social": "wba_social",
                         "nature": "wba_nature", "just_transition": "wba_just_transition"})


    long = pd.DataFrame(rows)

    # CAMPD observations attributed through ownerOperator.
    campd = _campd_by_company(master)
    if not campd.empty:
        long = pd.concat([long, campd], ignore_index=True)

    # SBTi.
    sbti = _sbti_by_company(master)
    if not sbti.empty:
        long = pd.concat([long, sbti], ignore_index=True)

    # Historical commercial comparison benchmark.
    esg_path = RAW / "esg_snapshot.parquet"
    if esg_path.exists():
        esg = pd.read_parquet(esg_path)
        e = pd.DataFrame({
            "ticker": esg["ticker"], "year": 2021, "metric": "esg_risk_total",
            "value": pd.to_numeric(esg["esg_risk_total"], errors="coerce"),
        }).dropna()
        long = pd.concat([long, e], ignore_index=True)

    # Combine share classes sharing a CIK.
    primary, _ = dedupe_cik(master)
    if primary:
        long["ticker"] = long["ticker"].replace(primary)

    # Attach source provenance and company metadata.
    meta = pd.DataFrame(
        [(k, *v) for k, v in METRICS.items()],
        columns=["metric", "metric_label", "unit", "direction", "axis", "source_id", "value_type"],
    )
    long = long.merge(meta, on="metric", how="left")
    long = long.merge(
        master[["ticker", "company", "gics_sector", "gics_sub_industry"]],
        on="ticker", how="left",
    )
    src = pd.DataFrame(
        [{"source_id": k, "source_name": v["name"], "source_url": v["url"],
          "source_access": v["access"], "source_license": v["license"]}
         for k, v in SOURCES.items()]
    )
    long = long.merge(src, on="source_id", how="left")
    long["assembled_at"] = BUILD_DATE
    # Mark current-year continuously reported observations as partial. A partial-year quantity must not be interpreted as a completed annual total.
    current_year = date.today().year
    long["partial_year"] = (long["year"] >= current_year) & long["source_id"].isin(
        {"epa_campd"}
    )
    long = long.dropna(subset=["company", "source_id"])
    long = long.drop_duplicates(["ticker", "year", "metric"])
    return long.sort_values(["ticker", "metric", "year"]).reset_index(drop=True)


# CO2-reporting program filter: ARP, RGGI, and NSPS Subpart TTTT, following the configured CAMD data guide.
CO2_PROGRAMS = ("ARP", "RGGI", "NSPS4T")


def _campd_by_company(master: pd.DataFrame) -> pd.DataFrame:
    """Attribute CAMPD observations through owner names. This implementation does not allocate fractional ownership shares."""
    from .resolve import OVERRIDES, normalize, override_prefix, owner_valid
    from .sources.epa_campd import split_owner_operator

    ep, fp = RAW / "campd_emission.parquet", RAW / "campd_facility.parquet"
    if not (ep.exists() and fp.exists()):
        return pd.DataFrame()
    emi, fac = pd.read_parquet(ep), pd.read_parquet(fp)
    lookup = {normalize(r.company): r.ticker for r in master.itertuples()}

    def to_ticker(name: str):
        k = normalize(name)
        if k in lookup:
            return lookup[k]
        if k in OVERRIDES:
            return OVERRIDES[k]
        return override_prefix(k)

    # A zero in a NOx-only reporting program is not
    # evidence of zero CO2. Keep CO2 observations
    # only for configured CO2-reporting programs
    # and treat other quantities as unavailable.
    programs = fac["programCodeInfo"].astype(str).str.upper()
    fac = fac[programs.str.contains("|".join(CO2_PROGRAMS), regex=True, na=False)]
    if fac.empty:
        return pd.DataFrame()
    own = fac[["facilityId", "year", "ownerOperator"]].drop_duplicates()
    recs = []
    for fid, yr, raw in own.itertuples(index=False):
        for name, role in split_owner_operator(raw):
            if role != "owner":
                continue
            t = to_ticker(name)
            if t and owner_valid(normalize(name), t, yr):
                recs.append({"facilityId": fid, "year": yr, "ticker": t})
    if not recs:
        return pd.DataFrame()
    link = pd.DataFrame(recs).drop_duplicates()
    j = emi.merge(link, on=["facilityId", "year"], how="inner")
    j = j.drop_duplicates(subset=["facilityId", "year", "ticker"])
    agg = j.groupby(["ticker", "year"], as_index=False).agg(
        campd_co2_t=("co2_t", "sum"), campd_plants=("facilityId", "nunique")
    )
    # Treat nonpositive emissions after program
    # filtering as missing.
    agg.loc[agg["campd_co2_t"] <= 0, "campd_co2_t"] = np.nan
    out = agg.melt(id_vars=["ticker", "year"], var_name="metric", value_name="value")
    return out.dropna(subset=["value"])


def _whd_by_company(master: pd.DataFrame) -> pd.DataFrame:
    """Match wage cases using legal names, trade names, and conservative parent/subsidiary prefixes. Avoid fuzzy substring matches such as APDC Cleaning Services to Air Products. Trade-name matches can still include independent franchise employers."""
    from .resolve import OVERRIDES, master_prefix, normalize, override_prefix

    p = RAW / "dol_whd.parquet"
    if not p.exists():
        return pd.DataFrame()
    w = pd.read_parquet(p)
    lookup = {normalize(r.company): r.ticker for r in master.itertuples()}

    def to_ticker(name):
        k = normalize(name)
        if not k:
            return None
        return lookup.get(k) or override_prefix(k) or master_prefix(k, lookup)

    w["ticker"] = w["legal_name"].map(to_ticker).fillna(w["trade_nm"].map(to_ticker))
    hit = w.dropna(subset=["ticker"])
    if hit.empty:
        return pd.DataFrame()
    agg = hit.groupby("ticker", as_index=False).agg(
        cases=("case_id", "nunique"),
        violations=("case_violtn_cnt", "sum"),
        backwages_usd=("bw_atp_amt", "sum"),
        employees=("ee_atp_cnt", "sum"),
        penalties_usd=("cmp_assd", "sum"),
    )
    return agg


def _sbti_by_company(master: pd.DataFrame) -> pd.DataFrame:
    from .resolve import normalize

    p = RAW / "sbti_targets.parquet"
    if not p.exists():
        return pd.DataFrame()
    s = pd.read_parquet(p)
    s["key"] = s["company_name"].map(normalize)
    m = master.assign(key=master["company"].map(normalize)).merge(
        s.drop_duplicates("key"), on="key", how="inner"
    )
    # Keep near-term and net-zero statuses
    # separate. A validated near-term target and a
    # withdrawn net-zero commitment can coexist and
    # must not be collapsed into a contradiction.
    near_status = m["near_term_status"].astype(str)
    net_zero = m["net_zero_status"].astype(str)
    target_set = near_status.str.contains("Targets set", case=False)
    near_year = pd.to_numeric(m["near_term_year"], errors="coerce")
    expired = target_set & near_year.notna() & (near_year < date.today().year)
    out = pd.DataFrame({
        "ticker": m["ticker"],
        # The current-status flag requires a set, unexpired near-term target.
        "sbti_validated": (target_set & ~expired).astype(float),
        "sbti_near_term_expired": expired.astype(float),
        "sbti_commitment_removed": near_status.str.contains("removed", case=False).astype(float),
        "sbti_net_zero_removed": net_zero.str.contains("removed", case=False).astype(float),
        "sbti_near_term_year": near_year,
        "sbti_net_zero_year": pd.to_numeric(m["net_zero_year"], errors="coerce")
        .where(net_zero.str.contains("Targets set|Committed", case=False)),
    })
    long = out.melt(id_vars="ticker", var_name="metric", value_name="value").dropna()
    long["year"] = 2026
    return long


def write_all() -> dict:
    long = build()
    # Attach existing review annotations without
    # changing numerical observations.
    from .flag_apply import apply as apply_flags
    long = apply_flags(long)
    long.to_parquet(OUT / "dataset_long.parquet", index=False)
    long.to_csv(OUT / "dataset_long.csv", index=False)

    (OUT / "sources.json").write_text(
        json.dumps(
            {k: {**v, "assembled_at": BUILD_DATE} for k, v in SOURCES.items()},
            indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (OUT / "metrics.json").write_text(
        json.dumps(
            {k: {"label": v[0], "unit": v[1], "direction": v[2], "axis": v[3],
                 "source_id": v[4], "value_type": v[5]} for k, v in METRICS.items()},
            indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "rows": len(long),
        "companies": int(long["ticker"].nunique()),
        "metrics": int(long["metric"].nunique()),
        "sources": int(long["source_id"].nunique()),
        "years": [int(long["year"].min()), int(long["year"].max())],
    }
