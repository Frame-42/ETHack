"""
Fuenfte Achse: wirtschaftliche Tragfaehigkeit (reduzierte Fassung).

WICHTIG, gehoert in den Bericht: Dies ist NICHT der volle Viability-Index
aus economic_viability.pdf. Der braucht zehn Jahre Cashflow-Historie fuer
den Stresstest gegen das eigene schlechteste Jahr. Im Team-Datensatz liegt
nur das Geschaeftsjahr 2024. Rekonstruiert sind daher drei Dimensionen aus
Bestandsgroessen, mit derselben Konstruktionslogik:

  - saettigende Schwellen: ab "genug" gibt es keine Punkte mehr,
    damit Profit den Nachhaltigkeitsrang nicht kaufen kann
  - geometrische Zusammenfassung: die schwaechste Dimension bindet
  - Ampel statt Zahl, weil viele Firmen die Obergrenze erreichen

Sobald die volle Fassung vorliegt, ersetzt sie diese hier eins zu eins.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import spearmanr

T = Path("team"); OUT = Path("team_out"); OUT.mkdir(exist_ok=True)

d = pd.read_parquet(T / "dataset_long.parquet")
M = json.loads((T / "metrics.json").read_text())
w = (d.dropna(subset=["value"]).sort_values("year")
       .drop_duplicates(["ticker", "metric"], keep="last"))
piv = w.pivot(index="ticker", columns="metric", values="value").apply(pd.to_numeric, errors="coerce")
meta = d.drop_duplicates("ticker").set_index("ticker")
sector = meta.gics_sector.reindex(piv.index).fillna("Unbekannt")

# Banken und Versicherer: Cashflow, Liquiditaet und Schuldenquoten bedeuten
# dort etwas anderes. Nicht mit dem falschen Massstab bewerten.
NOT_ASSESSABLE = sector.isin(["Financials"])


def ramp(x, zero, suff):
    """Linearer Anstieg zwischen 'null' und 'genug'. Danach flach bei 1."""
    x = pd.to_numeric(x, errors="coerce")
    return ((x - zero) / (suff - zero)).clip(0, 1)


ocf = piv.get("operating_cf_usd")
ta = piv.get("total_assets_usd")
td = piv.get("total_debt_usd")
cap = piv.get("capex_usd")

# 1  Eigenfinanzierung: bringt das Geschaeft Geld herein, gemessen an der Bilanz
d1 = ramp(ocf / ta, 0.0, 0.05)
# 2  Substanzerhalt: deckt der Cashflow die eigenen Investitionen
d2 = ramp(ocf / cap.replace(0, np.nan), 0.8, 2.0)
# 3  Schuldendienst: wie viele Jahre Cashflow braucht es, um die Schulden zu tilgen
years = (td / ocf.where(ocf > 0)).replace([np.inf, -np.inf], np.nan)
d3 = ramp(-years, -8.0, -2.0)          # 8 Jahre = 0, 2 Jahre = 1

dims = pd.DataFrame({"Eigenfinanzierung": d1, "Substanzerhalt": d2,
                     "Schuldendienst": d3}).astype(float)
n_dims = dims.notna().sum(axis=1)
with np.errstate(invalid="ignore", divide="ignore"):
    idx = 100 * np.exp(np.nanmean(np.log(dims.clip(lower=0.02).to_numpy()), axis=1))
idx = pd.Series(idx, index=dims.index)
weakest = dims.min(axis=1)
arr = dims.to_numpy()
allna = np.isnan(arr).all(axis=1)
wi = np.where(allna, -1, np.nanargmin(np.where(np.isnan(arr), np.inf, arr), axis=1))
weak_name = pd.Series([dims.columns[i] if i >= 0 else None for i in wi], index=dims.index)

level = pd.Series(index=piv.index, dtype=object)
level[:] = "nicht bewertbar"
ok = (n_dims >= 2) & ~NOT_ASSESSABLE
level[ok & (weakest >= 0.60)] = "tragfaehig"
level[ok & (weakest >= 0.25) & (weakest < 0.60)] = "angespannt"
level[ok & (weakest < 0.25)] = "gefaehrdet"

V = pd.DataFrame({"index": idx.round(1), "level": level, "weakest": weakest.round(2),
                  "weakest_dim": weak_name, "n_dims": n_dims}).join(dims.round(2))
V.index.name = "ticker"
V.to_csv(OUT / "axis_viability.csv")

print("Fuenfte Achse, wirtschaftliche Tragfaehigkeit (reduziert):")
print(level.value_counts().to_string())
print(f"\nGebunden durch: {weak_name[ok].value_counts().to_dict()}")

# --- Test 1: misst der Index nur Groesse oder Profit? --------------------
print("\nMisst der Index Groesse oder Profit? (soll nahe null sein)")
for name, s in [("Bilanzsumme", np.log10(ta)), ("Nettogewinn", piv.get("net_income_usd")),
                ("Gewinnmarge", piv.get("net_income_usd") / ta)]:
    b = pd.concat([idx[ok], s[ok]], axis=1).dropna()
    r = spearmanr(b.iloc[:, 0], b.iloc[:, 1])
    print(f"  {name:14s} rho={r.statistic:+.3f}  p={r.pvalue:.3f}  n={len(b)}")

# Ergebnis dieses Tests, offen protokolliert:
# Der Nachbau erreicht rho = 0.42 zur Gewinnmarge. Der volle Index aus
# economic_viability.pdf erreicht 0.12. Der Unterschied liegt an der
# fehlenden Historie: dort sind die Dimensionen Anteile ueber zehn Jahre
# ("in wie vielen Jahren war der Cashflow positiv"), hier Niveaukennzahlen
# eines einzelnen Jahres - und die haengen zwangslaeufig an der Ertragslage.
# Auch ein sehr frueher Saettigungspunkt behebt das nicht (getestet bis 0.02).
# Konsequenz: Die Achse wird als VORLAEUFIG gekennzeichnet und ersetzt,
# sobald die Zehnjahresreihe vorliegt.

# --- Test 2: bricht die fuenfte Achse den Kernbeleg? ---------------------
dash = json.loads(Path("dashboard/data.json").read_text())
ax_scores = {}
for f in dash["firms"]:
    for a, v in f["axes"].items():
        ax_scores.setdefault(a, {})[f["ticker"]] = v["median"]
S = pd.DataFrame(ax_scores)
S["V"] = idx[ok]
names = {"A": "Umwelt", "S": "Soziales", "G": "Regeltreue",
         "B": "Offenheit", "V": "Tragfaehigkeit"}
C = S.corr(method="spearman").rename(index=names, columns=names).round(2)
C.to_csv(OUT / "axis_correlation_5.csv")
print("\nKorrelation aller FUENF Achsen:")
print(C.to_string())
off = C.where(~np.eye(len(C), dtype=bool)).abs().stack()
print(f"\ngroesste |rho| zwischen zwei Achsen: {off.max():.2f} "
      f"({off.idxmax()[0]} / {off.idxmax()[1]}), median {off.median():.2f}")
if off.max() > 0.5:
    print("ACHTUNG: Kernbeleg 'die Achsen wissen nichts voneinander' haelt nicht mehr.")
else:
    print("Kernbeleg haelt: keine zwei Achsen messen dasselbe.")


# --- Manipulationsresistenz je Achse -------------------------------------
RESIST = [
    ("Umwelt", "EPA, Meldepflicht", "weniger aussto\u00dfen", "hoch"),
    ("Regeltreue", "EPA ECHO", "keine Verst\u00f6\u00dfe begehen", "hoch"),
    ("Soziales", "OSHA, DOL", "weniger Unf\u00e4lle, keine Lohnverfahren", "hoch"),
    ("Tragf\u00e4higkeit", "SEC-Pflichtberichte", "Cashflow verbessern", "mittel"),
    ("Offenheit: Ziele", "SBTi", "ein Ziel setzen", "niedrig"),
    ("Offenheit: Berichte", "Unternehmensberichte", "mehr berichten", "niedrig"),
]
R = pd.DataFrame(RESIST, columns=["Achse", "Quelle", "was die Firma tun muesste", "Resistenz"])
R.to_csv(OUT / "manipulationsresistenz.csv", index=False)
print("\nManipulationsresistenz:")
print(R.to_string(index=False))
print("\nVier von sechs Achsen lassen sich nur durch tatsaechliche Veraenderung verbessern.")
