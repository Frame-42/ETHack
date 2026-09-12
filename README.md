# ETHack — S&P-500-Nachhaltigkeitsranking

Ein branchenrelatives Ranking der 500 größten US-Börsenfirmen auf physisch
gemessenen Emissionen, mit Unsicherheitsanalyse statt Schein-Präzision.

**Bericht:** [`report/analyse_ranking.pdf`](report/analyse_ranking.pdf) — Methodik,
Ergebnisse beider Datenperioden, zehn Schwachstellen und neun Verbesserungsvorschläge.

## Die Grundidee

Fünf Entscheidungen tragen das System:

1. **Keine gekauften ESG-Noten.** Wenige physische Größen selbst messen.
2. **Nur innerhalb der Branche vergleichen.** Ein Versorger stößt pro Umsatzdollar
   hundertmal mehr aus als ein Softwarehaus.
3. **Multiplikativ aggregieren.** Eine gute Teilnote kann einen katastrophalen
   CO₂-Wert nicht zurückkaufen.
4. **Rangband statt Platzziffer.** Die Rangliste wird 1500-mal über verschiedene
   Methodenkombinationen gerechnet; ausgegeben wird die Spanne.
5. **Greenwashing als eigene Achse.** Ergebnisse und Glaubwürdigkeit werden nie
   miteinander verrechnet.

## Aufbau

```
pipeline/
  sources/          Connector-Schicht — die Plug-in-Grenze
    base.py           DataSource-Interface, Registry, Parquet-Cache
    sp500.py          Indexmitglieder, GICS-Sektor, CIK
    sec_revenue.py    Jahresumsätze aus SEC-XBRL (frames-API)
    epa_ghgrp.py      Scope-1-Emissionen je US-Anlage
    esg_snapshot.py   kommerzielle ESG-Ratings (nur als Vergleichsmaßstab)
  resolve.py        Anlage → Konzern → Ticker, mit Beteiligungsquoten
  canonical.py      eine Zeile je Firma und Jahr, mit Herkunft je Feld
  scoring/
    normalize.py      Rang | getrimmter Z-Wert | Min-Max | Median-MAD
    weight.py         gleich | Entropie | CRITIC
    aggregate.py      geometrisch | additiv
    montecarlo.py     Unsicherheitsanalyse über den Kombinationsraum
  analysis.py       Zwei-Perioden-Auswertung, Rückwärtstests
  figures.py        Grafiken für den Bericht
scripts/            01_fetch → 02_analyse → 03_grafiken
data/out/           alle Ergebnisse als CSV + kennzahlen.json
report/             LaTeX-Quelle, Grafiken, gebautes PDF
```

## Ausführen

```bash
python3 -m venv .venv
.venv/bin/pip install pandas numpy matplotlib scipy requests rapidfuzz pyarrow lxml

.venv/bin/python scripts/01_fetch.py      # Quellen ziehen (~4 min), Parquet-Cache
.venv/bin/python scripts/02_analyse.py    # Zuordnung, Monte Carlo, beide Perioden (~90 s)
.venv/bin/python scripts/03_grafiken.py   # Grafiken nach report/figures/

cd report && tectonic --untrusted --outdir . analyse_ranking.tex
```

Einzelne Quellen neu ziehen: `scripts/01_fetch.py epa_facility --force`.

## Erweitern

**Neue Quelle** — von `DataSource` erben, `_fetch()` implementieren, `@register`
dransetzen. Alles ab Stufe 03 bleibt unberührt.

**Neue Kennzahl** — Spalte in `canonical.py` berechnen, `Metric(...)` in
`scripts/02_analyse.py` ergänzen. Richtung `-1` heißt: kleiner ist besser.

**Neue Methode** — Funktion in `normalize.py`, `weight.py` oder `aggregate.py`
schreiben und registrieren. Die Monte-Carlo-Schleife nimmt sie automatisch in
den Kombinationsraum auf.

## Datenlage (Stand 12.09.2026, alles selbst geprüft)

| Quelle | Zugang | Grenze |
|---|---|---|
| EPA GHGRP (Envirofacts) | REST, ohne Anmeldung | Reihe endet mit Berichtsjahr **2023** |
| SEC XBRL frames | REST, User-Agent nötig | bis Geschäftsjahr 2025 |
| S&P-500-Liste | frei | nur der heutige Stand, keine Historie |
| Climate TRACE | REST, ohne Anmeldung | `Owners` leer → keine Firmenzuordnung |
| SBTi | **kein API** (404) | nur über die Dashboard-Seite |

Zwei Punkte, die man kennen muss:

- Die EPA-Emissionstabelle mischt Direktemittenten, Kraftstoff-Lieferanten und
  CO₂-Injektion. Wer alles aufsummiert, verdreifacht die Zahl und rechnet einem
  Ölkonzern die Emissionen seiner Kunden als eigene an. Getrennt wird über
  `sector_type`; biogenes CO₂ bleibt nach GHG-Protokoll außen vor.
- Für Geschäftsjahre ab 2024 gibt es **keine** freien Emissionsdaten auf
  Firmenebene. Der Rückwärtstest in `analysis.staleness_backtest` misst, was eine
  Fortschreibung kostet: Spearman 0,84, aber 37 % der Firmen verschieben sich um
  mehr als zehn Perzentilpunkte.

## Ergebnis in einem Satz

Von 503 Indexmitgliedern sind 157 bewertbar — fast ausschließlich Schwerindustrie,
weil Tech und Finanzen ihren Fußabdruck in Scope 2 und 3 haben, wo keine freien
Daten existieren. Deshalb sagt die Rangliste nicht „wer ist nachhaltig", sondern
„wer betreibt große Schornsteine, und wie effizient".
