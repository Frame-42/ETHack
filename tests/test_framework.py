"""Regression checks for identity, scoring, provenance, and review behavior."""
import importlib
import importlib.util
import json
import pkgutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from pipeline import canonical, flag_apply, quality, reliability
from pipeline.config import ROOT
from pipeline.consolidate import dedupe_cik
from pipeline.economy import economic_viability as ev
from pipeline.economy import sec_facts
from pipeline.resolve import normalize, override_prefix, owner_valid, parse_owners
from pipeline.scoring.aggregate import arithmetic, geometric
from pipeline.scoring.montecarlo import Metric, MonteCarloConfig, run
from pipeline.validate import validate


class FrameworkTests(unittest.TestCase):
    def test_all_modules_import_without_network(self):
        import pipeline
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Unexpected network request')):
            for info in pkgutil.walk_packages(pipeline.__path__, 'pipeline.'):
                importlib.import_module(info.name)
            for path in (ROOT / 'scripts').glob('*.py'):
                spec = importlib.util.spec_from_file_location('entry_' + path.stem, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

    def test_shipped_snapshot(self):
        self.assertEqual(validate(), json.loads((ROOT / 'data/out/snapshot_summary.json').read_text()))

    def test_missing_benchmark_does_not_block_core_analysis(self):
        from pipeline import analysis
        bands = pd.DataFrame({'ticker': ['A'], 'p50': [50.]})
        panel = pd.DataFrame({'ticker': ['A'], 'revenue_musd': [100.]})
        sector, summary = analysis.compare_with_commercial(bands, pd.DataFrame())
        self.assertTrue(sector.empty)
        self.assertEqual(summary, {'n': 0})
        self.assertEqual(analysis.size_bias(bands, panel, pd.DataFrame()), {})

    def test_share_class_identity(self):
        master = pd.DataFrame({'ticker': ['GOOG', 'GOOGL', 'NWS', 'NWSA'], 'cik': [1, 1, 2, 2]})
        primary, aliases = dedupe_cik(master)
        self.assertEqual(primary, {'GOOG': 'GOOGL', 'NWS': 'NWSA'})
        self.assertEqual(aliases['GOOGL'], ['GOOG'])

    def test_owner_boundaries_and_periods(self):
        self.assertIsNone(override_prefix(normalize('Linden Generating Station')))
        self.assertFalse(owner_valid('talen energy', 'VST', 2023))
        self.assertFalse(owner_valid('pioneer natural resources', 'XOM', 2023))
        self.assertTrue(owner_valid('pioneer natural resources', 'XOM', 2024))
        self.assertEqual(parse_owners('Alpha (60%); Beta'), [('Alpha', .6), ('Beta', .4)])

    def test_trend_uses_all_positive_years(self):
        years = pd.Series([2018, 2019, 2020, 2021])
        values = pd.Series([100 * 1.1 ** i for i in range(4)])
        self.assertAlmostEqual(canonical._cagr(values, years), .1)
        self.assertTrue(np.isnan(canonical._cagr(values[:2], years[:2])))

    def test_aggregation_compensation_and_missing(self):
        x = pd.DataFrame([[1., .01], [np.nan, .4], [np.nan, np.nan]])
        w = np.array([.5, .5])
        self.assertAlmostEqual(geometric(x, w)[0], .1)
        self.assertAlmostEqual(arithmetic(x, w)[0], .505)
        self.assertAlmostEqual(geometric(x, w)[1], .4)
        self.assertTrue(np.isnan(arithmetic(x, w)[2]))

    def test_monte_carlo_reproducibility(self):
        n = 12
        panel = pd.DataFrame({'ticker': [f'T{i}' for i in range(n)], 'company': [f'Company {i}' for i in range(n)],
            'gics_sector': ['Sector'] * n, 'gics_sub_industry': ['A'] * 4 + ['B'] * 8,
            'match_confidence': [.9] * n, 'intensity': np.arange(1., n + 1),
            'trend': np.linspace(-.1, .1, n), 'absolute': np.linspace(.2, -.2, n)})
        metrics = [Metric(c, -1, c) for c in ['intensity', 'trend', 'absolute']]
        cfg = MonteCarloConfig(n_draws=30)
        a, _ = run(panel, metrics, cfg)
        b, _ = run(panel, metrics, cfg)
        pd.testing.assert_frame_equal(a, b)
        self.assertTrue(((a.p10 <= a.p50) & (a.p50 <= a.p90)).all())

    def test_evidence_counts_families_once_and_excludes_errors(self):
        long = pd.DataFrame({'ticker': ['A'] * 4, 'metric': ['scope1_t', 'campd_co2_t', 'egrid_mwh', 'osha_deaths'],
                             'value': [10., 10., 20., 1.], 'quality_status': ['ok', 'review', 'ok', 'error']})
        master = pd.DataFrame({'ticker': ['A'], 'company': ['A'], 'gics_sector': ['Utilities']})
        with tempfile.TemporaryDirectory() as temp, patch.object(reliability, 'OUT', Path(temp)):
            result = reliability.assess(long, master).iloc[0]
        self.assertEqual(result.E_families, 2)
        self.assertEqual(result.E_score, 1.8)
        self.assertEqual(result.S_score, 0)

    def test_model_cannot_suppress_observation(self):
        row = pd.Series({'severity': 'review', 'route': 'automatic', 'ai_action': 'suppress', 'ai_verdict': 'error'})
        self.assertEqual(flag_apply.status_of(row), 'review')
        row['decision'] = 'keep'
        self.assertEqual(flag_apply.status_of(row), 'ok')
        row['decision'] = 'error'
        self.assertEqual(flag_apply.status_of(row), 'error')

    def test_review_identity_changes_with_evidence(self):
        row = {'rule': 'F10_whd_franchise', 'ticker': 'A', 'metric': 'whd_cases', 'year': 2024,
               'value': 4, 'evidence': {'cases': 4, 'trade_name_only': 3}}
        self.assertEqual(quality.stable_flag_id(row), quality.stable_flag_id(dict(reversed(list(row.items())))))
        self.assertNotEqual(quality.stable_flag_id(row), quality.stable_flag_id({**row, 'value': 5}))

    def test_latest_filing_and_ttm(self):
        tag = 'NetCashProvidedByUsedInOperatingActivities'
        def fact(start, end, value, filed, form):
            return dict(start=start, end=end, val=value, filed=filed, form=form, accn='test')
        facts = [fact('2023-01-01', '2023-12-31', 100, '2024-02-01', '10-K'),
                 fact('2023-01-01', '2023-12-31', 110, '2024-03-01', '10-K/A'),
                 fact('2023-01-01', '2023-06-30', 40, '2023-08-01', '10-Q'),
                 fact('2024-01-01', '2024-06-30', 60, '2024-08-01', '10-Q')]
        data = {'facts': {'us-gaap': {tag: {'units': {'USD': facts}}}}}
        self.assertEqual(sec_facts.flow(data, tag)['ttm'], 130)

    def test_economic_thresholds_and_stress(self):
        self.assertEqual(ev.ramp(.1, .5, .1), 1)
        self.assertEqual(ev.ramp(.5, .5, .1), 0)
        worst, pairs = ev.worst_cash_shortfall([('2021-12-31', 100), ('2022-12-31', 60), ('2023-12-31', 80)],
                                              {'2021-12-31': 200, '2022-12-31': 200})
        self.assertEqual(worst, ('2022-12-31', .2))
        self.assertEqual(pairs, 2)
        self.assertEqual(ev.analyse({'GICS Sector': 'Financials'}, {})['viability_level'], 'not assessable')


if __name__ == '__main__':
    unittest.main()
