"""Baut den gesammelten Datensatz -- mit einer Quelle an jedem einzelnen Wert.

Die Form ist bewusst lang statt breit: eine Zeile je Firma, Jahr und Kennzahl.
Nur so laesst sich die Herkunft an jedem *Wert* fuehren statt nur an der
Spalte. Eine breite Tabelle wuerde die Provenienz auf Spaltenebene
zusammenfassen und damit genau die Information verlieren, um die es geht --
naemlich dass die CO2-Zahl einer Firma gemessen, die der naechsten aber
selbstberichtet oder fortgeschrieben sein kann.

Ausgabe:

``dataset_long.parquet`` / ``.csv``   alle Werte mit Provenienz
``sources.json``                      Quellenregister mit Lizenz und Abrufdatum
``metrics.json``                      Kennzahlenregister mit Einheit und Richtung
``companies.json``                    verdichtete Sicht je Firma fuer die Web-App
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from .config import OUT, RAW

HEUTE = date.today().isoformat()

# ---------------------------------------------------------------------------
# Quellenregister. Jede Kennzahl verweist auf genau einen Eintrag hier.
# ---------------------------------------------------------------------------
SOURCES: dict[str, dict] = {
    "epa_ghgrp": {
        "name": "EPA Greenhouse Gas Reporting Program",
        "url": "https://data.epa.gov/efservice/PUB_DIM_FACILITY/",
        "access": "frei, ohne Anmeldung",
        "license": "US-Regierungswerk, gemeinfrei",
        "coverage": "US-Anlagen ueber 25 000 t CO2e, Berichtsjahre 2018-2023",
        "measurement": "gemeldet, teils aus Brennstoffmengen gerechnet",
        "caveat": "Reihe endet 2023; Direktemittenten von Lieferanten getrennt (sector_type)",
    },
    "epa_campd": {
        "name": "EPA Clean Air Markets Program Data",
        "url": "https://api.epa.gov/easey/emissions-mgmt/emissions/apportioned/annual",
        "access": "kostenloser Schluessel noetig",
        "license": "US-Regierungswerk, gemeinfrei",
        "coverage": "Kraftwerksbloecke der Handelsprogramme, 2019 bis laufendes Jahr",
        "measurement": "kontinuierliche Messung am Schornstein (CEMS)",
        "caveat": "nur Stromerzeugung; laufendes Jahr unvollstaendig",
    },
    "egrid": {
        "name": "EPA eGRID",
        "url": "https://www.epa.gov/egrid/download-data",
        "access": "frei",
        "license": "US-Regierungswerk, gemeinfrei",
        "coverage": "US-Kraftwerke, Berichtsjahr 2023",
        "measurement": "Emissionen und Erzeugung bereits verknuepft",
        "caveat": "nur aussagekraeftig fuer Firmen, deren Geschaeft Stromerzeugung ist",
    },
    "sec_xbrl": {
        "name": "SEC EDGAR XBRL frames",
        "url": "https://data.sec.gov/api/xbrl/frames/",
        "access": "frei, User-Agent noetig",
        "license": "oeffentlich",
        "coverage": "Geschaeftsjahre 2016-2025",
        "measurement": "aus Pflichtberichten",
        "caveat": "fuenf verschiedene Umsatz-Tags; Firmen taggen uneinheitlich",
    },
    "sbti": {
        "name": "Science Based Targets initiative",
        "url": "https://sciencebasedtargets.org/download/excel",
        "access": "frei, direkter xlsx-Download",
        "license": "Nutzung mit Quellenangabe",
        "coverage": "15 605 Organisationen weltweit, Stand laufend",
        "measurement": "Selbstmeldung, von SBTi geprueft",
        "caveat": "Selbstselektion: Firmen melden sich freiwillig; Energiebranche fehlt fast ganz",
    },
    "epa_tri": {
        "name": "EPA Toxics Release Inventory",
        "url": "https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/2023_US/csv/",
        "access": "frei",
        "license": "US-Regierungswerk, gemeinfrei",
        "coverage": "US-Anlagen, Berichtsjahr 2023",
        "measurement": "gemeldet",
        "caveat": "Gesamtmenge korreliert mit CO2 (rho 0,53); eigenstaendig ist der Krebserreger-Anteil",
    },
    "osha_ita": {
        "name": "OSHA Injury Tracking Application, Formular 300A",
        "url": "https://www.osha.gov/itadata",
        "access": "frei, vollstaendige Browser-Kopfzeilen noetig",
        "license": "US-Regierungswerk, gemeinfrei",
        "coverage": "US-Betriebsstaetten, 2023-2025",
        "measurement": "gemeldet, gesetzlich vorgeschrieben",
        "caveat": "DART misst auch Branchenstruktur; branchenrelativ vergleichen",
    },
    "epa_echo": {
        "name": "EPA ECHO Enforcement and Compliance History",
        "url": "https://echo.epa.gov/files/echodownloads/echo_exporter.zip",
        "access": "frei",
        "license": "US-Regierungswerk, gemeinfrei",
        "coverage": "US-Anlagen, Konformitaetshistorie drei Jahre",
        "measurement": "behoerdliche Feststellung",
        "caveat": "Zuordnung ueber FRS-Kennung, deshalb nur fuer Anlagen mit GHGRP-Eintrag",
    },
    "eia_923": {
        "name": "EIA Formular 923 (via PUDL und API)",
        "url": "https://www.eia.gov/electricity/data/eia923/",
        "access": "PUDL frei, API mit kostenlosem Schluessel",
        "license": "US-Regierungswerk, gemeinfrei",
        "coverage": "US-Kraftwerke ab 1 MW, 2021-2025",
        "measurement": "gemeldeter Brennstoffeinsatz und Erzeugung",
        "caveat": "unabhaengige Gegenprobe zu CEMS, nicht dieselbe Messkette",
    },
    "esg_snapshot": {
        "name": "Kommerzielle ESG-Risk-Ratings (Sustainalytics via Yahoo, gespiegelt)",
        "url": "https://raw.githubusercontent.com/sburstein/ESG-Stock-Data/main/sp_esg_stock_data.csv",
        "access": "frei gespiegelt",
        "license": "unklar -- nur als Vergleichsmassstab verwendet, nie als Eingabe",
        "coverage": "245 Firmen, Stand 2021",
        "measurement": "Anbieterbewertung",
        "caveat": "eingefroren 2021; fliesst in keine eigene Note ein",
    },
    "sp500_master": {
        "name": "S&P-500-Konstituenten",
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "access": "frei",
        "license": "CC BY-SA",
        "coverage": "503 Mitglieder, heutiger Stand",
        "measurement": "Stammdaten",
        "caveat": "nur der heutige Stand -- fuer historische Jahre ueberlebensverzerrt",
    },
    "pudl": {
        "name": "PUDL (Catalyst Cooperative) auf Zenodo",
        "url": "https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/stable/",
        "access": "frei, ohne Anmeldung",
        "license": "Public Domain",
        "coverage": "aufbereitete EIA-, EPA- und SEC-Daten, 1995 bis laufendes Jahr",
        "measurement": "aufbereitet aus Behoerdenquellen",
        "caveat": "Zwischenschicht: Aufbereitungsfehler sind moeglich, dafuer entfaellt eigene Bereinigung",
    },
    "pudl_sec_ex21": {
        "name": "SEC 10-K Anlage 21 (Konzernstruktur, via PUDL)",
        "url": "https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/stable/core_sec10k__quarterly_exhibit_21_company_ownership.parquet",
        "access": "frei, ohne Anmeldung",
        "license": "Public Domain",
        "coverage": "3,8 Mio. Tochtereintraege, 478 von 500 Indexmuettern",
        "measurement": "aus Pflichtanlagen der Boersenaufsicht",
        "caveat": "Namen in Kleinschreibung und teils abgeschnitten; Beteiligungsquote nur bei 99 117 Eintraegen",
    },
    "sec_dera": {
        "name": "SEC 10-K-Finanzkennzahlen (companyfacts, aufbereitet von Janis)",
        "url": "https://data.sec.gov/api/xbrl/companyfacts/",
        "access": "frei, User-Agent noetig",
        "license": "oeffentlich",
        "coverage": "Geschaeftsjahr 2024, 499 Indexfirmen",
        "measurement": "aus Pflichtberichten",
        "caveat": "Schulden uneinheitlich getaggt (debt_tag); F&E nur bei 135 Firmen berichtet",
    },
    "dol_whd": {
        "name": "DOL Wage and Hour Division, Verfahren (aufbereitet von Janis)",
        "url": "https://data.dol.gov/data-catalog/WHD/enforcement/WHD_enforcement.zip",
        "access": "frei, ohne Anmeldung",
        "license": "US-Regierungswerk, gemeinfrei",
        "coverage": "Feststellungsende 2022-2024",
        "measurement": "behoerdliche Feststellung",
        "caveat": "kein CIK, Zuordnung ueber Namen; Firmen ohne Treffer fehlen statt als Null zu erscheinen. Gegenprobe mit eigenem exakten Abgleich: 127 statt 213 Firmen, Rangkorrelation der Fallzahlen 0,62 -- die Team-Zuordnung zaehlt vermutlich Franchise-Betriebe unter dem Markennamen mit (McDonald's 142 gegen 64 Faelle)",
    },
    "sec_sd": {
        "name": "SEC Form SD, Konfliktmineralien (aufbereitet von Janis)",
        "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=SD",
        "access": "frei",
        "license": "oeffentlich",
        "coverage": "Meldungen 2022-2025",
        "measurement": "Pflichtmeldung",
        "caveat": "zeigt nur, dass gemeldet wird -- nicht, was die Meldung ueber Schmelzen und Herkunft sagt",
    },
    "wba": {
        "name": "World Benchmarking Alliance, Unternehmensprofile 2026 (erhoben von Janis)",
        "url": "https://www.worldbenchmarkingalliance.org/company-scoreboard",
        "access": "frei, oeffentliche Profilseiten",
        "license": "CC BY 4.0 -- Namensnennung: World Benchmarking Alliance",
        "coverage": "217 Indexfirmen, Bewertungsrunde 2026",
        "measurement": "Bewertung veroeffentlichter Angaben",
        "caveat": "haengt an Offenlegung; Benchmarks nicht unabhaengig; CTT fast ohne Streuung (216 von 217 = 0)",
    },
    "wikidata": {
        "name": "Wikidata, offizielle Websites (fuer Firmenlogos)",
        "url": "https://query.wikidata.org/sparql",
        "access": "frei, ohne Anmeldung",
        "license": "CC0",
        "coverage": "Website ueber CIK (P5531 -> P856), Rest aus SEC Submissions",
        "measurement": "Stammdaten",
        "caveat": "nur fuer die Anzeige; Logos sind Favicons und Marken der jeweiligen Firmen",
    },
    "eigene_berechnung": {
        "name": "Eigene Berechnung dieser Pipeline",
        "url": "scripts/02_analyse.py",
        "access": "reproduzierbar",
        "license": "-",
        "coverage": "abgeleitet aus den oben genannten Quellen",
        "measurement": "berechnet",
        "caveat": "Herkunft der Eingangsgroessen steht jeweils beim Basiswert",
    },
}

# ---------------------------------------------------------------------------
# Kennzahlenregister: Einheit, Richtung, Achse und Quelle.
# direction -1 = kleiner ist besser, +1 = groesser ist besser, 0 = neutral
# ---------------------------------------------------------------------------
METRICS: dict[str, dict] = {
    "scope1_t": ("Scope-1-Emissionen", "t CO2e", -1, "A", "epa_ghgrp"),
    "co2_intensity": ("CO2-Intensitaet", "t CO2e je Mio. USD Umsatz", -1, "A", "eigene_berechnung"),
    "intensity_cagr": ("Trend der Intensitaet", "%/Jahr", -1, "A", "eigene_berechnung"),
    "absolute_cagr": ("Trend der absoluten Tonnen", "%/Jahr", -1, "A", "eigene_berechnung"),
    "n_facilities": ("zugeordnete Anlagen", "Anzahl", 0, "meta", "epa_ghgrp"),
    "match_confidence": ("Zuordnungskonfidenz", "0-1", 1, "meta", "eigene_berechnung"),
    "revenue_musd": ("Umsatz", "Mio. USD", 0, "meta", "sec_xbrl"),
    "campd_co2_t": ("CO2 gemessen (CEMS)", "t CO2e", -1, "A", "epa_campd"),
    "campd_plants": ("Kraftwerke mit Messung", "Anzahl", 0, "meta", "epa_campd"),
    "t_co2_pro_mwh": ("CO2 je erzeugter MWh", "t CO2e/MWh", -1, "A", "egrid"),
    "egrid_plants": ("eGRID-Kraftwerke", "Anzahl", 0, "meta", "egrid"),
    "tri_releases_lbs": ("Giftstofffreisetzung", "lbs", -1, "A", "epa_tri"),
    "tri_carcinogen_lbs": ("davon krebserregend", "lbs", -1, "A", "epa_tri"),
    "tri_facilities": ("TRI-Anlagen", "Anzahl", 0, "meta", "epa_tri"),
    "dart_rate": ("Unfallrate DART", "Faelle je 100 Vollzeitkraefte", -1, "S", "osha_ita"),
    "osha_deaths": ("Todesfaelle", "Anzahl", -1, "S", "osha_ita"),
    "osha_sites": ("gemeldete Betriebsstaetten", "Anzahl", 0, "meta", "osha_ita"),
    "echo_penalties_usd": ("Umweltstrafen", "USD", -1, "G", "epa_echo"),
    "echo_nc_quarters_per_site": ("Verstossquartale je Anlage", "Quartale", -1, "G", "epa_echo"),
    "echo_significant": ("Anlagen mit schwerem Verstoss", "Anzahl", -1, "G", "epa_echo"),
    "rank_band_width": ("Breite des Rangbands", "Perzentilpunkte", 0, "meta", "epa_ghgrp"),
    "sbti_validated": ("SBTi-geprueftes Ziel", "ja/nein", 1, "B", "sbti"),
    "sbti_near_term_year": ("Zwischenzieljahr", "Jahr", 0, "B", "sbti"),
    "sbti_net_zero_year": ("Netto-null-Jahr", "Jahr", 0, "B", "sbti"),
    "sbti_commitment_removed": ("Nahziel-Zusage zurueckgezogen", "ja/nein", -1, "B", "sbti"),
    "sbti_net_zero_removed": ("Netto-null-Zusage zurueckgezogen", "ja/nein", -1, "B", "sbti"),
    "sbti_near_term_expired": ("Zwischenziel abgelaufen", "ja/nein", -1, "B", "sbti"),
    "intensity_illusion": ("Intensitaet faellt, Tonnen steigen", "ja/nein", -1, "B", "eigene_berechnung"),
    "base_year_ratio": ("Basisjahr-Bequemlichkeit", "Verhaeltnis", -1, "B", "eigene_berechnung"),
    "rank_p10": ("Rangband untere Grenze", "Perzentil", 1, "ergebnis", "eigene_berechnung"),
    "rank_p50": ("Rangband Median", "Perzentil", 1, "ergebnis", "eigene_berechnung"),
    "rank_p90": ("Rangband obere Grenze", "Perzentil", 1, "ergebnis", "eigene_berechnung"),
    "esg_risk_total": ("kommerzielles ESG-Risiko", "Punkte", -1, "vergleich", "esg_snapshot"),
    "net_income_usd": ("Nettogewinn", "USD", 0, "meta", "sec_dera"),
    "total_assets_usd": ("Bilanzsumme", "USD", 0, "meta", "sec_dera"),
    "total_debt_usd": ("Finanzschulden", "USD", 0, "meta", "sec_dera"),
    "operating_cf_usd": ("operativer Cashflow", "USD", 0, "meta", "sec_dera"),
    "capex_usd": ("Sachinvestitionen", "USD", 0, "meta", "sec_dera"),
    "rnd_usd": ("Forschung und Entwicklung", "USD", 0, "meta", "sec_dera"),
    "whd_cases": ("Lohnverfahren 2022-2024", "Anzahl", -1, "S", "dol_whd"),
    "whd_backwages_usd": ("nachgezahlte Loehne", "USD", -1, "S", "dol_whd"),
    "whd_employees": ("betroffene Beschaeftigte", "Anzahl", -1, "S", "dol_whd"),
    "whd_violations": ("festgestellte Verstoesse", "Anzahl", -1, "S", "dol_whd"),
    "whd_penalties_usd": ("Geldbussen Lohnrecht", "USD", -1, "S", "dol_whd"),
    "sd_conflict_minerals_filer": ("meldet Konfliktmineralien (Form SD)", "ja/nein", 0, "meta", "sec_sd"),
    "wba_tpq": ("WBA Qualitaet des Transitionsplans", "0-5", 1, "B", "wba"),
    "wba_ctt": ("WBA Beitrag zur Transition", "0-2", 1, "B", "wba"),
    "wba_social": ("WBA Social Benchmark", "0-100", 1, "S", "wba"),
    "wba_nature": ("WBA Nature Benchmark", "0-100", 1, "B", "wba"),
    "wba_just_transition": ("WBA Just Transition", "0-100", 1, "S", "wba"),
}


def _read(path, **kw) -> pd.DataFrame:
    return pd.read_csv(path, **kw) if path.exists() else pd.DataFrame()


def _add(rows: list, df: pd.DataFrame, mapping: dict[str, str], year=None) -> None:
    """Haengt Werte im Langformat an, eine Zeile je Firma/Jahr/Kennzahl."""
    if df.empty:
        return
    year_col = "year" if "year" in df.columns else None
    for col, metric in mapping.items():
        if col not in df.columns:
            continue
        sub = df[["ticker", col] + ([year_col] if year_col else [])].dropna(subset=[col])
        for rec in sub.itertuples(index=False):
            val = getattr(rec, col if col.isidentifier() else "_1")
            if isinstance(val, (np.bool_, bool)):
                val = float(bool(val))
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(val):
                continue
            rows.append(
                {
                    "ticker": rec.ticker,
                    "year": int(getattr(rec, year_col)) if year_col else year,
                    "metric": metric,
                    "value": val,
                }
            )


def dedupe_cik(master: pd.DataFrame) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Aktiengattungen derselben CIK auf einen Ticker zusammenfuehren.

    Alphabet stand als GOOG und GOOGL mit identischen Konzernzahlen im
    Bestand, ebenso Fox und News Corp. Ein Emittent ist eine Zeile; die
    Klasse A (meist die stimmberechtigte, hier stets die laengere Schreibweise)
    fuehrt, die andere wird zum Alias.
    """
    primaer: dict[str, str] = {}
    alias: dict[str, list[str]] = {}
    for cik, g in master.dropna(subset=["cik"]).groupby("cik"):
        if len(g) < 2:
            continue
        tickers = sorted(g["ticker"], key=lambda t: (-len(t), t))
        haupt, rest = tickers[0], tickers[1:]
        alias[haupt] = rest
        for t in rest:
            primaer[t] = haupt
    return primaer, alias


