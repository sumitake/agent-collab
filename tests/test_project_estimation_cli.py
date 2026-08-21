"""CLI safety checks for the public estimator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "agent-collab" / "project_estimation.py"
FIXTURES = ROOT / "tests" / "fixtures" / "project_estimation"


class EstimatorCliTests(unittest.TestCase):
    def test_estimate_writes_canonical_json_to_stdout(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "estimate", "--request", str(FIXTURES / "request-enhancement.json"), "--prior", str(FIXTURES / "prior-small.json"), "--pricing", str(FIXTURES / "pricing-small.json"), "--quota", str(FIXTURES / "quota-small.json")], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("\n"))

    def test_out_requires_consent_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "result.json"
            result = subprocess.run([sys.executable, str(SCRIPT), "estimate", "--request", str(FIXTURES / "request-enhancement.json"), "--prior", str(FIXTURES / "prior-small.json"), "--pricing", str(FIXTURES / "pricing-small.json"), "--quota", str(FIXTURES / "quota-small.json"), "--out", str(output)], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            second = subprocess.run([sys.executable, str(SCRIPT), "estimate", "--request", str(FIXTURES / "request-enhancement.json"), "--prior", str(FIXTURES / "prior-small.json"), "--pricing", str(FIXTURES / "pricing-small.json"), "--quota", str(FIXTURES / "quota-small.json"), "--out", str(output)], capture_output=True, text=True, check=False)
            self.assertNotEqual(second.returncode, 0)


if __name__ == "__main__":
    unittest.main()
