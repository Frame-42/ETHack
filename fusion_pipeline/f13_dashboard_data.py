"""
Daten fuer das Dashboard: alles je Firma, als eine JSON-Datei.

Was hier zum ersten Mal zusammenkommt:
  - vier Achsen mit Perzentilband (aus Monte Carlo je Achse)
  - die Offenlegungsbilanz mit der Unterscheidung
        offengelegt | nicht anwendbar | verschwiegen
  - die schwaechste Achse (Liebig: ein System ist so gut wie sein Minimum)
  - zwei Listen: bewertbar / nicht bewertbar, mit Grund
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import norm as ndist, spearmanr

T = Path("team"); OUT = Path("team_out")
SEED, DRAWS = 20260912, 60
AX = ["A", "S", "G", "B"]
AXN = {"A": "Umwelt", "S": "Soziales", "G": "Regeltreue", "B": "Offenheit & Ziele"}
MIN_PEER_COV = 0.30      # Thema gilt als "von Peers offengelegt", wenn >= 30 % es haben
MIN_AXES_SCORABLE = 3

df = pd.read_parquet(T / "dataset_long.parquet")
M = json.loads((T / "metrics.json").read_text())
S = json.loads((T / "sources.json").read_text())

w = (df.dropna(subset=["value"]).sort_values("year")
       .drop_duplicates(["ticker", "metric"], keep="last"))
piv = w.pivot(index="ticker", columns="metric", values="value").apply(pd.to_numeric, errors="coerce")
tickers = sorted(df.ticker.unique())
piv = piv.reindex(tickers)
meta = df.drop_duplicates("ticker").set_index("ticker").reindex(tickers)
sector = meta.gics_sector.fillna("Unbekannt")

core = [m for m, v in M.items() if v["axis"] in AX and v["direction"] != 0 and m in piv]
# Korrelations-Gate wie in der Simulation
gate_out = []
ref = piv.get("co2_intensity")
for m in list(core):
    if m == "co2_intensity" or ref is None:
        continue
    b = piv[[m]].join(ref.rename("r")).dropna()
    if len(b) >= 25 and abs(spearmanr(b[m], b.r).statistic) > 0.30:
        core.remove(m); gate_out.append(m)
ax_of = {m: M[m]["axis"] for m in core}

# ---------------------------------------------------------------- Anwendbarkeit
def has(col):
    return piv[col].notna() & (piv[col] > 0) if col in piv else pd.Series(False, index=piv.index)

phys = has("n_facilities")
tri = has("tri_facilities")
gen = has("egrid_plants") | has("campd_plants")
wba = piv[[c for c in piv.columns if c.startswith("wba_")]].notna().any(axis=1)

DERIVED = {"intensity_cagr", "absolute_cagr", "intensity_illusion", "base_year_ratio",
           "co2_intensity"}   # von uns gerechnet; Fehlen heisst zu wenig Jahre, nicht Schweigen

def applicable(m):
    src = M[m]["source_id"]
    if m.startswith("tri_"):            return tri
    if m in ("campd_co2_t", "t_co2_pro_mwh"): return gen
    if src in ("epa_ghgrp", "epa_echo") or m in (
        "co2_intensity", "intensity_cagr", "absolute_cagr",
        "intensity_illusion", "base_year_ratio"):
        return phys
    if src == "wba":                    return wba
    return pd.Series(True, index=piv.index)   # OSHA, DOL, SBTi: gilt fuer alle

APPL = pd.DataFrame({m: applicable(m) for m in core})
DISC = piv[core].notna()

# Peer-Abdeckung je Sektor und Kennzahl: Anteil der ANWENDBAREN Peers, die offenlegen
peer_cov = {}
for sec in sector.unique():
    idx = sector[sector == sec].index
    a = APPL.loc[idx]; d = DISC.loc[idx]
    denom = a.sum(); num = (a & d).sum()
    peer_cov[sec] = (num / denom.replace(0, np.nan)).fillna(0)

# ---------------------------------------------------------------- Achsen-Baender
rng = np.random.default_rng(SEED)
def axis_band(ms):
    """Perzentil im Sektor je Firma, ueber 3 Normalisierungen x DRAWS Ziehungen."""
    V = piv[ms].to_numpy(dtype=float, na_value=np.nan)
    pol = np.array([1. if M[m]["direction"] > 0 else -1. for m in ms])
    sd = np.nanstd(V, axis=0); sd[~np.isfinite(sd) | (sd == 0)] = 1.
    res = []
    for method in ("rank", "z", "minmax"):
        for _ in range(DRAWS):
            X = (V + 0.10 * sd * rng.standard_normal(V.shape)) * pol
            P = np.full_like(X, np.nan)
            for sec in sector.unique():
                idx = np.where(sector.values == sec)[0]
                sub = X[idx]
                for j in range(len(ms)):
                    col = sub[:, j]; ok = np.isfinite(col)
                    if ok.sum() < 2: continue
                    v = col[ok]
                    if method == "rank":
                        p = v.argsort().argsort() / (len(v) - 1)
                    elif method == "z":
                        p = ndist.cdf((v - v.mean()) / max(v.std(), 1e-9))
                    else:
                        p = (v - v.min()) / max(v.max() - v.min(), 1e-9)
                    tmp = np.full(len(idx), np.nan); tmp[ok] = p
                    P[idx, j] = tmp
            res.append(np.nanmean(P, axis=1) * 100)
    R = np.array(res)
    return np.nanmedian(R, 0), np.nanpercentile(R, 10, 0), np.nanpercentile(R, 90, 0)

bands = {}
for ax in AX:
    ms = [m for m in core if ax_of[m] == ax]
    med, lo, hi = axis_band(ms)
    bands[ax] = dict(med=med, lo=lo, hi=hi, n=DISC[ms].sum(axis=1).values, metrics=ms)

# ---------------------------------------------------------------- je Firma
firms = []
for i, t in enumerate(tickers):
    sec = sector[t]
    axes = {}
    for ax in AX:
        b = bands[ax]
        if np.isfinite(b["med"][i]) and b["n"][i] > 0:
            axes[ax] = dict(median=round(float(b["med"][i]), 1),
                            lo=round(float(b["lo"][i]), 1), hi=round(float(b["hi"][i]), 1),
                            n_metrics=int(b["n"][i]),
                            robust=bool(b["hi"][i] - b["lo"][i] <= 25))
    n_axes = len(axes)

    ledger = []
    for m in core:
        appl = bool(APPL.at[t, m]); disc = bool(DISC.at[t, m])
        cov = float(peer_cov[sec].get(m, 0))
        expected = appl and cov >= MIN_PEER_COV
        if disc: status = "offengelegt"
        elif m in DERIVED: status = "nicht berechenbar"
        elif not appl: status = "nicht anwendbar"
        elif expected: status = "verschwiegen"
        else: status = "nicht erwartet"
        ledger.append(dict(metric=m, label=M[m]["label"], axis=ax_of[m],
                           status=status, peer_pct=round(cov * 100),
                           value=(None if not disc else float(piv.at[t, m]))))
    exp = [l for l in ledger if l["status"] in ("offengelegt", "verschwiegen")
           and l["peer_pct"] >= MIN_PEER_COV * 100]
    n_exp = len(exp); n_disc = sum(l["status"] == "offengelegt" for l in exp)
    disc_score = round(100 * n_disc / n_exp) if n_exp else None
    silent = [l["label"] for l in ledger if l["status"] == "verschwiegen"]
    # Fuer die Offenlegungsquote zaehlen nur Angaben, die die Firma selbst macht

    binding = min(axes, key=lambda a: axes[a]["median"]) if axes else None
    scorable = n_axes >= MIN_AXES_SCORABLE
    reason = None if scorable else (
        "keine Nachhaltigkeitsdaten in einer freien Quelle" if n_axes == 0 else
        f"nur {n_axes} von 4 Achsen belegt - ein Vergleich waere Zufall")

    firms.append(dict(
        ticker=t, name=str(meta.company[t]) if pd.notna(meta.company[t]) else t,
        sector=sec, sub=str(meta.gics_sub_industry[t]) if pd.notna(meta.gics_sub_industry[t]) else "",
        axes=axes, n_axes=n_axes, scorable=scorable, reason=reason,
        binding=binding, binding_name=AXN.get(binding),
        disclosure=dict(score=disc_score, expected=n_exp, disclosed=n_disc, silent=silent),
        ledger=ledger,
    ))

# ---------------------------------------------------------------- global
sect_cov = []
for sec in sorted(sector.unique()):
    idx = sector[sector == sec].index
    f = [x for x in firms if x["sector"] == sec]
    sect_cov.append(dict(sector=sec, n=len(f),
                         scorable=sum(x["scorable"] for x in f),
                         axes={ax: int(sum(ax in x["axes"] for x in f)) for ax in AX}))

axis_corr = {}
Aval = {ax: pd.Series(bands[ax]["med"], index=tickers) for ax in AX}
for a in AX:
    for b in AX:
        if a < b:
            j = pd.concat([Aval[a], Aval[b]], axis=1).dropna()
            axis_corr[f"{AXN[a]} vs {AXN[b]}"] = round(float(spearmanr(j.iloc[:, 0], j.iloc[:, 1]).statistic), 2)

sens = pd.read_csv(OUT / "out_sensitivity.csv") if (OUT / "out_sensitivity.csv").exists() else None
scorable_n = sum(f["scorable"] for f in firms)

payload = dict(
    generated="2026-09-12",
    n_total=len(firms), n_any=sum(f["n_axes"] > 0 for f in firms), n_scorable=scorable_n,
    n_all_four=sum(f["n_axes"] == 4 for f in firms),
    axes=AXN, gate_out=gate_out, metrics_in_score={ax: bands[ax]["metrics"] for ax in AX},
    sector_coverage=sect_cov, axis_corr=axis_corr,
    sensitivity=(sens.to_dict("records") if sens is not None else []),
    sources={k: dict(name=v["name"], license=v["license"], measurement=v["measurement"],
                     caveat=v["caveat"]) for k, v in S.items()},
    firms=firms,
)
Path("dashboard").mkdir(exist_ok=True)
(Path("dashboard") / "data.json").write_text(json.dumps(payload, ensure_ascii=False))
print(f"Firmen: {len(firms)} | mit Daten: {payload['n_any']} | bewertbar (>= {MIN_AXES_SCORABLE} Achsen): "
      f"{scorable_n} | alle vier: {payload['n_all_four']}")
print("Achsen-Korrelation:", axis_corr)
print("Gate raus:", gate_out)
sil = pd.Series([len(f["disclosure"]["silent"]) for f in firms if f["scorable"]])
print(f"Verschwiegene Themen je bewertbare Firma: median {sil.median():.0f}, max {sil.max()}")
ds = pd.Series([f["disclosure"]["score"] for f in firms if f["disclosure"]["score"] is not None])
print(f"Offenlegungsscore: median {ds.median():.0f} %, p10 {ds.quantile(.1):.0f} %, p90 {ds.quantile(.9):.0f} %")
