"""
Simulation auf dem Team-Datensatz: sieben Achsen statt einer.

Gegenueber der bisherigen Fassung kommt eine Dimension dazu, die es vorher
nicht geben konnte: die Gewichtung ZWISCHEN den Achsen. Solange nur Umwelt
gemessen wurde, gab es diese Frage nicht. Jetzt lautet sie: Wie stark zaehlt
Regeltreue gegen Emissionen?

Das ist eine Ermessensentscheidung, fuer die es keine richtige Antwort gibt.
Also wird sie wie jede andere behandelt: als Achse im Kombinationsraum,
deren Beitrag zur Streuung am Ende gemessen wird.
"""
import itertools
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import norm as ndist

OUT = Path("team_out")
SEED = 20260912
N_DRAWS = 100
EPS = 1e-9

NORMALIZATIONS = ["Rank", "ZScoreWinsor", "MinMax"]
AGGREGATIONS = ["Arithmetic", "Geometric"]
PEER_LEVELS = ["Sector", "SubIndustry", "Global"]
IMPUTATIONS = ["PeerMedian", "GlobalMedian"]
MIN_PEER = 8

# Vier Gewichtungsprofile fuer die Achsen. Bewusst unterschiedlich in der
# Haltung, damit die Simulation misst, wie viel diese Haltung ausmacht.
AXIS_WEIGHTS = {
    "Gleich":        None,                      # alle Achsen gleich
    "Umweltlastig":  {"A": 0.60, "G": 0.15, "S": 0.15, "B": 0.10},
    "Ausgewogen":    {"A": 0.40, "G": 0.25, "S": 0.20, "B": 0.15},
    "Verhaltenslastig": {"A": 0.25, "G": 0.35, "S": 0.25, "B": 0.15},
}
# Achse B (Glaubwuerdigkeit) kann per Schalter ganz aus dem Score genommen
# werden - das war die bisherige Haltung und bleibt eine Option.
B_IN_SCORE = [False, True]


def load():
    wide = pd.read_parquet(OUT / "wide_latest.parquet")
    meta = pd.read_parquet(OUT / "meta.parquet")
    keep = pd.read_csv(OUT / "score_metrics.csv").metric.tolist()
    cov = pd.read_csv(OUT / "gate_abdeckung.csv").set_index("metric")
    axis = cov.achse.to_dict()
    direction = cov.richtung.to_dict()
    return wide, meta, keep, axis, direction


def peer_groups(meta, level):
    if level == "Global":
        return np.array(["ALL"] * len(meta), dtype=object)
    col = "gics_sector" if level == "Sector" else "gics_sub_industry"
    g = meta[col].fillna("Unbekannt").astype(str).values.copy()
    # Gruppen unter der Mindestgroesse auf Sektor bzw. Global zurueckfallen
    u, c = np.unique(g, return_counts=True)
    small = set(u[c < MIN_PEER])
    if level == "SubIndustry":
        fallback = meta["gics_sector"].fillna("Unbekannt").astype(str).values
    else:
        fallback = np.array(["ALL"] * len(meta), dtype=object)
    g = np.array([fallback[i] if g[i] in small else g[i] for i in range(len(g))],
                 dtype=object)
    u, c = np.unique(g, return_counts=True)
    small = set(u[c < MIN_PEER])
    g = np.array(["ALL" if x in small else x for x in g], dtype=object)
    return g


def normalize(X, method, gidx, winsor=0.05):
    D, C, K = X.shape
    out = np.empty_like(X)
    for grp in np.unique(gidx):
        m = gidx == grp
        sub = X[:, m, :]
        n = int(m.sum())
        if n == 1:
            out[:, m, :] = 0.5
            continue
        if method == "Rank":
            out[:, m, :] = (sub.argsort(axis=1).argsort(axis=1) + 0.5) / n
        elif method == "MinMax":
            lo, hi = sub.min(axis=1, keepdims=True), sub.max(axis=1, keepdims=True)
            out[:, m, :] = (sub - lo) / np.maximum(hi - lo, EPS)
        else:
            lo = np.quantile(sub, winsor, axis=1, keepdims=True)
            hi = np.quantile(sub, 1 - winsor, axis=1, keepdims=True)
            w = np.clip(sub, lo, hi)
            mu = w.mean(axis=1, keepdims=True)
            sd = np.maximum(w.std(axis=1, keepdims=True), EPS)
            out[:, m, :] = ndist.cdf((w - mu) / sd)
    return np.clip(out, 0.01, 1.0)


