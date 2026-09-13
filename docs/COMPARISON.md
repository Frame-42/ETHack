# Vergleich: Unser Framework vs. bestehende Rankings — Verbesserungen, Limitationen

Diese Datei gehört zum Clean-Branch `clean/sustainability-framework-v1`
(`dataset` c9d58f2 + `feat/economy` 1171a10). Sie downplayt nichts, versteckt
aber die Statistik nicht hinter Fachsprache: erst einfach, dann präzise.

## 1. Wogegen wir uns abgrenzen (MSCI, Sustainalytics, ISS, CDP, TPI)

| Punkt | Kommerziell üblich | Unser Framework |
|---|---|---|
| **Input** | Gekaufte ESG-Scores, Fragebögen, Analystenurteile; Methodik Blackbox | Nur physisch/behördlich Belegtes: EPA GHGRP/CAMPD/TRI/ECHO/eGRID, OSHA, DOL-WHD, SEC XBRL, SBTi-Excel, WBA/SBTi als Team-Daten. Jede Zahl mit `source_id`, URL, Abrufdatum in `dataset_long.csv`. Kommerzieller Snapshot (`esg_snapshot.py`) nur als Benchmark, nie Input. |
| **Vergleichsgruppe** | Oft universell oder intransparent | Strikt intra-sektoral (GICS Sector/Sub-Industry, min_peers=6, Fallback Sektor). Begründung: Khan/Serafeim/Yoon — nur relevante Kennzahlen zählen; Versorger vs. Software sonst Branchenmessung. |
| **Aggregation** | Meist additiv: gute Governance kauft schlechtes CO₂ zurück | Default geometrisch (begrenzt kompensierbar) + additiv als Kontrast in Monte-Carlo. OECD/JRC-konform als Ermessensentscheidung offengelegt. |
| **Präzision** | Exakter Rang „#42“, Score 73,4 | Rang**band** P10–P90 aus 1500 Draws über 576 Kombis (4 Normalizer × 3 Weighter × 2 Aggregatoren × Peer-Level × Winsor × Leave-one-out × Noise aus `match_confidence`). Median-Breite ~33–34 pp — ehrliche Unsicherheit statt Scheinpräzision. |
| **Greenwashing** | Oft implizit verrechnet | Eigene Achse (`intensity_illusion`, `base_year_ratio`, 35 + 48 Fälle, 82/157 ≥1 Flag). Nie mit Leistung verrechnet. |
| **Wirtschaft** | Profit/Marge/Wachstum = „gesund“ | **Neu (economy):** Kapazität statt Profit. Cash-Generierung + Schockpuffer (eigenes schlimmstes Cashflow-Jahr wiederholt, skaliert auf Assets) + Schuldendienst. Sättigend, schwächstes Glied (geometrisch) entscheidet. Banken = not assessable statt falsch zu messen. ρ Größe 0,03 / Marge 0,12. |
| **Reproduzierbarkeit** | Lizenzschranke, kein Code | `pipeline/sources/base.py`-Plug-in, Parquet-Cache, Seed 20260912, `scripts/01→11`, `report/*.tex` + `figures/`. Nur 2 kostenlose Keys nötig (EPA CAMD wichtig, EIA nachrangig). |

## 2. Was wir gegenüber dem Start verbessert haben (mit Beleg)

1. **Faktor-3-Rohdatenfehler gefixt.** EPA-Tabelle mischt Direkt/Supplier/Injektion.
   Trennung über `sector_type`, biogen raus (GHG-Protokoll). Sonst Ölkonzern =
   Emissionen seiner Kunden.
2. **Strom-Lücke geschlossen.** EPA endet 2023 → CAMPD-CEMS bis 2026 (Owner vs.
   Operator) + PUDL-Spiegel + Exhibit-21 (916k Töchter, 478/500 Mütter) statt
   handgepflegter OVERRIDES.
3. **Abdeckung 157 → 349.** OSHA (323, +187 neu, ρ −0,23), TRI (205, +87, ρ 0,53),
   ECHO (138, +13), eGRID/MWh (48, +9). Union 339, total 349 (69,4 %).