def build() -> pd.DataFrame:
    master = pd.read_parquet(RAW / "sp500_master.parquet")
    rows: list[dict] = []

    panel = _read(OUT / "panel_periode_a.csv")
    if not panel.empty:
        panel = panel.assign(year=panel["year_last"])
        _add(rows, panel, {
            "scope1_t": "scope1_t", "co2_intensity": "co2_intensity",
            "intensity_cagr": "intensity_cagr", "absolute_cagr": "absolute_cagr",
            "n_facilities": "n_facilities", "match_confidence": "match_confidence",
            "revenue_musd": "revenue_musd", "base_year_ratio": "base_year_ratio",
            "intensity_illusion": "intensity_illusion",
        })

    cy = _read(OUT / "company_year.csv")
    if not cy.empty:
        _add(rows, cy, {"scope1_t": "scope1_t", "revenue_musd": "revenue_musd",
                        "co2_intensity": "co2_intensity"})

    bands = _read(OUT / "rangbaender_periode_a.csv")
    if not bands.empty:
        bands = bands.assign(year=2023)
        # Ein Band ueber 70 Perzentilpunkten sagt nichts ueber den Rang aus.
        # Der Median suggeriert dann eine Einordnung, die es nicht gibt --
        # also Band zeigen, Mittelwert weglassen.
        breit = bands["band_width"] >= 70
        bands.loc[breit, "p50"] = np.nan
        _add(rows, bands, {"p10": "rank_p10", "p50": "rank_p50", "p90": "rank_p90",
                           "band_width": "rank_band_width"})

    egrid = _read(OUT / "egrid_je_firma.csv")
    if not egrid.empty:
        _add(rows, egrid.assign(year=2023),
             {"t_co2_pro_mwh": "t_co2_pro_mwh", "kraftwerke": "egrid_plants"})

    tri = _read(OUT / "tri_je_firma.csv")
    if not tri.empty:
        _add(rows, tri.assign(year=2023),
             {"freisetzung_lbs": "tri_releases_lbs", "krebs_lbs": "tri_carcinogen_lbs",
              "anlagen": "tri_facilities"})

    osha = _read(OUT / "osha_je_firma.csv")
    if not osha.empty:
        _add(rows, osha.assign(year=2025),
             {"dart_rate": "dart_rate", "tote": "osha_deaths", "betriebe": "osha_sites"})

    echo = _read(OUT / "echo_je_firma.csv")
    if not echo.empty:
        # Die Spaltennamen der ECHO-Auswertung haben zwei Auspraegungen, je
        # nachdem welches Skript sie zuletzt geschrieben hat.
        _add(rows, echo.assign(year=2025), {
            "strafen": "echo_penalties_usd",
            "strafen_usd": "echo_penalties_usd",
            "vq_je_anlage": "echo_nc_quarters_per_site",
            "verstossquartale_je_anlage": "echo_nc_quarters_per_site",
            "sv": "echo_significant",
            "schwere_verstoesse": "echo_significant",
        })

    # ---- Team: Janis' Querschnitt (SEC-Finanzen, DOL WHD, Form SD) --------
    hv_path = RAW / "team_harte_variablen.parquet"
    if hv_path.exists():
        hv = pd.read_parquet(hv_path)
        _add(rows, hv.assign(year=2024), {
            "net_usd_fy24": "net_income_usd", "assets_usd_fy24": "total_assets_usd",
            "debt_usd_fy24": "total_debt_usd", "ocf_usd_fy24": "operating_cf_usd",
            "capex_usd_fy24": "capex_usd", "rnd_usd_fy24": "rnd_usd",
        })
        sd = hv.assign(year=2025, sd_flag=(hv["sd_filer_22_25"] == "Ja").astype(float))
        _add(rows, sd, {"sd_flag": "sd_conflict_minerals_filer"})

    # ---- Lohnverfahren des Arbeitsministeriums ----------------------------
    whd = _whd_by_company(master)
    if not whd.empty:
        _add(rows, whd.assign(year=2024), {
            "faelle": "whd_cases", "verstoesse": "whd_violations",
            "nachzahlung_usd": "whd_backwages_usd", "beschaeftigte": "whd_employees",
            "strafen_usd": "whd_penalties_usd",
        })

    # ---- Team: WBA-Bewertungen (CC BY 4.0) --------------------------------
    wba_path = RAW / "team_wba.parquet"
    if wba_path.exists():
        wba = pd.read_parquet(wba_path).assign(year=2026)
        _add(rows, wba, {"tpq": "wba_tpq", "ctt": "wba_ctt", "social": "wba_social",
                         "nature": "wba_nature", "just_transition": "wba_just_transition"})

    # Mycelium bleibt bewusst draussen: Die Nutzungsbedingungen untersagen die
    # Weitergabe als Datensatz (siehe sources/team.py, INTERNAL_ONLY).

    long = pd.DataFrame(rows)

    # ---- CAMPD: die aktuellen Jahre, ueber ownerOperator zugeordnet ----------
    campd = _campd_by_company(master)
    if not campd.empty:
        long = pd.concat([long, campd], ignore_index=True)

    # ---- SBTi ---------------------------------------------------------------
    sbti = _sbti_by_company(master)
    if not sbti.empty:
        long = pd.concat([long, sbti], ignore_index=True)

    # ---- kommerzieller Vergleichsmassstab -----------------------------------
    esg_path = RAW / "esg_snapshot.parquet"
    if esg_path.exists():
        esg = pd.read_parquet(esg_path)
        e = pd.DataFrame({
            "ticker": esg["ticker"], "year": 2021, "metric": "esg_risk_total",
            "value": pd.to_numeric(esg["esg_risk_total"], errors="coerce"),
        }).dropna()
        long = pd.concat([long, e], ignore_index=True)

    # ---- Aktiengattungen derselben CIK zusammenfuehren -----------------------
    primaer, _ = dedupe_cik(master)
    if primaer:
        long["ticker"] = long["ticker"].replace(primaer)

    # ---- Provenienz und Stammdaten anhaengen --------------------------------
    meta = pd.DataFrame(
        [(k, v[0], v[1], v[2], v[3], v[4]) for k, v in METRICS.items()],
        columns=["metric", "metric_label", "unit", "direction", "axis", "source_id"],
    )
    long = long.merge(meta, on="metric", how="left")
    long = long.merge(
        master[["ticker", "company", "gics_sector", "gics_sub_industry"]],
        on="ticker", how="left",
    )
    src = pd.DataFrame(
        [{"source_id": k, "source_name": v["name"], "source_url": v["url"],
          "source_access": v["access"], "source_license": v["license"]}
         for k, v in SOURCES.items()]
    )
    long = long.merge(src, on="source_id", how="left")
    long["retrieved_at"] = HEUTE
    # Das laufende Kalenderjahr ist bei fortlaufend gemeldeten Quellen nur
    # teilweise erfasst. Ohne Kennzeichnung liest sich ein Fuenf-Monats-Wert
    # wie ein Jahreswert.
    laufend = date.today().year
    long["partial_year"] = (long["year"] >= laufend) & long["source_id"].isin(
        {"epa_campd"}
    )
    long = long.dropna(subset=["company", "source_id"])
    long = long.drop_duplicates(["ticker", "year", "metric"])
    return long.sort_values(["ticker", "metric", "year"]).reset_index(drop=True)


