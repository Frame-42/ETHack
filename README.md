# ETHack — Clean Framework (S&P-500-Nachhaltigkeit)

> 503 Ticker (= 500 Firmen) → 467 mit ≥1 Wert → 143 mit Klimaband P10–P90 →
> 378 wirtschaftlich tragfähig. Sagt nicht „wer ist nachhaltig“, sondern
> „große Schornsteine, wie effizient — und kann die Firma weiterzahlen?“

![Framework](framework_einfach.png)

**Leseroute (neu, ohne Vorkenntnisse):**
`README (du bist hier)` → `docs/FRAMEWORK.md` (was + warum) →
`docs/WALKTHROUGH.md` (wie es läuft + was wir dachten) →
`docs/COMPARISON.md` (vs MSCI & Co, Limits).

## Schnellstart

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # Keys nur nach Bedarf (Tabelle in WALKTHROUGH)

.venv/bin/python scripts/01_fetch.py   # Quellen → data/raw/
.venv/bin/python scripts/02_analyse.py # Ranking-Bänder
.venv/bin/python scripts/05b_firmenaggregate.py  # Pflicht vor 07!
.venv/bin/python scripts/07_dataset.py # dataset_long.csv (die Wahrheit)
.venv/bin/python scripts/09_belastbarkeit.py
.venv/bin/python scripts/10_pruefung.py          # ohne --ai kostenlos
.venv/bin/python scripts/11_economy.py fetch data/raw/sec_facts
.venv/bin/python scripts/11_economy.py score data/raw/sec_facts
```

## Was hier liegt

```
pipeline/      Framework (sources/ als Plug-in, scoring/, quality, reliability, economy)
scripts/       01,02,03,05b,07,09,10,11 in genau dieser Reihenfolge
data/          constituents.csv + external/team/ (Inputs) +
               out/dataset_long.csv, rangbaender, belastbarkeit,
               economic_viability, flags_gepruft, pruefung, Katalog (clean data)
               Rest wird regeneriert (siehe .gitignore)
docs/          FRAMEWORK.md + WALKTHROUGH.md + COMPARISON.md — das ist die ganze Doku
requirements.txt, .env.example, framework_einfach.png
```

Historie (`dataset`, Reports mit 10 PDFs, Web-App, Peer-Raster, Observatory)
bleibt in Git-Historie, ist aber bewusst nicht mehr in diesem Branch.
