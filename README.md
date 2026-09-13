# ETHack — S&P-500-Nachhaltigkeitsranking (Clean Framework v1)

> **In einem Satz:** 503 Börseneinträge (= 500 Firmen — Alphabet ist als GOOG+GOOGL
> doppelt gelistet) im Datensatz, davon 467 mit mindestens einem
> Nachhaltigkeitswert, 349 mit Umwelt/Sozial/Compliance-Werten aus den neuen
> Dimensionen, 143 mit Klimarangband — und 378 mit geprüfter wirtschaftlicher
> Tragfähigkeit (SEC). Das Ranking sagt nicht „wer ist nachhaltig“,
> sondern „wer betreibt große Schornsteine, wie effizient — und kann die Firma
> ihre Belegschaft auch im schlechten Jahr bezahlen?“
>
> **Zahlen-Wegweiser:** 503 = Ticker-Zeilen, 500 = Firmen (CIK-dedup). 467 = ≥1 Wert
> irgendeiner Art. 349 = mit OSHA/TRI/ECHO/eGRID-Werten (69 %). 143 = mit allen drei
> Klima-Kennzahlen für ein Rangband. 36 = ganz ohne Nachhaltigkeitswert im Export;
> 67 = ohne Daten in der Web-Ansicht (inkl. reiner Finanz-Metadaten-Fälle).
> Klimaband-Median-Breite ~33–34 Perzentilpunkte (P10–P90, kein Konfidenzintervall).

Branch: `clean/sustainability-framework-v1` — vereinigt `dataset` (c9d58f2)
mit `feat/economy` (1171a10). Bewusst **nicht** übernommen: `feat/sustainability-observatory`
(eigener WBA-JS-Stack), `worktree-peer-groups` (18er-Raster, als Limitation dokumentiert).

![Framework einfach](framework_einfach.png)

## 1. Schnellstart — in 10 Minuten zum ersten Ergebnis

Leseroute: `README (5 min)` → `docs/ONBOARDING.md (15 min)` → `docs/COMPARISON.md`
→ `report/*.tex` (volle Strenge). Glossar: siehe ONBOARDING.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # nur ausfüllen was du brauchst, siehe Key-Tabelle unten

# Kern — ohne Keys lauffähig (braucht data/raw/, wird von 01 angelegt):
.venv/bin/python scripts/01_fetch.py        # Quellen ziehen, Parquet-Cache (~4 min)
.venv/bin/python scripts/02_analyse.py      # Zuordnung + Monte Carlo 1500 Draws (~90 s)
.venv/bin/python scripts/03_grafiken.py     # Grafiken nach report/figures/

# Pflicht-Reihenfolge erweitert (jede Stufe braucht die davor):
.venv/bin/python scripts/04_datenluecke.py      # Lückenbilanz (braucht 02)
.venv/bin/python scripts/05_neue_dimensionen.py # OSHA/TRI/ECHO/eGRID-Beitrag (braucht 02)
.venv/bin/python scripts/05b_firmenaggregate.py # Firmenverdichtung (Pflicht vor 07!)
.venv/bin/python scripts/06_katalog.py          # report/generated/ (Pflicht vor PDFs)
.venv/bin/python scripts/07_dataset.py          # dataset_long + web/public/data+downloads
.venv/bin/python scripts/09_belastbarkeit.py    # E/S/G-Belastbarkeit (+ kopiert ins Web)
.venv/bin/python scripts/10_pruefung.py         # QA-Regeln (ohne --ai kostenlos)
.venv/bin/python scripts/11_economy.py fetch data/raw/sec_facts  # SEC companyfacts (~500 JSON)
.venv/bin/python scripts/11_economy.py score data/raw/sec_facts  # economic_viability.csv

