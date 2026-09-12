"""Misst, was die vier neuen Dimensionen tatsaechlich beitragen.

Bisher misst die Kernnote nur CO2, und zwei ihrer drei Kennzahlen stammen aus
derselben Reihe. Vier Quellen sollen das aufbrechen:

* **EIA-923** -- Megawattstunden als physischer Nenner statt Umsatzdollar
* **EPA TRI** -- Giftstofffreisetzung als zweite Umweltdimension
* **OSHA ITA** -- Unfallraten als soziale Dimension
* **EPA ECHO** -- Verstossquartale und Strafen als Governance-Dimension

Fuer jede wird beziffert: Wie viele Indexfirmen erreicht sie, und ist sie
tatsaechlich unabhaengig von dem, was schon gemessen wird? Eine neue Kennzahl,
die mit der CO2-Intensitaet korreliert, bringt der geometrischen Aggregation
nichts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from pipeline.config import OUT, RAW
from pipeline.resolve import OVERRIDES, normalize


def load(name: str) -> pd.DataFrame:
    p = RAW / f"{name}.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def match_to_tickers(names: pd.Series, master: pd.DataFrame) -> pd.Series:
    """Firmennamen auf Ticker abbilden: exakt, dann ueber die Tochtertabelle."""
    lookup = {normalize(r.company): r.ticker for r in master.itertuples()}
    keys = names.fillna("").map(normalize)
    out = keys.map(lookup)
    miss = out.isna()
    if miss.any():
        out.loc[miss] = keys[miss].map(OVERRIDES)
    return out


def main() -> None:
    master = pd.read_parquet(RAW / "sp500_master.parquet")
    panel = pd.read_csv(OUT / "panel_periode_a.csv")
    heute = set(panel["ticker"])
    stats: dict = {"ausgangslage": {"firmen_mit_emissionsdaten": len(heute)}}
    beitrag: list[dict] = []

    # ------------------------------------------------------------------ EIA
    gen = load("eia_generation")
    cross = load("epa_eia_crosswalk")
    if not gen.empty and not cross.empty:
        fac = load("epa_facility")
        # EPA-GHGRP-Anlagen tragen keine EIA-Kennung; die Bruecke laeuft ueber
        # die CAMPD-Kennung. Ohne CAMPD-Daten bleibt die Zuordnung offen --
        # hier wird deshalb nur das Mengengeruest beziffert.
        stats["eia"] = {
            "kraftwerke": int(gen["plant_id_eia"].nunique()),
            "jahre": [int(gen["year"].min()), int(gen["year"].max())],
            "mwh_2024_mrd": float(
                gen.loc[gen["year"] == 2024, "net_generation_mwh"].sum() / 1e9
            ),
            "crosswalk_paare": int(len(cross)),
        }
        beitrag.append({"quelle": "EIA-923", "dimension": "physischer Nenner (MWh)",
                        "einheiten": stats["eia"]["kraftwerke"]})

    # ------------------------------------------------------------------ TRI
    tri = load("epa_tri")
    if not tri.empty:
        parent_col = next(
            (c for c in tri.columns if "standardized_parent" in c or c.endswith("parent_co_name")),
            None,
        )
        rel_col = next(
            (c for c in tri.columns if c.startswith("total_releases") or c == "total_releases"),
            None,
        )
        tri["ticker"] = match_to_tickers(tri[parent_col], master) if parent_col else np.nan
        hit = tri.dropna(subset=["ticker"])
        stats["tri"] = {
            "anlagen": int(len(tri)),
            "konzernfeld": parent_col,
            "freisetzungsfeld": rel_col,
            "indexfirmen": int(hit["ticker"].nunique()),
            "davon_ohne_emissionsdaten": int(len(set(hit["ticker"]) - heute)),
        }
        if rel_col:
            agg = (
                hit.groupby(["ticker", "year"], as_index=False)[rel_col]
                .sum()
                .rename(columns={rel_col: "tri_releases_lbs"})
            )
            agg.to_csv(OUT / "tri_je_firma.csv", index=False)
        beitrag.append({"quelle": "EPA TRI", "dimension": "Giftstoffe",
                        "einheiten": stats["tri"]["indexfirmen"]})

    # ------------------------------------------------------------------ OSHA
    osha = load("osha_ita")
    if not osha.empty:
        osha["ticker"] = match_to_tickers(osha["company_name"], master)
        hit = osha.dropna(subset=["ticker"])
        agg = (
            hit.groupby(["ticker", "year"], as_index=False)
            .agg(
                betriebsstaetten=("establishment_name", "nunique"),
                stunden=("total_hours_worked", "sum"),
                dafw=("total_dafw_cases", "sum"),
                djtr=("total_djtr_cases", "sum"),
                tote=("total_deaths", "sum"),
            )
        )
        agg["dart_rate"] = (agg["dafw"] + agg["djtr"]) * 200000 / agg["stunden"].replace(0, np.nan)
        agg.to_csv(OUT / "osha_je_firma.csv", index=False)
        stats["osha"] = {
            "betriebsstaetten": int(len(osha)),
            "indexfirmen": int(hit["ticker"].nunique()),
            "davon_ohne_emissionsdaten": int(len(set(hit["ticker"]) - heute)),
            "median_dart": float(agg["dart_rate"].median()),
        }
        beitrag.append({"quelle": "OSHA ITA", "dimension": "Arbeitssicherheit",
                        "einheiten": stats["osha"]["indexfirmen"]})

    # ------------------------------------------------------------------ ECHO
    echo = load("epa_echo")
    if not echo.empty:
        fac = load("epa_facility")
        stats["echo"] = {"anlagen": int(len(echo))}
        if not fac.empty and "frs_id" in fac.columns and "registry_id" in echo.columns:
            # Der praezise Weg: ueber die FRS-Kennung statt ueber Namen.
            fac_ids = fac[["frs_id", "parent_company"]].dropna().drop_duplicates()
            fac_ids["frs_id"] = fac_ids["frs_id"].astype(str)
            echo["registry_id"] = echo["registry_id"].astype(str)
            j = echo.merge(fac_ids, left_on="registry_id", right_on="frs_id", how="inner")
            j["ticker"] = match_to_tickers(j["parent_company"], master)
            hit = j.dropna(subset=["ticker"])
            # Die Konformitaetshistorie ist eine Zeichenkette mit einem
            # Zeichen je Quartal ueber drei Jahre. Unterstriche stehen fuer
            # beanstandungsfrei, Buchstaben fuer einen Befund.
            hist = hit["fac_3yr_compliance_history"].fillna("").astype(str)
            hit = hit.assign(
                verstossquartale=hist.str.count(r"[A-Z]"),
                schwerer_verstoss=hit["fac_compliance_status"]
                .astype(str)
                .str.contains("Significant", case=False)
                .astype(int),
            )
            agg = (
                hit.groupby("ticker", as_index=False)
                .agg(
                    anlagen=("registry_id", "nunique"),
                    strafen_usd=("fac_total_penalties", "sum"),
                    inspektionen=("fac_inspection_count", "sum"),
                    verstossquartale=("verstossquartale", "sum"),
                    schwere_verstoesse=("schwerer_verstoss", "sum"),
                )
            )
            agg["verstossquartale_je_anlage"] = (
                agg["verstossquartale"] / agg["anlagen"]
            )
            agg.to_csv(OUT / "echo_je_firma.csv", index=False)
            stats["echo"].update(
                {
                    "ueber_frs_verknuepft": int(len(j)),
                    "indexfirmen": int(hit["ticker"].nunique()),
                    "strafen_gesamt_musd": float(agg["strafen_usd"].sum() / 1e6),
                }
            )
            beitrag.append({"quelle": "EPA ECHO", "dimension": "Regeltreue",
                            "einheiten": stats["echo"].get("indexfirmen", 0)})
        else:
            stats["echo"]["hinweis"] = (
                "frs_id fehlt im Anlagen-Cache -- epa_facility mit frs_id neu ziehen"
            )

    # ------------------------------------------------ Unabhaengigkeit pruefen
    korr = {}
    base = panel[["ticker", "co2_intensity", "intensity_cagr", "absolute_cagr"]]
    for name, path, col in [
        ("tri_releases", OUT / "tri_je_firma.csv", "tri_releases_lbs"),
        ("dart_rate", OUT / "osha_je_firma.csv", "dart_rate"),
        ("verstossquartale_je_anlage", OUT / "echo_je_firma.csv", "verstossquartale_je_anlage"),
    ]:
        if not path.exists():
            continue
        d = pd.read_csv(path)
        if "year" in d.columns:
            d = d.sort_values("year").groupby("ticker", as_index=False).last()
        m = base.merge(d[["ticker", col]], on="ticker", how="inner").dropna()
        if len(m) >= 12:
            korr[name] = {
                "n": int(len(m)),
                "vs_co2_intensity": round(
                    float(m["co2_intensity"].corr(m[col], method="spearman")), 3
                ),
            }
    stats["unabhaengigkeit"] = korr

    pd.DataFrame(beitrag).to_csv(OUT / "neue_dimensionen.csv", index=False)
    (OUT / "kennzahlen_dimensionen.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(json.dumps(stats, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
