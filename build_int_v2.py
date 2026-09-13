"""
Ebene 2, Version 2: Indikatorpanel mit CO2-Intensitaet und Brennstoffmix.

Aenderungen gegenueber Version 1:
  - log_scope1 (absolutes Niveau) wird durch log_intensity ersetzt.
    Emissionen pro Umsatzdollar ist die Groesse, die der Report fordert.
  - coal_share kommt als Transitionsrisiko-Indikator dazu.
  - SBTi-Ziele gehen NICHT in den Score, sondern auf die Glaubwuerdigkeitsachse.
    Grund: nur 26 der 115 Firmen haben eine auswertbare Zielrate; als
    Score-Indikator waeren 77 Prozent imputiert.
"""
import numpy as np
import pandas as pd
from pathlib import Path

B = Path("build")
LATEST = 2023

INDICATOR_SPEC = {
    "log_intensity": ("LowerIsBetter", "Normal", "log10(Scope-1-Emissionen je Mio. USD Umsatz)"),
    "cagr_long":     ("LowerIsBetter", "Normal", "Jaehrliche log-Veraenderung 2011-2023"),
    "cagr_short":    ("LowerIsBetter", "Normal", "Jaehrliche log-Veraenderung 2019-2023"),
    "momentum":      ("LowerIsBetter", "Normal", "cagr_short minus cagr_long"),
    "coal_share":    ("LowerIsBetter", "Beta",   "Kohleanteil an den fossilen Verbrennungsemissionen"),
    "asset_hhi":     ("LowerIsBetter", "Beta",   "Konzentration der Emissionen auf wenige Anlagen"),
    "volatility":    ("LowerIsBetter", "Normal", "Reststreuung der log-Emissionen"),
}


