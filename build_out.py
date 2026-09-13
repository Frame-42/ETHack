"""
Ergebnisebene (out_*): bedingte Rangbaender, Konsistenzachse, PAB-Portfolio.

Die unbedingte Auswertung ueber alle 216 Konfigurationen beantwortet:
"wie stabil ist die Rangliste, wenn man sich auf keine Methode festlegt".
Die bedingte Auswertung fixiert die Vergleichsebene auf Sektor und
beantwortet: "wie stabil ist sie, wenn man diese eine Entscheidung trifft".
"""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.optimize import minimize

B = Path("build")
FIG = Path("figures"); FIG.mkdir(exist_ok=True)
LATEST = 2023


def load_all():
    cfg = pd.read_parquet(B / "cfg_method_space.parquet")
    RANK = np.load(B / "mc_rank.npy")
    SCORE = np.load(B / "mc_score.npy")
    panel = pd.read_parquet(B / "int_indicator_panel.parquet")
    comp = pd.read_parquet(B / "src_companies.parquet")
    ids = sorted(panel.company_id.unique())
    meta = comp.set_index("company_id").loc[ids].reset_index()
    return cfg, RANK, SCORE, meta, ids


# ----------------------------------------------------------------------
def conditional_rank_bands(cfg, SCORE, meta, ids):
    """Rangbaender bei fixierter Vergleichsebene (peer_level = Sector).

    Zusaetzlich der Rang innerhalb des Sektors, denn das ist die
    Groesse, die bei sektorrelativer Normalisierung ueberhaupt
    interpretierbar ist.
    """
    sel = cfg.peer_level == "Sector"
    idx = (cfg.loc[sel, "config_id"].values - 1)
    S = SCORE[idx]                                   # (n_sel, D, C)
    n_sel, D, C = S.shape
    flat = S.reshape(-1, C)

    global_rank = (-flat).argsort(axis=1).argsort(axis=1) + 1

    sectors = meta.gics_sector.values
    within = np.zeros_like(global_rank)
    for sec in np.unique(sectors):
        m = sectors == sec
        sub = flat[:, m]
        within[:, m] = (-sub).argsort(axis=1).argsort(axis=1) + 1

    dec = max(1, C // 10)
    rows = []
    for i, cid in enumerate(ids):
        g, w = global_rank[:, i], within[:, i]
        rows.append({
            "company_id": cid,
            "median_rank": int(np.median(g)),
            "rank_p05": int(np.percentile(g, 5)),
            "rank_p95": int(np.percentile(g, 95)),
            "rank_iqr": int(np.percentile(g, 75) - np.percentile(g, 25)),
            "p_top_decile": float((g <= dec).mean()),
            "sector_median_rank": int(np.median(w)),
            "sector_rank_p05": int(np.percentile(w, 5)),
            "sector_rank_p95": int(np.percentile(w, 95)),
            "sector_rank_iqr": int(np.percentile(w, 75) - np.percentile(w, 25)),
        })
    out = pd.DataFrame(rows).merge(
        meta[["company_id", "ticker", "company_name", "gics_sector"]], on="company_id")
    out["n_in_sector"] = out.groupby("gics_sector").company_id.transform("count")
    out["stability"] = np.where(out.sector_rank_iqr <= np.maximum(2, out.n_in_sector * 0.2),
                                "Robust", "Unstable")
    out = out.sort_values("median_rank").reset_index(drop=True)
    out.to_parquet(B / "out_rank_conditional.parquet", index=False)
    print(f"out_rank_conditional (peer_level=Sector, {n_sel} Konfigurationen x {D} Ziehungen):")
    print(f"  median Rangbreite global    (p95-p05) = {int((out.rank_p95-out.rank_p05).median())} von {C}")
    print(f"  median Rangbreite im Sektor (p95-p05) = {int((out.sector_rank_p95-out.sector_rank_p05).median())}")
    print(f"  robust im Sektor: {(out.stability=='Robust').sum()} von {len(out)}")
    return out


# ----------------------------------------------------------------------
def credibility_axis(meta, ids):
    """Konsistenz- und Datenqualitaetsachse.

    Ohne SBTi-/Pledge-Daten ist dies KEINE Greenwashing-Achse im Sinne
    des Reports. Sie misst, wie gut die Emissionsangaben einer Firma
    gestuetzt sind und ob der kurze Trend dem langen widerspricht.
    """
    ana = pd.read_parquet(B / "ana_company_emissions.parquet")
    traj = pd.read_parquet(B / "ana_emission_trajectory.parquet")
    panel = pd.read_parquet(B / "int_indicator_panel.parquet")
    pledge = pd.read_parquet(B / "ana_pledge_gap.parquet").set_index("company_id")

    latest = ana[ana.year == LATEST].set_index("company_id")
    t = traj.set_index("company_id")
    imp = panel.groupby("company_id").is_imputed.sum()

    rows = []
    for cid in ids:
        a, tr = latest.loc[cid], t.loc[cid]
        flags = []
        # Trendumkehr: lange Reduktion, zuletzt aber Anstieg
        if pd.notna(tr.cagr_long) and pd.notna(tr.cagr_short) \
           and tr.cagr_long < 0 and tr.cagr_short > 0.01:
            flags.append("Trendumkehr")
        # Trend statistisch nicht von null unterscheidbar
        if pd.notna(tr.cagr_long_se) and abs(tr.cagr_long) < 1.96 * tr.cagr_long_se:
            flags.append("Trend nicht signifikant")
        # Unsichere Konzernzuordnung
        if a.match_score_min < 0.999:
            flags.append("Unsichere Zuordnung")
        # Hohe Betriebsschwankung erschwert Trendaussagen
        if pd.notna(tr.resid_sd_long) and tr.resid_sd_long > 0.25:
            flags.append("Hohe Schwankung")
        if imp.get(cid, 0) > 0:
            flags.append("Imputierte Werte")
        # SBTi: Versprechen gegen tatsaechliche Reduktion
        pl = pledge.loc[cid] if cid in pledge.index else None
        gap = float(pl.pledge_gap) if pl is not None and pd.notna(pl.pledge_gap) else np.nan
        if pl is not None and not bool(pl.sbti_listed):
            flags.append("Kein SBTi-Ziel")
        elif pd.notna(gap) and gap > 0.01:
            flags.append("Hinter dem eigenen Ziel")

        n = len(flags)
        band = "Gut gestuetzt" if n == 0 else ("Unklar" if n <= 2 else "Schwach gestuetzt")
        rows.append({
            "company_id": cid, "flag_count": n,
            "flags": "; ".join(flags) if flags else "-",
            "credibility_band": band,
            "cagr_long": tr.cagr_long, "cagr_short": tr.cagr_short,
            "match_score": a.match_score_min,
            "sbti_listed": bool(pl.sbti_listed) if pl is not None else False,
            "sbti_validated": bool(pl.sbti_validated) if pl is not None else False,
            "required_cagr": float(pl.required_cagr) if pl is not None and pd.notna(pl.required_cagr) else np.nan,
            "pledge_gap": gap,
        })
    out = pd.DataFrame(rows).merge(
        meta[["company_id", "ticker", "company_name", "gics_sector"]], on="company_id")
    out.to_parquet(B / "out_credibility_axis.parquet", index=False)
    print("out_credibility_axis:", out.credibility_band.value_counts().to_dict())
    return out


# ----------------------------------------------------------------------
def pab_portfolio(meta, ids, ranks):
    """PAB-Nachbau: Emissionen halbieren, Sektoren nicht untergewichten,
    Abweichung vom Benchmark minimieren.

    Achtung: Die EU-Regel nutzt Emissionsintensitaet (Emissionen/Umsatz).
    Ohne Umsatzdaten wird hier auf absolute Emissionen je Indexgewicht
    optimiert. Die Methode ist identisch, der Nenner nicht.
    """
    ana = pd.read_parquet(B / "ana_company_emissions.parquet")
    e = ana[ana.year == LATEST].set_index("company_id").scope1_tonnes
    emis = np.array([e.get(c, 0.0) for c in ids], float)
    n = len(ids)

    w0 = np.full(n, 1.0 / n)                       # gleichgewichteter Benchmark
    base_carbon = float(w0 @ emis)
    sectors = meta.gics_sector.values
    uniq = np.unique(sectors)
    sector_base = {s: w0[sectors == s].sum() for s in uniq}

    # Rangbasierter Tilt-Score: besserer Rang -> hoehere Zielgewichtung
    r = ranks.set_index("company_id").median_rank
    rank_v = np.array([r.get(c, n) for c in ids], float)
    tilt = (n - rank_v) / n

    def obj(w):
        return float(((w - w0) ** 2).sum()) - 0.02 * float(w @ tilt)

    cons = [
        {"type": "eq", "fun": lambda w: w.sum() - 1.0},
        {"type": "ineq", "fun": lambda w: 0.5 * base_carbon - (w @ emis)},
    ]
    # Sektoren duerfen nicht untergewichtet werden (PAB-Kernregel)
    for s in uniq:
        m = (sectors == s).astype(float)
        cons.append({"type": "ineq",
                     "fun": (lambda w, m=m, b=sector_base[s]: (w @ m) - b)})

    res = minimize(obj, w0, method="SLSQP",
                   bounds=[(0.0, 0.10)] * n, constraints=cons,
                   options={"maxiter": 400, "ftol": 1e-10})
    w = np.clip(res.x, 0, None); w = w / w.sum()

    new_carbon = float(w @ emis)
    te_proxy = float(np.sqrt(((w - w0) ** 2).sum()))
    red = 1 - new_carbon / base_carbon

    out = pd.DataFrame({
        "company_id": ids,
        "benchmark_weight": w0,
        "weight": w,
        "scope1_tonnes": emis,
        "median_rank": rank_v,
    }).merge(meta[["company_id", "ticker", "company_name", "gics_sector"]], on="company_id")
    out["weight_delta"] = out.weight - out.benchmark_weight
    out["pab_compliant"] = red >= 0.50
    out.attrs = {}
    out.to_parquet(B / "out_portfolio.parquet", index=False)

    sec_chk = out.groupby("gics_sector")[["benchmark_weight", "weight"]].sum()
    ok = bool((sec_chk.weight >= sec_chk.benchmark_weight - 1e-6).all())
    print(f"out_portfolio: Emissionsreduktion {red*100:.1f}% "
          f"(PAB-Schwelle 50%), Gewichtsabweichung {te_proxy:.4f}, "
          f"Sektoren nicht untergewichtet: {ok}, Optimierer: {res.message}")
    summary = {"reduction": red, "te_proxy": te_proxy, "sector_ok": ok,
               "base_carbon": base_carbon, "new_carbon": new_carbon}
    return out, summary


if __name__ == "__main__":
    cfg, RANK, SCORE, meta, ids = load_all()
    cond = conditional_rank_bands(cfg, SCORE, meta, ids)
    cred = credibility_axis(meta, ids)
    port, psum = pab_portfolio(meta, ids, cond)
    pd.Series(psum).to_json(B / "portfolio_summary.json")
