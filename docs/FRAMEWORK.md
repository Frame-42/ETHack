# FRAMEWORK — was es ist und warum es so gebaut ist

S&P-500-Nachhaltigkeitsvergleich aus belegten Behörden- und Filings-Daten.
Kein gekaufter Score, kein exakter Rang, keine vermischten Themen.

## Das Versprechen in 6 Sätzen

1. **Gemessen, nicht gekauft.** Nur physisch/behördlich Belegtes: EPA-Emissionen,
   Schadstoffe, Verstöße, Unfälle, Lohnverfahren, SEC-Finanzen, SBTi-Ziele.
   Jede Zahl mit Quelle, Jahr, Einheit. Kommerzielle Scores nur als Benchmark, nie Input.
2. **Nur innerhalb der Branche.** Versorger vs. Software ist Branchenmessung.
   Vergleichsgruppe = GICS-Sektor/Sub-Industry (min 6, sonst Fallback Sektor).
3. **Schwachstelle zählt.** Geometrisches Mittel (Default): ein katastrophales
   CO₂-Ergebnis lässt sich nicht durch Nebenwerte zurückkaufen. Additiv nur als Kontrast.
4. **Band statt Platz.** 1500 Draws über 144 diskrete Kombis (4 Normalizer × 3 Weighter
   × 2 Aggregatoren × 2 Peer-Level × 3 Winsor) + Leave-one-out + Noise aus
   Zuordnungs-Sicherheit → Perzentilband P10–P90 je Firma. Kein „#42“.
5. **Greenwashing separat.** Intensitäts-Illusion + bequemes Basisjahr stehen daneben,
   werden nie mit Leistung verrechnet.
6. **Tragfähigkeit separat.** SEC-Viability: Cash-Erwirtschaftung + Schockpuffer
   (eigenes schlimmstes Jahr wiederholt) + Schuldendienst. Sättigend, schwächstes
   Glied entscheidet. Banken = not assessable.

## Was reingeht, was rauskommt

**Rein:** `constituents.csv` (503 Ticker = 500 Firmen, Alphabet doppelt) +
Behörden-APIs (EPA GHGRP bis 2023, CAMPD bis 2026 mit Key, TRI/ECHO/eGRID,
OSHA, DOL-WHD, EIA) + SEC XBRL (Umsatz + companyfacts) + Team-Inputs
(`data/external/team/`).

**Raus (clean data in `data/out/`):**
- `dataset_long.csv` — eine Zeile je Ticker×Jahr×Kennzahl, mit Quelle (die Wahrheit)
- `rangbaender_periode_a.csv` — P10/P50/P90 je Firma (die Klimazusammenfassung)
- `belastbarkeit.csv/json` — E/S/G-Beweisstärke je Firma
- `economic_viability.csv` — 378 viable / 29 strained / 19 at-risk / 77 NA
- `flags_gepruft.csv/json`, `pruefung.json`, `data/review/entscheidungen.csv` — QA
- `companies/metrics/sources.json`, `katalog_stats.json` — Katalog/Register

**Abdeckung ehrlich:** 467 mit ≥1 Wert, 349 mit neuen Dimensionen (69 %),
143 mit Klimaband (fast nur Schwerindustrie — Tech/Finanzen stecken in Scope 2/3,
wo es keine freien Firmendaten gibt). Median-Band ~33 Punkte. 36 ganz ohne Wert.

## Warum objektiver als gekauft

Gezeigt, nicht behauptet: Quelle je Zelle, Unsicherheit als Band,
Kompensation begrenzt, Täuschungs-Signale separat, Schwellen offengelegt,
Seed fix (20260912), Code + Cache reproduzierbar. Details: `docs/COMPARISON.md`.
Limitationen dort ebenso — kein „wer ist nachhaltig“-Urteil, sondern
„große Schornsteine, wie effizient — und kann die Firma weiterzahlen?“.
