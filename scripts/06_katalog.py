"""Erzeugt den Datenkatalog: LaTeX-Tabellen direkt aus den Daten.

Zwei Sichten auf denselben Bestand:

1. **Nach Quelle** -- woher kommt es, was kostet der Zugang, welche Lizenz,
   wie weit reicht es zeitlich, und wo liegt die Grenze.
2. **Nach Datentyp** -- was misst es eigentlich, in welcher Einheit, fuer wie
   viele Firmen, und auf welcher Achse des Modells liegt es.

Der Katalog wird erzeugt und nicht geschrieben. Damit stimmt er auch dann
noch, wenn eine Quelle dazukommt oder eine Abdeckung sich aendert.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from pipeline.config import OUT, RAW, REPORT
from pipeline.consolidate import METRICS, SOURCES

GEN = REPORT / "generated"
GEN.mkdir(parents=True, exist_ok=True)

# Welche Rohtabellen gehoeren zu welcher Quelle.
RAW_TO_SOURCE = {
    "epa_facility": "epa_ghgrp",
    "epa_emission": "epa_ghgrp",
    "campd_emission": "epa_campd",
    "campd_facility": "epa_campd",
    "egrid_plant": "egrid",
    "sec_revenue": "sec_xbrl",
    "sbti_targets": "sbti",
    "epa_tri": "epa_tri",
    "osha_ita": "osha_ita",
    "epa_echo": "epa_echo",
    "eia_generation": "eia_923",
    "eia_api_facility_fuel": "eia_923",
    "epa_eia_crosswalk": "eia_923",
    "esg_snapshot": "esg_snapshot",
    "sp500_master": "sp500_master",
    # PUDL-Zwischenschicht, liegt in einem Unterordner
    "pudl/eia923_gen_fuel": "pudl",
    "pudl/out_eia860__yearly_ownership": "pudl",
    "pudl/out_eia__yearly_utilities": "pudl",
    "pudl/out_epacems__yearly_operational_characteristics": "pudl",
    "pudl/core_epa__assn_eia_epacamd": "pudl",
    "pudl/sec10k_ex21": "pudl_sec_ex21",
}

# Gruppierung nach Datentyp -- die zweite Sicht des Katalogs.
GROUPS: dict[str, tuple[str, str]] = {
    "Emissionsmengen": (
        "Absolute Treibhausgasmengen, wie sie gemeldet oder gemessen wurden.",
        "scope1_t campd_co2_t",
    ),
    "Intensitaeten und Trends": (
        "Emissionen bezogen auf eine Aktivitaetsgroesse, und ihre Entwicklung. "
        "Hier entscheidet die Wahl des Nenners.",
        "co2_intensity t_co2_pro_mwh intensity_cagr absolute_cagr",
    ),
    "Weitere Umweltwirkung": (
        "Was neben CO2 in Luft, Wasser und Boden gelangt.",
        "tri_releases_lbs tri_carcinogen_lbs",
    ),
    "Arbeitssicherheit": (
        "Die soziale Dimension als gemeldete Kennzahl statt als Selbstbeschreibung.",
        "dart_rate osha_deaths",
    ),
    "Regeltreue": (
        "Dokumentiertes Verhalten gegenueber Umweltauflagen. Die einzige Achse, "
        "die nachweislich unabhaengig von der CO2-Intensitaet ist.",
        "echo_penalties_usd echo_nc_quarters_per_site echo_significant",
    ),
    "Ziele und Glaubwuerdigkeit": (
        "Achse B des Modells. Wird getrennt ausgewiesen und nie in die Kernnote "
        "eingerechnet.",
        "sbti_validated sbti_near_term_year sbti_net_zero_year "
        "sbti_commitment_removed intensity_illusion base_year_ratio",
    ),
    "Ergebnis des Modells": (
        "Kein Einzelplatz, sondern die Spanne ueber alle Methodenkombinationen.",
        "rank_p10 rank_p50 rank_p90",
    ),
    "Vergleichsmassstab": (
        "Fremdbewertung, ausschliesslich zum Gegenhalten. Fliesst in keine "
        "eigene Note ein.",
        "esg_risk_total",
    ),
    "Bezugs- und Guetegroessen": (
        "Nenner, Zaehlwerte und Konfidenzangaben, die keine Bewertung sind.",
        "revenue_musd n_facilities match_confidence campd_plants egrid_plants "
        "tri_facilities osha_sites",
    ),
}

ESC = {"&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#", "$": r"\$"}


def tex(s) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return "--"
    out = str(s)
    for a, b in ESC.items():
        out = out.replace(a, b)
    return out



def texurl(u: str) -> str:
    """URL fuer ttfamily: Sonderzeichen maskieren und Umbruchpunkte setzen."""
    s = tex(u)
    for sep in ("/", "?", "&", "-", "."):
        s = s.replace(sep, sep + "\\allowbreak{}")
    return s


def raw_inventory() -> pd.DataFrame:
    rows = []
    for name, source_id in RAW_TO_SOURCE.items():
        p = RAW / f"{name}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        year_col = next(
            (c for c in ("year", "report_year", "report_date") if c in df.columns), None
        )
        years = "--"
        if year_col is not None:
            y = pd.to_numeric(
                pd.Series(df[year_col]).astype(str).str[:4], errors="coerce"
            ).dropna()
            if len(y):
                years = f"{int(y.min())}--{int(y.max())}"
        rows.append(
            {
                "tabelle": name.split("/")[-1],
                "source_id": source_id,
                "zeilen": len(df),
                "spalten": df.shape[1],
                "mb": round(os.path.getsize(p) / 1e6, 1),
                "jahre": years,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    long = pd.read_parquet(OUT / "dataset_long.parquet")
    inv = raw_inventory()

    # ---------------------------------------------------- Sicht 1: nach Quelle
    per_source = (
        long.groupby("source_id")
        .agg(firmen=("ticker", "nunique"), werte=("value", "size"),
             kennzahlen=("metric", "nunique"))
        .reset_index()
    )
    inv_agg = inv.groupby("source_id").agg(
        rohzeilen=("zeilen", "sum"), mb=("mb", "sum"), tabellen=("tabelle", "size")
    ).reset_index()

    lines = []
    for sid, meta in SOURCES.items():
        s = per_source[per_source.source_id == sid]
        i = inv_agg[inv_agg.source_id == sid]
        key_needed = "ja" if "Schluessel" in meta["access"] else "nein"
        lines.append(
            "\\textbf{%s} & %s & %s & %s & %s & %s \\\\\n"
            "\\multicolumn{6}{p{0.96\\textwidth}}{\\footnotesize\\ttfamily %s}\\\\\n"
            "\\multicolumn{6}{p{0.96\\textwidth}}{\\footnotesize %s \\quad\\textit{Grenze:} %s}\\\\"
            % (
                tex(meta["name"]),
                key_needed,
                tex(meta["license"][:30]),
                f"{int(i.rohzeilen.iloc[0]):,}".replace(",", "\\,") if len(i) else "--",
                f"{int(s.firmen.iloc[0])}" if len(s) else "--",
                f"{int(s.werte.iloc[0]):,}".replace(",", "\\,") if len(s) else "--",
                texurl(meta["url"]),
                tex(meta["coverage"]),
                tex(meta["caveat"]),
            )
        )
    (GEN / "tab_quellen.tex").write_text(
        "\n\\addlinespace[3pt]\n".join(lines) + "\n\\bottomrule%", encoding="utf-8"
    )

    # ------------------------------------------------- Sicht 2: nach Datentyp
    cov = (
        long.groupby("metric")
        .agg(firmen=("ticker", "nunique"), werte=("value", "size"),
             jahr_min=("year", "min"), jahr_max=("year", "max"))
        .reset_index()
    )
    blocks = []
    seen: set[str] = set()
    for group, (desc, metric_str) in GROUPS.items():
        metrics = metric_str.split()
        rows = []
        for m in metrics:
            if m not in METRICS:
                continue
            seen.add(m)
            label, unit, direction, axis, source_id = METRICS[m]
            c = cov[cov.metric == m]
            arrow = {-1: "$\\downarrow$", 1: "$\\uparrow$", 0: "--"}[direction]
            rows.append(
                "%s & \\texttt{%s} & %s & %s & %s & %s & %s \\\\"
                % (
                    tex(label), tex(m), tex(unit), arrow,
                    f"{int(c.firmen.iloc[0])}" if len(c) else "0",
                    f"{int(c.jahr_min.iloc[0])}--{int(c.jahr_max.iloc[0])}" if len(c) else "--",
                    tex(SOURCES[source_id]["name"].split(" (")[0][:26]),
                )
            )
        if rows:
            blocks.append(
                "\\textbf{%s} & & & & & & \\\\\n"
                "\\multicolumn{7}{p{0.96\\textwidth}}{\\footnotesize %s}\\\\\n\\addlinespace[2pt]\n%s\n\\midrule"
                % (tex(group), tex(desc), "\n".join(rows))
            )
    (GEN / "tab_kennzahlen.tex").write_text(
        "\n\\midrule\n".join(blocks) + "\n\\bottomrule%", encoding="utf-8"
    )

    # ------------------------------------------------------ Rohdaten-Inventar
    inv_rows = []
    for r in inv.sort_values("zeilen", ascending=False).itertuples(index=False):
        inv_rows.append(
            "\\texttt{%s} & %s & %s & %s & %s \\\\"
            % (
                tex(r.tabelle),
                f"{r.zeilen:,}".replace(",", "\\,"),
                r.spalten,
                f"{r.mb:.1f}",
                tex(r.jahre),
            )
        )
    (GEN / "tab_rohdaten.tex").write_text("\n".join(inv_rows) + "\n\\bottomrule%", encoding="utf-8")

    stats = {
        "quellen": len(SOURCES),
        "rohtabellen": int(len(inv)),
        "rohzeilen": int(inv.zeilen.sum()),
        "roh_mb": round(float(inv.mb.sum()), 1),
        "werte": int(len(long)),
        "firmen": int(long.ticker.nunique()),
        "kennzahlen": int(long.metric.nunique()),
        "jahre": [int(long.year.min()), int(long.year.max())],
        "schluessel_noetig": [
            v["name"] for v in SOURCES.values() if "Schluessel" in v["access"]
        ],
        "nicht_gruppiert": sorted(set(METRICS) - seen),
    }
    # Eckzahlen als LaTeX-Makros, damit im Dokument nichts fest eingetippt ist.
    def de(n: int) -> str:
        return f"{n:,}".replace(",", "\\,")

    (GEN / "stats.tex").write_text(
        "\n".join(
            [
                f"\\newcommand{{\\statQuellen}}{{{len(SOURCES)}}}",
                f"\\newcommand{{\\statRohtabellen}}{{{len(inv)}}}",
                f"\\newcommand{{\\statRohzeilen}}{{{de(int(inv.zeilen.sum()))}}}",
                f"\\newcommand{{\\statRohMB}}{{{inv.mb.sum():.1f}}}".replace(".", "{,}"),
                f"\\newcommand{{\\statWerte}}{{{de(len(long))}}}",
                f"\\newcommand{{\\statFirmen}}{{{int(long.ticker.nunique())}}}",
                f"\\newcommand{{\\statKennzahlen}}{{{int(long.metric.nunique())}}}",
                f"\\newcommand{{\\statJahrVon}}{{{int(long.year.min())}}}",
                f"\\newcommand{{\\statJahrBis}}{{{int(long.year.max())}}}",
                f"\\newcommand{{\\statOhneQuelle}}{{{int(long.source_id.isna().sum())}}}",
                "\\newcommand{\\statSchluessel}{%d}"
                % sum("Schluessel" in v["access"] for v in SOURCES.values()),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (OUT / "katalog_stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
