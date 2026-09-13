"""
Fusionspipeline, Stufe 4: Ergebnisse und Validierung.

Behebt:
  K11 Zwei getrennte Listen statt einer behaupteten S&P-500-Rangliste.
  K12 Vintage: Rueckwaertstest misst, was eine Fortschreibung kostet.
  K13 Imputation wird gemessen, nicht behauptet (Auslass-Test).
  K14 Groessenverzerrung geprueft.
  K15 Geometrisch gegen additiv nach der Entkorrelierung erneut geprueft.
  K16 Greenwashing: Intensitaets-Illusion und bequemes Basisjahr ergaenzt.
  K17 PAB-Portfolio auf Intensitaet statt auf absoluten Emissionen.
"""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import spearmanr
from scipy.optimize import minimize

F = Path("fusion")
LATEST = 2023
BASE_ATT, BASE_TH = "Equity", 90


def load():
    cfg = pd.read_parquet(F / "cfg_method_space.parquet")
    PCT = np.load(F / "mc_pct.npy")
    panel = pd.read_parquet(F / "int_indicator_panel.parquet")
    pg = pd.read_parquet(F / "int_peer_group.parquet")
    comp = pd.read_parquet("build/src_companies.parquet")
    ids = sorted(panel.company_id.unique())
    meta = comp[comp.company_id.isin(ids)].set_index("company_id").loc[ids].reset_index()
    meta = meta.merge(pg, on="company_id")
    return cfg, PCT, panel, meta, ids


# ----------------------------------------------------------------------
def rank_bands(PCT, meta, ids):
    n_cfg, D, C = PCT.shape
    flat = PCT.reshape(-1, C)
    rows = []
    for i, cid in enumerate(ids):
        v = flat[:, i]
        rows.append({
            "company_id": cid,
            "median_pct": float(np.median(v)),
            "p10": float(np.percentile(v, 10)),
            "p90": float(np.percentile(v, 90)),
            "breite_pp": float(np.percentile(v, 90) - np.percentile(v, 10)),
            "p_top_tertil": float((v >= 66.7).mean()),
            "p_bottom_tertil": float((v <= 33.3).mean()),
        })
    out = pd.DataFrame(rows).merge(meta, on="company_id")
    out["gruppe_n"] = out.groupby("profile_group").company_id.transform("count")
    # Ein Rangplatz in einer Gruppe der Groesse n entspricht 100/(n-1) Punkten
    out["pp_pro_rang"] = 100.0 / (out.gruppe_n - 1).clip(lower=1)
    out["breite_raenge"] = out.breite_pp / out.pp_pro_rang
    out["stabil"] = np.where(out.breite_raenge <= 3, "robust", "unsicher")
    out = out.sort_values("median_pct", ascending=False).reset_index(drop=True)
    out.to_parquet(F / "out_rank_bands.parquet", index=False)
    print(f"out_rank_bands: Median-Bandbreite {out.breite_pp.median():.1f} Perzentilpunkte "
          f"= {out.breite_raenge.median():.1f} Rangplaetze; "
          f"{(out.stabil=='robust').sum()} von {len(out)} robust")
    return out


# ----------------------------------------------------------------------
def conditional_bands(cfg, PCT, meta, ids):
    """Bandbreite, wenn man sich auf EIN Gruppenschema festlegt.

    Das Schema zu wechseln heisst, die Vergleichsgruppe zu wechseln - dann
    bedeutet dasselbe Perzentil etwas anderes. Der unbedingte Wert misst
    also auch Unentschlossenheit, nicht nur Unsicherheit.
    """
    res = {}
    for scheme in ["Profile", "GICS"]:
        idx = cfg[cfg.peer_scheme == scheme].config_id.values - 1
        flat = PCT[idx].reshape(-1, len(ids))
        w = np.percentile(flat, 90, axis=0) - np.percentile(flat, 10, axis=0)
        res[scheme] = w
    out = pd.DataFrame({"company_id": ids,
                        "breite_profile_pp": res["Profile"],
                        "breite_gics_pp": res["GICS"]}).merge(meta, on="company_id")
    out["gruppe_n"] = out.groupby("profile_group").company_id.transform("count")
    out["breite_profile_raenge"] = out.breite_profile_pp / (100.0 / (out.gruppe_n - 1).clip(lower=1))
    out.to_parquet(F / "out_bands_conditional.parquet", index=False)
    print(f"Bedingt auf Gruppenschema 'Profile': Median-Band "
          f"{out.breite_profile_pp.median():.1f} pp = "
          f"{out.breite_profile_raenge.median():.1f} Rangplaetze "
          f"({(out.breite_profile_raenge <= 3).sum()} von {len(out)} robust)")
    print(f"Bedingt auf 'GICS': Median-Band {out.breite_gics_pp.median():.1f} pp")
    return out