def build_panel():
    ana = pd.read_parquet(B / "ana_company_emissions.parquet")
    traj = pd.read_parquet(B / "ana_emission_trajectory.parquet").set_index("company_id")
    struct = pd.read_parquet(B / "ana_asset_structure.parquet").set_index("company_id")
    fin = pd.read_parquet(B / "src_financials.parquet").set_index("company_id")
    fuel = pd.read_parquet(B / "src_fuel_mix.parquet").set_index("company_id")
    latest = ana[ana.year == LATEST].set_index("company_id")

    ids = sorted(latest.index.intersection(traj.index).intersection(struct.index))
    rows = []
    for cid in ids:
        a, t = latest.loc[cid], traj.loc[cid]

        # --- CO2-Intensitaet ---------------------------------------------
        if cid in fin.index:
            rev_musd = fin.loc[cid, "revenue_usd"] / 1e6
            val = np.log10(a.scope1_tonnes / rev_musd)
            # Fehlerfortpflanzung: Zaehler und Nenner unabhaengig
            rel = np.sqrt(a.measurement_se_rel ** 2 + fin.loc[cid, "revenue_se_rel"] ** 2)
            se = rel / np.log(10)
            imp = False
        else:
            val, se, imp = np.nan, np.nan, True
        rows.append((cid, "log_intensity", val, se, "Normal", imp))

        rows.append((cid, "cagr_long", t.cagr_long, t.cagr_long_se, "Normal", pd.isna(t.cagr_long)))
        rows.append((cid, "cagr_short", t.cagr_short, t.cagr_short_se, "Normal", pd.isna(t.cagr_short)))
        rows.append((cid, "momentum", t.momentum, t.momentum_se, "Normal", pd.isna(t.momentum)))

        if cid in fuel.index:
            rows.append((cid, "coal_share", float(fuel.loc[cid, "coal_share"]),
                         float(fuel.loc[cid, "coal_share_se"]), "Beta", False))
        else:
            rows.append((cid, "coal_share", np.nan, np.nan, "Beta", True))

        s = struct.loc[cid]
        rows.append((cid, "asset_hhi", s.hhi, s.hhi_se, "Beta", False))
        rows.append((cid, "volatility", t.resid_sd_long,
                     t.resid_sd_long / np.sqrt(2 * max(t.n_years_long - 2, 1)),
                     "Normal", pd.isna(t.resid_sd_long)))

    panel = pd.DataFrame(rows, columns=[
        "company_id", "indicator_code", "raw_value", "value_se", "dist_family", "is_imputed"])
    panel["polarity"] = panel.indicator_code.map(lambda c: INDICATOR_SPEC[c][0])

    # Imputation: Sektormedian, Standardfehler auf die Sektorstreuung aufgeblaeht.
    # So geht eine gefuellte Luecke nie als sicherer Wert in die Simulation.
    comp = pd.read_parquet(B / "src_companies.parquet")[["company_id", "gics_sector"]]
    panel = panel.merge(comp, on="company_id", how="left")
    med = panel.groupby(["gics_sector", "indicator_code"]).raw_value.transform("median")
    glob = panel.groupby("indicator_code").raw_value.transform("median")
    spread = panel.groupby("indicator_code").raw_value.transform("std")
    fill = med.fillna(glob)
    panel.loc[panel.is_imputed, "raw_value"] = fill[panel.is_imputed]
    panel.loc[panel.is_imputed, "value_se"] = spread[panel.is_imputed]

    med_se = panel.groupby("indicator_code").value_se.transform("median")
    panel["value_se"] = panel.value_se.fillna(med_se).fillna(0.0).clip(lower=1e-6)

    msc = latest.match_score_min
    panel["match_score"] = panel.company_id.map(msc)
    panel["trust_tier"] = np.select(
        [panel.is_imputed, panel.match_score >= 0.999, panel.match_score >= 0.93],
        ["Low", "High", "Medium"], default="Low")
    panel = panel.drop(columns=["gics_sector"])

    panel.to_parquet(B / "int_indicator_panel.parquet", index=False)
    print(f"int_indicator_panel v2: {len(panel):,} Zeilen "
          f"({panel.company_id.nunique()} Firmen x {panel.indicator_code.nunique()} Indikatoren)")
    print(panel.groupby("indicator_code").agg(
        median=("raw_value", "median"), median_se=("value_se", "median"),
        imputiert=("is_imputed", "sum")).round(4).to_string())
    return panel


def build_credibility_inputs():
    """SBTi-Ziele und Zielluecke fuer die Glaubwuerdigkeitsachse."""
    traj = pd.read_parquet(B / "ana_emission_trajectory.parquet").set_index("company_id")
    sbti = pd.read_parquet(B / "src_sbti_target.parquet").set_index("company_id")
    panel_ids = pd.read_parquet(B / "int_indicator_panel.parquet").company_id.unique()

    rows = []
    for cid in sorted(panel_ids):
        has = cid in sbti.index
        req = sbti.loc[cid, "required_cagr"] if has else np.nan
        val = bool(sbti.loc[cid, "sbti_validated"]) if has else False
        realized = traj.loc[cid, "cagr_long"] if cid in traj.index else np.nan
        gap = (realized - req) if (pd.notna(req) and pd.notna(realized)) else np.nan
        rows.append({
            "company_id": cid, "sbti_listed": has, "sbti_validated": val,
            "required_cagr": req, "realized_cagr": realized, "pledge_gap": gap,
            "net_zero_year": sbti.loc[cid, "net_zero_year"] if has else np.nan,
        })
    out = pd.DataFrame(rows)
    out.to_parquet(B / "ana_pledge_gap.parquet", index=False)
    g = out.pledge_gap.dropna()
    print(f"ana_pledge_gap: {out.sbti_listed.sum()} Firmen bei SBTi gelistet, "
          f"{out.sbti_validated.sum()} validiert, {len(g)} mit Zielluecke; "
          f"davon {(g > 0).sum()} hinter Plan, {(g <= 0).sum()} vor Plan")
    return out


if __name__ == "__main__":
    build_panel()
    build_credibility_inputs()
