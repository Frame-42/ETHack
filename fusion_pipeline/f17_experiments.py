"""
Zehn Experimente am fertigen Modell. Jedes beantwortet eine Frage,
die eine Jury stellen koennte - und jedes kann auch schlecht ausgehen.
"""
import json, numpy as np, pandas as pd
from pathlib import Path
from scipy.stats import spearmanr, mannwhitneyu

rng = np.random.default_rng(20260913)
D = json.loads(Path("dashboard/data.json").read_text())
T = Path("team"); OUT = Path("team_out")
d = pd.read_parquet(T / "dataset_long.parquet"); M = json.loads((T / "metrics.json").read_text())
w = d.dropna(subset=["value"]).sort_values("year").drop_duplicates(["ticker", "metric"], keep="last")
piv = w.pivot(index="ticker", columns="metric", values="value").apply(pd.to_numeric, errors="coerce")
sec = d.drop_duplicates("ticker").set_index("ticker").gics_sector.reindex(piv.index)
AX = ["A", "S", "G", "B"]; AXN = D["axes"]
firms = {f["ticker"]: f for f in D["firms"]}
score = pd.DataFrame({t: {a: f["axes"][a]["median"] for a in AX if a in f["axes"]} for t, f in firms.items()}).T
scorable = [t for t, f in firms.items() if f["scorable"]]
core = {a: [m for m in D["metrics_in_score"][a] if m in piv] for a in AX}
results = {}

def pct_in_sector(series):
    out = pd.Series(index=series.index, dtype=float)
    for g in sec.unique():
        m = (sec == g) & series.notna()
        if m.sum() > 1: out[m] = series[m].rank(pct=True) * 100
    return out

def axis_score(ms, sector_rel=True):
    cols = []
    for m in ms:
        s = piv[m] * (1 if M[m]["direction"] > 0 else -1)
        cols.append(pct_in_sector(s) if sector_rel else s.rank(pct=True) * 100)
    return pd.concat(cols, axis=1).mean(axis=1)

# ---------------------------------------------------------------- E1
print("E1  Ist die Achsen-Unabhaengigkeit stabil? (Bootstrap, 500x)")
pairs = [("A", "S"), ("A", "G"), ("A", "B"), ("S", "G"), ("S", "B"), ("G", "B")]
boot = {p: [] for p in pairs}
S = score.loc[scorable]
for _ in range(500):
    idx = rng.choice(len(S), len(S), replace=True)
    b = S.iloc[idx]
    for a, c in pairs:
        j = b[[a, c]].dropna()
        if len(j) > 20: boot[(a, c)].append(spearmanr(j[a], j[c]).statistic)
e1 = {f"{AXN[a]}/{AXN[c]}": (round(np.percentile(v, 2.5), 2), round(np.median(v), 2), round(np.percentile(v, 97.5), 2))
      for (a, c), v in boot.items() if v}
for k, (lo, md, hi) in e1.items(): print(f"    {k:28s} {md:+.2f}  [{lo:+.2f}, {hi:+.2f}]")
results["E1"] = {k: dict(lo=v[0], med=v[1], hi=v[2]) for k, v in e1.items()}
maxhi = max(v[2] for v in e1.values())
print(f"    -> groesste Obergrenze {maxhi:+.2f}: {'haelt' if maxhi < 0.5 else 'WACKELT'}")

# ---------------------------------------------------------------- E2
print("\nE2  Wie stark haengt der Offenlegungsscore an der Peer-Schwelle?")
L = pd.DataFrame([dict(t=f["ticker"], m=l["metric"], st=l["status"], pp=l["peer_pct"], ax=l["axis"])
                  for f in D["firms"] for l in f["ledger"]])