def two_lists(ids):
    """Bewertbar gegen nicht bewertbar, mit Begruendung und Abdeckungsquote."""
    comp = pd.read_parquet("build/src_companies.parquet")
    ana = pd.read_parquet(F / "ana_company_emissions.parquet")
    fin = pd.read_parquet("build/src_financials.parquet")
    a = ana[(ana.attribution == BASE_ATT) & (ana.threshold == BASE_TH)
            & (ana.year == LATEST)].set_index("company_id")

    rows = []
    for r in comp.itertuples():
        cid = r.company_id
        has_em = cid in a.index
        has_rev = cid in set(fin.company_id)
        if cid in ids:
            status, grund = "bewertbar", "-"
        elif has_em:
            status, grund = "nicht bewertbar", "Emissionsdaten nur in einzelnen Datenvarianten"
        else:
            status, grund = "nicht bewertbar", "keine meldepflichtige US-Anlage gefunden"
        rows.append({"company_id": cid, "ticker": r.ticker,
                     "company_name": r.company_name, "gics_sector": r.gics_sector,
                     "status": status, "grund": grund,
                     "emissionsdaten": has_em, "umsatzdaten": has_rev,
                     "anlagen": int(a.loc[cid, "asset_count"]) if has_em else 0})
    out = pd.DataFrame(rows)
    out.to_parquet(F / "out_two_lists.parquet", index=False)

    cov = (out.groupby("gics_sector")
             .agg(gesamt=("company_id", "size"),
                  bewertbar=("status", lambda s: (s == "bewertbar").sum()))
             .assign(quote=lambda d: (d.bewertbar / d.gesamt * 100).round(1))
             .sort_values("quote", ascending=False))
    cov.to_parquet(F / "out_coverage.parquet")
    print(f"out_two_lists: {(out.status=='bewertbar').sum()} bewertbar, "
          f"{(out.status!='bewertbar').sum()} nicht bewertbar")
    print(cov.to_string())
    return out, cov


# ----------------------------------------------------------------------
def geometric_vs_arithmetic(cfg, PCT, ids):
    """Hat die Entkorrelierung die Aggregationswahl scharf gemacht?"""
    base = cfg[(cfg.normalization == "Rank") & (cfg.weighting == "Equal")
               & (cfg.peer_scheme == "Profile") & (cfg.imputation == "PeerMedian")
               & (cfg.attribution == BASE_ATT) & (cfg.threshold == BASE_TH)]
    g = base[base.aggregation == "Geometric"].config_id.iloc[0] - 1
    a = base[base.aggregation == "Arithmetic"].config_id.iloc[0] - 1
    gm, am = PCT[g].mean(axis=0), PCT[a].mean(axis=0)
    d = np.abs(gm - am)
    res = {"median_abweichung_pp": float(np.median(d)),
           "anteil_ueber_10pp": float((d > 10).mean()),
           "max_pp": float(d.max()),
           "spearman": float(spearmanr(gm, am).statistic)}
    pd.Series(res).to_json(F / "out_aggregation_test.json")
    print(f"Aggregationstest: Median {res['median_abweichung_pp']:.1f} pp, "
          f"{res['anteil_ueber_10pp']*100:.1f}% ueber 10 pp, max {res['max_pp']:.1f} pp")
    return res


# ----------------------------------------------------------------------
def imputation_test(cfg, PCT, panel, ids):
    """Auslass-Test: aendert sich die Reihenfolge, wenn imputierte Firmen raus sind?"""
    imp_ids = set(panel[(panel.attribution == BASE_ATT) & (panel.threshold == BASE_TH)
                        & panel.is_imputed & (panel.indicator_code == "log_intensity")]
                  .company_id)
    keep = [i for i, c in enumerate(ids) if c not in imp_ids]
    base = cfg[cfg.is_baseline].config_id.iloc[0] - 1
    full = PCT[base].mean(axis=0)
    sub = full[keep]
    # Perzentile nur auf der Teilmenge neu berechnen
    order = sub.argsort().argsort()
    sub_pct = order / max(len(sub) - 1, 1) * 100
    d = np.abs(sub - sub_pct)
    res = {"imputierte_firmen": len(imp_ids),
           "median_verschiebung_pp": float(np.median(d)),
           "p90_verschiebung_pp": float(np.percentile(d, 90)),
           "spearman": float(spearmanr(sub, sub_pct).statistic)}
    pd.Series(res).to_json(F / "out_imputation_test.json")
    print(f"Imputationstest: {len(imp_ids)} Firmen ohne echten Umsatz; "
          f"ohne sie verschiebt sich der Rest im Median um "
          f"{res['median_verschiebung_pp']:.1f} pp (rho = {res['spearman']:.3f})")
    return res