4. **Staleness ehrlich gemessen.** Backtest Spearman 0,84, aber 37 % >10pp-Shift
   bei Fortschreibung ab 2024 — deshalb Zwei-Perioden-Modell A (2018–23 voll)
   vs. B (2024+ ohne EPA).
5. **Qualität als System.** `quality.py` F01–F13+P01–P02 (hart → Mechanismus →
   Statistik), 382 Flags (239 fehler / 143 pruefen, 176 Firmen, 106 ranking-relevant)
   → Reparatur statt nur Markierung (neu: 10 + Grenzfälle), KI-Gutachten +
   Mensch-in-der-Schleife (`data/review/entscheidungen.csv`), `pruefung_vorgehen.pdf`.
6. **Belastbarkeit E/S/G.** Beweisgewichte 1,0 (gemessen) → 0,2 (Status),
   Familien nur einmal gezählt, belastbar = ≥2 Familien + Anker ≥0,8 + Summe ≥1,5.
7. **Viability statt Profit.** 4 Iterationen dokumentiert (Profit-Score → 6-Monats-Cash
   → Revenue-Stabilität → Cashflow-Stress). Ergebnis 378/29/19/77 beweist:
   kein Größen-/Margen-Proxy.
8. **Aufgeräumt.** `ai_review_cache/` (944 Files), `web/public/logos/` (424 Binaries,
   via `08_logos.py` regenerierbar), `fusionsbericht (1).pdf` (altes f01–f07-Modell)
   aus clean entfernt; `.gitignore` + `pipeline/economy/` + `scripts/11_economy.py`.

## 3. Limitationen — wo das Framework (noch) nicht trägt

- **Nur 143 Klimabänder, 36 Firmen ohne Wert.** Tech/Finanzen/Real Estate
  (25–40 % Abdeckung vs. Utilities/Materials 100 %) leben in Scope 2/3-15 —
  keine freien Firmendaten. Ranking = „große Schornsteine, wie effizient“.
- **EPA-Lag ex Strom.** Ab FY2024 keine freien Firmenemissionen; Fortschreibung
  kostet 37 % >10pp (s. o.). CARB SB253 (ab 11/2026 Scope 1+2, 2027 Scope 3) als Hoffnung.
- **Peer-Raster grob.** `worktree-peer-groups` (6 Archetypen → 18 Gruppen,
  physische Nenner BOE/MWh/tkm/m² statt Umsatz) **nicht** gemergt — clean nutzt
  GICS mit Fallback. Gleiche Perzentile ≠ gleiche absolute Leistung.
- **SBTi/CDP/TPI-Lücken.** SBTi nur Excel (241, 50 zurückgezogen, kein API),
  CDP nur Städte, TPI Scraping-Verbot, TRACE Owners leer. SEC-Volltext nur 215 Firmen.
- **S&P-Liste ahistorisch.** Nur heutiger Stand, keine Historie; Survivorship-Bias.
- **Geometrie ≠ Verbot.** Geometrisch dämpft Kompensation, verbietet sie nicht;
  Leave-one-out (p=0,3) + Noise (0,05 + 0,35×(1−confidence)) sind Setzungen (Seed fix).
- **Economy eng.** Nur SEC-Filer, nur USD, nur 10 Jahre; Banken/Insurer NA;
  Schwellen (`THRESHOLDS`) gesetzt, nicht geschätzt — „hier zu streiten“.
- **Observatory nicht integriert.** WBA-Rekombination (217 core / 71 nature,
  CTT 216×0-Problem) bleibt separater JS-Stack — als Idee referenziert, nicht gemergt.

**Fazit:** Objektiver als gekaufte Rankings, weil gemessen, bandbreitenehrlich,
quellenbelegt und schwächenoffen — aber kein „wer ist nachhaltig“-Urteil.
Für Schwerindustrie belastbar, für Finanz/IT/Real Estate vor allem eine
Datenlücken-Karte + Viability-Check.
