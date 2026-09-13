"""Checks for the rebuilt portfolio data consumed by Dashboard 11."""
import importlib.util
import json
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rebuild", ROOT / "scripts/rebuild_dashboard11_portfolios.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DashboardPortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(MODULE.DATA.search(MODULE.DASHBOARD.read_text())[2])
        cls.portfolio = MODULE.rebuild(cls.data)
        cls.firms = {f["ticker"]: f for f in cls.data["firms"]}

    def test_holdings_satisfy_constraints_and_match_summaries(self):
        for axis in MODULE.AXES:
            with self.subTest(axis=axis):
                p = self.portfolio[axis]
                rows = p["positions"]
                self.assertEqual(p["titles"], len(rows))
                self.assertAlmostEqual(sum(r["gewicht"] for r in rows), 1, places=8)
                self.assertAlmostEqual(max(r["gewicht"] for r in rows), p["maxw"])
                self.assertLessEqual(p["maxw"], .06 + 1e-8)
                self.assertAlmostEqual(sum(r["gewicht"] * r["intensitaet"] for r in rows), p["new"])
                self.assertGreaterEqual(p["red"], .5 - 1e-8)
                self.assertTrue(all(self.firms[r["ticker"]]["viability"]["level"] != "at risk" for r in rows))
                for sector in p["sector_alloc"]:
                    weight = sum(r["gewicht"] for r in rows if r["sector"] == sector["sector"])
                    self.assertAlmostEqual(weight, sector["w"])
                    self.assertAlmostEqual(weight, sector["b"], places=8)

    def test_saved_portfolios_reproduce_rebuild(self):
        for axis in MODULE.AXES:
            stored = {r["ticker"]: r["gewicht"] for r in self.data["portfolio"][axis]["positions"]}
            rebuilt = {r["ticker"]: r["gewicht"] for r in self.portfolio[axis]["positions"]}
            self.assertEqual(stored.keys(), rebuilt.keys())
            np.testing.assert_allclose(list(stored.values()), [rebuilt[t] for t in stored], atol=1e-8)

    def test_categories_produce_different_holdings(self):
        signatures = {tuple((p["ticker"], round(p["gewicht"], 6)) for p in self.portfolio[a]["positions"])
                      for a in MODULE.AXES}
        self.assertEqual(len(signatures), 5)
        # Zero tilt removes the category preference, so both optima coincide.
        self.assertAlmostEqual(self.portfolio["tilt_sensitivity"][0]["overlap_AG"], 1)


if __name__ == "__main__":
    unittest.main()
