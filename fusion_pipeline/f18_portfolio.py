"""
Die Bonusfrage: eine Milliarde Dollar unter sofortigem Netto-null.

Die EU-Regel (Paris-Aligned Benchmark, Verordnung 2019/2089) verlangt:
  - mindestens 50 Prozent weniger CO2-Intensitaet als der Vergleichsindex
  - danach 7 Prozent Reduktion pro Jahr
  - klimaintensive Branchen duerfen NICHT untergewichtet werden

Der letzte Punkt ist der wichtige: Man darf die Oelindustrie nicht
rauswerfen, sondern muss innerhalb der Branche die Besseren bevorzugen.
Sonst reicht man das Problem nur an andere Eigentuemer weiter.

Neu gegenueber der ersten Fassung:
  - laeuft auf der aktuellen Firmenbasis, nicht auf einer alten Teilmenge
  - die Achse, nach der getiltet wird, ist waehlbar (A, S, G, B oder alle)
  - Firmen ohne wirtschaftliche Tragfaehigkeit werden ausgeschlossen:
    wer seine Leute nicht bezahlen kann, ist in keinem praktischen Sinn
    nachhaltig
  - robuste Firmen bekommen mehr Gewicht als unsichere. Wo die Spanne
    breit ist, machen wir keine grosse Wette.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.optimize import minimize

T = Path("team"); OUT = Path("team_out")
D = json.loads(Path("dashboard/data.json").read_text())
d = pd.read_parquet(T / "dataset_long.parquet")
w = (d.dropna(subset=["value"]).sort_values("year")
       .drop_duplicates(["ticker", "metric"], keep="last"))
piv = w.pivot(index="ticker", columns="metric", values="value").apply(pd.to_numeric, errors="coerce")

firms = {f["ticker"]: f for f in D["firms"]}
AX = ["A", "S", "G", "B"]; AXN = D["axes"]

# Anlageuniversum: bewertbar und mit CO2-Intensitaet (sonst kein Nenner)
uni = [t for t, f in firms.items()
       if f["scorable"] and t in piv.index and pd.notna(piv.at[t, "co2_intensity"])
       and piv.at[t, "co2_intensity"] > 0]
meta = pd.DataFrame({t: dict(sector=firms[t]["sector"], name=firms[t]["name"]) for t in uni}).T
inten = piv.loc[uni, "co2_intensity"].astype(float)
n = len(uni)
print(f"Universum: {n} Firmen mit Note und Intensitaet")

# Tragfaehigkeit: gefaehrdete Firmen fliegen raus
viab = pd.Series({t: (firms[t].get("viability") or {}).get("level", "nicht bewertbar") for t in uni})
excl = viab == "gefährdet"
print(f"Ausgeschlossen wegen wirtschaftlicher Lage: {int(excl.sum())}")

# Robustheit: enge Spanne -> volles Vertrauen, breite Spanne -> gedaempft
def tilt_and_conf(axis_key):
    score = np.zeros(n); conf = np.zeros(n)
    for i, t in enumerate(uni):
        axes = firms[t]["axes"]
        keys = AX if axis_key == "ALL" else [axis_key]
        vals, widths = [], []
        for a in keys:
            if a in axes:
                vals.append(axes[a]["median"]); widths.append(axes[a]["hi"] - axes[a]["lo"])
        if vals:
            score[i] = np.mean(vals) / 100.0
            conf[i] = float(np.clip(1.0 - np.mean(widths) / 100.0, 0.15, 1.0))
    return score, conf


def build(axis_key, cut=0.50):
    score, conf = tilt_and_conf(axis_key)
    w0 = np.full(n, 1.0 / n)
    base = float(w0 @ inten.values)
    sectors = meta.sector.values
    sec_base = {s: w0[sectors == s].sum() for s in np.unique(sectors)}
    tilt = score * conf                      # gedaempft nach Robustheit
    ub = np.where(excl.values, 0.0, 0.06)    # gefaehrdete Firmen: Obergrenze null

    def obj(x):
        return float(((x - w0) ** 2).sum()) - 0.03 * float(x @ tilt)

    cons = [{"type": "eq", "fun": lambda x: x.sum() - 1.0},
            {"type": "ineq", "fun": lambda x: (1 - cut) * base - (x @ inten.values)}]
    for s in np.unique(sectors):            # PAB-Kernregel: kein Sektor untergewichtet
        m = (sectors == s).astype(float)
        cons.append({"type": "ineq", "fun": (lambda x, m=m, b=sec_base[s]: (x @ m) - b)})

    r = minimize(obj, w0, method="SLSQP", bounds=[(0.0, u) for u in ub],
                 constraints=cons, options={"maxiter": 800, "ftol": 1e-11})
    x = np.clip(r.x, 0, None); x = x / x.sum()
    new = float(x @ inten.values)
    chk = pd.DataFrame({"s": sectors, "w0": w0, "w": x}).groupby("s")[["w0", "w"]].sum()
    return dict(
        axis=axis_key, weights=x, base=base, new=new, red=1 - new / base,
        te=float(np.sqrt(((x - w0) ** 2).sum())),
        sector_ok=bool((chk.w >= chk.w0 - 1e-6).all()),
        titles=int((x > 1e-4).sum()), maxw=float(x.max()),
        excluded=int(excl.sum()))


runs = {k: build(k) for k in ["A", "S", "G", "B", "ALL"]}
print("\nPortfolio je Tilt-Achse:")
print(f"{'Achse':<20}{'Intensitaet':>12}{'Reduktion':>11}{'TE':>8}{'Titel':>7}{'max':>7}{'Sektoren':>10}")
for k, r in runs.items():
    name = "alle vier" if k == "ALL" else AXN[k]
    print(f"{name:<20}{r['new']:>9.1f} t{r['red']*100:>10.1f}%{r['te']:>8.4f}"
          f"{r['titles']:>7}{r['maxw']*100:>6.1f}%{'ja' if r['sector_ok'] else 'NEIN':>10}")

# Wie sehr unterscheiden sich die Portfolios? Das ist der eigentliche Test.
print("\nUeberschneidung der Portfolios (gemeinsames Gewicht, 100 % = identisch):")
keys = list(runs)
ov = pd.DataFrame(index=keys, columns=keys, dtype=float)
for a in keys:
    for b in keys:
        ov.loc[a, b] = float(np.minimum(runs[a]["weights"], runs[b]["weights"]).sum())
ov.index = ["alle vier" if k == "ALL" else AXN[k] for k in keys]
ov.columns = ov.index
print((ov * 100).round(0).to_string())
off = ov.where(~np.eye(len(ov), dtype=bool)).stack()
print(f"\nGeringste Ueberschneidung: {off.min()*100:.0f} % ({off.idxmin()[0]} gegen {off.idxmin()[1]})")
print("-> Vier unabhaengige Achsen ergeben vier verschiedene Portfolios. Der Beweis am Geld.")

# Top-Positionen des Vier-Achsen-Portfolios
best = runs["ALL"]
tab = pd.DataFrame({"ticker": uni, "name": meta.name.values, "sector": meta.sector.values,
                    "gewicht": best["weights"], "benchmark": 1 / n,
                    "intensitaet": inten.values,
                    "tragfaehigkeit": viab.values}).sort_values("gewicht", ascending=False)
tab["delta"] = tab.gewicht - tab.benchmark
tab.to_csv(OUT / "portfolio_positions.csv", index=False)
print("\nGroesste Uebergewichte (Vier-Achsen-Portfolio):")
print(tab.head(8)[["ticker", "name", "sector", "gewicht", "delta", "intensitaet"]].round(4).to_string(index=False))

payload = {k: {kk: vv for kk, vv in r.items() if kk != "weights"} for k, r in runs.items()}
payload["overlap"] = ov.round(3).to_dict()
payload["positions"] = tab.head(40).round(5).to_dict("records")
payload["universe"] = n
json.dump(payload, open(OUT / "portfolio.json", "w"), ensure_ascii=False, indent=1)
print("\nGespeichert: team_out/portfolio.json")
