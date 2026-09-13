"""
Ist Schweigen ein Signal? Ein Test, kein Glaubenssatz.

Die Offenlegungsachse steht auf einer Theorie (Dye 1985): Wer Gutes zu
berichten haette, berichtet es; wer schweigt, hat vermutlich weniger Gutes.
Das ist plausibel - aber ob es in DIESEN Daten gilt, hat bisher niemand
geprueft. Hier die Pruefung:

  Firmen, die zu einem Thema schweigen (obwohl es auf sie zutrifft und die
  Branche darueber berichtet), werden mit Firmen verglichen, die reden -
  und zwar auf Kennzahlen, die BEIDE Gruppen haben und die nicht selbst
  Offenlegung sind: gemessene Emissionen, Trends, Unfaelle, Verstoesse.

  Wenn Schweigende dort systematisch schlechter dastehen, ist Schweigen
  informativ und die Achse gerechtfertigt. Wenn nicht, muss das so im
  Bericht stehen.

Zweiter Teil: Was verbirgt Schweigen? Fuer jede schweigende Firma wird
das verschwiegene Thema mit dem Branchenmedian gefuellt und die Achse neu
gerechnet. Die Verschiebung zeigt, wie viel Unsicherheit das Schweigen
in die Note bringt.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import mannwhitneyu

D = json.loads(Path("dashboard/data.json").read_text())
OUT = Path("team_out")
AXN = D["axes"]

firms = {f["ticker"]: f for f in D["firms"]}
rows = []
for f in D["firms"]:
    for l in f["ledger"]:
        rows.append(dict(ticker=f["ticker"], sector=f["sector"], metric=l["metric"],
                         label=l["label"], axis=l["axis"], status=l["status"],
                         value=l["value"]))
L = pd.DataFrame(rows)

# Beobachtbares Verhalten je Firma: Perzentile der Achsen A, S, G
obs = pd.DataFrame({
    t: {ax: f["axes"][ax]["median"] for ax in ["A", "S", "G"] if ax in f["axes"]}
    for t, f in firms.items()}).T
obs.index.name = "ticker"

# ---------------------------------------------------------------- Test 1
# Themen, bei denen es ueberhaupt Schweigende gibt
silent_metrics = (L[L.status == "verschwiegen"].groupby("metric").ticker.nunique())
silent_metrics = silent_metrics[silent_metrics >= 15]

res = []
for m, n_sil in silent_metrics.items():
    sil = set(L[(L.metric == m) & (L.status == "verschwiegen")].ticker)
    dis = set(L[(L.metric == m) & (L.status == "offengelegt")].ticker)
    label = L[L.metric == m].label.iloc[0]
    for ax in ["A", "S", "G"]:
        a = obs.loc[obs.index.isin(sil), ax].dropna()
        b = obs.loc[obs.index.isin(dis), ax].dropna()
        if len(a) < 10 or len(b) < 10:
            continue
        u = mannwhitneyu(a, b, alternative="two-sided")
        res.append(dict(thema=label, metric=m, achse=AXN[ax],
                        n_schweigend=len(a), n_offen=len(b),
                        median_schweigend=round(a.median(), 1),
                        median_offen=round(b.median(), 1),
                        differenz=round(a.median() - b.median(), 1),
                        p=round(u.pvalue, 4)))
R = pd.DataFrame(res)
R["befund"] = np.where(R.p < 0.05,
                       np.where(R.differenz < 0, "Schweigende schlechter", "Schweigende BESSER"),
                       "kein Unterschied")
R = R.sort_values(["thema", "achse"])
R.to_csv(OUT / "silence_test.csv", index=False)
print("TEST 1  Verhalten sich Schweigende anders?  (Perzentil in der Branche, 100 = besser)")
print(R.to_string(index=False))
sig = R[R.p < 0.05]
print(f"\n{len(sig)} von {len(R)} Vergleichen signifikant; "
      f"davon {int((sig.differenz < 0).sum())} mal Schweigende schlechter, "
      f"{int((sig.differenz > 0).sum())} mal besser.")

# ---------------------------------------------------------------- Test 2
# Was verbirgt Schweigen? Perzentilverschiebung, wenn man die Luecke mit
# dem Branchenmedian fuellt - als Bandbreite: bestenfalls / schlimmstenfalls
shift = []
for t, f in firms.items():
    sil = [l for l in f["ledger"] if l["status"] == "verschwiegen"]
    if not sil or "B" not in f["axes"]:
        continue
    n_b = f["axes"]["B"]["n_metrics"]
    k = len([l for l in sil if l["axis"] == "B"])
    if k == 0:
        continue
    # Die Achse ist der Mittelwert der Perzentile ihrer Kennzahlen.
    # Eine verschwiegene Kennzahl koennte zwischen 0 und 100 liegen; wir
    # rechnen beide Grenzen und den Median (50).
    cur = f["axes"]["B"]["median"]
    lo = (cur * n_b + 0 * k) / (n_b + k)
    hi = (cur * n_b + 100 * k) / (n_b + k)
    mid = (cur * n_b + 50 * k) / (n_b + k)
    shift.append(dict(ticker=t, name=f["name"], sector=f["sector"],
                      verschwiegen=k, offen=n_b, aktuell=round(cur, 1),
                      wenn_median=round(mid, 1), bestenfalls=round(hi, 1),
                      schlimmstenfalls=round(lo, 1),
                      spanne_durch_schweigen=round(hi - lo, 1)))
S = pd.DataFrame(shift).sort_values("spanne_durch_schweigen", ascending=False)
S.to_csv(OUT / "silence_cost.csv", index=False)
print(f"\nTEST 2  Was verbirgt Schweigen?  {len(S)} Firmen mit verschwiegenen Angaben auf der Offenheitsachse")
print(f"Median-Spanne, die allein durch Schweigen entsteht: {S.spanne_durch_schweigen.median():.0f} Perzentilpunkte")
print(S.head(10).to_string(index=False))