# Browser (liest nur vorbereitete Dateien, keine Live-Behördenabfrage):
cd web && npm ci && npm run dev  # -> http://localhost:3000 (Node 20+, Next 15.5)
```

Versionen: Python 3.12, Node 20.11, Tectonic 0.15.0, Poppler `pdfinfo/pdftoppm`.
Gespeichert ansehen ohne Rechnen: `data/out/*.csv|json`, `report/*.pdf`.

### Keys: was bricht ohne was?

| Key (in `.env`) | Wofür | Ohne Key passiert |
|---|---|---|
| `EPA_CAMD_API_KEY` (kostenlos, wichtig) | `epa_campd.py`: Kraftwerks-CO₂ bis 2026 | Strom-Lücke bleibt; Code läuft weiter (`01_fetch` fängt Fehler, Quelle fehlt) — im Code steht noch `or "DEMO_KEY"`, das ist nur Rate-Limit-Demo, kein Ersatz |
| `EIA_API_KEY` (kostenlos, nachrangig) | `eia_api.py`: Stromerzeugung | EIA-Quelle fehlt, Rest läuft |
| `SEC_USER_AGENT` (Pflicht-Header, deine Mail) | SEC XBRL + `11_economy fetch` | 403 von SEC; Vorlage in `.env.example` anpassen (kein persönlicher Default im Code verwenden) |
| `OPENAI_API_KEY` (optional, kostet Geld!) | `10_pruefung.py --ai`: KI-Gutachten | Ohne `--ai` läuft reine Regelprüfung kostenlos; mit `--ai` erst Kosten prüfen (`pipeline/ai_review.py`) |

## 2. Die Idee in 6 Sätzen (ohne Statistik)

1. **Keine gekauften Noten.** Wir messen wenige physische Größen selbst (CO₂,
   Unfälle, Schadstoffe, Verstöße), statt ESG-Scores zu kaufen.
2. **Nur innerhalb der Branche.** Ein Versorger stößt pro Umsatz-Dollar ~100×
   mehr aus als ein Softwarehaus — also Sektor/Sub-Industry als Vergleichsgruppe.
3. **Schwachstelle zählt.** Geometrisches Mittel: ein katastrophaler CO₂-Wert
   lässt sich nicht durch gute Nebenwerte „zurückkaufen“.
4. **Band statt Platz.** 1500 Zufallsdraws (Default in `02_analyse.py`; `montecarlo.py`-Default
   ist 1000) über 144 diskrete Kombis (4 Normalizer × 3 Weighter × 2 Aggregatoren ×
   2 Peer-Level × 3 Winsor) plus Leave-one-out (p=0,3) und Noise aus `match_confidence` —
   nominell als „576“ kommuniziert inkl. Drop-Varianten, technisch Zufallsstichprobe mit
   Wiederholung, keine Vollenumeration → Perzentilband P10–P90, kein Schein-Platz „#42“.
5. **Greenwashing extra.** Intensitäts-Illusion + bequemes Basisjahr stehen
   daneben, werden nie mit Leistung verrechnet.
6. **Kann die Firma weitermachen?** Neu: Economic Viability aus SEC-Filings —
   Cash-Erwirtschaftung + Schockpuffer (eigenes schlimmstes Jahr wiederholt)
   + Schuldendienst. Sättigend („genug ist genug“), schwächstes Glied entscheidet.
   Banken/Versicherer = not assessable.

Das ist bewusst einfach erzählt. Die volle Strenge steht in
`report/analyse_ranking.tex` (Methode+Perioden), `report/datenluecke.tex` (Quellen),
`report/datenkatalog.tex` (Katalog aus Daten), `report/qualitaetspruefung.tex` (QA),
`report/pruefung_vorgehen.tex` (Menschen-Workflow), `report/fusionsbericht.tex`
(Einstieg lang), `report/economic_viability.tex` (Economy) und `docs/COMPARISON.md`.
Generierte Tabellen: `report/generated/` (nie von Hand editieren).

## 3. Aufbau

```
pipeline/
  sources/base.py       Plug-in-Grenze: DataSource + Registry + Parquet-Cache
  sources/sp500.py, sec_revenue.py, epa_ghgrp.py, epa_campd.py, epa_tri.py,
          epa_echo.py, egrid.py, eia_*.py, osha_ita.py, dol_whd.py,
          sbti.py, team.py, esg_snapshot.py (nur Vergleichsmaßstab)
  resolve.py            Anlage → Konzern → Ticker (exakt/Override/fuzzy, Schwelle 92)
  canonical.py          eine Zeile je Firma×Jahr, Herkunft je Feld
  scoring/normalize.py  rang | z-getrimmt | min-max | median-mad
  scoring/weight.py     gleich | Entropie | CRITIC
  scoring/aggregate.py  geometrisch (default) | additiv
  scoring/montecarlo.py Unsicherheit → Rangband
  quality.py            F01–F13+P01–P02: fehler (nicht rechnen) vs pruefen (Beleg nötig)
  reliability.py        E/S/G-Belastbarkeit (≥2 Familien + Anker ≥0.8 + Summe ≥1.5)
  ai_review.py, flag_apply.py, consolidate.py, analysis.py, figures.py
  economy/              fetch_sec_facts.py + financial_health.py (Helfer) + economic_viability.py
scripts/ 01_fetch → 02_analyse → 03_grafiken → 04_datenluecke → 05_neue_dimensionen
         → 05b_firmenaggregate → 06_katalog → 07_dataset → 08_logos
         → 09_belastbarkeit → 10_pruefung → 11_economy (neu)
data/out/  committed Beispiel-Outputs als CSV+json (dataset_long, rangbaender,
           belastbarkeit, flags, economic_viability.csv, katalog_stats.json, ...).
           Parquet + data/raw/ sind ignoriert und werden regeneriert.
report/    LaTeX-Quellen + PDFs + figures/ + generated/ (generiert, nicht von Hand)
web/       Next.js-Browser: / (Liste), /firma/[ticker], /kennzahlen, /quellen,
           /vergleich, /belastbarkeit, /pruefung, /downloads. Liest
           web/public/data/*.json (App) + web/public/downloads/* (CSV/PDF) —
           beides generiert via 07+09 (nicht committen, lokal via 07 erzeugen).
           Logos via 08_logos.py (Wikidata+SEC+Favicon, Netz nötig).
docs/      ONBOARDING.md (Glossar+Zahlen+DAG) + COMPARISON.md (Abgrenzung/Limits)
```

**Erweitern (3 Zeilen):**
- Neue Quelle: von `DataSource` erben, `_fetch()` + `@register` — Stufen danach unverändert.
- Neue Kennzahl: Spalte in `canonical.py` + `Metric(...)` in `02_analyse.py` (`direction=-1` = kleiner besser).
- Neue Methode: Funktion in `normalize/weight/aggregate.py` registrieren — Monte-Carlo nimmt sie automatisch auf.

## 4. Datenlage (selbst geprüft, Stand 09/2026)

| Quelle | Zugang | Bringt / Grenze |
|---|---|---|
| EPA GHGRP (Envirofacts) | REST ohne Login | Scope-1 je Anlage, endet **2023**; `sector_type` trennen (Direkt vs. Supplier vs. Injektion), biogen auslassen — sonst Faktor-3-Fehler |
| SEC XBRL frames + companyfacts | REST, User-Agent | Umsatz bis FY2025; Viability FY2016–2026, 420 TTM ≥06/2026 |
| EPA CAMPD (CEMS) | kostenloser Key `EPA_CAMD_API_KEY` (Name mit D, Quelle mit P!) | Kraftwerks-CO₂ bis **2026**, Owner vs. Operator getrennt — schließt Strom-Lücke |
| PUDL Zenodo / Exhibit-21 | frei | CEMS-Spiegel + 916.290 Töchter (478/500 Mütter) — ersetzt OVERRIDES |
| SBTi-Excel | frei (kein API, 404) | 241 Firmen Zielstatus, 50 zurückgezogen |
| OSHA ITA, TRI, ECHO, eGRID, DOL-WHD, EIA | frei / EIA-Key nachrangig | OSHA 323, TRI 205, ECHO 138, eGRID 48 Firmen; davon +192 vorher nicht bewertbar → 349 bewertbar (69 %) |
| Kommerziell (esg_snapshot) | nur Benchmark | fließt **nie** in Note ein; Spearman-Vergleich in `analysis.py` |
| Sackgassen | geprüft | CDP (nur Städte), iShares (nur Fonds), TPI (Scraping-Verbot), TRACE Owners leer |

Nur `EPA CAMPD API` (Key heißt `EPA_CAMD_API_KEY`, wichtig) + `EIA` (nachrangig)
brauchen Accounts, beide kostenlos. Schreibweise: CAMPD = Quelle, CAMD = Key-Name.

## 5. Ergebnis + Vergleich + Limitationen (Kurzfassung)

- **Abdeckung:** 503 Ticker-Zeilen (= 500 Firmen), 44–45 Kennzahlen, ~11,4k Werte,
  18–19 Quellen (14 liefernd, Stand 09/2026).
  Klimaband nur 143 Firmen — fast nur Schwerindustrie, weil Tech/Finanzen in
  Scope 2/3 liegen (keine freien Firmendaten). Median-Bandbreite ~33–34 Punkte.
- **Viability:** 378 viable / 29 strained / 19 at-risk / 77 NA. Korrelation mit
  Größe ρ=0,03, mit Marge ρ=0,12 — kein Profit-Proxy (Intel-Verlust vs. Cash als Test).
- **Qualität:** 382 Flags (239 fehler, 143 pruefen) → nach Reparatur 10 + Grenzfälle;
  E/S/G-Belastbarkeit mit Beweisgewichten (gemessen 1,0 → Status 0,2).
- **Vs. MSCI/Sustainalytics/ISS:** keine gekauften Scores, keine additive
  Kompensation, kein exakter Rang, Greenwashing separat, jede Zahl mit Quelle +
  Unsicherheitsband. Details, Verbesserungen (Faktor-3-Fix, Staleness-Backtest
  Spearman 0,84 aber 37 % >10pp-Shift, Entkorrelierung) und ehrliche Limitationen
  (EPA-Lag, nur 143 Bänder, 36 ohne Wert, kein Scope 3, keine Historie der
  S&P-Liste, Peer-Raster nur GICS) → **`docs/COMPARISON.md`**.

## 6. Was bewusst fehlt / alt ist

- `data/out/ai_review_cache/`, `web/public/logos/`, `web/public/data/`,
  `web/public/downloads/` = generiert (siehe `.gitignore`), via 07/08/09 regenerierbar.
  Frischer Clone hat leeren Browser bis `07_dataset.py` läuft.
- `fusionsbericht (1).pdf` (altes f01–f07-Modell) aus clean enttrackt, liegt lokal
  weiter vor (Historie behält es, `.gitignore`).
- `feat/sustainability-observatory` (WBA-JS-App) und `worktree-peer-groups`
  (18er-Raster) nicht gemergt — Ideen in COMPARISON referenziert.
- `financial_health.py` bleibt nur als Helfer + dokumentierter Irrweg (Versuch 1);
  gültig ist `economic_viability.py` (Versuch 4).
- Alt-Triplikat `scripts/09_flags.py` + `report/auffaellige_werte.md` +
  `report/verbesserungen.*` (380-Flag-Vorläufer) ist ersetzt durch
  `pipeline/quality.py` + `scripts/10_pruefung.py` + `report/qualitaetspruefung.tex`
  (382 Flags) — siehe Cleanup-Commit.

PDF bauen (Tectonic 0.15.0, erster Lauf braucht HTTPS für Pakete):
`tectonic --untrusted --outdir report report/fusionsbericht.tex`
→ `pdfinfo`, `pdftoppm -scale-to 1200 -png` prüfen (Warnungen: Glyphen/Refs/Boxen).
Hinweis: `AGENTS.md` nennt anderes Beispiel (`--outdir .` für anderen Report) —
gültig für clean ist die Zeile hier. Web: immer `npm ci` (nicht `npm install`).
