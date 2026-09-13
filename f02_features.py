"""
Fusionspipeline, Stufe 2: Indikatoren und Vergleichsgruppen.

Behebt:
  K5  Entkorrelierte Kennzahlen. Die beiden Trends korrelierten mit
      rho = 0.64; damit konnte die geometrische Aggregation nicht greifen.
      Ersetzt durch Branchen-Trendabweichung und Momentum.
  K6  Vergleichsgruppen aus den Daten (k-Means ueber NAICS-Profile,
      Mindestgroesse 8) statt GICS. Berkshire landet dann nicht bei Banken.
      GICS bleibt als zweite Sicht erhalten.
  K7  Messqualitaet (CEMS-Anteil) als eigener, unkorrelierter Indikator.
  K4  Acht Datenvarianten: Zurechnung x Matching-Schwelle.
"""
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.cluster import KMeans

F = Path("fusion")
LATEST = 2023
TREND_LONG = (2011, 2023)
TREND_SHORT = (2019, 2023)
MIN_PEER = 8

INDICATORS = {
    # code: (Polarität, Verteilung, Beschreibung)
    "log_intensity": ("LowerIsBetter", "Normal", "log10 Scope 1 je Mio. USD Umsatz"),
    "trend_rel":     ("LowerIsBetter", "Normal", "Langtrend minus Gruppenmedian"),
    "momentum":      ("LowerIsBetter", "Normal", "Kurztrend minus Langtrend"),
    "coal_share":    ("LowerIsBetter", "Beta",   "Kohleanteil fossiler Verbrennung"),
    "asset_hhi":     ("LowerIsBetter", "Beta",   "Konzentration auf wenige Anlagen"),
    "volatility":    ("LowerIsBetter", "Normal", "Reststreuung der log-Emissionen"),
    # Neue Dimensionen: nicht mehr nur CO2
    "karzinogen_anteil": ("LowerIsBetter", "Beta",  "Anteil krebserregender Stoffe an der Freisetzung"),
}
# Bewusst NICHT im Score: cems_share korreliert mit 0.65 zum Kohleanteil und
# mit 0.62 zur Intensitaet. Der Anteil gemessener statt berechneter Emissionen
# ist eine Aussage ueber Berichtsqualitaet, nicht ueber Nachhaltigkeit.
# Er wandert deshalb auf die Glaubwuerdigkeitsachse.
# Ebenfalls nicht im Score, aber aus anderen Gruenden:
#   tri_intensity  korreliert mit rho = 0.71 zur CO2-Intensitaet. Beide messen
#                  Industrieaktivitaet je Umsatz. Die Zusammensetzung der
#                  Freisetzung (karzinogen_anteil) ist die unabhaengige Groesse.
#   unfallrate     ist nur fuer 47 der 116 Firmen gemessen. Bei 59 Prozent
#                  Imputation traegt ein Score-Indikator vor allem Gruppenmedian.
QUALITY_ONLY = {
    "cems_share":    ("HigherIsBetter", "Beta", "Anteil kontinuierlich gemessener Emissionen"),
    "tri_intensity": ("LowerIsBetter", "Normal", "Giftstofffreisetzung je Mio. USD Umsatz"),
    "unfallrate":    ("LowerIsBetter", "Normal", "Arbeitsunfaelle je 200 000 Stunden"),
}


def ols_log_slope(years, values):
    m = np.asarray(values) > 0
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
    return slope, np.sqrt(s2 / sxx), np.sqrt(s2), n