base = None; e2 = {}
for thr in [10, 20, 30, 40, 50, 60]:
    sc = {}
    for t, g in L[L.t.isin(scorable)].groupby("t"):
        exp = g[(g.st.isin(["offengelegt", "verschwiegen"])) & (g.pp >= thr)]
        if len(exp): sc[t] = 100 * (exp.st == "offengelegt").mean()
    s = pd.Series(sc)
    if base is None: base = s
    j = pd.concat([base, s], axis=1).dropna()
    rho = spearmanr(j.iloc[:, 0], j.iloc[:, 1]).statistic
    e2[thr] = dict(median=round(s.median(), 1), rho_zu_10=round(rho, 3), n=len(s))
    print(f"    Schwelle {thr:2d}%: Median {s.median():5.1f}%  rho zur 10%-Variante {rho:.3f}  (n={len(s)})")
results["E2"] = e2

# ---------------------------------------------------------------- E3
print("\nE3  Welche einzelne Kennzahl bewegt die Umweltnote am meisten? (weglassen und schauen)")
full = axis_score(core["A"]).loc[scorable]
e3 = {}
for m in core["A"]:
    red = axis_score([x for x in core["A"] if x != m]).loc[scorable]
    j = pd.concat([full, red], axis=1).dropna()
    rho = spearmanr(j.iloc[:, 0], j.iloc[:, 1]).statistic
    e3[m] = round(rho, 3); print(f"    ohne {m:18s}  rho zum vollen Score {rho:.3f}")
results["E3"] = e3

# ---------------------------------------------------------------- E4
print("\nE4  Branchenintern gegen global: wie sehr kippt die Umweltnote?")
a_sec = axis_score(core["A"], True).loc[scorable]; a_glob = axis_score(core["A"], False).loc[scorable]
j = pd.concat([a_sec, a_glob], axis=1).dropna()
rho = spearmanr(j.iloc[:, 0], j.iloc[:, 1]).statistic
flip = ((j.iloc[:, 0] >= 66.7) != (j.iloc[:, 1] >= 66.7)).mean()
print(f"    rho = {rho:.3f}; {flip*100:.0f}% der Firmen wechseln das Drittel")
results["E4"] = dict(rho=round(rho, 3), drittel_wechsel=round(flip, 3))

# ---------------------------------------------------------------- E5
print("\nE5  Zufallsvergleich: sind unsere Spannen enger als bei gewuerfelten Daten?")
real_w = np.median([f["axes"]["A"]["hi"] - f["axes"]["A"]["lo"] for t, f in firms.items() if t in scorable and "A" in f["axes"]])
sim_w = []
for _ in range(60):
    F0 = piv[core["A"]].to_numpy(dtype=float, na_value=np.nan)
    fake = F0.copy()
    for g in sec.unique():
        m = (sec == g).values
        for j in range(fake.shape[1]):
            v = fake[m, j].copy(); rng.shuffle(v); fake[m, j] = v
    sd = np.nanstd(fake, axis=0); sd[~np.isfinite(sd) | (sd == 0)] = 1.0
    # Band aus drei Normalisierungen einer Ziehung naehern: Spannweite ueber 30 Stoerungen
    scores = []
    for _ in range(30):
        X = pd.DataFrame(fake + 0.1 * sd * rng.standard_normal(fake.shape),
                         index=piv.index, columns=core["A"])
        cols = [pct_in_sector(X[m] * (1 if M[m]["direction"] > 0 else -1)) for m in core["A"]]
        scores.append(pd.concat(cols, axis=1).mean(axis=1))
    Sx = pd.concat(scores, axis=1)
    sim_w.append(float(np.nanmedian((Sx.quantile(.9, axis=1) - Sx.quantile(.1, axis=1)).loc[scorable])))
print(f"    echte Median-Spanne Umwelt: {real_w:.1f} pp | bei gewuerfelten Daten: {np.median(sim_w):.1f} pp")
print(f"    -> {'echte Struktur, Spannen sind kein Rauschen' if real_w < np.median(sim_w) else 'ACHTUNG: nicht von Zufall unterscheidbar'}")
results["E5"] = dict(real=round(real_w, 1), random=round(float(np.median(sim_w)), 1))

