"""
Fusionspipeline, Stufe 3: Simulation.

Behebt:
  K8  Zurechnungsregel und Matching-Schwelle sind jetzt Achsen im
      Kombinationsraum, nicht versteckte Festlegungen im Code.
  K9  Vergleichsgruppenschema (datengetrieben vs. GICS) ebenfalls.
  K10 Die Zerlegung trennt gemessene Datenvarianz (Zurechnung, Schwelle)
      von gesetztem Rauschen (Verteilungsziehung).

Kombinationsraum
  Methode: 3 Normalisierung x 4 Gewichtung x 2 Aggregation
           x 2 Gruppenschema x 2 Luecken = 96
  Daten:   2 Zurechnung x 4 Schwelle = 8
  gesamt   768 Konfigurationen x 100 Ziehungen = 76 800 Ranglisten
"""
import itertools
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import norm as ndist

F = Path("fusion")
SEED = 20260912
N_DRAWS = 100
EPS = 1e-9

NORMALIZATIONS = ["Rank", "ZScoreWinsor", "MinMax"]
WEIGHTINGS = ["Equal", "Entropy", "PCA", "Expert"]
AGGREGATIONS = ["Arithmetic", "Geometric"]
PEER_SCHEMES = ["Profile", "GICS"]
IMPUTATIONS = ["PeerMedian", "GlobalMedian"]
ATTRIBUTIONS = ["Equity", "Control"]
THRESHOLDS = [85, 90, 92, 95]

EXPERT_WEIGHTS = {
    "log_intensity": 0.26,
    "trend_rel": 0.22,
    "karzinogen_anteil": 0.14,   # zweite Umweltdimension, unabhaengig von CO2
    "momentum": 0.13,
    "coal_share": 0.13,
    "asset_hhi": 0.06,
    "volatility": 0.06,
}


def build_config_space():
    rows = []
    cid = 0
    for n, w, a, p, imp in itertools.product(
            NORMALIZATIONS, WEIGHTINGS, AGGREGATIONS, PEER_SCHEMES, IMPUTATIONS):
        for att, th in itertools.product(ATTRIBUTIONS, THRESHOLDS):
            cid += 1
            rows.append({"config_id": cid, "normalization": n, "weighting": w,
                         "aggregation": a, "peer_scheme": p, "imputation": imp,
                         "attribution": att, "threshold": th,
                         "is_baseline": (n == "Rank" and w == "Equal"
                                         and a == "Geometric" and p == "Profile"
                                         and imp == "PeerMedian"
                                         and att == "Equity" and th == 90)})
    cfg = pd.DataFrame(rows)
    cfg.to_parquet(F / "cfg_method_space.parquet", index=False)
    print(f"cfg_method_space: {len(cfg)} Konfigurationen "
          f"(96 Methoden x 8 Datenvarianten)")
    return cfg


def load_data():
    panel = pd.read_parquet(F / "int_indicator_panel.parquet")
    pg = pd.read_parquet(F / "int_peer_group.parquet").set_index("company_id")
    codes = sorted(panel.indicator_code.unique())
    ids = sorted(panel.company_id.unique())
    ci = {c: i for i, c in enumerate(ids)}
    ki = {k: i for i, k in enumerate(codes)}
    C, K = len(ids), len(codes)

    V, S, IMP, FAM, POL = {}, {}, {}, np.empty(K, dtype=object), np.ones(K)
    for att, th in itertools.product(ATTRIBUTIONS, THRESHOLDS):
        sub = panel[(panel.attribution == att) & (panel.threshold == th)]
        v = np.full((C, K), np.nan); s = np.full((C, K), np.nan)
        im = np.zeros((C, K), bool)
        for r in sub.itertuples():
            i, j = ci[r.company_id], ki[r.indicator_code]
            v[i, j], s[i, j], im[i, j] = r.raw_value, r.value_se, r.is_imputed
            FAM[j] = r.dist_family
            POL[j] = 1.0 if r.polarity == "HigherIsBetter" else -1.0
        V[(att, th)], S[(att, th)], IMP[(att, th)] = v, s, im

    groups = {
        "Profile": np.array([pg.loc[c, "profile_group"] for c in ids], dtype=object),
        "GICS": np.array([pg.loc[c, "gics_group"] for c in ids], dtype=object),
    }
    return dict(ids=ids, codes=codes, V=V, S=S, IMP=IMP, FAM=FAM, POL=POL,
                groups=groups, C=C, K=K)


def normalize(X, method, gidx, winsor=0.05):
    D, C, K = X.shape
    out = np.empty_like(X)
    for g in np.unique(gidx):
        m = gidx == g
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


def weights(Z, method, codes):
    D, C, K = Z.shape
    if method == "Equal":
        return np.full((D, K), 1.0 / K)
    if method == "Expert":
        w = np.array([EXPERT_WEIGHTS[c] for c in codes])
        return np.tile(w / w.sum(), (D, 1))
    if method == "Entropy":
        p = Z / np.maximum(Z.sum(axis=1, keepdims=True), EPS)
        e = -(p * np.log(np.maximum(p, EPS))).sum(axis=1) / np.log(C)
        d = np.maximum(1.0 - e, EPS)
        return d / d.sum(axis=1, keepdims=True)
    Zc = Z - Z.mean(axis=1, keepdims=True)
    W = np.empty((D, K))
    for d in range(D):
        _, sv, vt = np.linalg.svd(Zc[d], full_matrices=False)
        load = np.abs(vt[0]) * sv[0]
        W[d] = load / max(load.sum(), EPS)
    return W


def aggregate(Z, W, method):
    if method == "Arithmetic":
        return (Z * W[:, None, :]).sum(axis=2)
    return np.exp((W[:, None, :] * np.log(np.maximum(Z, EPS))).sum(axis=2))


