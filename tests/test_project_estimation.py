"""Focused public contract tests for the deterministic estimator."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "project_estimation"
SHA = "a" * 64


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


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _approved(record: dict[str, object]) -> dict[str, object]:
    record = dict(record)
    record["approved_value_sha256"] = hashlib.sha256(_canonical(record)).hexdigest()
    return record


def _deep_prior(module, request: dict[str, object]) -> dict[str, object]:
    prior = _json("prior-small.json")
    names = module._hierarchy_names(request)
    base = prior["nodes"][0]
    nodes = []
    for index, name in enumerate(names):
        node = copy.deepcopy(base)
        node["hierarchy_node"] = name
        node["fallback_parent"] = names[index - 1] if index else None
        nodes.append(node)
    prior["nodes"] = sorted(nodes, key=lambda row: row["hierarchy_node"])
    return prior


def _second_route(request: dict[str, object]) -> None:
    request["routes"] = [
        {**request["routes"][0], "token_share_basis_points": 5000},
        {
            "id": "route-b", "provider": "provider-b", "model": "m",
            "modality": "text", "tier": "standard",
            "token_share_basis_points": 5000, "quota_usage": [],
        },
    ]


class ValidatorTests(unittest.TestCase):
    def test_runtime_schema_enums_and_top_level_shapes_are_in_parity(self):
        request_schema = json.loads((ROOT / "plugins" / "agent-collab" / "project-estimation-data" / "estimate-request.schema.json").read_text())
        result_schema = json.loads((ROOT / "plugins" / "agent-collab" / "project-estimation-data" / "estimate-result.schema.json").read_text())
        pricing_schema = json.loads((ROOT / "plugins" / "agent-collab" / "project-estimation-data" / "pricing-snapshot.schema.json").read_text())
        quota_schema = json.loads((ROOT / "plugins" / "agent-collab" / "project-estimation-data" / "quota-snapshot.schema.json").read_text())
        self.assertIn("unknown", request_schema["properties"]["reusable_classification"]["enum"])
        self.assertEqual(
            pricing_schema["$defs"]["provider"]["properties"]["status"]["enum"],
            ["official", "estimated_stale", "review_required", "unpriced"],
        )
        self.assertEqual(pricing_schema["$defs"]["record"]["properties"]["currency"], {"const": "USD"})
        self.assertEqual(pricing_schema["$defs"]["record"]["properties"]["unit"], {"const": "per_million_tokens"})
        self.assertEqual(
            set(quota_schema["$defs"]["record"]["properties"]["limit_kind"]["enum"]),
            {"rpm", "tpm", "concurrency", "subscription_5_hour", "subscription_weekly", "subscription_monthly", "cooldown"},
        )
        self.assertFalse(result_schema["additionalProperties"])
        self.assertEqual(set(result_schema["required"]), {"schema_version", "result_kind", "labels"})
        for variant in result_schema["anyOf"]:
            self.assertEqual(variant["type"], "object")
            self.assertFalse(variant["additionalProperties"])
            self.assertEqual(set(variant["required"]), set(variant["properties"]))

    def test_request_exact_types_recursive_and_caller_hash(self):
        module = _load()
        class DictSubclass(dict):
            pass

        with self.assertRaises(module.EstimationError):
            module.estimate(DictSubclass(_json("request-enhancement.json")), _json("prior-small.json"), _json("pricing-small.json"), _json("quota-small.json"))
        request = _json("request-enhancement.json")
        request["artifact_kind"] = []
        with self.assertRaises(module.EstimationError):
            module.validate_request(request)
        request = _json("request-plan-auto.json")
        with self.assertRaisesRegex(module.EstimationError, "recursive_invocation"):
            module.validate_request(request)
        request = _json("request-enhancement.json")
        request["artifact_scope_hash"] = "0" * 64
        with self.assertRaisesRegex(module.EstimationError, "artifact_scope_hash"):
            module.validate_request(request)

    def test_request_allows_unknown_reusable_classification(self):
        module = _load()
        request = _json("request-enhancement.json")
        request["reusable_classification"] = "unknown"
        self.assertEqual(module.validate_request(request)["reusable_classification"], "unknown")

    def test_dag_route_and_external_wait_contracts_fail_closed(self):
        module = _load()
        request = _json("request-enhancement.json")
        request["dependency_edges"].append({"from": "test", "to": "design"})
        with self.assertRaisesRegex(module.EstimationError, "cycle"):
            module.validate_request(request)
        request = _json("request-enhancement.json")
        request["dependency_edges"].append(copy.deepcopy(request["dependency_edges"][0]))
        with self.assertRaises(module.EstimationError):
            module.validate_request(request)
        request = _json("request-enhancement.json")
        request["phases"][0]["external_wait_seconds"] = {"p50": 1, "p80": 2, "p95": 3}
        with self.assertRaises(module.EstimationError):
            module.validate_request(request)
        request = _json("request-enhancement.json")
        request["routes"][0]["quota_usage"].append({"limit_kind": "tpm", "quantity": 1})
        with self.assertRaises(module.EstimationError):
            module.validate_request(request)

    def test_aggregate_snapshot_actual_and_result_are_closed(self):
        module = _load()
        prior = _json("prior-small.json")
        prior["nodes"][0]["surprise"] = 1
        with self.assertRaises(module.EstimationError):
            module.validate_aggregate(prior)
        pricing = _json("pricing-small.json")
        pricing["providers"]["provider-a"]["values"][0]["approved_value_sha256"] = SHA
        with self.assertRaisesRegex(module.EstimationError, "approved_value"):
            module.validate_pricing(pricing)
        request = _json("request-enhancement.json")
        result = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), _json("quota-small.json"))
        self.assertEqual(module.validate_result(result)["result_kind"], "estimate")
        forged = copy.deepcopy(result)
        forged["surprise"] = True
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)
        actual = module.validate_actual({
            "schema_version": 1,
            "completion_boundary": "merged",
            "focused_agent_wall_clock_seconds": 4000,
            "calendar_elapsed_seconds": 5000,
            "summed_agent_runtime_seconds": 4500,
            "token_usage": [{"route_id": "route-a", "token_class": "input", "quantity": 1200000}],
            "wait_decomposition": {"operator_seconds": 0, "vendor_seconds": 0, "quota_seconds": 1000},
            "actual_marginal_cash": {"status": "unknown"},
            "persistence_consent": False,
        })
        self.assertEqual(actual["actual_marginal_cash"]["status"], "unknown")

    def test_snapshot_status_dates_units_and_digest_are_strict(self):
        module = _load()
        pricing = _json("pricing-small.json")
        row = pricing["providers"]["provider-a"]
        row.update({"status": "review_required", "retrieved_date": None,
                    "last_successful_official_date": None, "values": [], "value_sha256": None,
                    "source_url_sha256": None, "final_url_sha256": None, "redirect_chain_sha256": None,
                    "content_type": None, "elapsed_class": None, "failure_class": "lookup_failed"})
        pricing["operator_notification_required"] = True
        pricing["material_unpriced"] = True
        pricing["uncertainty_basis_points"] = 1000
        self.assertEqual(module.validate_pricing(pricing)["providers"]["provider-a"]["status"], "review_required")
        with self.assertRaisesRegex(module.EstimationError, "review_required"):
            module.estimate(_json("request-enhancement.json"), _json("prior-small.json"), pricing, _json("quota-small.json"))
        pricing = _json("pricing-small.json")
        pricing["retrieved_date"] = "2026-02-30"
        with self.assertRaises(module.EstimationError):
            module.validate_pricing(pricing)


class ProjectionAndHierarchyTests(unittest.TestCase):
    def test_scope_hash_is_order_and_prose_invariant(self):
        module = _load()
        left = _json("request-enhancement.json")
        right = copy.deepcopy(left)
        right["phases"] = list(reversed(right["phases"]))
        right["dependency_edges"] = list(reversed(right["dependency_edges"]))
        right["routes"][0]["quota_usage"] = list(reversed(right["routes"][0]["quota_usage"]))
        right["assumptions"] = ["changed prose"]
        right["exclusions"] = ["also inert"]
        right["as_of_date"] = "2026-08-22"
        self.assertEqual(module.artifact_scope_hash(left), module.artifact_scope_hash(right))
        right["max_agent_concurrency"] = 3
        self.assertNotEqual(module.artifact_scope_hash(left), module.artifact_scope_hash(right))

    def test_scope_hash_includes_wait_and_quota_usage(self):
        module = _load()
        request = _json("request-enhancement.json")
        request["phases"].append({
            "id": "approve", "kind": "approval", "prior_phase": "release",
            "owner": "operator", "scenario": "production_pilot",
            "delivery_class": "project_specific", "effort_weight": 1,
            "external_wait_seconds": {"p50": 60, "p80": 120, "p95": 180},
        })
        request["dependency_edges"].append({"from": "test", "to": "approve"})
        wait_changed = copy.deepcopy(request)
        wait_changed["phases"][-1]["external_wait_seconds"]["p95"] = 181
        self.assertNotEqual(module.artifact_scope_hash(request), module.artifact_scope_hash(wait_changed))
        usage_changed = copy.deepcopy(request)
        usage_changed["routes"][0]["quota_usage"][0]["quantity"] += 1
        self.assertNotEqual(module.artifact_scope_hash(request), module.artifact_scope_hash(usage_changed))

    def test_hierarchy_matches_task3_and_never_crosses_project_type(self):
        module = _load()
        request = _json("request-enhancement.json")
        expected = [
            "project_type.enhancement", "h2.f9c0dc358bece64b.cb-merged",
            "h3.e0e4ccf3a75dd854.rc-plugin", "h4.b69d4ef98be344de.pm-established",
            "h5.32378e3c14471143.si-low-low", "h6.740ae857850c02db.risk-medium",
            "h7.3d985a1bda02f533.burden-ordinary", "h8.b081fe2e7997e901.ep-low-single",
            "h9.5827b875e0eb8f52.orch-single",
        ]
        self.assertEqual(module._hierarchy_names(request), expected)
        prior = _deep_prior(module, request)
        result = module.estimate(request, prior, _json("pricing-small.json"), _json("quota-small.json"))
        self.assertEqual(result["headline"]["calibration"]["selected_node"], expected[-1])
        wrong = copy.deepcopy(prior)
        wrong["nodes"] = [{**wrong["nodes"][0], "hierarchy_node": "project_type.greenfield", "fallback_parent": None}]
        result = module.estimate(request, wrong, _json("pricing-small.json"), _json("quota-small.json"))
        self.assertEqual(result["estimate_unavailable"], "no_compatible_prior")

    def test_backoff_is_visible_and_uncertainty_is_applied(self):
        module = _load()
        request = _json("request-enhancement.json")
        result = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), _json("quota-small.json"))
        calibration = result["headline"]["calibration"]
        self.assertGreater(calibration["backoff_penalty_basis_points"], 0)
        self.assertEqual(calibration["base_duration_uncertainty_basis_points"], 0)
        self.assertEqual(calibration["base_token_uncertainty_basis_points"], 0)
        self.assertEqual(calibration["token_uncertainty_floor_basis_points"], calibration["backoff_penalty_basis_points"])
        self.assertIn("hierarchy_backoff", result["headline"]["uncertainty_drivers"])
        self.assertGreater(result["detail"]["calendar_elapsed_seconds"]["p95"], 10800)


class SimulationTests(unittest.TestCase):
    def test_deterministic_result_and_cash_separation(self):
        module = _load()
        request = _json("request-enhancement.json")
        inputs = (_json("prior-small.json"), _json("pricing-small.json"), _json("quota-small.json"))
        first = module.estimate(request, *inputs)
        second = module.estimate(request, *inputs)
        self.assertEqual(first, second)
        self.assertEqual(first["labels"]["api_equivalent"], "not billed cash")
        self.assertNotIn("actual_marginal_cash", first["headline"])
        self.assertEqual(first["detail"]["actual_marginal_cash_status"], "unknown")

    def test_overall_allocation_preserves_total_and_uses_known_medians(self):
        module = _load()
        request = _json("request-enhancement.json")
        prior = _json("prior-small.json")
        prior["nodes"][0]["phase_duration_quantiles"].append({"phase": "primary", "p50": 3000, "p80": 3000, "p95": 3000})
        result = module.estimate(request, prior, _json("pricing-small.json"), _json("quota-small.json"))
        phase_rows = result["detail"]["phase_rows"]
        for percentile in ("p50", "p80", "p95"):
            allocated = sum(row["duration_seconds"][percentile] for row in phase_rows if row["owner"] == "autonomous_agent")
            overall = result["detail"]["allocated_overall_seconds"][percentile]
            self.assertEqual(allocated, overall)

    def test_complete_phase_evidence_uses_direct_rows_and_reports_their_sum(self):
        module = _load()
        request = _json("request-enhancement.json")
        prior = _json("prior-small.json")
        prior["nodes"][0]["phase_duration_quantiles"] += [
            {"phase": "primary", "p50": 100, "p80": 100, "p95": 100},
            {"phase": "test", "p50": 400, "p80": 400, "p95": 400},
        ]
        result = module.estimate(request, prior, _json("pricing-small.json"), _json("quota-small.json"))
        self.assertNotIn("overall_allocated", result["headline"]["uncertainty_drivers"])
        for percentile in ("p50", "p80", "p95"):
            phase_sum = sum(row["duration_seconds"][percentile] for row in result["detail"]["phase_rows"])
            self.assertEqual(result["detail"]["allocated_overall_seconds"][percentile], phase_sum)

    def test_worker_union_sum_external_wait_rework_and_full_critical_chain(self):
        module = _load()
        request = _json("request-enhancement.json")
        request["phases"].append({
            "id": "approve", "kind": "approve", "prior_phase": "release", "owner": "operator",
            "scenario": "production_pilot", "delivery_class": "project_specific", "effort_weight": 1,
            "external_wait_seconds": {"p50": 600, "p80": 600, "p95": 600},
        })
        request["phases"].append({
            "id": "rework", "kind": "rework", "prior_phase": "rework", "owner": "autonomous_agent",
            "scenario": "production_pilot", "delivery_class": "reusable_core", "effort_weight": 1,
            "route_id": "route-a",
        })
        request["dependency_edges"] += [{"from": "test", "to": "approve"}, {"from": "approve", "to": "rework"}]
        result = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), _json("quota-small.json"))
        self.assertEqual(result["headline"]["critical_path"], ["design", "test", "approve", "rework"])
        self.assertGreater(result["detail"]["summed_agent_runtime_seconds"]["p80"], 0)
        self.assertEqual(result["detail"]["wait_decomposition_seconds"]["operator"]["p50"], 600)
        self.assertIn("rework", {row["id"] for row in result["detail"]["phase_rows"]})


class CostQuotaTests(unittest.TestCase):
    def test_multiple_token_classes_are_aggregated_once_per_route_sample(self):
        module = _load()
        request = _json("request-enhancement.json")
        prior = _json("prior-small.json")
        prior["nodes"][0]["token_class_quantiles"].append(
            {"token_class": "output", "p50": 2_000_000, "p80": 2_000_000, "p95": 2_000_000}
        )
        pricing = _json("pricing-small.json")
        values = pricing["providers"]["provider-a"]["values"]
        values.append(_approved({
            "record_id": "p2", "model": "m", "modality": "text", "tier": "standard",
            "token_class": "output", "currency": "USD", "unit": "per_million_tokens",
            "amount_microusd": 2_000_000, "amount_text": "2.0", "modifiers": [],
        }))
        pricing["providers"]["provider-a"]["value_sha256"] = hashlib.sha256(_canonical(values)).hexdigest()
        result = module.estimate(request, prior, pricing, _json("quota-small.json"))
        route = result["detail"]["route_costs"][0]
        self.assertEqual(route["known_token_quantity"]["p50"], 3_000_000)
        self.assertEqual(route["known_microusd"]["p50"], 5_000_000)

    def test_empty_routes_are_unpriced_not_zero(self):
        module = _load()
        request = _json("request-enhancement.json")
        for phase in request["phases"]:
            phase.pop("route_id", None)
        request["routes"] = []
        result = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), _json("quota-small.json"))
        cost = result["headline"]["api_equivalent_cost_current"]
        self.assertIsNone(cost["known_microusd"]["p50"])
        self.assertEqual(cost["known_basis_points"], 0)
        self.assertEqual(cost["unpriced_basis_points"], 10000)

    def test_partial_pricing_retains_known_cost_and_exact_coverage(self):
        module = _load()
        request = _json("request-enhancement.json")
        _second_route(request)
        pricing = _json("pricing-small.json")
        pricing["providers"]["provider-a"]["material_share_basis_points"] = 5000
        provider_b = copy.deepcopy(pricing["providers"]["provider-a"])
        provider_b.update({"provider": "provider-b", "status": "unpriced", "retrieved_date": None,
                           "last_successful_official_date": None, "original_last_good_date": None,
                           "values": [], "value_sha256": None, "source_url_sha256": None,
                           "final_url_sha256": None, "redirect_chain_sha256": None,
                           "content_type": None, "elapsed_class": None, "failure_class": "not_found",
                           "material_share_basis_points": 5000})
        pricing["providers"]["provider-b"] = provider_b
        pricing["operator_notification_required"] = True
        pricing["material_unpriced"] = True
        pricing["uncertainty_basis_points"] = 1000
        result = module.estimate(request, _json("prior-small.json"), pricing, _json("quota-small.json"))
        cost = result["headline"]["api_equivalent_cost_current"]
        self.assertGreater(cost["known_microusd"]["p50"], 0)
        self.assertEqual(cost["known_basis_points"], 5000)
        self.assertEqual(cost["unpriced_basis_points"], 5000)

    def test_ambiguous_price_dimensions_are_unpriced_not_order_selected(self):
        module = _load()
        pricing = _json("pricing-small.json")
        values = pricing["providers"]["provider-a"]["values"]
        duplicate = _approved({**{key: value for key, value in values[0].items() if key != "approved_value_sha256"}, "record_id": "p-duplicate", "amount_microusd": 9_000_000})
        values.append(duplicate)
        pricing["providers"]["provider-a"]["value_sha256"] = hashlib.sha256(_canonical(values)).hexdigest()
        result = module.estimate(_json("request-enhancement.json"), _json("prior-small.json"), pricing, _json("quota-small.json"))
        self.assertIsNone(result["headline"]["api_equivalent_cost_current"]["known_microusd"]["p50"])
        self.assertEqual(result["headline"]["api_equivalent_cost_current"]["unpriced_basis_points"], 10_000)

    def test_quota_kinds_aggregate_provider_sum_cross_provider_max(self):
        module = _load()
        request = _json("request-enhancement.json")
        request["routes"][0]["quota_usage"] += [
            {"limit_kind": "subscription_5_hour", "quantity": 3},
            {"limit_kind": "cooldown", "quantity": 2},
        ]
        quota = _json("quota-small.json")
        values = quota["providers"]["provider-a"]["values"]
        values += [
            _approved({"record_id": "sub", "model": "m", "modality": "text", "tier": "standard", "limit_kind": "subscription_5_hour", "limit_value": 1, "window_seconds": 18000, "cooldown_seconds": 60, "modifiers": []}),
            _approved({"record_id": "cool", "model": "m", "modality": "text", "tier": "standard", "limit_kind": "cooldown", "limit_value": 1, "window_seconds": None, "cooldown_seconds": 30, "modifiers": []}),
        ]
        quota["providers"]["provider-a"]["value_sha256"] = hashlib.sha256(_canonical(values)).hexdigest()
        result = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), quota)
        self.assertGreaterEqual(result["detail"]["quota"]["delay_seconds"]["p50"], 36150)
        self.assertEqual(result["detail"]["quota"]["provider_aggregation_rule"], "sum_within_provider_max_across_providers")

    def test_every_quota_kind_has_unit_safe_behavior(self):
        module = _load()
        request = _json("request-enhancement.json")
        request["routes"][0]["quota_usage"] += [
            {"limit_kind": "rpm", "quantity": 3},
            {"limit_kind": "subscription_5_hour", "quantity": 2},
            {"limit_kind": "subscription_weekly", "quantity": 2},
            {"limit_kind": "subscription_monthly", "quantity": 2},
            {"limit_kind": "cooldown", "quantity": 3},
        ]
        quota = _json("quota-small.json")
        values = quota["providers"]["provider-a"]["values"]
        for record in (
            {"record_id": "rpm", "limit_kind": "rpm", "limit_value": 1, "window_seconds": 60, "cooldown_seconds": 0},
            {"record_id": "concurrency", "limit_kind": "concurrency", "limit_value": 1, "window_seconds": None, "cooldown_seconds": 0},
            {"record_id": "five", "limit_kind": "subscription_5_hour", "limit_value": 1, "window_seconds": 18_000, "cooldown_seconds": 10},
            {"record_id": "week", "limit_kind": "subscription_weekly", "limit_value": 1, "window_seconds": 604_800, "cooldown_seconds": 20},
            {"record_id": "month", "limit_kind": "subscription_monthly", "limit_value": 1, "window_seconds": 2_592_000, "cooldown_seconds": 30},
            {"record_id": "cooldown", "limit_kind": "cooldown", "limit_value": 1, "window_seconds": None, "cooldown_seconds": 40},
        ):
            values.append(_approved({"model": "m", "modality": "text", "tier": "standard", "modifiers": [], **record}))
        quota["providers"]["provider-a"]["value_sha256"] = hashlib.sha256(_canonical(values)).hexdigest()
        result = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), quota)
        self.assertEqual(result["headline"]["planned_concurrency"], 1)
        self.assertGreaterEqual(result["detail"]["quota"]["delay_seconds"]["p50"], 3_215_060)
        self.assertEqual(result["detail"]["quota"]["coverage_basis_points"], 10_000)

    def test_unknown_quota_widens_p95_and_never_shortens(self):
        module = _load()
        request = _json("request-enhancement.json")
        known = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), _json("quota-small.json"))
        quota = _json("quota-small.json")
        row = quota["providers"]["provider-a"]
        row.update({"status": "unknown", "retrieved_date": None, "last_successful_official_date": None,
                    "original_last_good_date": None, "values": [], "value_sha256": None,
                    "source_url_sha256": None, "final_url_sha256": None, "redirect_chain_sha256": None,
                    "content_type": None, "elapsed_class": None, "failure_class": "quota_unavailable"})
        quota["operator_notification_required"] = True
        quota["uncertainty_basis_points"] = 1000
        unknown = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), quota)
        self.assertGreaterEqual(unknown["detail"]["calendar_elapsed_seconds"]["p95"], known["detail"]["calendar_elapsed_seconds"]["p95"])
        self.assertLess(unknown["detail"]["quota"]["coverage_basis_points"], 10000)


class ReconciliationTests(unittest.TestCase):
    def test_reconciliation_reports_three_non_additive_views_and_errors(self):
        module = _load()
        request = _json("request-enhancement.json")
        pricing = _json("pricing-small.json")
        prior_result = module.estimate(request, _json("prior-small.json"), pricing, _json("quota-small.json"))
        actual = {
            "schema_version": 1, "completion_boundary": "merged",
            "focused_agent_wall_clock_seconds": 4000, "calendar_elapsed_seconds": 5000,
            "summed_agent_runtime_seconds": 4500,
            "token_usage": [{"route_id": "route-a", "token_class": "input", "quantity": 1200000}],
            "wait_decomposition": {"operator_seconds": 0, "vendor_seconds": 0, "quota_seconds": 1000},
            "actual_marginal_cash": {"status": "operator_supplied", "amount_microusd": 2500000, "evidence_sha256": SHA},
            "execution_era_pricing": pricing, "persistence_consent": False,
        }
        result = module.reconcile(prior_result, actual, pricing)
        self.assertEqual(module.validate_result(result)["result_kind"], "reconciliation")
        self.assertIn("duration_errors", result)
        self.assertIn("current_api_equivalent", result["cost_views"])
        self.assertIn("execution_era_api_equivalent", result["cost_views"])
        self.assertEqual(result["cost_views"]["actual_marginal_cash"]["amount_microusd"], 2500000)
        self.assertIn("non_additive", result["labels"]["non_additivity"])


if __name__ == "__main__":
    unittest.main()
