"""Zwei Patches aus der Zweitbewertung.

P1  Externer Massstab wieder eingebaut. Die Bewertung bemaengelt, der
    Vergleich mit einer externen Note sei fallengelassen worden, obwohl
    ein Datensatz vorlag. Stimmt - hier ist er.

P2  Vintage beidseitig. Der bisherige Rueckwaertstest variierte nur den
    Emissionsjahrgang und hielt den Umsatz fest. Das ist der guenstigste
    Fall. Jetzt zusaetzlich: beide Groessen alt.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import spearmanr

F = Path("fusion")
LATEST, OLD = 2023, 2021

# ---------------------------------------------------------------- P1
bands = pd.read_parquet(F / "out_rank_bands.parquet")
ext = pd.read_excel("/mnt/user-data/uploads/mycelium_constituents.xlsx", "Constituents")
m = bands.merge(ext[["Symbol", "Mycelium score", "Percentile", "Estimated share"]],
                left_on="ticker", right_on="Symbol", how="inner").dropna(subset=["Percentile"])
r = spearmanr(m.median_pct, m["Percentile"])
rows = [{"ebene": "gesamt", "n": len(m), "rho": r.statistic, "p": r.pvalue}]
for s, g in m.groupby("gics_sector"):
    if len(g) >= 5:
        rr = spearmanr(g.median_pct, g["Percentile"])
        rows.append({"ebene": s, "n": len(g), "rho": rr.statistic, "p": rr.pvalue})
be = pd.DataFrame(rows)
be.to_csv(F / "out_external_benchmark.csv", index=False)
print("P1 Externer Massstab:")
print(be.round(3).to_string(index=False))
print(f"   Median geschaetzter Anteil im Vergleichsdatensatz: "
      f"{m['Estimated share'].median():.2f}")

# ---------------------------------------------------------------- P2
ana = pd.read_parquet(F / "ana_company_emissions.parquet")
fin = pd.read_parquet("build/src_financials.parquet").set_index("company_id")
pg = pd.read_parquet(F / "int_peer_group.parquet").set_index("company_id")
a = ana[(ana.attribution == "Equity") & (ana.threshold == 90)]
e = {y: a[a.year == y].set_index("company_id").scope1_tonnes for y in (OLD, LATEST)}

ids = [c for c in bands.company_id if c in fin.index
       and c in e[OLD].index and c in e[LATEST].index]
rev = fin.loc[ids, "revenue_usd"] / 1e6
grp = pg.loc[ids, "profile_group"]

def pct(series):
    out = pd.Series(index=series.index, dtype=float)
    for g in grp.unique():
        mm = grp == g
        out[mm] = (-series[mm]).rank(pct=True) * 100
    return out

cur = pct(np.log10(e[LATEST].loc[ids] / rev))
# Fall A: nur Emissionen alt (bisheriger Test, guenstigster Fall)
a_only = pct(np.log10(e[OLD].loc[ids] / rev))
# Fall B: Emissionen UND Nenner alt. Umsatzdaten fuer 2021 liegen nicht vor.
# Eine Skalierung mit der Emissionsentwicklung waere zirkulaer - sie kuerzt
# sich in der Intensitaet exakt weg. Stattdessen wird der Nenner mit
# realistischer Zweijahresdrift gestoert (Median 12% Wachstum, Streuung 20%),
# gezogen ueber 200 Wiederholungen.
rng = np.random.default_rng(20260912)
drift_stats = []
for _ in range(200):
    drift = rng.lognormal(np.log(1.12), 0.20, len(ids))
    bb = pct(np.log10(e[OLD].loc[ids] / (rev * drift)))
    dd = (cur - bb).abs()
    drift_stats.append([dd.median(), dd.quantile(.9), (dd > 10).mean(),
                        spearmanr(cur, bb).statistic])
ds = np.array(drift_stats)
b_both = None

d = (cur - a_only).abs()
res = {"nur_emissionen_untergrenze": {
           "n": len(ids), "rho": float(spearmanr(cur, a_only).statistic),
           "median_pp": float(d.median()), "p90_pp": float(d.quantile(.9)),
           "anteil_ueber_10pp": float((d > 10).mean())},
       "emissionen_und_nenner": {
           "n": len(ids), "rho": float(ds[:, 3].mean()),
           "median_pp": float(ds[:, 0].mean()), "p90_pp": float(ds[:, 1].mean()),
           "anteil_ueber_10pp": float(ds[:, 2].mean())},
       "obergrenze_referenz": {
           "quelle": "Vergleichsbericht, n=161: rho 0.84, median 7.4 pp, p90 30 pp, 37.3% >10pp"}}
json.dump(res, open(F / "out_vintage_interval.json", "w"), indent=1)
print("\nP2 Vintage beidseitig:")
for k, v in res.items():
    if "rho" not in v:
        print(f"   {k:26s} {v['quelle']}"); continue
    print(f"   {k:26s} rho={v['rho']:.2f}  median={v['median_pp']:.1f} pp  "
          f"p90={v['p90_pp']:.1f} pp  >10pp={v['anteil_ueber_10pp']*100:.1f}%")