# ---------------------------------------------------------------- E6
print("\nE6  Mindestzahl Achsen: wie viele Firmen, wie robust?")
e6 = {}
for k in [1, 2, 3, 4]:
    ids = [t for t, f in firms.items() if f["n_axes"] >= k and "A" in f["axes"]]
    wd = [f["axes"]["A"]["hi"] - f["axes"]["A"]["lo"] for f in (firms[t] for t in ids)]
    e6[k] = dict(n=len(ids), median_breite=round(float(np.median(wd)), 1) if wd else None)
    print(f"    >= {k} Achsen: {len(ids):3d} Firmen, Median-Spanne Umwelt {np.median(wd) if wd else float('nan'):.1f} pp")
results["E6"] = e6

# ---------------------------------------------------------------- E7
print("\nE7  Groessenverzerrung je Achse (Bilanzsumme, sektorbereinigt)")
size = pct_in_sector(np.log10(piv["total_assets_usd"]))
e7 = {}
for a in AX:
    j = pd.concat([score.loc[scorable, a], size.loc[scorable]], axis=1).dropna()
    r = spearmanr(j.iloc[:, 0], j.iloc[:, 1])
    e7[a] = dict(rho=round(r.statistic, 3), p=round(r.pvalue, 4), n=len(j))
    print(f"    {AXN[a]:18s} rho={r.statistic:+.3f} p={r.pvalue:.3f} n={len(j)}  {'SIGNIFIKANT' if r.pvalue<.05 else ''}")
results["E7"] = e7

# ---------------------------------------------------------------- E8
print("\nE8  Wie viele Firmenpaare lassen sich ueberhaupt entscheiden? (Spannen ueberlappen nicht)")
e8 = {}
for a in AX:
    fs = [firms[t]["axes"][a] for t in scorable if a in firms[t]["axes"]]
    n = len(fs); dec = 0; tot = 0
    for i in range(n):
        for j2 in range(i + 1, n):
            tot += 1
            if fs[i]["lo"] > fs[j2]["hi"] or fs[j2]["lo"] > fs[i]["hi"]: dec += 1
    e8[a] = round(dec / tot, 3) if tot else None
    print(f"    {AXN[a]:18s} {dec/tot*100:5.1f}% der Paare entscheidbar ({n} Firmen)")
results["E8"] = e8

# ---------------------------------------------------------------- E9
print("\nE9  Wie viel der Umweltnote erklaert allein die Branche?")
raw = piv.loc[scorable, "co2_intensity"].dropna()
lr = np.log10(raw.clip(lower=1e-3))
grp = sec.loc[lr.index]
ss_tot = ((lr - lr.mean()) ** 2).sum()
ss_bet = sum(len(g) * (g.mean() - lr.mean()) ** 2 for _, g in lr.groupby(grp))
print(f"    Branche erklaert {ss_bet/ss_tot*100:.0f}% der Varianz der log-Intensitaet -> branchenintern vergleichen ist Pflicht")
results["E9"] = dict(r2_sector=round(ss_bet / ss_tot, 3))

# ---------------------------------------------------------------- E10
print("\nE10 SBTi-Befund per Permutation absichern (1000x)")
sil = [t for t, f in firms.items() if t in scorable and any(l["metric"] == "sbti_validated" and l["status"] == "verschwiegen" for l in f["ledger"])]
dis = [t for t, f in firms.items() if t in scorable and any(l["metric"] == "sbti_validated" and l["status"] == "offengelegt" for l in f["ledger"])]
g = score.loc[sil + dis, "G"].dropna()
lab = np.array([1 if t in sil else 0 for t in g.index])
obs_diff = g[lab == 1].median() - g[lab == 0].median()
perm = []
for _ in range(1000):
    p = rng.permutation(lab); perm.append(g[p == 1].median() - g[p == 0].median())
pval = np.mean(np.abs(perm) >= abs(obs_diff))
print(f"    beobachtet: Schweigende {obs_diff:+.1f} Perzentilpunkte bei Regeltreue; Permutations-p = {pval:.3f}")
results["E10"] = dict(diff=round(float(obs_diff), 1), p_perm=round(float(pval), 3), n_silent=int(lab.sum()), n_disc=int((lab == 0).sum()))

json.dump(results, open(OUT / "experiments.json", "w"), ensure_ascii=False, indent=1)
print("\nGespeichert: team_out/experiments.json")