# Handelsprogramme mit CO2-Meldepflicht (CAMD Power Sector Emissions Data
# Guide, Juli 2022): Acid Rain Program, RGGI, NSPS Subpart TTTT.
CO2_PROGRAMME = ("ARP", "RGGI", "NSPS4T")


def _campd_by_company(master: pd.DataFrame) -> pd.DataFrame:
    """CAMPD-Emissionen ueber das Eigentuemerfeld auf Ticker verteilen."""
    from .resolve import OVERRIDES, normalize, override_prefix, owner_valid
    from .sources.epa_campd import split_owner_operator

    ep, fp = RAW / "campd_emission.parquet", RAW / "campd_facility.parquet"
    if not (ep.exists() and fp.exists()):
        return pd.DataFrame()
    emi, fac = pd.read_parquet(ep), pd.read_parquet(fp)
    lookup = {normalize(r.company): r.ticker for r in master.itertuples()}

    def to_ticker(name: str):
        k = normalize(name)
        if k in lookup:
            return lookup[k]
        if k in OVERRIDES:
            return OVERRIDES[k]
        return override_prefix(k)

    # CO2 melden nur bestimmte Programme. Der CAMD-Datenleitfaden nennt fuer
    # SIPNOX "heat input and NOx", fuer RGGI "heat input and CO2". Eine Anlage,
    # die nur im NOx-Programm steckt, meldet null CO2, weil niemand es misst --
    # als Messwert waere diese Null falsch. Deshalb zaehlen hier nur Anlagen
    # mit CO2-Pflicht; fuer alle anderen bleibt der Wert fehlend.
    programme = fac["programCodeInfo"].astype(str).str.upper()
    fac = fac[programme.str.contains("|".join(CO2_PROGRAMME), regex=True, na=False)]
    if fac.empty:
        return pd.DataFrame()
    own = fac[["facilityId", "year", "ownerOperator"]].drop_duplicates()
    recs = []
    for fid, yr, raw in own.itertuples(index=False):
        for name, role in split_owner_operator(raw):
            if role != "owner":
                continue
            t = to_ticker(name)
            if t and owner_valid(normalize(name), t, yr):
                recs.append({"facilityId": fid, "year": yr, "ticker": t})
    if not recs:
        return pd.DataFrame()
    link = pd.DataFrame(recs).drop_duplicates()
    j = emi.merge(link, on=["facilityId", "year"], how="inner")
    j = j.drop_duplicates(subset=["facilityId", "year", "ticker"])
    agg = j.groupby(["ticker", "year"], as_index=False).agg(
        campd_co2_t=("co2_t", "sum"), campd_plants=("facilityId", "nunique")
    )
    # Bleibt nach dem Programmfilter nichts uebrig, ist die Menge fehlend --
    # nicht null.
    agg.loc[agg["campd_co2_t"] <= 0, "campd_co2_t"] = np.nan
    out = agg.melt(id_vars=["ticker", "year"], var_name="metric", value_name="value")
    return out.dropna(subset=["value"])


