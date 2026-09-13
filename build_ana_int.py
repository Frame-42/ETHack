"""
Ebene 2 (ana_* / int_*): Ableitung und Unsicherheits-Annotation,
nach UML final_2_ableitung.

Erzeugt:
  ana_company_emissions.parquet    Firma x Jahr, Scope 1 + measurement_se
  ana_emission_trajectory.parquet  OLS-Steigung auf log(Emissionen) + slope_se
  ana_asset_structure.parquet      Anlagenstruktur (Konzentration, Streuung)
  int_peer_group.parquet           Vergleichsgruppen je peer_level
  int_indicator_panel.parquet      Langformat: Wert + Standardfehler je Zelle
"""
import numpy as np
import pandas as pd
from pathlib import Path

B = Path("build")

# Parameter der Messfehler-Heuristik.
# Grundrauschen der EPA-Meldung + Aufschlag fuer unsichere Namenszuordnung
# + Aufschlag, wenn nur wenige Anlagen die Firmensumme tragen.
SE_BASE = 0.05          # 5% Grundunsicherheit auf Anlagensummen
SE_MATCH_COEF = 0.50    # voller Aufschlag bei match_score = 0
SE_NFAC_COEF = 0.10     # Aufschlag ~ 1/sqrt(Anlagenzahl)

TREND_SHORT = (2019, 2023)
TREND_LONG = (2011, 2023)
LATEST = 2023


# ----------------------------------------------------------------------
def ols_log_slope(years, values):
    """OLS-Steigung auf log(Emissionen) plus Standardfehler der Steigung.

    Liefert die jaehrliche relative Veraenderungsrate. Der Standardfehler
    ist die eigentliche Ausbeute: er ist die ehrliche Aussage darueber,
    wie gut der Trend durch die Datenpunkte gestuetzt wird.
    """
    m = values > 0
    x, y = np.asarray(years, float)[m], np.log(np.asarray(values, float)[m])
    n = len(x)
    if n < 3:
        return np.nan, np.nan, np.nan, n
    xm, ym = x.mean(), y.mean()
    sxx = ((x - xm) ** 2).sum()
    if sxx == 0:
        return np.nan, np.nan, np.nan, n
    slope = ((x - xm) * (y - ym)).sum() / sxx
    resid = y - (ym + slope * (x - xm))
    dof = n - 2
    s2 = (resid ** 2).sum() / dof if dof > 0 else np.nan
    slope_se = np.sqrt(s2 / sxx) if dof > 0 else np.nan
    ss_tot = ((y - ym) ** 2).sum()
    r2 = 1 - (resid ** 2).sum() / ss_tot if ss_tot > 0 else np.nan
    return slope, slope_se, np.sqrt(s2) if dof > 0 else np.nan, n


# ----------------------------------------------------------------------
def build_ana_company_emissions():
    fac = pd.read_parquet(B / "src_epa_facility.parquet")
    link = pd.read_parquet(B / "src_parent_link.parquet")
    er = pd.read_parquet(B / "src_entity_resolution.parquet")
    er = er.dropna(subset=["company_id"])
    er["company_id"] = er["company_id"].astype(int)

    m = link.merge(fac[["facility_id", "reporting_year", "co2e_tonnes"]],
                   on=["facility_id", "reporting_year"], how="inner")
    m = m.merge(er[["name_raw", "company_id", "match_score"]],
                left_on="parent_name_raw", right_on="name_raw", how="inner")

    # Anteilige Zurechnung nach Eigentumsanteil
    m["attributed_tonnes"] = m["co2e_tonnes"] * m["parent_share_pct"] / 100.0

    g = m.groupby(["company_id", "reporting_year"])
    ana = g.agg(
        scope1_tonnes=("attributed_tonnes", "sum"),
        asset_count=("facility_id", "nunique"),
        match_score_min=("match_score", "min"),
        match_score_wmean=("match_score", "mean"),
    ).reset_index().rename(columns={"reporting_year": "year"})

    # Messfehler: relativer Standardfehler auf scope1_tonnes
    rel_se = (SE_BASE
              + SE_MATCH_COEF * (1.0 - ana["match_score_min"])
              + SE_NFAC_COEF / np.sqrt(ana["asset_count"]))
    ana["measurement_se_rel"] = rel_se.clip(0.03, 0.60)
    ana["measurement_se"] = ana["measurement_se_rel"] * ana["scope1_tonnes"]

    ana["source_mix"] = "EPAonly"
    ana["coverage_flag"] = np.where(ana["match_score_min"] >= 0.999, "Full", "Partial")

    ana.to_parquet(B / "ana_company_emissions.parquet", index=False)
    n23 = (ana.year == LATEST).sum()
    print(f"ana_company_emissions: {len(ana):,} Firma-Jahr-Zeilen, "
          f"{ana.company_id.nunique()} Firmen, {n23} davon mit {LATEST}er Wert")
    return ana


