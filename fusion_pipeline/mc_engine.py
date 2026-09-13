"""
Ebene 3 (cfg_* / mc_* / out_*): Monte-Carlo-Maschine,
nach UML final_3_montecarlo.

Zwei getrennte Unsicherheitsquellen, beide vollstaendig gekreuzt:
  1. Datenunsicherheit  -> perturbed_value ~ dist_family(raw_value, value_se)
  2. Methodenunsicherheit -> cfg_method_space als volles Kreuzprodukt

Weil das Design voll faktoriell ist, laesst sich die Varianzzerlegung
exakt per ANOVA rechnen statt per Saltelli-Stichprobe.
"""
import itertools
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import norm as ndist

B = Path("build")
RNG_MASTER = 20260912
N_DRAWS = 200          # Datenziehungen, gekreuzt mit jeder Konfiguration
EPS = 1e-9

NORMALIZATIONS = ["Rank", "ZScoreWinsor", "MinMax"]
WEIGHTINGS = ["Equal", "Entropy", "PCA", "Expert"]
AGGREGATIONS = ["Arithmetic", "Geometric"]
PEER_LEVELS = ["Sector", "Industry", "Global"]
IMPUTATIONS = ["PeerMedian", "GlobalMedian", "Drop"]

# Expertengewichte: bewusst subjektiv und offengelegt.
# Trend zaehlt mehr als Niveau, weil das Niveau stark von der Branche abhaengt.
EXPERT_WEIGHTS = {
    "log_intensity": 0.22,   # Emissionen je Umsatz: die Kernkennzahl
    "cagr_long": 0.20,       # langfristiger Trend
    "cagr_short": 0.18,      # aktueller Trend
    "momentum": 0.12,        # beschleunigt die Reduktion?
    "coal_share": 0.15,      # Transitionsrisiko aus dem Brennstoffmix
    "asset_hhi": 0.07,
    "volatility": 0.06,
}


# ----------------------------------------------------------------------
def build_cfg_method_space():
    rows = []
    for i, (n, w, a, p, imp) in enumerate(itertools.product(
            NORMALIZATIONS, WEIGHTINGS, AGGREGATIONS, PEER_LEVELS, IMPUTATIONS), start=1):
        rows.append({
            "config_id": i, "normalization": n, "weighting": w,
            "aggregation": a, "peer_level": p, "imputation": imp,
            "winsor_pct": 0.05,
            "is_baseline": (n == "Rank" and w == "Equal" and a == "Geometric"
                            and p == "Sector" and imp == "PeerMedian"),
        })
    cfg = pd.DataFrame(rows)
    cfg.to_parquet(B / "cfg_method_space.parquet", index=False)
    print(f"cfg_method_space: {len(cfg)} Konfigurationen "
          f"({len(NORMALIZATIONS)}x{len(WEIGHTINGS)}x{len(AGGREGATIONS)}"
          f"x{len(PEER_LEVELS)}x{len(IMPUTATIONS)})")
    return cfg


