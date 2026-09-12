"""Misst, wie weit die neu gefundenen Quellen die Datenluecke schliessen.

Zwei Luecken wurden im ersten Bericht benannt:

* die **zeitliche**: die EPA-Reihe endet 2023, danach nichts
* die **strukturelle**: nur 157 von 503 Firmen bewertbar, fast nur Schwerindustrie

Dieses Skript beziffert je Quelle, wie viel davon uebrig bleibt.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from pipeline.canonical import load_raw
from pipeline.config import OUT, RAW
from pipeline.resolve import normalize

# Quellen, die im Laufe der Recherche geprueft wurden. ``jahr_bis`` ist das
# letzte Geschaeftsjahr, das die Quelle am 12.09.2026 tatsaechlich lieferte.
QUELLEN = [
    ("EPA GHGRP", "Scope 1, Anlagen", 2023, "frei", "Reihe endet 2023"),
    ("EPA CAMPD", "Scope 1, Kraftwerke (CEMS)", 2026, "Schluessel", "nur Stromerzeugung"),
    ("PUDL/Zenodo", "EPA-CEMS-Spiegel + EIA-Eigentum", 2026, "frei", "4,5 GB Stundenwerte"),
    ("SEC XBRL", "Umsatz", 2025, "frei", "Nenner, keine Emissionen"),
    ("SEC Volltext", "selbstberichtetes Scope 1/2/3", 2026, "frei", "Extraktion noetig"),
    ("SBTi", "Zielstatus, Zwischenziele", 2026, "frei", "Selbstselektion"),
    ("CARB SB 253", "Scope 1+2, verpflichtend", 2025, "frei", "Frist erst 10.11.2026"),
    ("CDP offen", "nur Staedte und Regionen", 2025, "frei", "keine Firmendaten"),
    ("TPI", "Transitionsbewertung", 2026, "frei", "Auslesen per Bot untersagt"),
]


def main() -> None:
    raw = load_raw()
    master = raw["sp500_master"]
    panel = pd.read_csv(OUT / "panel_periode_a.csv")
    stats: dict = {}

    heute = set(panel["ticker"])
    stats["ausgangslage"] = {
        "firmen_gesamt": int(len(master)),
        "firmen_mit_emissionsdaten": int(len(heute)),
        "letztes_jahr": 2023,
    }

    # ---------------------------------------------------------------- SBTi
    sbti = pd.read_parquet(RAW / "sbti_targets.parquet")
    sbti["key"] = sbti["company_name"].map(normalize)
    m = master.assign(key=master["company"].map(normalize)).merge(
        sbti.drop_duplicates("key"), on="key", how="left"
    )
    sbti_hit = m[m["near_term_status"].notna()]
    stats["sbti"] = {
        "treffer": int(len(sbti_hit)),
        "anteil_pct": round(len(sbti_hit) / len(master) * 100, 1),
        "davon_ohne_emissionsdaten": int((~sbti_hit["ticker"].isin(heute)).sum()),
        "mit_geprueftem_ziel": int(sbti_hit["has_validated_target"].sum()),
        "zusage_zurueckgezogen": int(sbti_hit["commitment_removed"].sum()),
        "mit_zwischenziel": int(sbti_hit["near_term_year"].notna().sum()),
    }

    # ---------------------------------------------------------------- SEC-Volltext
    fts_path = OUT / "sec_fts_kandidaten.csv"
    fts = pd.read_csv(fts_path) if fts_path.exists() else pd.DataFrame(columns=["ticker"])
    stats["sec_volltext"] = {
        "treffer": int(len(fts)),
        "davon_ohne_emissionsdaten": int((~fts["ticker"].isin(heute)).sum()),
        "extraktionsausbeute_pct": 80,
        "hinweis": "Ausbeute an 40 Firmen gemessen; Praezision ungeprueft",
    }

    # ---------------------------------------------------------------- Vereinigung
    # Wichtig: die Quellen liefern nicht dasselbe. EPA liefert gemessene Tonnen,
    # SEC-Volltext selbstberichtete Tonnen (noch zu extrahieren), SBTi ueberhaupt
    # keine Menge, sondern nur den Zielstatus. Eine Gesamtzahl, die das
    # vermischt, waere genau die aufgeblasene Kennzahl, die der erste Bericht
    # kritisiert hat -- deshalb hier getrennt.
    union = heute | set(sbti_hit["ticker"]) | set(fts["ticker"])
    mengen = heute | set(fts["ticker"])  # Quellen mit einer Emissionsmenge
    YIELD = 0.80  # an 40 Firmen gemessene Extraktionsausbeute
    erwartet_extrahierbar = int(round(len(set(fts["ticker"]) - heute) * YIELD))
    stats["vereinigung"] = {
        "firmen_mit_mindestens_einer_quelle": int(len(union)),
        "anteil_pct": round(len(union) / len(master) * 100, 1),
        "gewinn_gegenueber_heute": int(len(union) - len(heute)),
        "davon_mit_emissionsmenge_optimistisch": int(len(mengen)),
        "davon_mit_emissionsmenge_erwartet": int(len(heute) + erwartet_extrahierbar),
        "nur_zielstatus_ohne_menge": int(len(union - mengen)),
    }

    # ---------------------------------------------------------------- je Sektor
    rows = []
    for sector, g in master.groupby("gics_sector"):
        t = set(g["ticker"])
        rows.append(
            {
                "gics_sector": sector,
                "firmen": len(t),
                "epa": len(t & heute),
                "sbti": len(t & set(sbti_hit["ticker"])),
                "sec_volltext": len(t & set(fts["ticker"])),
                "vereinigung": len(t & union),
            }
        )
    cov = pd.DataFrame(rows)
    cov["epa_pct"] = cov["epa"] / cov["firmen"] * 100
    cov["union_pct"] = cov["vereinigung"] / cov["firmen"] * 100
    cov = cov.sort_values("union_pct", ascending=False)
    cov.to_csv(OUT / "abdeckung_neue_quellen.csv", index=False)
    stats["abdeckung_sektor"] = cov.to_dict("records")

    pd.DataFrame(
        QUELLEN, columns=["quelle", "liefert", "jahr_bis", "zugang", "grenze"]
    ).to_csv(OUT / "quellenlage.csv", index=False)

    (OUT / "kennzahlen_datenluecke.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Heute bewertbar:              {len(heute)} von {len(master)}")
    print(f"SBTi-Treffer:                 {stats['sbti']['treffer']}"
          f" (davon {stats['sbti']['davon_ohne_emissionsdaten']} neu)")
    print(f"SEC-Volltext-Kandidaten:      {stats['sec_volltext']['treffer']}"
          f" (davon {stats['sec_volltext']['davon_ohne_emissionsdaten']} neu)")
    print(f"Mindestens eine Quelle:       {len(union)} = {len(union)/len(master)*100:.0f} %")
    print()
    print(cov[["gics_sector", "firmen", "epa", "sbti", "sec_volltext", "vereinigung"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
