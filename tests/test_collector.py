"""Parser contract tests; fixture numbers are synthetic test cases, never dataset inputs."""
import unittest
from scripts.collect import normalize, parse_assessment


class CollectorTests(unittest.TestCase):
    def test_missing_is_not_zero(self):
        result = parse_assessment('<html><h1>No assessment</h1></html>')
        self.assertIsNone(result['ctt'])
        self.assertIsNone(result['social'])

    def test_native_units_and_zero_scores(self):
        result = parse_assessment('''
        <div class="score-tab"><div class="t-row"><div class="tag">Social Benchmark</div>
        <div class="t-sub-score">0.0/100</div></div></div>
        <div class="company-benchmark-act-text-col">transition plan quality (TPQ), for which the company scores 5 out of 5;
        and contribution to the low-carbon transition (CTT), for which the company scores 2 out of 2.</div>''')
        self.assertEqual(result['ctt'], 2)
        self.assertEqual(result['tpq'], 5)
        self.assertEqual(result['social'], 0)
        self.assertIsNone(result['nature'])

    def test_names_do_not_confuse_similar_companies(self):
        self.assertEqual(normalize('Alphabet Inc. (Class A)'), normalize('Alphabet'))
        self.assertNotEqual(normalize('Alliant Energy'), normalize('AGL Energy'))
        self.assertNotEqual(normalize('Loews Corporation'), normalize("Lowe's"))


if __name__ == '__main__':
    unittest.main()