def run():
    wide, meta, keep, axis, direction = load()
    keep = [m for m in keep if m in wide.columns]
    ax = np.array([str(axis.get(m, "A")) for m in keep], dtype=object)
    pol = np.array([1.0 if float(direction.get(m, -1)) > 0 else -1.0 for m in keep])

    V = wide[keep].values.astype(float)
    C, K = V.shape
    imputed = np.isnan(V)
    print(f"Panel: {C} Firmen x {K} Score-Kennzahlen, "
          f"{imputed.mean()*100:.1f} Prozent Luecken")
    print("Achsenbesetzung:", {a: int((ax == a).sum()) for a in np.unique(ax)})

    # Fehlerbalken: ohne gemeldete Unsicherheit konservativ aus der
    # Querschnittsstreuung je Kennzahl abgeleitet und als Annahme markiert.
    sd = np.nanstd(V, axis=0)
    SE = np.tile(0.10 * sd, (C, 1))
    SE[imputed] = np.tile(sd, (C, 1))[imputed]      # Luecken: volle Streuung

    configs = []
    cid = 0
    for n, a, p, imp, aw, binscore in itertools.product(
            NORMALIZATIONS, AGGREGATIONS, PEER_LEVELS, IMPUTATIONS,
            AXIS_WEIGHTS, B_IN_SCORE):
        cid += 1
        configs.append({"config_id": cid, "normalization": n, "aggregation": a,
                        "peer_level": p, "imputation": imp,
                        "axis_weights": aw, "b_in_score": binscore})
    cfg = pd.DataFrame(configs)
    print(f"Konfigurationen: {len(cfg)} "
          f"({len(NORMALIZATIONS)}x{len(AGGREGATIONS)}x{len(PEER_LEVELS)}"
          f"x{len(IMPUTATIONS)}x{len(AXIS_WEIGHTS)}x{len(B_IN_SCORE)})")

    rng = np.random.default_rng(SEED)
    Z = rng.standard_normal((N_DRAWS, C, K))
    base = np.where(imputed, np.nanmedian(V, axis=0), V)
    PCT = np.empty((len(cfg), N_DRAWS, C), dtype=np.float32)

    gcache = {lv: peer_groups(meta, lv) for lv in PEER_LEVELS}

    for row in cfg.itertuples():
        gidx = gcache[row.peer_level]
        X = base[None, :, :] + SE[None, :, :] * Z
        if row.imputation == "GlobalMedian":
            fill = np.nanmedian(base, axis=0)
            X = np.where(np.broadcast_to(imputed, X.shape),
                         np.broadcast_to(fill, X.shape), X)
        X = X * pol[None, None, :]
        N = normalize(X, row.normalization, gidx)

        # Achsenscore, dann Achsengewichtung
        axes_used = [a for a in np.unique(ax) if row.b_in_score or a != "B"]
        parts, wts = [], []
        prof = AXIS_WEIGHTS[row.axis_weights]
        for a in axes_used:
            sel = ax == a
            if not sel.any():
                continue
            sub = N[:, :, sel]
            parts.append(sub.mean(axis=2) if row.aggregation == "Arithmetic"
                         else np.exp(np.log(np.maximum(sub, EPS)).mean(axis=2)))
            wts.append(1.0 if prof is None else prof.get(str(a), 0.1))
        w = np.array(wts); w = w / w.sum()
        P = np.stack(parts, axis=2)
        sc = ((P * w[None, None, :]).sum(axis=2) if row.aggregation == "Arithmetic"
              else np.exp((w[None, None, :] * np.log(np.maximum(P, EPS))).sum(axis=2)))

        pct = np.empty_like(sc)
        for grp in np.unique(gidx):
            m = gidx == grp
            s = sc[:, m]; n = int(m.sum())
            pct[:, m] = s.argsort(axis=1).argsort(axis=1) / max(n - 1, 1) * 100
        PCT[row.config_id - 1] = pct.astype(np.float32)

    np.save(OUT / "mc_pct.npy", PCT)
    cfg.to_csv(OUT / "cfg.csv", index=False)
    print(f"Simulation: {len(cfg)} x {N_DRAWS} x {C} = {len(cfg)*N_DRAWS*C:,} Werte")

    # --- Baender ---
    flat = PCT.reshape(-1, C)
    bands = pd.DataFrame({
        "ticker": wide.index,
        "median_pct": np.median(flat, axis=0),
        "p10": np.percentile(flat, 10, axis=0),
        "p90": np.percentile(flat, 90, axis=0)})
    bands["breite_pp"] = (bands.p90 - bands.p10).round(1)
    bands = bands.join(meta.reset_index(drop=True).set_index(wide.index), on="ticker")
    bands.sort_values("median_pct", ascending=False).to_csv(
        OUT / "out_rank_bands.csv", index=False)
    print(f"Median-Bandbreite: {bands.breite_pp.median():.1f} Perzentilpunkte")

    # --- ANOVA ---
    Y = PCT.astype(np.float64)
    Y = Y - Y.mean(axis=(0, 1), keepdims=True)
    F = Y.reshape(len(cfg) * N_DRAWS, C)
    var_tot = F.var(axis=0).sum()
    keys = {k: np.repeat(pd.factorize(cfg[k])[0], N_DRAWS)
            for k in ["normalization", "aggregation", "peer_level",
                      "imputation", "axis_weights", "b_in_score"]}
    keys["Verteilungsziehung"] = np.tile(np.arange(N_DRAWS), len(cfg))

    def expl(kk):
        comb = np.zeros(len(cfg) * N_DRAWS, dtype=np.int64)
        for k in kk:
            c = keys[k]; comb = comb * (c.max() + 1) + c
        _, inv = np.unique(comb, return_inverse=True)
        nl = inv.max() + 1
        sums = np.zeros((nl, C)); cnts = np.bincount(inv, minlength=nl).astype(float)
        np.add.at(sums, inv, F)
        means = sums / cnts[:, None]
        w = cnts / cnts.sum()
        gm = (w[:, None] * means).sum(axis=0)
        return float((w[:, None] * (means - gm) ** 2).sum(axis=0).sum())

    allf = list(keys)
    rows = [{"faktor": f,
             "haupteffekt": round(float(np.clip(expl([f]) / var_tot, 0, 1)), 4),
             "totaleffekt": round(float(np.clip(1 - expl([g for g in allf if g != f]) / var_tot, 0, 1)), 4)}
            for f in allf]
    sens = pd.DataFrame(rows).sort_values("haupteffekt", ascending=False)
    sens.to_csv(OUT / "out_sensitivity.csv", index=False)
    print(f"\nANOVA (Summe Haupteffekte {sens.haupteffekt.sum():.3f}):")
    print(sens.to_string(index=False))


if __name__ == "__main__":
    run()
