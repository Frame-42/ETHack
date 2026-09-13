"""
Auswertung des Team-Datensatzes: vier Achsen, ehrliche Abdeckung.

Der Datensatz erreicht 467 von 503 Firmen. Diese Zahl traegt aber nicht,
was sie verspricht: Sie zaehlt jede Firma mit, die zu irgendeiner Kennzahl
einen Wert hat. Eine Firma, von der nur die Arbeitsunfallrate bekannt ist,
laesst sich nicht gegen eine Firma stellen, von der Emissionen, Regeltreue
und Ziele vorliegen.

Deshalb wird hier zuerst gemessen, wie viele Firmen ueberhaupt auf mehreren
Achsen Daten haben - und die Zahl der bewerteten Achsen wird selbst zu einer
Dimension der Unsicherheitsanalyse.
"""
import itertools, json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import norm as ndist, spearmanr

T = Path("team"); OUT = Path("team_out"); OUT.mkdir(exist_ok=True)
SEED, N_DRAWS, EPS = 20260912, 100, 1e-9
SCORE_AXES = ["A", "S", "G", "B"]
AXIS_NAME = {"A": "Umwelt", "S": "Soziales", "G": "Regeltreue", "B": "Glaubwuerdigkeit"}

NORMALIZATIONS = ["Rank", "ZScoreWinsor", "MinMax"]
AGGREGATIONS = ["Arithmetic", "Geometric"]
PEER_LEVELS = ["Sector", "Global"]
MIN_AXES = [2, 3, 4]
AXIS_WEIGHTS = {
    "Gleich": None,
    "Umweltlastig": {"A": .55, "S": .18, "G": .17, "B": .10},
    "Ausgewogen": {"A": .35, "S": .25, "G": .25, "B": .15},
    "Verhaltenslastig": {"A": .22, "S": .26, "G": .32, "B": .20},
}


def prepare():
    df = pd.read_parquet(T / "dataset_long.parquet")
    M = json.loads((T / "metrics.json").read_text())
    core = [m for m, v in M.items() if v["axis"] in SCORE_AXES and v["direction"] != 0]

    w = (df.dropna(subset=["value"]).sort_values("year")
           .drop_duplicates(["ticker", "metric"], keep="last"))
    piv = w[w.metric.isin(core)].pivot(index="ticker", columns="metric", values="value")
    meta = (df.drop_duplicates("ticker").set_index("ticker")
              [["company", "gics_sector", "gics_sub_industry"]])
    piv = piv.reindex(sorted(df.ticker.unique()))
    meta = meta.reindex(piv.index)

    ax_of = {m: M[m]["axis"] for m in core}
    dir_of = {m: M[m]["direction"] for m in core}

    has_axis = pd.DataFrame({
        ax: piv[[m for m in core if ax_of[m] == ax]].notna().any(axis=1)
        for ax in SCORE_AXES}, index=piv.index)
    n_axes = has_axis.sum(axis=1)

    # Korrelations-Gate gegen die CO2-Intensitaet
    keep, dropped = [], []
    if "co2_intensity" in piv.columns:
        ref = piv["co2_intensity"]
        for m in core:
            if m == "co2_intensity":
                keep.append(m); continue
            b = piv[[m]].join(ref.rename("r")).dropna()
            if len(b) < 25:
                keep.append(m); continue
            rho = spearmanr(b[m], b["r"]).statistic
            (dropped if abs(rho) > 0.30 else keep).append(m)
            if abs(rho) > 0.30:
                print(f"  Tor 2: {m} raus (rho = {rho:+.2f} zur CO2-Intensitaet)")
    else:
        keep = core
    return piv, meta, keep, ax_of, dir_of, has_axis, n_axes