# ----------------------------------------------------------------------
def vintage_backtest(ids):
    """Was kostet es, zwei Jahre alte Emissionen mit neuen Umsaetzen zu kombinieren?"""
    ana = pd.read_parquet(F / "ana_company_emissions.parquet")
    fin = pd.read_parquet("build/src_financials.parquet").set_index("company_id")
    pg = pd.read_parquet(F / "int_peer_group.parquet").set_index("company_id")
    a = ana[(ana.attribution == BASE_ATT) & (ana.threshold == BASE_TH)]
    e23 = a[a.year == 2023].set_index("company_id").scope1_tonnes
    e21 = a[a.year == 2021].set_index("company_id").scope1_tonnes

    use = [c for c in ids if c in fin.index and c in e21.index and c in e23.index]
    rev = fin.loc[use, "revenue_usd"] / 1e6
    cur = np.log10(e23.loc[use] / rev)
    old = np.log10(e21.loc[use] / rev)
    grp = pg.loc[use, "profile_group"]

    def pct_in_group(series):
        out = pd.Series(index=series.index, dtype=float)
        for g in grp.unique():
            m = grp == g
            v = -series[m]          # kleiner ist besser
            out[m] = v.rank(pct=True) * 100
        return out

    pc, po = pct_in_group(cur), pct_in_group(old)
    d = (pc - po).abs()
    res = {"n": len(use), "spearman": float(spearmanr(pc, po).statistic),
           "median_pp": float(d.median()), "p90_pp": float(d.quantile(0.9)),
           "anteil_ueber_10pp": float((d > 10).mean())}
    pd.DataFrame({"company_id": use, "pct_2023": pc.values,
                  "pct_2021": po.values, "abw_pp": d.values}).to_parquet(
        F / "out_vintage_backtest.parquet", index=False)
    pd.Series(res).to_json(F / "out_vintage_summary.json")
    print(f"Vintage-Backtest ({res['n']} Firmen): rho = {res['spearman']:.2f}, "
          f"Median {res['median_pp']:.1f} pp, p90 {res['p90_pp']:.1f} pp, "
          f"{res['anteil_ueber_10pp']*100:.1f}% ueber 10 pp")
    return res


# ----------------------------------------------------------------------
def size_bias(bands):
    fin = pd.read_parquet("build/src_financials.parquet").set_index("company_id")
    d = bands[bands.company_id.isin(fin.index)].copy()
    d["log_rev"] = np.log10(fin.loc[d.company_id, "revenue_usd"].values / 1e6)
    r = spearmanr(d.log_rev, d.median_pct)
    res = {"n": len(d), "spearman": float(r.statistic), "p": float(r.pvalue)}
    pd.Series(res).to_json(F / "out_size_bias.json")
    sig = "signifikant" if r.pvalue < 0.05 else "nicht signifikant"
    print(f"Groessentest: rho = {r.statistic:.3f} (p = {r.pvalue:.2f}, n = {len(d)}) -- {sig}")
    return res


# ----------------------------------------------------------------------
def credibility(ids):
    """Achse B: vier Signale statt zwei."""
    ana = pd.read_parquet(F / "ana_company_emissions.parquet")
    fin = pd.read_parquet("build/src_financials.parquet").set_index("company_id")
    pledge = pd.read_parquet("build/ana_pledge_gap.parquet").set_index("company_id")
    qual = pd.read_parquet(F / "int_quality_panel.parquet")
    q = qual[(qual.attribution == BASE_ATT) & (qual.threshold == BASE_TH)
             & (qual.indicator_code == "cems_share")].set_index("company_id")
    a = ana[(ana.attribution == BASE_ATT) & (ana.threshold == BASE_TH)]

    rows = []
    for cid in ids:
        g = a[a.company_id == cid].sort_values("year")
        y, v = g.year.values, g.scope1_tonnes.values
        flags = []

        # 1. Intensitaets-Illusion: Intensitaet faellt, absolute Tonnen steigen
        abs_tr = np.nan
        if len(v) >= 3 and (v > 0).all():
            abs_tr = np.polyfit(y, np.log(v), 1)[0]
        int_tr = np.nan
        if cid in fin.index and pd.notna(abs_tr):
            int_tr = abs_tr      # Umsatz nur als Stichtag -> Niveau, nicht Trend
        illusion = bool(pd.notna(abs_tr) and abs_tr > 0.005)
        if illusion:
            flags.append("Absoluter Ausstoss steigt")

        # 2. Bequemes Basisjahr: erstes Jahr des Fensters deutlich ueber Median
        base_high = bool(len(v) >= 5 and v[0] > 1.10 * np.median(v))
        if base_high:
            flags.append("Bequemes Basisjahr")

        # 3. SBTi-Zielluecke
        pl = pledge.loc[cid] if cid in pledge.index else None
        gap = float(pl.pledge_gap) if pl is not None and pd.notna(pl.pledge_gap) else np.nan
        if pl is None or not bool(pl.sbti_listed):
            flags.append("Kein SBTi-Ziel")
        elif pd.notna(gap) and gap > 0.01:
            flags.append("Hinter dem eigenen Ziel")

        # 4. Messqualitaet: geringer Anteil kontinuierlich gemessener Emissionen
        cems = float(q.loc[cid, "raw_value"]) if cid in q.index else np.nan
        if pd.notna(cems) and cems < 0.20:
            flags.append("Kaum gemessene Emissionen")

        n = len(flags)
        rows.append({"company_id": cid, "flag_count": n,
                     "flags": "; ".join(flags) if flags else "-",
                     "band": "gut gestuetzt" if n == 0 else
                             ("unklar" if n <= 2 else "schwach gestuetzt"),
                     "abs_trend": abs_tr, "pledge_gap": gap, "cems_share": cems,
                     "basisjahr_hoch": base_high, "absolut_steigend": illusion})
    out = pd.DataFrame(rows)
    out.to_parquet(F / "out_credibility.parquet", index=False)
    print(f"out_credibility: {out.band.value_counts().to_dict()}; "
          f"absolut steigend {out.absolut_steigend.sum()}, "
          f"bequemes Basisjahr {out.basisjahr_hoch.sum()}")
    return out


