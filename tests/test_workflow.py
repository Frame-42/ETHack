"""Exercise entry-point compatibility in an isolated synthetic data build."""
from pathlib import Path
import subprocess
import sys
import unittest


class WorkflowTest(unittest.TestCase):
    def test_cached_source_workflow(self):
        fixture = Path(__file__).with_name("workflow_fixture.py")
        result = subprocess.run([sys.executable, str(fixture)], capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS complete synthetic workflow", result.stdout)
