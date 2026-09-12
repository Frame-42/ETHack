"""Wie belastbar ist das, was wir über eine Firma wissen -- getrennt nach E, S und G.

Die Frage ist nicht "wie gut ist die Firma", sondern "reicht das Material, um
das überhaupt zu beurteilen". Drei Grundsätze bestimmen die Regeln:

1. **Nicht jede Zahl zählt gleich.** Am Schornstein Gemessenes wiegt mehr als
   behördlich Gemeldetes, das mehr als eine Bewertung von Offenlegung, das
   mehr als eine Selbstauskunft. Das Gewicht drückt Beweiskraft aus, keine
   inhaltliche Wichtigkeit.

2. **Abgeleitetes zählt nicht doppelt.** CO2-Menge, CO2-Intensität und
   Messung am Schornstein beschreiben denselben Sachverhalt. Kennzahlen
   werden deshalb zu *Familien* zusammengefasst; eine Familie zählt einmal,
   mit dem Gewicht ihrer stärksten vorhandenen Kennzahl.

3. **Eine Quelle allein trägt kein Urteil.** Die ESG-Forschung zeigt, dass
   Einzelmessungen stark streuen. "Belastbar" verlangt deshalb mindestens zwei
   unabhängige Familien, davon mindestens einen harten Anker.

Die Werte unten sind gesetzt, nicht geschätzt. Sie stehen hier, damit sie
diskutiert und geändert werden können.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

PILLARS = {
    "E": "Umwelt",
    "S": "Soziales",
    "G": "Unternehmensführung",
}


@dataclass(frozen=True)
class Evidence:
    pillar: str
    family: str
    family_label: str
    weight: float
    evidence: str


# Beweiskraft je Kennzahl. 1,0 gemessen oder behördlich festgestellt;
# 0,8 gesetzlich gemeldet; 0,5 bis 0,7 abgeleitet oder mit unsicherer
# Zuordnung; 0,3 bis 0,4 Bewertung von Offenlegung oder geprüfte
# Selbstauskunft; 0,2 bloßer Meldestatus.
METRIC_EVIDENCE: dict[str, Evidence] = {
    # ---- E ---------------------------------------------------------------
    "campd_co2_t": Evidence("E", "ghg", "Treibhausgase", 1.0, "am Schornstein gemessen (CEMS)"),
    "scope1_t": Evidence("E", "ghg", "Treibhausgase", 0.8, "behördlich gemeldet (GHGRP)"),
    "co2_intensity": Evidence("E", "ghg", "Treibhausgase", 0.8, "gemeldet, auf Umsatz bezogen"),
    "t_co2_pro_mwh": Evidence("E", "effizienz", "Erzeugungseffizienz", 0.8, "gemessen und gemeldet, nur Stromerzeuger"),
    "tri_releases_lbs": Evidence("E", "schadstoffe", "Schadstofffreisetzung", 0.8, "behördlich gemeldet (TRI)"),
    "tri_carcinogen_lbs": Evidence("E", "schadstoffe", "Schadstofffreisetzung", 0.8, "behördlich gemeldet (TRI)"),
    "intensity_cagr": Evidence("E", "trend", "Emissionstrend", 0.5, "abgeleitet aus mindestens drei Jahren"),
    "absolute_cagr": Evidence("E", "trend", "Emissionstrend", 0.5, "abgeleitet aus mindestens drei Jahren"),
    "wba_nature": Evidence("E", "natur", "Naturbewertung", 0.4, "Bewertung veröffentlichter Angaben (WBA)"),
    "sbti_validated": Evidence("E", "klimaziele", "Klimaziele", 0.3, "Selbstauskunft, extern geprüft (SBTi)"),
    "sbti_near_term_year": Evidence("E", "klimaziele", "Klimaziele", 0.3, "Selbstauskunft, extern geprüft (SBTi)"),
    "sbti_net_zero_year": Evidence("E", "klimaziele", "Klimaziele", 0.3, "Selbstauskunft, extern geprüft (SBTi)"),
    "wba_tpq": Evidence("E", "klimaziele", "Klimaziele", 0.3, "Bewertung des Transitionsplans (WBA)"),
    "wba_ctt": Evidence("E", "klimaziele", "Klimaziele", 0.3, "Bewertung des Transitionsbeitrags (WBA)"),
    # ---- S ---------------------------------------------------------------
    "dart_rate": Evidence("S", "arbeitssicherheit", "Arbeitssicherheit", 1.0, "gesetzliche Meldung je Betrieb (OSHA)"),
    "osha_deaths": Evidence("S", "arbeitssicherheit", "Arbeitssicherheit", 1.0, "gesetzliche Meldung je Betrieb (OSHA)"),
    "whd_cases": Evidence("S", "lohnrecht", "Lohnrecht", 0.7, "behördlich festgestellt, Namenszuordnung unsicher"),
    "whd_backwages_usd": Evidence("S", "lohnrecht", "Lohnrecht", 0.7, "behördlich festgestellt, Namenszuordnung unsicher"),
    "whd_employees": Evidence("S", "lohnrecht", "Lohnrecht", 0.7, "behördlich festgestellt, Namenszuordnung unsicher"),
    "wba_social": Evidence("S", "sozialbewertung", "Sozialbewertung", 0.4, "Bewertung veröffentlichter Angaben (WBA)"),
    "wba_just_transition": Evidence("S", "sozialbewertung", "Sozialbewertung", 0.4, "Bewertung veröffentlichter Angaben (WBA)"),
    # ---- G ---------------------------------------------------------------
    "echo_penalties_usd": Evidence("G", "regeltreue", "Umweltregeltreue", 1.0, "behördlich festgestellt (ECHO)"),
    "echo_nc_quarters_per_site": Evidence("G", "regeltreue", "Umweltregeltreue", 1.0, "behördlich festgestellt (ECHO)"),
    "echo_significant": Evidence("G", "regeltreue", "Umweltregeltreue", 1.0, "behördlich festgestellt (ECHO)"),
    "sbti_commitment_removed": Evidence("G", "zusagen", "Umgang mit Zusagen", 0.5, "protokollierter Rückzug (SBTi)"),
    "intensity_illusion": Evidence("G", "greenwashing", "Greenwashing-Signale", 0.4, "abgeleitet aus Emissionsreihe"),
    "base_year_ratio": Evidence("G", "greenwashing", "Greenwashing-Signale", 0.4, "abgeleitet aus Emissionsreihe"),
    "sd_conflict_minerals_filer": Evidence("G", "lieferkette", "Lieferkettenpflicht", 0.2, "nur Meldestatus (Form SD)"),
}

# Schwellen je Bereich.
ANCHOR_WEIGHT = 0.8     # ab diesem Gewicht gilt eine Familie als harter Anker
MIN_FAMILIES = 2        # unabhängige Familien für "belastbar"
MIN_SCORE = 1.5         # Summe der Familiengewichte für "belastbar"
PARTIAL_SCORE = 1.0     # darunter und ohne Anker: "dünn"
MIN_PEERS = 6           # Firmen je Branche, ab denen ein Branchenvergleich trägt
NARROW_BAND = 20.0      # Rangband (p90 - p10) in Perzentilpunkten, ab dem ein Platz eindeutig ist

LEVELS = ["belastbar", "eingeschränkt", "dünn", "keine"]
LEVEL_RULES = {
    "belastbar": f"mindestens {MIN_FAMILIES} unabhängige Familien, davon ein Anker (Gewicht ≥ {ANCHOR_WEIGHT:.1f}), Summe ≥ {MIN_SCORE:.1f}",
    "eingeschränkt": f"ein Anker vorhanden oder Summe ≥ {PARTIAL_SCORE:.1f}",
    "dünn": "einzelne weiche Angaben",
    "keine": "kein Wert in diesem Bereich",
}


def max_score(pillar: str) -> float:
    fam: dict[str, float] = {}
    for e in METRIC_EVIDENCE.values():
        if e.pillar == pillar:
            fam[e.family] = max(fam.get(e.family, 0.0), e.weight)
    return round(sum(fam.values()), 2)


def level(score: float, families: int, anchor: bool) -> str:
    if score <= 0:
        return "keine"
    if anchor and families >= MIN_FAMILIES and score >= MIN_SCORE:
        return "belastbar"
    if anchor or score >= PARTIAL_SCORE:
        return "eingeschränkt"
    return "dünn"


def assess(long: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """Eine Zeile je Firma: Punkte, Familien und Stufe je Bereich."""
    present = long.dropna(subset=["value"]).groupby("ticker")["metric"].apply(set)
    counts = long.dropna(subset=["value"]).groupby("ticker")["metric"].nunique()
    bands = long[long["metric"].isin(["rank_p10", "rank_p90"])].pivot_table(
        index="ticker", columns="metric", values="value", aggfunc="last"
    )
    rows = []
    for r in master.itertuples(index=False):
        have = present.get(r.ticker, set())
        row = {
            "ticker": r.ticker,
            "company": r.company,
            "gics_sector": r.gics_sector,
            "n_values": int(counts.get(r.ticker, 0)),
        }
        for p in PILLARS:
            fam: dict[str, float] = {}
            for m in have:
                e = METRIC_EVIDENCE.get(m)
                if e and e.pillar == p:
                    fam[e.family] = max(fam.get(e.family, 0.0), e.weight)
            score = round(sum(fam.values()), 2)
            anchor = any(w >= ANCHOR_WEIGHT for w in fam.values())
            row[f"{p}_score"] = score
            row[f"{p}_families"] = len(fam)
            row[f"{p}_family_list"] = ", ".join(sorted(fam))
            row[f"{p}_anchor"] = anchor
            row[f"{p}_level"] = level(score, len(fam), anchor)
        if r.ticker in bands.index and {"rank_p10", "rank_p90"} <= set(bands.columns):
            b = bands.loc[r.ticker]
            row["e_band_width"] = float(b["rank_p90"] - b["rank_p10"]) if b.notna().all() else None
        else:
            row["e_band_width"] = None
        rows.append(row)
    df = pd.DataFrame(rows)
    df["n_reliable"] = sum((df[f"{p}_level"] == "belastbar").astype(int) for p in PILLARS)
    return df
