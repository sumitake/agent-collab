"""Focused public contract tests for the deterministic estimator."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "project_estimation"


def _load():
    path = ROOT / "plugins" / "agent-collab" / "project_estimation.py"
    spec = importlib.util.spec_from_file_location("project_estimation", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class EstimatorTests(unittest.TestCase):
    def test_request_rejects_unknown_field_and_recursive_auto(self):
        module = _load()
        request = _json("request-enhancement.json")
        request["surprise"] = True
        with self.assertRaises(module.EstimationError):
            module.validate_request(request)
        request = _json("request-plan-auto.json")
        with self.assertRaisesRegex(module.EstimationError, "recursive_invocation"):
            module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), _json("quota-small.json"))

    def test_scope_hash_is_order_and_prose_invariant(self):
        module = _load()
        left = _json("request-enhancement.json")
        right = copy.deepcopy(left)
        right["phases"] = list(reversed(right["phases"]))
        right["dependency_edges"] = list(reversed(right["dependency_edges"]))
        right["assumptions"] = ["changed prose"]
        right["exclusions"] = ["also inert"]
        self.assertEqual(module.artifact_scope_hash(left), module.artifact_scope_hash(right))
        right["max_agent_concurrency"] = 3
        self.assertNotEqual(module.artifact_scope_hash(left), module.artifact_scope_hash(right))

    def test_deterministic_result_and_headline_cash_separation(self):
        module = _load()
        request = _json("request-enhancement.json")
        prior, pricing, quota = (_json(name) for name in ("prior-small.json", "pricing-small.json", "quota-small.json"))
        first = module.estimate(request, prior, pricing, quota)
        second = module.estimate(request, prior, pricing, quota)
        self.assertEqual(first, second)
        self.assertEqual(first["labels"]["api_equivalent"], "not billed cash")
        self.assertIn("api_equivalent_cost_current", first["headline"])
        self.assertNotIn("actual_marginal_cash", first["headline"])
        self.assertEqual(first["detail"]["actual_marginal_cash_status"], "unknown")

    def test_empty_phases_is_typed_unavailable(self):
        module = _load()
        request = _json("request-enhancement.json")
        request["phases"] = []
        request["dependency_edges"] = []
        result = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), _json("quota-small.json"))
        self.assertEqual(result["estimate_unavailable"], "insufficient_scope")

    def test_dag_and_wait_contracts_fail_closed(self):
        module = _load()
        request = _json("request-enhancement.json")
        request["dependency_edges"].append({"from": "test", "to": "design"})
        with self.assertRaisesRegex(module.EstimationError, "cycle"):
            module.validate_request(request)
        request = _json("request-enhancement.json")
        request["phases"][0]["external_wait_seconds"] = {"p50": 1, "p80": 2, "p95": 3}
        with self.assertRaises(module.EstimationError):
            module.validate_request(request)

    def test_unpriced_route_is_coverage_not_zero(self):
        module = _load()
        pricing = _json("pricing-small.json")
        pricing["providers"]["provider-a"]["values"] = []
        result = module.estimate(_json("request-enhancement.json"), _json("prior-small.json"), pricing, _json("quota-small.json"))
        self.assertGreater(result["headline"]["unpriced_basis_points"], 0)
        self.assertIsNone(result["headline"]["api_equivalent_cost_current"]["p50_microusd"])


if __name__ == "__main__":
    unittest.main()