def normalize(X, method, gidx, winsor=.05):
    out = np.empty_like(X)
    for g in np.unique(gidx):
        m = gidx == g
        sub = X[:, m, :]; n = int(m.sum())
        if n == 1:
            out[:, m, :] = .5; continue
        if method == "Rank":
            out[:, m, :] = (sub.argsort(axis=1).argsort(axis=1) + .5) / n
        elif method == "MinMax":
            lo, hi = sub.min(1, keepdims=True), sub.max(1, keepdims=True)
            out[:, m, :] = (sub - lo) / np.maximum(hi - lo, EPS)
        else:
            lo = np.quantile(sub, winsor, axis=1, keepdims=True)
            hi = np.quantile(sub, 1 - winsor, axis=1, keepdims=True)
            c = np.clip(sub, lo, hi)
            mu, sd = c.mean(1, keepdims=True), np.maximum(c.std(1, keepdims=True), EPS)
            out[:, m, :] = ndist.cdf((c - mu) / sd)
    return np.clip(out, .01, 1.)


def run():
    piv, meta, keep, ax_of, dir_of, has_axis, n_axes = prepare()

    print("\nAbdeckung je Achse:")
    for ax in SCORE_AXES:
        ms = [m for m in keep if ax_of[m] == ax]
        print(f"  {AXIS_NAME[ax]:18s} {len(ms)} Kennzahlen, "
              f"{int(has_axis[ax].sum()):3d} Firmen ({has_axis[ax].mean():.0%})")
    print("\nFirmen nach Zahl besetzter Achsen:")
    for k in range(5):
        print(f"  {k}: {(n_axes == k).sum():3d}")

    ids = piv.index[n_axes >= min(MIN_AXES)]
    P = piv.loc[ids, keep]
    meta = meta.loc[ids]
    has_axis = has_axis.loc[ids]
    C, K = P.shape
    V = P.apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    miss = np.isnan(V)
    pol = np.array([1. if dir_of[m] > 0 else -1. for m in keep])
    axarr = np.array([ax_of[m] for m in keep], dtype=object)

    sd = np.nanstd(V, axis=0); sd[sd == 0] = 1.
    SE = np.tile(.10 * sd, (C, 1)); SE[miss] = np.tile(sd, (C, 1))[miss]
    base = np.where(miss, np.nanmedian(V, axis=0), V)

    cfg = pd.DataFrame([
        dict(config_id=i + 1, normalization=n, aggregation=a, peer_level=p,
             min_axes=ma, axis_weights=aw)
        for i, (n, a, p, ma, aw) in enumerate(itertools.product(
            NORMALIZATIONS, AGGREGATIONS, PEER_LEVELS, MIN_AXES, AXIS_WEIGHTS))])
    print(f"\nUniversum: {C} Firmen (mind. {min(MIN_AXES)} Achsen), "
          f"{K} Kennzahlen, {miss.mean()*100:.0f}% Luecken")
    print(f"Konfigurationen: {len(cfg)}, Ziehungen {N_DRAWS}")

    rng = np.random.default_rng(SEED)
    Z = rng.standard_normal((N_DRAWS, C, K))
    sect = meta.gics_sector.fillna("?").values
    u, c = np.unique(sect, return_counts=True); small = set(u[c < 8])
    gcache = {"Sector": np.array(["Rest" if s in small else s for s in sect], dtype=object),
              "Global": np.array(["ALL"] * C, dtype=object)}

    PCT = np.full((len(cfg), N_DRAWS, C), np.nan, dtype=np.float32)
    for row in cfg.itertuples():
        elig = (n_axes.loc[ids] >= row.min_axes).values
        gidx = gcache[row.peer_level]
        X = (base[None] + SE[None] * Z) * pol[None, None, :]
        N = normalize(X, row.normalization, gidx)
        prof = AXIS_WEIGHTS[row.axis_weights]
        parts, wts = [], []
        for ax in SCORE_AXES:
            sel = axarr == ax
            if not sel.any():
                continue
            sub = N[:, :, sel]
            parts.append(sub.mean(2) if row.aggregation == "Arithmetic"
                         else np.exp(np.log(np.maximum(sub, EPS)).mean(2)))
            wts.append(1. if prof is None else prof[ax])
        wv = np.array(wts); wv /= wv.sum()
        S = np.stack(parts, 2)
        sc = ((S * wv[None, None]).sum(2) if row.aggregation == "Arithmetic"
              else np.exp((wv[None, None] * np.log(np.maximum(S, EPS))).sum(2)))
        sc = np.where(elig[None, :], sc, np.nan)
        pct = np.full_like(sc, np.nan)
        for g in np.unique(gidx):
            m = (gidx == g) & elig
            if m.sum() < 2:
                continue
            s = sc[:, m]
            pct[:, m] = s.argsort(1).argsort(1) / (m.sum() - 1) * 100
        PCT[row.config_id - 1] = pct.astype(np.float32)

    flat = PCT.reshape(-1, C)
    bands = pd.DataFrame({
        "ticker": ids,
        "laeufe": np.isfinite(flat).sum(0),
        "median_pct": np.nanmedian(flat, 0),
        "p10": np.nanpercentile(flat, 10, 0),
        "p90": np.nanpercentile(flat, 90, 0)})
    bands["breite_pp"] = (bands.p90 - bands.p10).round(1)
    bands["achsen"] = n_axes.loc[ids].values
    bands = bands.merge(meta.reset_index(), on="ticker")
    bands.sort_values("median_pct", ascending=False).to_csv(
        OUT / "out_rank_bands.csv", index=False)
    print(f"\nMedian-Bandbreite: {bands.breite_pp.median():.1f} Perzentilpunkte")
    print("Bandbreite nach Zahl besetzter Achsen:")
    print(bands.groupby("achsen").breite_pp.agg(["size", "median"]).round(1).to_string())

    Y = np.nan_to_num(PCT - np.nanmean(PCT, axis=(0, 1), keepdims=True))
    F = Y.reshape(len(cfg) * N_DRAWS, C)
    vt = F.var(0).sum()
    keys = {k: np.repeat(pd.factorize(cfg[k])[0], N_DRAWS)
            for k in ["normalization", "aggregation", "peer_level",
                      "min_axes", "axis_weights"]}
    keys["Verteilungsziehung"] = np.tile(np.arange(N_DRAWS), len(cfg))

    def expl(kk):
        comb = np.zeros(len(cfg) * N_DRAWS, np.int64)
        for k in kk:
            cc = keys[k]; comb = comb * (cc.max() + 1) + cc
        _, inv = np.unique(comb, return_inverse=True)
        nl = inv.max() + 1
        sm = np.zeros((nl, C)); cn = np.bincount(inv, minlength=nl).astype(float)
        np.add.at(sm, inv, F)
        mn = sm / cn[:, None]; wv = cn / cn.sum()
        gm = (wv[:, None] * mn).sum(0)
        return float((wv[:, None] * (mn - gm) ** 2).sum(0).sum())

    allf = list(keys)
    sens = pd.DataFrame([
        {"faktor": f,
         "haupteffekt": round(float(np.clip(expl([f]) / vt, 0, 1)), 4),
         "totaleffekt": round(float(np.clip(1 - expl([g for g in allf if g != f]) / vt, 0, 1)), 4)}
        for f in allf]).sort_values("haupteffekt", ascending=False)
    sens.to_csv(OUT / "out_sensitivity.csv", index=False)
    print(f"\nANOVA (Summe Haupteffekte {sens.haupteffekt.sum():.3f}):")
    print(sens.to_string(index=False))

    # Unabhaengigkeit der vier Achsen
    A = {}
    for ax in SCORE_AXES:
        ms = [m for m in keep if ax_of[m] == ax]
        sub = P[ms].rank(pct=True)
        A[AXIS_NAME[ax]] = sub.mean(axis=1)
    Cm = pd.DataFrame(A).corr(method="spearman").round(2)
    Cm.to_csv(OUT / "achsen_korrelation.csv")
    print("\nKorrelation der vier Achsen untereinander:")
    print(Cm.to_string())


if __name__ == "__main__":
    run()
