"""Aggregate eGRID, TRI, OSHA, and ECHO observations by company. Use exact names, subsidiary mappings, and bounded prefixes rather than fuzzy site-name matching. Write intermediate tables consumed by consolidation."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from pipeline.config import OUT, RAW
from pipeline.resolve import OVERRIDES, master_prefix, normalize, override_prefix

from pipeline.universe import load_master

MASTER = load_master()
LOOKUP = {normalize(r.company): r.ticker for r in MASTER.itertuples()}


def to_ticker(name) -> str | None:
    k = normalize(name)
    if not k:
        return None
    if k in LOOKUP:
        return LOOKUP[k]
    if k in OVERRIDES:
        return OVERRIDES[k]
    return override_prefix(k) or master_prefix(k, LOOKUP)


def with_meta(df: pd.DataFrame) -> pd.DataFrame:
    return df.merge(MASTER[["ticker", "company", "gics_sector"]], on="ticker", how="left")


def egrid() -> None:
    """Sum reported plant emissions and generation separately. Derived tonnes-per-MWh ratios belong in analysis rather than the observation table."""
    eg = pd.read_parquet(RAW / "egrid_plant.parquet")
    eg = eg[eg["co2_t"].notna() & (eg["net_generation_mwh"] > 0)].copy()
    eg["ticker"] = eg["operator_name"].map(to_ticker).fillna(eg["utility_name"].map(to_ticker))
    agg = eg.dropna(subset=["ticker"]).groupby(["ticker", "year"], as_index=False).agg(
        plants=("plant_name", "nunique"), co2_t=("co2_t", "sum"),
        mwh=("net_generation_mwh", "sum"),
    )
    with_meta(agg).to_csv(OUT / "egrid_by_company.csv", index=False)
    print(f"eGRID: {len(agg)} companies")


def tri() -> None:
    t = pd.read_parquet(RAW / "epa_tri.parquet")
    t["ticker"] = t["standard_parent_co_name"].map(to_ticker)
    hit = t.dropna(subset=["ticker"]).copy()
    rel = "total_releases" if "total_releases" in hit.columns else "on-site_release_total"
    hit[rel] = pd.to_numeric(hit[rel], errors="coerce")
    hit["carcinogenic"] = hit["carcinogen"].astype(str).str.upper().str.startswith("Y")
    hit["carcinogen_lbs"] = hit[rel].where(hit["carcinogenic"], 0.0)
    agg = hit.groupby("ticker", as_index=False).agg(
        facilities=("frs_id", "nunique"), releases_lbs=(rel, "sum"), carcinogen_lbs=("carcinogen_lbs", "sum"),
    )
    with_meta(agg).to_csv(OUT / "tri_by_company.csv", index=False)
    print(f"TRI: {len(agg)} companies")


def osha() -> None:
    """Sum reported establishment hours and cases separately. A derived injury rate would depend on a denominator that may itself require review."""
    o = pd.read_parquet(RAW / "osha_ita.parquet")
    o["ticker"] = o["company_name"].map(to_ticker)
    hit = o.dropna(subset=["ticker"]).copy()
    agg = hit.groupby("ticker", as_index=False).agg(
        sites=("establishment_name", "nunique"), hours=("total_hours_worked", "sum"),
        dafw=("total_dafw_cases", "sum"), djtr=("total_djtr_cases", "sum"),
        deaths=("total_deaths", "sum"),
    )
    for c in ("hours", "dafw", "djtr", "deaths"):
        agg[c] = pd.to_numeric(agg[c], errors="coerce")
    with_meta(agg).to_csv(OUT / "osha_by_company.csv", index=False)
    print(f"OSHA: {len(agg)} companies")


def echo() -> None:
    e = pd.read_parquet(RAW / "epa_echo.parquet")
    fac = pd.read_parquet(RAW / "epa_facility.parquet")
    fi = fac[["frs_id", "parent_company"]].dropna().drop_duplicates()
    fi["frs_id"] = fi["frs_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    e["rid"] = e["registry_id"].astype("Int64").astype(str)
    j = e.merge(fi, left_on="rid", right_on="frs_id", how="inner")
    # Use the first listed owner in EPA parent-
    # company text for this ECHO attribution.
    first = j["parent_company"].astype(str).str.split(";").str[0].str.replace(
        r"\([^)]*\)", "", regex=True
    )
    j["ticker"] = first.map(to_ticker)
    hit = j.dropna(subset=["ticker"]).copy()
    # Deduplicate facility/company joins; repeated
    # parent-name variants must not multiply the
    # twelve-quarter compliance history.
    before = len(hit)
    hit = hit.drop_duplicates(subset=["rid", "ticker"])
    if before != len(hit):
        print(f"ECHO: {before - len(hit)} duplicate facility rows removed from the join")
    # Read at most twelve history characters. Count
    # V and S as violations; U means unresolved,
    # underscore means no recorded noncompliance,
    # and blanks mean missing data.
    hist = hit["fac_3yr_compliance_history"].fillna("").astype(str).str.slice(0, 12)
    hit["vq"] = hist.str.count(r"[VS]").clip(0, 12)
    hit["sv"] = hit["fac_compliance_status"].astype(str).str.contains("Significant", case=False).astype(int)
    agg = hit.groupby("ticker", as_index=False).agg(
        facilities=("rid", "nunique"), penalties_usd=("fac_total_penalties", "sum"),
        inspections=("fac_inspection_count", "sum"), noncompliance_quarters=("vq", "sum"),
        significant_violations=("sv", "sum"),
    )
    # Retain total quarters and facility counts
    # separately rather than a derived ratio.
    assert (agg["noncompliance_quarters"] <= 12 * agg["facilities"]).all(), "More than 12 quarters per facility"
    with_meta(agg).to_csv(OUT / "echo_by_company.csv", index=False)
    print(f"ECHO: {len(agg)} companies")


if __name__ == "__main__":
    egrid()
    tri()
    osha()
    echo()
