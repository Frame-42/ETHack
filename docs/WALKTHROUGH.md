# WALKTHROUGH — wie es läuft, was wir uns dabei dachten

Voraussetzung: Python 3.12, `pip install -r requirements.txt`, `cp .env.example .env`
(nur Keys eintragen die du brauchst — Tabelle unten). Zeit: Kern ~6 min.

## Schritt für Schritt (Pflichtreihenfolge)

```
01_fetch   Quellen ziehen → data/raw/*.parquet (Cache; --force neu)
             Wir dachten: eine Plug-in-Grenze (DataSource + @register), danach
             ändert sich nichts mehr. Jede Quelle genau eine Methode (_fetch).
02_analyse  Anlage→Firma (resolve, fuzzy-Schwelle 92, match_confidence) →
             Firmenjahre (canonical) → 1500 Monte-Carlo-Draws → panel + Bänder
             Wir dachten: OECD/JRC hat recht — Normierung/Gewichtung/Aggregation
             sind Ermessen, also zeigen wir die Spannweite statt sie zu verstecken.
             Noise hängt an match_confidence: unsicher zugeordnet → breiteres Band.
03_grafiken Grafiken für Berichte (figures.py). Optional zum Verstehen.
05b_firmenaggregate  eGRID/TRI/OSHA/ECHO auf Firmen verdichten (exakt/Tochter/Präfix,
             kein Fuzzy — Filialnamen treffen sonst beliebig). PFLICHT vor 07!
07_dataset   Alles zusammenführen (consolidate) → dataset_long.csv + companies/
             metrics/sources.json. DIE Wahrheit steht in dataset_long, nicht im Band.
09_belastbarkeit  E/S/G-Beweisstärke: Familien einmal zählen, Gewichte 1,0→0,2,
             belastbar = ≥2 Familien + Anker ≥0,8 + Summe ≥1,5.
             Wir dachten: nicht „wie gut“, sondern „reicht das Material für ein Urteil“.
10_pruefung  Regeln (quality.py F01–F13+P01–P02) → fehler (nicht rechnen) vs
             pruefen (Beleg nötig) → optional --ai (kostet!) → Mensch in
             data/review/entscheidungen.csv hat Vorrang. 382 → 10 + Grenzfälle.
11_economy   fetch (500 SEC-JSONs) → score (Cash + Schock + Schulden).
             Wir dachten: Kapazität statt Profit (sättigend), beobachtet statt
             prognostiziert, schwächstes Glied. 4 Anläufe dokumentiert, 3 verworfen
             (Profit-Score belohnt Marge; 6-Monats-Cash median 1,5 Mo; Revenue bricht
             bei Spinoffs). Banken NA statt falsch messen.
```

## Warum diese 6 Entscheidungen (was wir dachten)

- **Kein Kauf:** Blackbox-Scores sind nicht prüfbar. Lieber 3 ehrliche Kennzahlen
  (Intensität, Intensitäts-Trend, absoluter Trend, je kleiner desto besser, log-linear,
  ≥3 positive Jahre 2018–23) als 50 weiche.
- **Intra-Sektor:** Khan/Serafeim/Yoon — nur relevante Kennzahlen tragen.
  GICS ist grob (Peer-Raster mit physischen Nennern wäre besser, liegt in Historie),
  aber ehrlicher als universal.
- **Geometrisch:** Additiv lässt Katastrophen zurückkaufen. Geometrie dämpft,
  verbietet nicht — deshalb zeigen wir beide im Sensitivitätslauf.
- **Band:** 144 diskret + LOO/Noise → 1500 Draws (Stichprobe, keine Enumeration).
  P10–P90 ist kein Konfidenzintervall. Breite ≥70 = „nicht einordenbar“.
- **Greenwashing extra:** Wer Intensität senkt aber Tonnen steigert, bekommt ein
  Warnsignal, keine Abwertung. Vermischen wäre Moral-Arithmetik.
- **Viability extra:** Emissions-Beste ohne Lohnfortzahlung ist nicht nachhaltig.
  Aber Profit ≠ Tragfähigkeit (Intel-Test: Verlust, trotzdem Cash). Darum Sättigung.

## Keys (was bricht ohne was)

- `EPA_CAMD_API_KEY` (gratis, wichtig): ohne ihn keine CAMPD-Kraftwerksdaten bis 2026,
  Strom-Lücke bleibt. `01_fetch` läuft weiter, Quelle fehlt.
- `EIA_API_KEY` (gratis, nachrangig): ohne ihn fehlt EIA-Erzeugung.
- `SEC_USER_AGENT` (eigene Mail!): ohne ihn 403 bei SEC.
- `OPENAI_API_KEY` (kostet!): nur für `10_pruefung --ai`. Ohne Flag kostenlos.

## Zahlen, Glossar, Limits

- **503/500:** Ticker/Firmen (GOOG+GOOGL, eine CIK — Dedup geplant).
- **467/349/143/36:** ≥1 Wert / neue Dimensionen / volles Klimaband / ganz ohne.
- **Glossar:** GHGRP (Schornstein je Anlage), CAMPD/CEMS (Kraftwerk-Messung),
  TRI (Gifte), ECHO (Verstöße, max 12 Quartale!), eGRID (t/MWh, nur Versorger, ≤1,2),
  OSHA/DART (Unfälle, Nenner!), WHD (Lohnverfahren), SBTi (Ziele, Excel-only),
  XBRL/TTM (SEC-Maschinenbilanz/12M), GICS, CRITIC, Winsor, LOO, match_confidence.
- **Limits:** EPA-Lag ex Strom, kein Scope 3, S&P-Liste ahistorisch, SBTi ohne API,
  Thresholds gesetzt nicht geschätzt. Voll: `docs/COMPARISON.md`.

## Erweitern (bleibt 3-zeilig)

Neue Quelle: `DataSource` + `_fetch` + `@register`. Neue Kennzahl: Spalte in
`canonical.py` + `Metric` in `02_analyse.py`. Neue Methode: in `normalize/weight/
aggregate.py` registrieren — Monte Carlo nimmt sie automatisch.