# ----------------------------------------------------------------------
def load_panel():
    panel = pd.read_parquet(B / "int_indicator_panel.parquet")
    comp = pd.read_parquet(B / "src_companies.parquet")
    pg = pd.read_parquet(B / "int_peer_group.parquet")

    codes = sorted(panel.indicator_code.unique())
    ids = sorted(panel.company_id.unique())
    ci = {c: i for i, c in enumerate(ids)}
    ki = {k: i for i, k in enumerate(codes)}

    C, K = len(ids), len(codes)
    V = np.full((C, K), np.nan)
    S = np.full((C, K), np.nan)
    IMP = np.zeros((C, K), bool)
    FAM = np.empty((C, K), dtype=object)

    for r in panel.itertuples():
        i, j = ci[r.company_id], ki[r.indicator_code]
        V[i, j], S[i, j] = r.raw_value, r.value_se
        IMP[i, j], FAM[i, j] = r.is_imputed, r.dist_family

    # Polaritaet: alle Indikatoren sind LowerIsBetter -> Vorzeichen drehen,
    # danach gilt durchgaengig "groesser ist besser".
    pol = np.array([1.0 if panel[panel.indicator_code == c].polarity.iloc[0]
                    == "HigherIsBetter" else -1.0 for c in codes])

    # Vergleichsgruppen. Gruppen unter MIN_PEER_N sind statistisch wertlos
    # (eine Rangnormalisierung in einer 2er-Gruppe erzeugt reines Rauschen),
    # deshalb fallen sie auf die naechsthoehere Ebene zurueck.
    MIN_PEER_N = 5
    groups = {}
    sector_map = pg[pg.peer_level == "Sector"].set_index("company_id").peer_group_id
    for lv in PEER_LEVELS:
        sub = pg[pg.peer_level == lv].set_index("company_id")
        g = []
        for cid in ids:
            if cid in sub.index and sub.loc[cid, "peer_n"] >= MIN_PEER_N:
                g.append(sub.loc[cid, "peer_group_id"])
            else:
                g.append(sector_map.get(cid, "ALL"))
        g = np.array(g, dtype=object)
        # Zweite Stufe: auch Sektoren unter MIN_PEER_N auf Global zusammenlegen
        u, cnt = np.unique(g, return_counts=True)
        small = set(u[cnt < MIN_PEER_N])
        g = np.array(["ALL" if x in small else x for x in g], dtype=object)
        groups[lv] = g
    for lv in PEER_LEVELS:
        u, cnt = np.unique(groups[lv], return_counts=True)
        print(f"  peer_level={lv}: {len(u)} effektive Gruppen, "
              f"kleinste {cnt.min()}, median {int(np.median(cnt))}")

    meta = comp.set_index("company_id").loc[ids]
    return dict(ids=ids, codes=codes, V=V, S=S, IMP=IMP, FAM=FAM,
                pol=pol, groups=groups, meta=meta)


# ----------------------------------------------------------------------
def draw_data(P, rng, n_draws):
    """Datenunsicherheit: eine Stichprobe je Zelle und Ziehung."""
    V, S, FAM = P["V"], P["S"], P["FAM"]
    C, K = V.shape
    X = V[None, :, :] + S[None, :, :] * rng.standard_normal((n_draws, C, K))
    # Beta-verteilte Groessen (Anteile) im Einheitsintervall halten
    is_beta = (FAM == "Beta")
    if is_beta.any():
        X[:, is_beta] = np.clip(X[:, is_beta], 1e-4, 1 - 1e-4)
    return X


# ----------------------------------------------------------------------
def normalize(X, method, gidx, winsor_pct):
    """Normalisierung innerhalb der Vergleichsgruppe.

    Ergebnis liegt immer in (0, 1], damit auch die geometrische
    Aggregation definiert ist.
    """
    D, C, K = X.shape
    out = np.empty_like(X)
    for g in np.unique(gidx):
        m = (gidx == g)
        sub = X[:, m, :]
        n = m.sum()
        if n == 1:
            out[:, m, :] = 0.5
            continue
        if method == "Rank":
            order = sub.argsort(axis=1).argsort(axis=1).astype(float)
            out[:, m, :] = (order + 0.5) / n
        elif method == "MinBase":
            pass
        elif method == "MinMax":
            lo = sub.min(axis=1, keepdims=True)
            hi = sub.max(axis=1, keepdims=True)
            out[:, m, :] = (sub - lo) / np.maximum(hi - lo, EPS)
        elif method == "ZScoreWinsor":
            lo = np.quantile(sub, winsor_pct, axis=1, keepdims=True)
            hi = np.quantile(sub, 1 - winsor_pct, axis=1, keepdims=True)
            w = np.clip(sub, lo, hi)
            mu = w.mean(axis=1, keepdims=True)
            sd = np.maximum(w.std(axis=1, keepdims=True), EPS)
            out[:, m, :] = ndist.cdf((w - mu) / sd)
        else:
            raise ValueError(method)
    return np.clip(out, 0.01, 1.0)


# ----------------------------------------------------------------------
def compute_weights(Z, method, codes):
    """Gewichte je Ziehung. Form (D, K), Zeilensumme 1."""
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
    if method == "PCA":
        Zc = Z - Z.mean(axis=1, keepdims=True)
        W = np.empty((D, K))
        for d in range(D):
            _, s, vt = np.linalg.svd(Zc[d], full_matrices=False)
            load = np.abs(vt[0]) * s[0]
            W[d] = load / max(load.sum(), EPS)
        return W
    raise ValueError(method)