# ----------------------------------------------------------------------
def build_ana_trajectory(ana):
    rows = []
    for cid, grp in ana.groupby("company_id"):
        grp = grp.sort_values("year")
        rec = {"company_id": cid}
        for tag, (y0, y1) in [("short", TREND_SHORT), ("long", TREND_LONG)]:
            w = grp[(grp.year >= y0) & (grp.year <= y1)]
            s, se, resid_sd, n = ols_log_slope(w.year.values, w.scope1_tonnes.values)
            rec[f"cagr_{tag}"] = s
            rec[f"cagr_{tag}_se"] = se
            rec[f"resid_sd_{tag}"] = resid_sd
            rec[f"n_years_{tag}"] = n
        rows.append(rec)

    traj = pd.DataFrame(rows)
    # Momentum: beschleunigt die Firma ihre Reduktion?
    traj["momentum"] = traj["cagr_short"] - traj["cagr_long"]
    traj["momentum_se"] = np.sqrt(traj["cagr_short_se"] ** 2
                                  + traj["cagr_long_se"] ** 2)
    traj.to_parquet(B / "ana_emission_trajectory.parquet", index=False)
    ok = traj["cagr_long"].notna().sum()
    print(f"ana_emission_trajectory: {len(traj)} Firmen, {ok} mit langem Trend, "
          f"median slope_se(long) = {traj.cagr_long_se.median():.4f}")
    return traj


# ----------------------------------------------------------------------
def build_ana_asset_structure():
    """Anlagenkonzentration je Firma im aktuellsten Jahr.

    Ein hoher HHI heisst: die Emissionen haengen an wenigen Anlagen.
    Das ist gleichzeitig ein Konzentrationsrisiko (stranded assets) und
    ein Hebel (wenige Anlagen umzuruesten ist einfacher als viele).
    """
    fac = pd.read_parquet(B / "src_epa_facility.parquet")
    link = pd.read_parquet(B / "src_parent_link.parquet")
    er = pd.read_parquet(B / "src_entity_resolution.parquet").dropna(subset=["company_id"])
    er["company_id"] = er["company_id"].astype(int)

    f = fac[fac.reporting_year == LATEST]
    l = link[link.reporting_year == LATEST]
    m = (l.merge(f[["facility_id", "co2e_tonnes"]], on="facility_id")
           .merge(er[["name_raw", "company_id"]], left_on="parent_name_raw",
                  right_on="name_raw"))
    m["attr"] = m.co2e_tonnes * m.parent_share_pct / 100.0

    rows = []
    for cid, grp in m.groupby("company_id"):
        v = grp.groupby("facility_id").attr.sum().values
        tot = v.sum()
        if tot <= 0:
            continue
        share = v / tot
        hhi = float((share ** 2).sum())
        rows.append({
            "company_id": cid,
            "n_facilities": len(v),
            "hhi": hhi,
            "top1_share": float(share.max()),
            "hhi_se": float(hhi * (0.15 / np.sqrt(len(v)))),
        })
    st = pd.DataFrame(rows)
    st.to_parquet(B / "ana_asset_structure.parquet", index=False)
    print(f"ana_asset_structure: {len(st)} Firmen, median HHI = {st.hhi.median():.3f}")
    return st


# ----------------------------------------------------------------------
def build_int_peer_group(company_ids):
    comp = pd.read_parquet(B / "src_companies.parquet")
    comp = comp[comp.company_id.isin(company_ids)]

    frames = []
    for level, col in [("Sector", "gics_sector"), ("Industry", "gics_industry")]:
        sub = comp[["company_id", col]].rename(columns={col: "peer_group_id"})
        sub["peer_level"] = level
        frames.append(sub)
    g = comp[["company_id"]].copy()
    g["peer_group_id"] = "ALL"
    g["peer_level"] = "Global"
    frames.append(g)

    pg = pd.concat(frames, ignore_index=True)
    pg["peer_n"] = pg.groupby(["peer_level", "peer_group_id"]).company_id.transform("count")
    pg.to_parquet(B / "int_peer_group.parquet", index=False)
    for lv in ["Sector", "Industry", "Global"]:
        s = pg[pg.peer_level == lv]
        print(f"int_peer_group [{lv}]: {s.peer_group_id.nunique()} Gruppen, "
              f"median Gruppengroesse {s.peer_n.median():.0f}")
    return pg