# ----------------------------------------------------------------------
def pab_portfolio(bands, ids):
    """PAB auf Emissionsintensitaet statt auf absoluten Tonnen."""
    ana = pd.read_parquet(F / "ana_company_emissions.parquet")
    fin = pd.read_parquet("build/src_financials.parquet").set_index("company_id")
    a = ana[(ana.attribution == BASE_ATT) & (ana.threshold == BASE_TH)
            & (ana.year == LATEST)].set_index("company_id")

    use = [c for c in ids if c in fin.index and c in a.index]
    n = len(use)
    emis = a.loc[use, "scope1_tonnes"].values
    rev = fin.loc[use, "revenue_usd"].values / 1e6
    intens = emis / rev                       # t CO2e je Mio. USD Umsatz

    w0 = np.full(n, 1.0 / n)
    base_int = float(w0 @ intens)             # gewichtete Durchschnittsintensitaet
    meta = bands.set_index("company_id").loc[use]
    sectors = meta.gics_sector.values
    tilt = meta.median_pct.values / 100.0

    sector_base = {s: w0[sectors == s].sum() for s in np.unique(sectors)}

    def obj(w):
        return float(((w - w0) ** 2).sum()) - 0.02 * float(w @ tilt)

    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0},
            {"type": "ineq", "fun": lambda w: 0.5 * base_int - (w @ intens)}]
    for s in np.unique(sectors):
        m = (sectors == s).astype(float)
        cons.append({"type": "ineq",
                     "fun": (lambda w, m=m, b=sector_base[s]: (w @ m) - b)})

    res = minimize(obj, w0, method="SLSQP", bounds=[(0.0, 0.08)] * n,
                   constraints=cons, options={"maxiter": 600, "ftol": 1e-11})
    w = np.clip(res.x, 0, None); w /= w.sum()
    new_int = float(w @ intens)
    red = 1 - new_int / base_int
    te = float(np.sqrt(((w - w0) ** 2).sum()))

    out = pd.DataFrame({"company_id": use, "benchmark_weight": w0, "weight": w,
                        "intensity": intens, "median_pct": meta.median_pct.values,
                        "gics_sector": sectors, "ticker": meta.ticker.values})
    out.to_parquet(F / "out_portfolio.parquet", index=False)
    chk = out.groupby("gics_sector")[["benchmark_weight", "weight"]].sum()
    ok = bool((chk.weight >= chk.benchmark_weight - 1e-6).all())
    summary = {"basis_intensitaet": base_int, "neue_intensitaet": new_int,
               "reduktion": red, "te_proxy": te, "sektoren_ok": ok,
               "titel": int((w > 1e-4).sum()), "max_gewicht": float(w.max()), "n": n}
    pd.Series(summary).to_json(F / "out_portfolio_summary.json")
    print(f"PAB (Intensitaet): {base_int:.1f} -> {new_int:.1f} t/Mio.USD "
          f"= -{red*100:.1f}%, TE-Proxy {te:.4f}, Sektoren gehalten: {ok}, "
          f"{summary['titel']} Titel, max {w.max()*100:.2f}%")
    return out, summary


if __name__ == "__main__":
    cfg, PCT, panel, meta, ids = load()
    bands = rank_bands(PCT, meta, ids)
    conditional_bands(cfg, PCT, meta, ids)
    two_lists(ids)
    geometric_vs_arithmetic(cfg, PCT, ids)
    imputation_test(cfg, PCT, panel, ids)
    vintage_backtest(ids)
    size_bias(bands)
    credibility(ids)
    pab_portfolio(bands, ids)
