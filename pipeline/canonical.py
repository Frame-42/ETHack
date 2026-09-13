"""Construct company-year observations and a climate analysis panel.

The core metrics are attributed US facility emissions per million USD of revenue, the annual intensity trend, and the annual absolute-emissions trend. Absolute change matters because intensity can case while total emissions rise. Contextual warning signals are calculated separately. These are partial operational measures, not a complete global corporate footprint."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RAW
from .resolve import resolve_owners


def _cagr(values: pd.Series, years: pd.Series) -> float:
    """Estimate annual growth as exp(log-linear OLS slope) - 1. Use at least three positive observations. Using all years avoids dependence on endpoints alone, but OLS is not an outlier-robust estimator."""
    v = pd.to_numeric(values, errors="coerce")
    y = pd.to_numeric(years, errors="coerce")
    mask = np.isfinite(v) & np.isfinite(y) & (v > 0)
    if mask.sum() < 3:
        return np.nan
    slope = np.polyfit(y[mask], np.log(v[mask]), 1)[0]
    return float(np.exp(slope) - 1.0)


def load_raw() -> dict[str, pd.DataFrame]:
    out = {}
    for name in ("sp500_master", "epa_facility", "epa_emission", "sec_revenue", "esg_snapshot"):
        path = RAW / f"{name}.parquet"
        out[name] = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    return out


def build_company_year(raw: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict]:
    """Build attributed company-year observations and return matching diagnostics."""
    master = raw["sp500_master"]
    fac = raw["epa_facility"]
    emi = raw["epa_emission"]
    rev = raw["sec_revenue"]

    facilities = fac.merge(emi, on=["facility_id", "year"], how="inner")
    # A facility record with zero or missing quantity does not establish zero emissions. This pipeline excludes nonpositive quantities from the climate panel; it does not infer that an unmatched or nonreporting facility is emission- free.
    n_zero = int((facilities["scope1_t"].fillna(0) <= 0).sum())
    facilities = facilities[facilities["scope1_t"] > 0]
    total_emissions = facilities["scope1_t"].sum()

    owners = resolve_owners(facilities, master)
    alloc = facilities.merge(owners, on=["facility_id", "year"], how="inner")
    alloc["scope1_attributed_t"] = alloc["scope1_t"] * alloc["share"]

    matched_emissions = alloc["scope1_attributed_t"].sum()

    company_year = (
        alloc.groupby(["ticker", "year"], as_index=False)
        .agg(
            scope1_t=("scope1_attributed_t", "sum"),
            n_facilities=("facility_id", "nunique"),
            match_confidence=("match_confidence", "mean"),
        )
    )

    # Keep company-year totals and facility counts
    # even when the facility base changes. Guard
    # the derived trend separately rather than
    # deleting the underlying reported
    # observations.
    n_incomplete = 0

    # Join revenue through the issuer CIK.
    rev_join = rev.merge(master[["ticker", "cik"]], on="cik", how="inner")
    company_year = company_year.merge(
        rev_join[["ticker", "year", "revenue_musd"]], on=["ticker", "year"], how="left"
    )
    company_year["co2_intensity"] = (
        company_year["scope1_t"] / company_year["revenue_musd"]
    ).replace([np.inf, -np.inf], np.nan)

    company_year = company_year.merge(
        master[["ticker", "company", "gics_sector", "gics_sub_industry"]],
        on="ticker",
        how="left",
    )

    diag = {
        "epa_facility_rows": len(fac),
        "facility_years_without_quantity": n_zero,
        "company_years_incomplete_attribution": n_incomplete,
        "epa_emission_rows": len(emi),
        "facilities_with_emissions": facilities["facility_id"].nunique(),
        "total_epa_emissions_t": float(total_emissions),
        "matched_emissions_t": float(matched_emissions),
        "matched_share": float(matched_emissions / total_emissions) if total_emissions else 0.0,
        "sp500_companies": len(master),
        "companies_matched": company_year["ticker"].nunique(),
        "owner_match_methods": owners["match_method"].value_counts().to_dict()
        if not owners.empty
        else {},
    }
    return company_year, diag


def build_panel(company_year: pd.DataFrame, year_from: int, year_to: int) -> pd.DataFrame:
    """Reduce an observation window to one analysis row per company."""
    win = company_year[
        (company_year["year"] >= year_from) & (company_year["year"] <= year_to)
    ].copy()
    if win.empty:
        return win

    rows: list[dict] = []
    for ticker, g in win.groupby("ticker"):
        g = g.sort_values("year")
        last = g.iloc[-1]
        intensity = g.dropna(subset=["co2_intensity"])
        base = g.iloc[0]["scope1_t"]
        median_t = g["scope1_t"].median()
        # Guard against unstable starting years. A large difference
        # from the period median can reflect a changing facility
        # match, as in PPL's historical one-facility starting year.
        # Withhold the derived ratio outside the configured bounds.
        ratio = float(base / median_t) if median_t and median_t > 0 else np.nan
        base_stable = bool(np.isfinite(ratio) and 0.2 <= ratio <= 2.5)
        # Require at least three years and reject estimated annual changes beyond the configured absolute 100% bound. This is a screening assumption, not a physical law.
        enough_years = int(g["year"].nunique()) >= 3
        def _guard(v: float) -> float:
            return float(v) if (enough_years and base_stable
                                and np.isfinite(v) and abs(v) <= 1.0) else np.nan
        rows.append(
            {
                "ticker": ticker,
                "company": last["company"],
                "gics_sector": last["gics_sector"],
                "gics_sub_industry": last["gics_sub_industry"],
                "years_observed": int(g["year"].nunique()),
                "year_last": int(last["year"]),
                "scope1_t": float(last["scope1_t"]),
                "revenue_musd": float(last["revenue_musd"])
                if pd.notna(last["revenue_musd"])
                else np.nan,
                "co2_intensity": float(last["co2_intensity"])
                if pd.notna(last["co2_intensity"])
                else np.nan,
                "n_facilities": int(last["n_facilities"]),
                "match_confidence": float(g["match_confidence"].mean()),
                "intensity_cagr": _guard(_cagr(intensity["co2_intensity"], intensity["year"])),
                "absolute_cagr": _guard(_cagr(g["scope1_t"], g["year"])),
                "trend_eligible": enough_years and base_stable,
                # A high starting year can make later
                # reductions look unusually large. Keep this
                # contextual signal separate from performance.
                "base_year_ratio": ratio if base_stable else np.nan,
                "base_stable": base_stable,
            }
        )
    panel = pd.DataFrame(rows)

    # Intensity falls while absolute emissions rise.
    panel["intensity_illusion"] = (
        (panel["intensity_cagr"] < 0) & (panel["absolute_cagr"] > 0)
    )
    panel["illusion_gap"] = panel["absolute_cagr"] - panel["intensity_cagr"]
    return panel
