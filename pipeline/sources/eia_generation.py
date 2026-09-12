"""EIA-923: erzeugte Megawattstunden je Kraftwerk -- der physische Nenner.

Bisher wird jede Intensitaet auf den Umsatz bezogen: Tonnen je Million Dollar.
Das hat zwei Probleme. Erstens haengt der Nenner am Strompreis, nicht an der
Leistung -- ein Versorger sieht in einem Jahr mit hohen Grosshandelspreisen
sauberer aus, ohne eine Tonne weniger auszustossen. Zweitens ist der Umsatz
ueber Branchen hinweg nicht vergleichbar.

Fuer Stromerzeuger gibt es einen besseren Nenner: die erzeugte Arbeit.
**Tonnen CO2 je Megawattstunde** ist die Kennzahl, nach der Energiewirtschaft
tatsaechlich beurteilt wird, und sie ist immun gegen Preisschwankungen.

Bezogen ueber PUDL, das die EIA-Formulare 923 und 860 aufbereitet und als
Parquet veroeffentlicht -- Public Domain, ohne Anmeldung. Die Verknuepfung zu
den EPA-Anlagen laeuft ueber die Crosswalk-Tabelle
``core_epa__assn_eia_epacamd``, die ``plant_id_eia`` und ``plant_id_epa``
zusammenfuehrt.
"""
from __future__ import annotations

import io

import pandas as pd

from .base import DataSource, register, session

PUDL = "https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/stable/{table}.parquet"


def _pudl(table: str) -> pd.DataFrame:
    r = session().get(PUDL.format(table=table), timeout=600)
    r.raise_for_status()
    return pd.read_parquet(io.BytesIO(r.content))


@register
class EiaGenerationSource(DataSource):
    name = "eia_generation"
    endpoint = PUDL.format(table="out_eia923__yearly_generation_fuel_by_generator_energy_source")
    description = "Nettostromerzeugung je Kraftwerk und Jahr aus EIA-923 (via PUDL)"

    def _fetch(self) -> pd.DataFrame:
        df = _pudl("out_eia923__yearly_generation_fuel_by_generator_energy_source")
        df["year"] = pd.to_datetime(df["report_date"]).dt.year
        out = (
            df.groupby(["plant_id_eia", "year"], as_index=False)
            .agg(
                net_generation_mwh=("net_generation_mwh", "sum"),
                fuel_consumed_mmbtu=("fuel_consumed_mmbtu", "sum"),
            )
        )
        return out[out["net_generation_mwh"] > 0].reset_index(drop=True)


@register
class EpaEiaCrosswalkSource(DataSource):
    name = "epa_eia_crosswalk"
    endpoint = PUDL.format(table="core_epa__assn_eia_epacamd")
    description = "Zuordnung EPA-Anlagenkennung zu EIA-Kraftwerkskennung (ORIS)"

    def _fetch(self) -> pd.DataFrame:
        df = _pudl("core_epa__assn_eia_epacamd")
        return (
            df[["plant_id_epa", "plant_id_eia", "report_year"]]
            .dropna()
            .drop_duplicates()
            .reset_index(drop=True)
        )
