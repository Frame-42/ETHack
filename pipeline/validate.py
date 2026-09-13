"""Offline integrity checks and reproducible counts for the shipped snapshot."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT


def validate(root: Path = ROOT) -> dict:
    out = root / 'data' / 'out'
    long = pd.read_csv(out / 'dataset_long.csv', float_precision='round_trip')
    membership = pd.read_csv(root / 'constituents.csv')
    primary = membership.assign(_length=membership.Symbol.str.len()).sort_values(
        ['_length', 'Symbol'], ascending=[False, True]).drop_duplicates('CIK')
    tickers = set(primary.Symbol)
    metrics = json.loads((out / 'metrics.json').read_text())
    sources = json.loads((out / 'sources.json').read_text())
    required = ['ticker', 'year', 'metric', 'value', 'source_id', 'source_url',
                'unit', 'value_type', 'quality_status', 'assembled_at']
    assert set(required) <= set(long), 'Missing observation columns'
    assert long[required].notna().all().all(), 'Missing required observation metadata'
    assert not long.duplicated(['ticker', 'year', 'metric']).any(), 'Duplicate observations'
    assert set(long.ticker) <= tickers, 'Unknown ticker or duplicate share class'
    assert np.isfinite(long.value).all(), 'Non-finite observations'
    assert set(long.value_type) <= {'reported', 'aggregated'}, 'Unknown value type'
    assert set(long.quality_status) <= {'ok', 'review', 'error'}, 'Unknown quality status'
    assert set(long.metric) <= set(metrics), 'Unregistered metric'
    assert set(long.source_id) <= set(sources), 'Unregistered source'
    for field, key in [('metric_label', 'label'), ('unit', 'unit'), ('direction', 'direction'),
                       ('axis', 'axis'), ('source_id', 'source_id'), ('value_type', 'value_type')]:
        expected = long.metric.map(lambda m: metrics[m][key])
        assert (long[field] == expected).all(), f'Catalog mismatch: {field}'
    assert long.source_url.str.startswith(('https://', 'http://')).all(), 'Invalid source URL'
    assert not {'co2_intensity', 'intensity_cagr', 'absolute_cagr', 'p50'} & set(long.metric), 'Derived analysis leaked into observations'
    emissions = long[long.metric.isin(['scope1_t', 'campd_co2_t'])]
    assert (emissions.value > 0).all(), 'Nonpositive emissions in the retained series'
    wide = long.pivot(index=['ticker', 'year'], columns='metric', values='value')
    if {'echo_nc_quarters', 'echo_facilities'} <= set(wide):
        pairs = wide[['echo_nc_quarters', 'echo_facilities']].dropna()
        assert (pairs.echo_nc_quarters <= 12 * pairs.echo_facilities).all(), 'Multiplied ECHO history'
    bands = pd.read_csv(out / 'climate_bands.csv')
    assert not bands.ticker.duplicated().any() and set(bands.ticker) <= tickers
    assert bands[['p10', 'p50', 'p90']].notna().all().all()
    assert ((0 <= bands.p10) & (bands.p10 <= bands.p50) & (bands.p50 <= bands.p90) & (bands.p90 <= 100)).all(), 'Invalid percentile ordering'
    assert np.allclose(bands.band_width, bands.p90 - bands.p10), 'Band widths do not reconcile'
    economy = pd.read_csv(out / 'economic_viability.csv')
    reliability = pd.read_csv(out / 'reliability.csv')
    for table in [economy, reliability]:
        assert not table.ticker.duplicated().any() and set(table.ticker) == tickers, 'Issuer universe mismatch'
    flags = pd.read_csv(out / 'reviewed_flags.csv')
    from .quality import stable_flag_id
    from .flag_apply import status_of
    assert not flags.flag_id.duplicated().any(), 'Duplicate quality IDs'
    assert all(r.flag_id == stable_flag_id(r) for _, r in flags.iterrows()), 'Stale review identity'
    assert (flags['final'] == flags.apply(status_of, axis=1)).all(), 'Review status mismatch'
    observations = long.set_index(['ticker', 'metric', 'year'])
    for _, row in flags.iterrows():
        key = (row.ticker, row.metric, int(row.year))
        assert key in observations.index, f'Flag without an observation: {key}'
        assert observations.loc[key, 'quality_status'] == status_of(row), f'Stale quality annotation: {key}'
    team = pd.read_csv(root / 'data' / 'external' / 'team' / 'hard_variables.csv', dtype=str)
    assert not team.ticker.str.startswith('Bedeutung').any(), 'Documentation row inside data'
    dictionary = json.loads((root / 'data' / 'external' / 'team' / 'hard_variables_dictionary.json').read_text())
    assert set(team) == set(dictionary), 'Input data dictionary mismatch'
    sustainability = long[(~long.axis.isin(['meta', 'comparison'])) & (long.quality_status != 'error')]
    return {
        'securities': len(membership), 'issuers': len(primary), 'observations': len(long),
        'metrics': int(long.metric.nunique()), 'sources_with_observations': int(long.source_id.nunique()),
        'issuers_with_observations': int(long.ticker.nunique()),
        'issuers_with_sustainability_observations': int(sustainability.ticker.nunique()),
        'issuers_without_sustainability_observations': len(tickers - set(sustainability.ticker)),
        'years': [int(long.year.min()), int(long.year.max())],
        'climate_bands': len(bands), 'median_band_width': float(bands.band_width.median()),
        'quality_status': long.quality_status.value_counts().to_dict(),
        'review_findings': len(flags), 'viability_levels': economy.viability_level.value_counts().to_dict(),
        'strong_evidence_by_pillar': {p: int((reliability[f'{p}_level'] == 'strong').sum()) for p in 'ESG'},
        'strong_evidence_all_pillars': int((reliability.n_reliable == 3).sum()),
    }