def _whd_by_company(master: pd.DataFrame) -> pd.DataFrame:
    """Lohnverfahren aus den Rohdaten des Arbeitsministeriums zuordnen.

    Die Team-Datei hatte diese Zahlen ueber Namensbestandteile zugeordnet und
    dabei "APDC Cleaning Services" Air Products zugeschlagen (212 Verfahren,
    in den Rohdaten null). Die Verfahren tragen keine Firmenkennung, nur
    Rechts- und Handelsnamen -- deshalb hier nur exakte Namen, die
    Tochtertabelle und der Konzernpraefix, kein unscharfer Abgleich.
    """
    from .resolve import OVERRIDES, master_prefix, normalize, override_prefix

    p = RAW / "dol_whd.parquet"
    if not p.exists():
        return pd.DataFrame()
    w = pd.read_parquet(p)
    lookup = {normalize(r.company): r.ticker for r in master.itertuples()}

    def to_ticker(name):
        k = normalize(name)
        if not k:
            return None
        return lookup.get(k) or override_prefix(k) or master_prefix(k, lookup)

    w["ticker"] = w["legal_name"].map(to_ticker).fillna(w["trade_nm"].map(to_ticker))
    hit = w.dropna(subset=["ticker"])
    if hit.empty:
        return pd.DataFrame()
    agg = hit.groupby("ticker", as_index=False).agg(
        faelle=("case_id", "nunique"),
        verstoesse=("case_violtn_cnt", "sum"),
        nachzahlung_usd=("bw_atp_amt", "sum"),
        beschaeftigte=("ee_atp_cnt", "sum"),
        strafen_usd=("cmp_assd", "sum"),
    )
    return agg