def impute(X, IMPm, method, gidx):
    if not IMPm.any():
        return X
    Y = X.copy()
    if method == "GlobalMedian":
        fill = np.median(Y, axis=1, keepdims=True)
        mask = np.broadcast_to(IMPm, Y.shape)
        return np.where(mask, np.broadcast_to(fill, Y.shape), Y)
    for g in np.unique(gidx):
        m = gidx == g
        sub = Y[:, m, :]
        fill = np.median(sub, axis=1, keepdims=True)
        mask = np.broadcast_to(IMPm[m, :], sub.shape)
        Y[:, m, :] = np.where(mask, np.broadcast_to(fill, sub.shape), sub)
    return Y


def run(P, cfg, n_draws=N_DRAWS, seed=SEED):
    rng = np.random.default_rng(seed)
    C, K = P["C"], P["K"]
    # Gemeinsame Standardnormal-Ziehungen fuer ALLE Konfigurationen.
    # Nur so ist das Design voll faktoriell und die ANOVA exakt.
    Zs = rng.standard_normal((n_draws, C, K))

    n_cfg = len(cfg)
    SCORE = np.empty((n_cfg, n_draws, C), dtype=np.float32)
    RANKP = np.empty((n_cfg, n_draws, C), dtype=np.float32)   # Perzentil in der Gruppe

    for row in cfg.itertuples():
        key = (row.attribution, row.threshold)
        V, S, IMPm = P["V"][key], P["S"][key], P["IMP"][key]
        X = V[None, :, :] + S[None, :, :] * Zs
        beta = np.array([f == "Beta" for f in P["FAM"]])
        if beta.any():
            X[:, :, beta] = np.clip(X[:, :, beta], 1e-4, 1 - 1e-4)
        X = X * P["POL"][None, None, :]

        gidx = P["groups"][row.peer_scheme]
        X = impute(X, IMPm, row.imputation, gidx)
        Z = normalize(X, row.normalization, gidx)
        W = weights(Z, row.weighting, P["codes"])
        sc = aggregate(Z, W, row.aggregation)

        pct = np.empty_like(sc)
        for g in np.unique(gidx):
            m = gidx == g
            sub = sc[:, m]
            n = int(m.sum())
            pct[:, m] = (sub.argsort(axis=1).argsort(axis=1)) / max(n - 1, 1) * 100.0

        i = row.config_id - 1
        SCORE[i] = sc.astype(np.float32)
        RANKP[i] = pct.astype(np.float32)

    print(f"Simulation: {n_cfg} x {n_draws} x {C} = {n_cfg*n_draws*C:,} Scores")
    np.save(F / "mc_pct.npy", RANKP)
    np.save(F / "mc_score.npy", SCORE)
    return SCORE, RANKP


def anova(RANKP, cfg, run_id=1):
    """Exakte Varianzzerlegung auf dem voll faktoriellen Design."""
    n_cfg, D, C = RANKP.shape
    Y = RANKP.astype(np.float64)
    Y = Y - Y.mean(axis=(0, 1), keepdims=True)
    Fl = Y.reshape(n_cfg * D, C)
    var_tot = Fl.var(axis=0).sum()

    cf = {
        "Normalisierung": cfg.normalization.values,
        "Gewichtung": cfg.weighting.values,
        "Aggregation": cfg.aggregation.values,
        "Gruppenschema": cfg.peer_scheme.values,
        "Luecken": cfg.imputation.values,
        "Zurechnung": cfg.attribution.values,
        "Matching-Schwelle": cfg.threshold.values,
    }
    keys = {k: np.repeat(pd.factorize(v)[0], D) for k, v in cf.items()}
    keys["Verteilungsziehung"] = np.tile(np.arange(D), n_cfg)
    allf = list(keys)

    def explained(keep):
        if not keep:
            return 0.0
        comb = np.zeros(n_cfg * D, dtype=np.int64)
        for k in keep:
            c = keys[k]
            comb = comb * (c.max() + 1) + c
        _, inv = np.unique(comb, return_inverse=True)
        nl = inv.max() + 1
        sums = np.zeros((nl, C))
        cnts = np.bincount(inv, minlength=nl).astype(float)
        np.add.at(sums, inv, Fl)
        means = sums / cnts[:, None]
        w = cnts / cnts.sum()
        gm = (w[:, None] * means).sum(axis=0)
        return float((w[:, None] * (means - gm) ** 2).sum(axis=0).sum())

    rows = []
    for f in allf:
        s1 = explained([f]) / var_tot
        snot = explained([g for g in allf if g != f]) / var_tot
        rows.append({"run_id": run_id, "faktor": f,
                     "haupteffekt": float(np.clip(s1, 0, 1)),
                     "totaleffekt": float(np.clip(1 - snot, 0, 1))})
    sens = pd.DataFrame(rows).sort_values("haupteffekt", ascending=False)
    sens["art"] = np.where(sens.faktor.isin(
        ["Zurechnung", "Matching-Schwelle", "Verteilungsziehung"]),
        "Daten", "Methode")
    sens.to_parquet(F / "out_sensitivity.parquet", index=False)
    tot = sens.haupteffekt.sum()
    print(f"\nANOVA: Summe Haupteffekte {tot:.3f}, Wechselwirkungen {1-tot:.3f}")
    print(sens.round(4).to_string(index=False))
    return sens


if __name__ == "__main__":
    cfg = build_config_space()
    P = load_data()
    print(f"Panel: {P['C']} Firmen x {P['K']} Indikatoren")
    SCORE, RANKP = run(P, cfg)
    anova(RANKP, cfg)