# ----------------------------------------------------------------------
def facility_profiles(er, threshold):
    """NAICS-Profil je Firma: Emissionsanteil je zweistelligem NAICS-Code."""
    fac = pd.read_parquet(F / "src_epa_facility.parquet")
    link = pd.read_parquet("build/src_parent_link.parquet")
    f = fac[fac.reporting_year == LATEST]
    l = link[link.reporting_year == LATEST]
    m = er[(er.threshold == threshold) & er.company_id.notna()]
    j = (l.merge(f[["facility_id", "co2e_tonnes", "naics_code"]], on="facility_id")
           .merge(m[["name_raw", "company_id"]], left_on="parent_name_raw",
                  right_on="name_raw"))
    j["attr"] = j.co2e_tonnes * j.parent_share_pct / 100.0
    j["naics2"] = j.naics_code.astype(str).str[:3]
    piv = j.pivot_table(index="company_id", columns="naics2", values="attr",
                        aggfunc="sum", fill_value=0.0)
    piv = piv.div(piv.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return piv


def build_peer_groups(er, ids, threshold=90, k=9, seed=7):
    """k-Means ueber das NAICS-Emissionsprofil, Mindestgroesse erzwungen."""
    prof = facility_profiles(er, threshold).reindex(ids).fillna(0.0)
    km = KMeans(n_clusters=k, random_state=seed, n_init=20).fit(prof.values)
    lab = pd.Series(km.labels_, index=prof.index, name="cluster")

    # Zu kleine Cluster in den naechstgelegenen grossen Cluster verschieben
    counts = lab.value_counts()
    big = counts[counts >= MIN_PEER].index.tolist()
    if not big:
        big = [counts.index[0]]
    centers = km.cluster_centers_
    for cid in lab.index:
        if lab[cid] not in big:
            d = [np.linalg.norm(prof.loc[cid].values - centers[b]) for b in big]
            lab[cid] = big[int(np.argmin(d))]

    comp = pd.read_parquet("build/src_companies.parquet").set_index("company_id")
    out = pd.DataFrame({
        "company_id": lab.index,
        "profile_group": ["P" + str(v) for v in lab.values],
        "gics_group": comp.loc[lab.index, "gics_sector"].values,
    })
    # GICS-Gruppen unter der Mindestgroesse auf "GICS-Rest" zusammenfassen
    vc = out.gics_group.value_counts()
    small = set(vc[vc < MIN_PEER].index)
    out["gics_group"] = out.gics_group.where(~out.gics_group.isin(small), "GICS-Rest")
    out.to_parquet(F / "int_peer_group.parquet", index=False)
    print(f"int_peer_group: {out.profile_group.nunique()} Profilgruppen "
          f"(kleinste {out.profile_group.value_counts().min()}), "
          f"{out.gics_group.nunique()} GICS-Gruppen "
          f"(kleinste {out.gics_group.value_counts().min()})")
    return out


# ----------------------------------------------------------------------
def build_panels():
    ana = pd.read_parquet(F / "ana_company_emissions.parquet")
    er = pd.read_parquet(F / "src_entity_resolution.parquet")
    fin = pd.read_parquet("build/src_financials.parquet").set_index("company_id")
    cems_f = pd.read_parquet(F / "src_cems_facility.parquet")
    link = pd.read_parquet("build/src_parent_link.parquet")
    fuel = pd.read_parquet("build/src_fuel_mix.parquet").set_index("company_id")
    fac = pd.read_parquet(F / "src_epa_facility.parquet")
    tri = pd.read_parquet(F / "src_tri.parquet").set_index("company_id")
    eia = pd.read_parquet(F / "src_eia_generation.parquet").set_index("company_id")
    osha = pd.read_parquet(F / "src_osha.parquet").set_index("company_id")

    variants = ana[["attribution", "threshold"]].drop_duplicates().values.tolist()
    # Firmen, die in ALLEN acht Varianten mit 2023er Wert vorkommen
    sets = []
    for att, th in variants:
        s = ana[(ana.attribution == att) & (ana.threshold == th) & (ana.year == LATEST)]
        sets.append(set(s.company_id))
    ids = sorted(set.intersection(*sets))
    print(f"Gemeinsame Firmenbasis ueber alle acht Varianten: {len(ids)}")

    pg = build_peer_groups(er, ids)
    prof_map = dict(zip(pg.company_id, pg.profile_group))

    # Gruppen, in denen mindestens zwei Drittel der Firmen Erzeugungsdaten
    # haben, bekommen den physischen Nenner (t CO2 je MWh). Das ist genau
    # die Materialitaetsidee: der richtige Nenner haengt von der Branche ab.
    gdf = pd.DataFrame({"company_id": ids})
    gdf["grp"] = gdf.company_id.map(prof_map)
    gdf["hat_mwh"] = gdf.company_id.isin(eia.index[eia.mwh > 0])
    frac = gdf.groupby("grp").hat_mwh.mean()
    phys_groups = set(frac[frac >= 0.66].index)
    frac.round(2).to_csv(F / "eia_group_coverage.csv")
    if not phys_groups:
        print("Physischer Nenner NICHT eingesetzt: keine Profilgruppe erreicht "
              f"die 66-Prozent-Schwelle (beste Gruppe {frac.max():.0%}). "
              "Ein gemischter Nenner innerhalb einer Gruppe waere schlimmer "
              "als ein einheitlich falscher.")
    else:
        print(f"Physischer Nenner fuer {sorted(phys_groups)}: "
              f"{gdf[gdf.grp.isin(phys_groups)].shape[0]} Firmen")

    l23 = link[link.reporting_year == LATEST]
    f23 = fac[fac.reporting_year == LATEST]

    rows = []
    for att, th in variants:
        sub = ana[(ana.attribution == att) & (ana.threshold == th)]
        latest = sub[sub.year == LATEST].set_index("company_id")

        # Trends je Firma
        tr = {}
        for cid, g in sub[sub.company_id.isin(ids)].groupby("company_id"):
            g = g.sort_values("year")
            w = g[(g.year >= TREND_LONG[0]) & (g.year <= TREND_LONG[1])]
            sl, se, rsd, n = ols_log_slope(w.year.values, w.scope1_tonnes.values)
            w2 = g[(g.year >= TREND_SHORT[0]) & (g.year <= TREND_SHORT[1])]
            sl2, se2, _, _ = ols_log_slope(w2.year.values, w2.scope1_tonnes.values)
            tr[cid] = (sl, se, rsd, n, sl2, se2)

        # Gruppenmedian des Langtrends fuer die Trendabweichung
        tdf = pd.DataFrame([(c, v[0]) for c, v in tr.items()],
                           columns=["company_id", "cagr_long"])
        tdf["grp"] = tdf.company_id.map(prof_map)
        gmed = tdf.groupby("grp").cagr_long.median()

        # CEMS und Anlagenstruktur je Firma in dieser Variante
        mm = er[(er.threshold == th) & er.company_id.notna()]
        jj = (l23.merge(f23[["facility_id", "co2e_tonnes"]], on="facility_id")
                 .merge(mm[["name_raw", "company_id"]], left_on="parent_name_raw",
                        right_on="name_raw"))
        jj["w"] = 1.0 if att == "Control" else jj.parent_share_pct / 100.0
        jj["attr"] = jj.co2e_tonnes * jj.w
        hhi = (jj.groupby(["company_id", "facility_id"]).attr.sum()
                 .groupby(level=0).apply(lambda v: float(((v / v.sum()) ** 2).sum())))
        nfac = jj.groupby("company_id").facility_id.nunique()
        cj = jj.merge(cems_f, on="facility_id", how="left")
        cs = (cj.groupby("company_id")
                .apply(lambda g: (g.co2_cems.fillna(0) * g.w).sum()
                       / max((g.co2_total.fillna(0) * g.w).sum(), 1e-9),
                       include_groups=False))

        for cid in ids:
            a = latest.loc[cid]
            sl, se, rsd, n, sl2, se2 = tr.get(cid, (np.nan,) * 6)
            rel_se = (0.05 + 0.10 / np.sqrt(max(a.asset_count, 1)))

            # Intensitaet: physischer Nenner, wo die ganze Gruppe ihn hat
            gname = prof_map.get(cid)
            use_mwh = gname in phys_groups and cid in eia.index and eia.loc[cid, "mwh"] > 0
            if use_mwh:
                val = np.log10(a.scope1_tonnes / eia.loc[cid, "mwh"])
                vse = rel_se / np.log(10)
                imp = False
            elif cid in fin.index:
                val = np.log10(a.scope1_tonnes / (fin.loc[cid, "revenue_usd"] / 1e6))
                vse = np.sqrt(rel_se ** 2 + fin.loc[cid, "revenue_se_rel"] ** 2) / np.log(10)
                imp = False
            else:
                val, vse, imp = np.nan, np.nan, True
            rows.append((att, th, cid, "log_intensity", val, vse, imp))

            # Giftstofffreisetzung je Umsatz
            if cid in tri.index and cid in fin.index and tri.loc[cid, "tri_kg"] > 0:
                tv = np.log10(tri.loc[cid, "tri_kg"] / (fin.loc[cid, "revenue_usd"] / 1e6))
                tse = np.sqrt(0.15 ** 2 + fin.loc[cid, "revenue_se_rel"] ** 2) / np.log(10)
                rows.append((att, th, cid, "tri_intensity", tv, tse, False))
            else:
                rows.append((att, th, cid, "tri_intensity", np.nan, np.nan, True))

            if cid in tri.index and tri.loc[cid, "tri_kg"] > 0:
                ka = float(tri.loc[cid, "karzinogen_anteil"])
                n_rep = max(int(tri.loc[cid, "tri_meldungen"]), 2)
                rows.append((att, th, cid, "karzinogen_anteil", ka,
                             float(np.sqrt(max(ka, 1e-4) * (1 - min(ka, .9999)) / n_rep)),
                             False))
            else:
                rows.append((att, th, cid, "karzinogen_anteil", np.nan, np.nan, True))

            # Arbeitsunfallrate
            if cid in osha.index:
                rows.append((att, th, cid, "unfallrate",
                             float(osha.loc[cid, "unfallrate"]),
                             float(osha.loc[cid, "unfallrate_se"]), False))
            else:
                rows.append((att, th, cid, "unfallrate", np.nan, np.nan, True))

            g = prof_map.get(cid)
            rel = sl - gmed.get(g, np.nan) if pd.notna(sl) else np.nan
            rows.append((att, th, cid, "trend_rel", rel, se, pd.isna(rel)))
            mom = sl2 - sl if (pd.notna(sl) and pd.notna(sl2)) else np.nan
            mse = np.sqrt((se or 0) ** 2 + (se2 or 0) ** 2) if pd.notna(mom) else np.nan
            rows.append((att, th, cid, "momentum", mom, mse, pd.isna(mom)))
            rows.append((att, th, cid, "volatility", rsd,
                         (rsd / np.sqrt(2 * max(n - 2, 1))) if pd.notna(rsd) else np.nan,
                         pd.isna(rsd)))

            cshare = float(fuel.loc[cid, "coal_share"]) if cid in fuel.index else np.nan
            cse = float(fuel.loc[cid, "coal_share_se"]) if cid in fuel.index else np.nan
            rows.append((att, th, cid, "coal_share", cshare, cse, pd.isna(cshare)))

            h = float(hhi.get(cid, np.nan))
            rows.append((att, th, cid, "asset_hhi", h,
                         h * 0.15 / np.sqrt(max(nfac.get(cid, 1), 1)) if pd.notna(h) else np.nan,
                         pd.isna(h)))
            c = float(cs.get(cid, np.nan))
            rows.append((att, th, cid, "cems_share", c,
                         np.sqrt(max(c, 0) * (1 - min(c, 1)) / max(nfac.get(cid, 2), 2))
                         if pd.notna(c) else np.nan, pd.isna(c)))

    panel = pd.DataFrame(rows, columns=["attribution", "threshold", "company_id",
                                        "indicator_code", "raw_value", "value_se",
                                        "is_imputed"])
    spec = {**INDICATORS, **QUALITY_ONLY}
    panel["polarity"] = panel.indicator_code.map(lambda c: spec[c][0])
    panel["dist_family"] = panel.indicator_code.map(lambda c: spec[c][1])
    panel["in_score"] = panel.indicator_code.isin(INDICATORS)

    # Imputation je Variante: Gruppenmedian, Fehlerbalken auf Gruppenstreuung
    panel["grp"] = panel.company_id.map(prof_map)
    med = panel.groupby(["attribution", "threshold", "grp", "indicator_code"]).raw_value.transform("median")
    glob = panel.groupby(["attribution", "threshold", "indicator_code"]).raw_value.transform("median")
    spread = panel.groupby(["attribution", "threshold", "indicator_code"]).raw_value.transform("std")
    fill = med.fillna(glob)
    panel.loc[panel.is_imputed, "raw_value"] = fill[panel.is_imputed]
    panel.loc[panel.is_imputed, "value_se"] = spread[panel.is_imputed]
    mse = panel.groupby("indicator_code").value_se.transform("median")
    panel["value_se"] = panel.value_se.fillna(mse).fillna(0.0).clip(lower=1e-6)
    panel = panel.drop(columns="grp")

    print(f"int_indicator_panel: {len(ids)} Firmen x {len(INDICATORS)} Score-Indikatoren "
          f"x {len(variants)} Datenvarianten")

    # cems_share separat sichern, dann aus dem Score-Panel entfernen
    panel[~panel.in_score].to_parquet(F / "int_quality_panel.parquet", index=False)
    panel = panel[panel.in_score].drop(columns="in_score").reset_index(drop=True)
    panel.to_parquet(F / "int_indicator_panel.parquet", index=False)
    ref = panel[(panel.attribution == "Equity") & (panel.threshold == 90)]
    print(ref.groupby("indicator_code").agg(
        median=("raw_value", "median"), se=("value_se", "median"),
        imputiert=("is_imputed", "sum")).round(4).to_string())

    # Korrelationsmatrix: belegt die Entkorrelierung
    wide = ref.pivot(index="company_id", columns="indicator_code", values="raw_value")
    corr = wide.corr(method="spearman").round(2)
    corr.to_csv(F / "indicator_correlation.csv")
    off = corr.where(~np.eye(len(corr), dtype=bool)).abs().stack()
    print(f"\nKorrelationen: max |rho| = {off.max():.2f} "
          f"({off.idxmax()[0]} / {off.idxmax()[1]}), median |rho| = {off.median():.2f}")
    return panel, ids


if __name__ == "__main__":
    build_panels()