def _sbti_by_company(master: pd.DataFrame) -> pd.DataFrame:
    from .resolve import normalize

    p = RAW / "sbti_targets.parquet"
    if not p.exists():
        return pd.DataFrame()
    s = pd.read_parquet(p)
    s["key"] = s["company_name"].map(normalize)
    m = master.assign(key=master["company"].map(normalize)).merge(
        s.drop_duplicates("key"), on="key", how="inner"
    )
    # SBTi fuehrt den Status je Zieltyp. Ein gesetztes Nahziel und eine
    # zurueckgezogene Netto-null-Zusage sind kein Widerspruch, sondern zwei
    # Zeilen -- vorher wurden beide in ein Feld geworfen und 25 Firmen waren
    # gleichzeitig "geprueft" und "zurueckgezogen".
    nah = m["near_term_status"].astype(str)
    netto = m["net_zero_status"].astype(str)
    gesetzt = nah.str.contains("Targets set", case=False)
    nah_jahr = pd.to_numeric(m["near_term_year"], errors="coerce")
    abgelaufen = gesetzt & nah_jahr.notna() & (nah_jahr < date.today().year)
    out = pd.DataFrame({
        "ticker": m["ticker"],
        # Geprueft ist nur, wer ein gesetztes und nicht abgelaufenes Nahziel hat.
        "sbti_validated": (gesetzt & ~abgelaufen).astype(float),
        "sbti_near_term_expired": abgelaufen.astype(float),
        "sbti_commitment_removed": nah.str.contains("removed", case=False).astype(float),
        "sbti_net_zero_removed": netto.str.contains("removed", case=False).astype(float),
        "sbti_near_term_year": nah_jahr,
        "sbti_net_zero_year": pd.to_numeric(m["net_zero_year"], errors="coerce")
        .where(netto.str.contains("Targets set|Committed", case=False)),
    })
    long = out.melt(id_vars="ticker", var_name="metric", value_name="value").dropna()
    long["year"] = 2026
    return long