# ----------------------------------------------------------------------
def aggregate(Z, W, method):
    if method == "Arithmetic":
        return (Z * W[:, None, :]).sum(axis=2)
    if method == "Geometric":
        return np.exp((W[:, None, :] * np.log(np.maximum(Z, EPS))).sum(axis=2))
    raise ValueError(method)


def apply_imputation(X, IMP, method, gidx):
    """Behandlung imputierter Zellen; Drop setzt sie auf den Gruppenmedian
    und wird beim Gewichten faktisch neutralisiert."""
    if not IMP.any():
        return X
    Y = X.copy()
    for g in np.unique(gidx):
        m = (gidx == g)
        if method == "PeerMedian":
            fill = np.median(Y[:, m, :], axis=1, keepdims=True)
        elif method == "GlobalMedian":
            fill = np.median(Y, axis=1, keepdims=True)
        else:  # Drop -> auf Gruppenmedian setzen (neutral)
            fill = np.median(Y[:, m, :], axis=1, keepdims=True)
        sub = Y[:, m, :]
        mask = np.broadcast_to(IMP[m, :], sub.shape)
        sub = np.where(mask, np.broadcast_to(fill, sub.shape), sub)
        Y[:, m, :] = sub
    return Y


# ----------------------------------------------------------------------
def run_simulation(P, cfg, n_draws=N_DRAWS, seed=RNG_MASTER):
    """Volles Kreuzprodukt: jede Konfiguration sieht dieselben Datenziehungen.

    Dadurch ist das Design voll faktoriell und die Varianzzerlegung exakt.
    """
    rng = np.random.default_rng(seed)
    Xbase = draw_data(P, rng, n_draws)          # (D, C, K)
    Xor = Xbase * P["pol"][None, None, :]       # Polaritaet angewandt

    C = Xbase.shape[1]
    n_cfg = len(cfg)
    RANK = np.empty((n_cfg, n_draws, C), dtype=np.int16)
    SCORE = np.empty((n_cfg, n_draws, C), dtype=np.float32)

    gidx_cache = {lv: P["groups"][lv] for lv in PEER_LEVELS}

    for row in cfg.itertuples():
        gidx = gidx_cache[row.peer_level]
        X = apply_imputation(Xor, P["IMP"], row.imputation, gidx)
        Z = normalize(X, row.normalization, gidx, row.winsor_pct)
        W = compute_weights(Z, row.weighting, P["codes"])
        sc = aggregate(Z, W, row.aggregation)              # (D, C)
        # Globaler Rang 1 = bester Score
        rk = (-sc).argsort(axis=1).argsort(axis=1) + 1
        idx = row.config_id - 1
        SCORE[idx] = sc.astype(np.float32)
        RANK[idx] = rk.astype(np.int16)

    print(f"mc_company_score: {n_cfg} Konfigurationen x {n_draws} Ziehungen "
          f"x {C} Firmen = {n_cfg*n_draws*C:,} Score-Zeilen")
    return SCORE, RANK


