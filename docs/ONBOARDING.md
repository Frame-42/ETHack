# ONBOARDING — in 15 Minuten zum Verständnis (ohne Statistik-Vorkenntnisse)

Du brauchst keine Statistik. Lies in dieser Reihenfolge. Alles Schwere steht
erst in den Reports.

## 0. Das Bild (30 Sekunden)

```
Behörden/SEC ──01_fetch──▶ data/raw/*.parquet ──02_analyse──▶ Rangband P10–P90
                                                     │
                    05b (Firmenaggregate) ──07──▶ dataset_long.csv (jede Zahl + Quelle)
                                                     │
                    09 (Belastbarkeit) + 10 (QA) + 11 (Economy) ──▶ Browser :3000
```

Siehe auch `framework_einfach.png`. Regel: **nie Firma+Wert ohne Jahr+Einheit+Quelle lesen.**

## 1. Drei Beispiele zum Anfassen (2 Minuten)

- **Firma suchen:** `web` starten, z. B. Kraft Heinz (KHC): 2022 Scope = 0 trotz
  zugeordneter Anlagen → QA-Flag „0 statt fehlend“, kein Rang-Triumph.
- **Band lesen:** „Band 30–80, Mitte 60“ = unter 1500 Rechenvarianten oft Mittel,
  schwankt stark. Höher = relativ besser **in der Branche**. Kein Beweis, keine
  Wahrscheinlichkeit.
- **Viability lesen:** „viable, weakest=debt_service“ = Cash ok, Schock ok,
  Schuldendienst ist das schwächste Glied. Banken = not assessable (richtig so).

## 2. Zahlen, die sich widersprechen — Auflösung (3 Minuten)

- **503 vs 500:** 503 Ticker-Zeilen in `constituents.csv` (Header + 503).
  Alphabet doppelt (GOOG/GOOGL, eine CIK). Firmen = 500. Web zeigt 500 Seiten,
  Export 503 Zeilen. Fix geplant: CIK-Dedup in `consolidate.py`.
- **467 vs 349 vs 143:** 467 = ≥1 Wert irgendwelcher Art. 349 = mit neuen
  Dimensionen (OSHA/TRI/ECHO/eGRID) bewertbar (69 %). 143 = alle 3 Klima-Kennzahlen
  vorhanden → Rangband. Rest: Profile mit Einzelwerten, kein Band.
- **36 vs 67:** 36 = null Nachhaltigkeitswerte im Export. 67 = ohne Daten in
  Web-Sicht (inkl. reiner Metadaten-Fälle). Unterschied = Zählweise, kein Fehler.
- **576 vs 1500 vs 144:** 144 = diskrete Kombis (4×3×2×2×3). 576 = inkl.
  Drop-Varianten kommuniziert. 1500 = Zufallsdraws in `02_analyse.py`
  (mit Wiederholung, keine Enumeration). `montecarlo.py`-Default 1000 gilt nur
  ohne Config. Sensitivität: +800+800 in `02_analyse.py:93-95`.
- **380 vs 382 vs 10:** 380 = alter Vorläufer `09_flags.py` (untracked, gelöscht).
  382 = aktuelles `quality.py` (239 fehler/143 pruefen, 176 Firmen).
  10 = nach Reparatur übrig + Grenzfälle (siehe Commits df507d2/c9d58f2).

## 3. Glossar (5 Minuten, Deutsch→Klartext)

| Kürzel | Heißt | Merksatz |
|---|---|---|
| GHGRP | EPA-Treibhausgas-Meldeprogramm | Schornstein-Daten je Anlage, endet 2023 |
| CAMPD/CEMS | EPA-Kraftwerksmessung (kontinuierlich) | Strom-CO₂ bis 2026, braucht `EPA_CAMD_API_KEY` (D im Key, P in Quelle) |
| PUDL | Public Utility Data Liberation | Freier CEMS-Spiegel + Tochterfirmen-Liste |
| TRI | Toxics Release Inventory | Giftstoffe |
| ECHO | EPA Enforcement/Compliance | Verstöße/Strafen (max 12 Quartale/3J!) |
| eGRID | EPA-Strommix je Kraftwerk | t CO₂/MWh, nur für Versorger sinnvoll (≤1,2!) |
| OSHA ITA | Arbeitsunfall-Meldungen | DART-Rate, Nenner beachten |
| DOL-WHD | Lohn-/Arbeitszeit-Verfahren | Fälle vs. Betroffene vs. Nachzahlung trennen |
| EIA-923 | Energie-Erzeugungserhebung | MWh als physischer Nenner |
| SBTi | Science Based Targets | Zielstatus, Excel only (241, 50 zurückgezogen) |
| WBA | World Benchmarking Alliance | Team-Vergleichsdaten (CTT fast nur 0!) |
| XBRL/companyfacts | SEC-Maschinenbilanz | Umsatz + Viability-Input |
| TTM | letzte 12 Monate | aus FY+YTD−Vorjahr-YTD |
| GICS | Branchen-System | Sector/Sub-Industry = Vergleichsgruppe |
| CRITIC/Entropie | Gewichtungsverfahren | aus Datenstreuung, nicht Handgewicht |
| Winsor/LOO | Extremdeckel / Weglass-Test | Robustheits-Tricks im Monte Carlo |
| match_confidence | Zuordnungs-Sicherheit | unsicher → breiteres Band (0,05+0,35×(1−c)) |
| Familie/Anker | Beweisgruppen in reliability.py | gemessen 1,0 → Status 0,2; belastbar = ≥2 Familien + Anker ≥0,8 + Summe ≥1,5 |
| Sättigend | genug ist genug | Viability: mehr Profit ≠ mehr Punkte |
| FEHLER/PRÜFEN | QA-Stufen | fehler = nicht rechnen; pruefen = Beleg nötig |

## 4. Datenfluss mit Dateien (3 Minuten)

```
data/raw/sp500_master.parquet ← 01 (Wiki/Wikidata/SEC)
data/raw/epa_*|sec_revenue|... ← 01 (je Quelle, --force neu)
data/out/panel_periode_a.csv + rangbaender_periode_a.csv ← 02 (1500 Draws)
data/out/neue_dimensionen.csv ← 05 | *_je_firma.csv ← 05b
data/out/dataset_long.csv|parquet + companies/metrics/sources.json ← 07
web/public/data/*.json + web/public/downloads/* ← 07+09 kopiert (generiert!)
report/generated/*.tex ← 06 (nie von Hand)
report/*.pdf ← tectonic (Tectonic 0.15.0)
data/out/economic_viability.csv ← 11 (braucht data/raw/sec_facts/ + SEC_USER_AGENT)
data/review/entscheidungen.csv ← Menschen (Vorrang vor Regel+KI)
```

Frischer Clone: `data/raw/` leer, `web/public/{data,downloads,logos}/` leer bis
07/08/09 laufen. `data/out/*.csv` sind committed Beispiele, Parquet nicht.

## 5. Was als Nächstes zu tun ist (für dich)

1. `cp .env.example .env`, nur Keys eintragen die du brauchst (Tabelle in README §1).
2. Kern laufen lassen (01→02→03), dann eine Firma im Browser öffnen + Quelle klicken.
3. `docs/COMPARISON.md` lesen für Abgrenzung/Limits.
4. Erst dann Reports: fusionsbericht (Einstieg) → analyse_ranking → datenlücke →
   qualitätsprüfung → economy.
