"""Retrieve EIA-923 plant generation via PUDL. Physical generation can support tonnes-per-MWh comparisons without electricity-price effects. The EPA/EIA crosswalk connects plant identifiers. The core climate ranking still uses revenue as its denominator."""
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
    description = "Annual plant net generation from EIA-923 via PUDL"

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
    description = "EPA-to-EIA plant identifier crosswalk"

    def _fetch(self) -> pd.DataFrame:
        df = _pudl("core_epa__assn_eia_epacamd")
        return (
            df[["plant_id_epa", "plant_id_eia", "report_year"]]
            .dropna()
            .drop_duplicates()
            .reset_index(drop=True)
        )