def write_all() -> dict:
    long = build()
    # Prüfergebnisse anhängen, sofern eine Prüfung gelaufen ist. Werte werden
    # dabei nicht geändert, nur gekennzeichnet (pipeline/flag_apply.py).
    from .flag_apply import apply as apply_flags
    long = apply_flags(long)
    long.to_parquet(OUT / "dataset_long.parquet", index=False)
    long.to_csv(OUT / "dataset_long.csv", index=False)

    (OUT / "sources.json").write_text(
        json.dumps(
            {k: {**v, "retrieved_at": HEUTE} for k, v in SOURCES.items()},
            indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (OUT / "metrics.json").write_text(
        json.dumps(
            {k: {"label": v[0], "unit": v[1], "direction": v[2], "axis": v[3],
                 "source_id": v[4]} for k, v in METRICS.items()},
            indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Verdichtete Sicht je Firma fuer die Web-App: neuester Wert je Kennzahl.
    # Fuer die verdichtete Sicht das juengste *vollstaendige* Jahr nehmen und
    # nur dann auf ein angebrochenes ausweichen, wenn es kein anderes gibt.
    # Doppelte Aktiengattungen (gleiche CIK) nur einmal fuehren; als Fehler
    # gekennzeichnete Werte bleiben im Langformat, aber nicht in der Firmenansicht.
    master = pd.read_parquet(RAW / "sp500_master.parquet")
    _, alias = dedupe_cik(master)
    duplicate_tickers = {t for lst in alias.values() for t in lst}
    shown = long[long["quality_status"] != "fehler"]
    latest = (
        shown.sort_values(["partial_year", "year"], ascending=[False, True])
        .groupby(["ticker", "metric"], as_index=False)
        .last()
    )
    companies = []
    for ticker, g in latest.groupby("ticker"):
        row = g.iloc[0]
        companies.append(
            {
                "ticker": ticker,
                "company": row["company"],
                "sector": row["gics_sector"],
                "subIndustry": row["gics_sub_industry"],
                "alias": alias.get(ticker, []),
                "metrics": [
                    {
                        "metric": r["metric"],
                        "label": r["metric_label"],
                        "value": None if pd.isna(r["value"]) else float(r["value"]),
                        "unit": r["unit"],
                        "year": int(r["year"]) if pd.notna(r["year"]) else None,
                        "axis": r["axis"],
                        "sourceId": r["source_id"],
                        "sourceName": r["source_name"],
                        "sourceUrl": r["source_url"],
                        "partial": bool(r.get("partial_year", False)),
                        "qualityStatus": r.get("quality_status", "ok"),
                        "qualityRule": r.get("quality_rule", ""),
                        "qualityNote": r.get("quality_note", ""),
                    }
                    for _, r in g.iterrows()
                ],
            }
        )
    # "Ohne Daten" heisst ohne Nachhaltigkeitsdaten. Seit die Finanzkennzahlen
    # aus den 10-K-Berichten dabei sind, hat fast jede Firma irgendeinen Wert --
    # ein Umsatz macht eine Firma aber nicht bewertbar.
    bewertend = latest[~latest["axis"].isin(["meta", "vergleich"])]
    assessed = set(bewertend["ticker"])
    for c in companies:
        c["assessed"] = c["ticker"] in assessed
    missing = [
        {"ticker": r.ticker, "company": r.company, "sector": r.gics_sector}
        for r in master.itertuples()
        if r.ticker not in assessed and r.ticker not in duplicate_tickers
    ]
    payload = {
        "generatedAt": HEUTE,
        "companies": sorted(companies, key=lambda c: -len(c["metrics"])),
        "withoutData": missing,
        "sources": {k: {**v, "retrieved_at": HEUTE} for k, v in SOURCES.items()},
        "metrics": {
            k: {"label": v[0], "unit": v[1], "direction": v[2], "axis": v[3],
                "sourceId": v[4]}
            for k, v in METRICS.items()
        },
    }
    (OUT / "companies.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "zeilen": len(long),
        "firmen": int(long["ticker"].nunique()),
        "kennzahlen": int(long["metric"].nunique()),
        "quellen": int(long["source_id"].nunique()),
        "jahre": [int(long["year"].min()), int(long["year"].max())],
        "ohne_daten": len(missing),
    }