# ----------------------------------------------------------------------
INDICATOR_SPEC = {
    # code: (polarity, dist_family, beschreibung)
    "log_scope1":    ("LowerIsBetter", "Normal", "log10 der absoluten Scope-1-Emissionen 2023"),
    "cagr_long":     ("LowerIsBetter", "Normal", "Jaehrliche log-Veraenderung 2011-2023"),
    "cagr_short":    ("LowerIsBetter", "Normal", "Jaehrliche log-Veraenderung 2019-2023"),
    "momentum":      ("LowerIsBetter", "Normal", "cagr_short minus cagr_long (Beschleunigung)"),
    "asset_hhi":     ("LowerIsBetter", "Beta",   "Konzentration der Emissionen auf wenige Anlagen"),
    "volatility":    ("LowerIsBetter", "Normal", "Reststreuung der log-Emissionen (Betriebskonstanz)"),
}


def build_int_indicator_panel(ana, traj, struct):
    latest = ana[ana.year == LATEST].set_index("company_id")
    traj = traj.set_index("company_id")
    struct = struct.set_index("company_id")
    ids = latest.index.intersection(traj.index).intersection(struct.index)

    rows = []
    for cid in ids:
        a, t, s = latest.loc[cid], traj.loc[cid], struct.loc[cid]

        # log10(Emissionen); SE per Delta-Methode aus dem relativen Fehler
        val = np.log10(a.scope1_tonnes)
        se = a.measurement_se_rel / np.log(10)
        rows.append((cid, "log_scope1", val, se, "Normal"))

        rows.append((cid, "cagr_long", t.cagr_long, t.cagr_long_se, "Normal"))
        rows.append((cid, "cagr_short", t.cagr_short, t.cagr_short_se, "Normal"))
        rows.append((cid, "momentum", t.momentum, t.momentum_se, "Normal"))
        rows.append((cid, "asset_hhi", s.hhi, s.hhi_se, "Beta"))
        rows.append((cid, "volatility", t.resid_sd_long,
                     t.resid_sd_long / np.sqrt(2 * max(t.n_years_long - 2, 1)), "Normal"))

    panel = pd.DataFrame(rows, columns=[
        "company_id", "indicator_code", "raw_value", "value_se", "dist_family"])

    panel["polarity"] = panel.indicator_code.map(lambda c: INDICATOR_SPEC[c][0])
    panel["is_imputed"] = panel.raw_value.isna()

    # Fehlende Werte: Sektormedian, aber mit aufgeblaehtem Standardfehler,
    # damit die Imputation in der Simulation nicht als sicher durchgeht.
    comp = pd.read_parquet(B / "src_companies.parquet")[["company_id", "gics_sector"]]
    panel = panel.merge(comp, on="company_id", how="left")
    med = panel.groupby(["gics_sector", "indicator_code"]).raw_value.transform("median")
    glob = panel.groupby("indicator_code").raw_value.transform("median")
    fill = med.fillna(glob)
    spread = panel.groupby("indicator_code").raw_value.transform("std")
    panel.loc[panel.is_imputed, "raw_value"] = fill[panel.is_imputed]
    panel.loc[panel.is_imputed, "value_se"] = spread[panel.is_imputed]

    # Verbleibende fehlende Standardfehler konservativ auffuellen
    med_se = panel.groupby("indicator_code").value_se.transform("median")
    panel["value_se"] = panel["value_se"].fillna(med_se).fillna(0.0)
    panel["value_se"] = panel["value_se"].clip(lower=1e-6)

    # Vertrauensstufe aus Match-Qualitaet und Imputation
    msc = ana[ana.year == LATEST].set_index("company_id").match_score_min
    panel["match_score"] = panel.company_id.map(msc)
    panel["trust_tier"] = np.select(
        [panel.is_imputed, panel.match_score >= 0.999, panel.match_score >= 0.93],
        ["Low", "High", "Medium"], default="Low")

    panel = panel.drop(columns=["gics_sector"])
    panel.to_parquet(B / "int_indicator_panel.parquet", index=False)
    print(f"int_indicator_panel: {len(panel):,} Zeilen "
          f"({panel.company_id.nunique()} Firmen x {panel.indicator_code.nunique()} Indikatoren), "
          f"{panel.is_imputed.sum()} imputiert")
    print(panel.groupby("indicator_code").agg(
        median=("raw_value", "median"),
        median_se=("value_se", "median"),
        imputed=("is_imputed", "sum")).round(4).to_string())
    return panel


if __name__ == "__main__":
    ana = build_ana_company_emissions()
    traj = build_ana_trajectory(ana)
    struct = build_ana_asset_structure()
    panel_ids = set(ana[ana.year == LATEST].company_id)
    build_int_peer_group(panel_ids)
    build_int_indicator_panel(ana, traj, struct)