# ----------------------------------------------------------------------
def out_rank_distribution(RANK, P, run_id=1):
    n_cfg, D, C = RANK.shape
    flat = RANK.reshape(-1, C)
    dec = max(1, C // 10)
    rows = []
    for i, cid in enumerate(P["ids"]):
        r = flat[:, i]
        iqr = int(np.percentile(r, 75) - np.percentile(r, 25))
        rows.append({
            "run_id": run_id, "company_id": cid,
            "median_rank": int(np.median(r)),
            "rank_p05": int(np.percentile(r, 5)),
            "rank_p95": int(np.percentile(r, 95)),
            "rank_iqr": iqr,
            "rank_min": int(r.min()), "rank_max": int(r.max()),
            "p_top_decile": float((r <= dec).mean()),
            "p_bottom_decile": float((r > C - dec).mean()),
            "stability": "Robust" if iqr <= max(3, C * 0.08) else "Unstable",
        })
    out = pd.DataFrame(rows)
    meta = P["meta"].reset_index()[["company_id", "ticker", "company_name", "gics_sector"]]
    out = out.merge(meta, on="company_id")
    out = out.sort_values("median_rank").reset_index(drop=True)
    out.to_parquet(B / "out_rank_distribution.parquet", index=False)
    print(f"out_rank_distribution: {len(out)} Firmen, "
          f"{(out.stability=='Robust').sum()} robust, "
          f"median Rangbreite (p95-p05) = {int((out.rank_p95-out.rank_p05).median())}")
    return out


# ----------------------------------------------------------------------
def out_sensitivity(RANK, cfg, run_id=1):
    """Exakte Varianzzerlegung auf dem voll faktoriellen Design.

    S_f   = Var(E[Y | X_f]) / Var(Y)                  (Haupteffekt)
    S_T_f = 1 - Var(E[Y | X_~f]) / Var(Y)             (Totaleffekt)

    Y ist der firmenzentrierte Rang: es geht um Rang-Instabilitaet,
    nicht darum, dass Firmen unterschiedliche Raenge haben.
    """
    n_cfg, D, C = RANK.shape
    Y = RANK.astype(np.float64)
    Y = Y - Y.mean(axis=(0, 1), keepdims=True)     # je Firma zentrieren
    F = Y.reshape(n_cfg * D, C)                    # (N, C)
    var_per_company = F.var(axis=0)
    var_tot = var_per_company.sum()

    cfg_factors = {
        "Normalization": cfg.normalization.values,
        "Weighting": cfg.weighting.values,
        "Aggregation": cfg.aggregation.values,
        "PeerLevel": cfg.peer_level.values,
        "Imputation": cfg.imputation.values,
    }
    # Faktorstufen auf das (config, draw)-Gitter ausrollen
    keys = {k: np.repeat(pd.factorize(v)[0], D) for k, v in cfg_factors.items()}
    keys["DataNoise"] = np.tile(np.arange(D), n_cfg)
    allf = list(keys)

    def explained(keep):
        """Var(E[Y | Faktoren in keep]), ueber Firmen aufsummiert."""
        if not keep:
            return 0.0
        comb = np.zeros(n_cfg * D, dtype=np.int64)
        for k in keep:
            c = keys[k]
            comb = comb * (c.max() + 1) + c
        _, inv = np.unique(comb, return_inverse=True)
        nlev = inv.max() + 1
        sums = np.zeros((nlev, C))
        cnts = np.bincount(inv, minlength=nlev).astype(float)
        np.add.at(sums, inv, F)
        means = sums / cnts[:, None]
        w = cnts / cnts.sum()
        gm = (w[:, None] * means).sum(axis=0)
        return float((w[:, None] * (means - gm) ** 2).sum(axis=0).sum())

    rows = []
    for f in allf:
        s1 = explained([f]) / var_tot
        s_not = explained([g for g in allf if g != f]) / var_tot
        rows.append({"run_id": run_id, "factor": f,
                     "sobol_first_order": float(np.clip(s1, 0, 1)),
                     "sobol_total": float(np.clip(1.0 - s_not, 0, 1))})
    sens = pd.DataFrame(rows)
    tot = sens.sobol_first_order.sum()
    sens["share_of_variance"] = sens.sobol_first_order / max(tot, EPS)
    sens = sens.sort_values("sobol_first_order", ascending=False).reset_index(drop=True)
    sens.to_parquet(B / "out_sensitivity.parquet", index=False)
    print(f"out_sensitivity: Summe Haupteffekte = {tot:.3f} "
          f"(Rest {1-tot:.3f} sind Wechselwirkungen)")
    print(sens.round(4).to_string(index=False))
    return sens


if __name__ == "__main__":
    cfg = build_cfg_method_space()
    P = load_panel()
    print(f"Panel: {len(P['ids'])} Firmen x {len(P['codes'])} Indikatoren")
    SCORE, RANK = run_simulation(P, cfg)
    np.save(B / "mc_rank.npy", RANK)
    np.save(B / "mc_score.npy", SCORE)
    out_rank_distribution(RANK, P)
    out_sensitivity(RANK, cfg)
