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


def _rehash_provider(snapshot: dict[str, object], provider_name: str = "provider-a") -> None:
    values = snapshot["providers"][provider_name]["values"]
    snapshot["providers"][provider_name]["value_sha256"] = hashlib.sha256(_canonical(values)).hexdigest()


def _unknown_quota() -> dict[str, object]:
    quota = _json("quota-small.json")
    row = quota["providers"]["provider-a"]
    row.update({"status": "unknown", "retrieved_date": None,
                "last_successful_official_date": None, "original_last_good_date": None,
                "values": [], "value_sha256": None, "source_url_sha256": None,
                "final_url_sha256": None, "redirect_chain_sha256": None,
                "content_type": None, "elapsed_class": None,
                "failure_class": "quota_unavailable"})
    quota["operator_notification_required"] = True
    quota["uncertainty_basis_points"] = 1000
    return quota


def _actual(*, route_id: str = "route-a", quantity: int = 1_000_000) -> dict[str, object]:
    return {
        "schema_version": 1, "completion_boundary": "merged",
        "focused_agent_wall_clock_seconds": 4000, "calendar_elapsed_seconds": 5000,
        "summed_agent_runtime_seconds": 4500,
        "token_usage": [{"route_id": route_id, "token_class": "input", "quantity": quantity}],
        "wait_decomposition": {"operator_seconds": 0, "vendor_seconds": 0, "quota_seconds": 1000},
        "actual_marginal_cash": {"status": "unknown"}, "persistence_consent": False,
    }


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
        self.assertIn("nullable_seconds", result_schema["$defs"])
        self.assertIn("nullable_hours", result_schema["$defs"])
        self.assertEqual(
            set(result_schema["$defs"]["route_cost"]["required"]),
            {"route_id", "provider", "model", "modality", "tier", "known_microusd",
             "known_token_quantity", "unpriced_token_quantity", "coverage_basis_points"},
        )
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

    def test_all_programmatic_validators_enforce_exact_schema_type_and_one_mib(self):
        module = _load()
        request = _json("request-enhancement.json")
        prior = _json("prior-small.json")
        pricing = _json("pricing-small.json")
        quota = _json("quota-small.json")
        result = module.estimate(request, prior, pricing, quota)
        actual = _actual()
        cases = (
            (module.validate_request, request), (module.validate_aggregate, prior),
            (module.validate_pricing, pricing), (module.validate_quota, quota),
            (module.validate_actual, actual), (module.validate_result, result),
        )
        for validator, document in cases:
            with self.subTest(validator=validator.__name__, condition="boolean-version"):
                malformed = copy.deepcopy(document)
                malformed["schema_version"] = True
                with self.assertRaises(module.EstimationError):
                    validator(malformed)
            with self.subTest(validator=validator.__name__, condition="oversized"):
                oversized = copy.deepcopy(document)
                oversized["oversized"] = "x" * (module.MAX_BYTES + 1)
                with self.assertRaisesRegex(module.EstimationError, "one MiB"):
                    validator(oversized)
        nested = copy.deepcopy(prior)
        nested["nodes"][0]["schema_version"] = True
        with self.assertRaises(module.EstimationError):
            module.validate_aggregate(nested)

    def test_mixed_mapping_keys_and_malformed_metric_objects_are_typed_errors(self):
        module = _load()
        request = _json("request-enhancement.json")
        request[7] = "mixed-key"
        with self.assertRaises(module.EstimationError):
            module.validate_request(request)
        request = _json("request-enhancement.json")
        request["assumptions"].append(request)
        with self.assertRaises(module.EstimationError):
            module.validate_request(request)
        deeply_nested: dict[str, object] = {}
        cursor = deeply_nested
        for _ in range(2000):
            child: dict[str, object] = {}
            cursor["child"] = child
            cursor = child
        with self.assertRaises(module.EstimationError):
            module.validate_request(deeply_nested)
        prior = _json("prior-small.json")
        prior["nodes"][0]["uncertainty_floors"] = 7
        with self.assertRaises(module.EstimationError):
            module.validate_aggregate(prior)

    def test_estimate_rejects_snapshots_after_request_date(self):
        module = _load()
        request = _json("request-enhancement.json")
        pricing = _json("pricing-small.json")
        pricing["retrieved_date"] = "2026-08-22"
        pricing["providers"]["provider-a"]["retrieved_date"] = "2026-08-22"
        pricing["providers"]["provider-a"]["last_successful_official_date"] = "2026-08-22"
        with self.assertRaisesRegex(module.EstimationError, "after request"):
            module.estimate(request, _json("prior-small.json"), pricing, _json("quota-small.json"))
        quota = _json("quota-small.json")
        quota["retrieved_date"] = "2026-08-22"
        quota["providers"]["provider-a"]["retrieved_date"] = "2026-08-22"
        quota["providers"]["provider-a"]["last_successful_official_date"] = "2026-08-22"
        with self.assertRaisesRegex(module.EstimationError, "after request"):
            module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), quota)

    def test_actual_focused_time_cannot_exceed_calendar_time(self):
        module = _load()
        actual = _actual()
        actual["focused_agent_wall_clock_seconds"] = 5001
        actual["summed_agent_runtime_seconds"] = 6000
        with self.assertRaisesRegex(module.EstimationError, "calendar"):
            module.validate_actual(actual)


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

    def test_allocated_fallback_uses_pinned_odd_and_even_integer_medians(self):
        module = _load()
        odd_phases = [
            {"id": "a", "owner": "autonomous_agent", "prior_phase": "primary", "effort_weight": 1},
            {"id": "b", "owner": "autonomous_agent", "prior_phase": "review", "effort_weight": 1},
            {"id": "c", "owner": "autonomous_agent", "prior_phase": "test", "effort_weight": 1},
            {"id": "missing", "owner": "autonomous_agent", "prior_phase": "deployment", "effort_weight": 1},
        ]
        odd_rows = {
            "primary": {"p50": 100, "p80": 100, "p95": 100},
            "review": {"p50": 1000, "p80": 1000, "p95": 1000},
            "test": {"p50": 100, "p80": 100, "p95": 100},
        }
        odd, total, allocated = module._allocated_durations(
            odd_phases, odd_rows, {"p50": 1300, "p80": 1300, "p95": 1300}, 0, 7,
        )
        self.assertTrue(allocated)
        self.assertEqual(sum(odd.values()), total)
        self.assertEqual(odd["missing"], odd["a"])

        even_phases = odd_phases[:2] + [odd_phases[-1]]
        even_rows = {
            "primary": {"p50": 100, "p80": 100, "p95": 100},
            "review": {"p50": 101, "p80": 101, "p95": 101},
        }
        even, total, _ = module._allocated_durations(
            even_phases, even_rows, {"p50": 302, "p80": 302, "p95": 302}, 0, 7,
        )
        self.assertEqual(sum(even.values()), total)
        self.assertEqual(even, {"a": 100, "b": 101, "missing": 101})


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

    def test_unknown_quota_preserves_a_numeric_known_calendar_floor(self):
        module = _load()
        request = _json("request-enhancement.json")
        quota = _json("quota-small.json")
        row = quota["providers"]["provider-a"]
        row.update({"status": "unknown", "retrieved_date": None, "last_successful_official_date": None,
                    "original_last_good_date": None, "values": [], "value_sha256": None,
                    "source_url_sha256": None, "final_url_sha256": None, "redirect_chain_sha256": None,
                    "content_type": None, "elapsed_class": None, "failure_class": "quota_unavailable"})
        quota["operator_notification_required"] = True
        quota["uncertainty_basis_points"] = 1000
        unknown = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), quota)
        self.assertTrue(all(
            type(value) is int
            for value in unknown["detail"]["calendar_known_floor_seconds"].values()
        ))
        self.assertLess(unknown["detail"]["quota"]["coverage_basis_points"], 10000)

    def test_unknown_quota_exposes_only_numeric_floors_and_never_changes_work(self):
        module = _load()
        request = _json("request-enhancement.json")
        request["routes"][0]["quota_usage"].append({"limit_kind": "subscription_5_hour", "quantity": 3})
        known_quota = _json("quota-small.json")
        known_quota["providers"]["provider-a"]["values"].append(_approved({
            "record_id": "five", "model": "m", "modality": "text", "tier": "standard",
            "limit_kind": "subscription_5_hour", "limit_value": 1,
            "window_seconds": 18_000, "cooldown_seconds": 60, "modifiers": [],
        }))
        _rehash_provider(known_quota)
        known = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), known_quota)
        unknown = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), _unknown_quota())
        self.assertEqual(known["headline"]["calendar_estimate_status"], "complete")
        self.assertEqual(known["detail"]["calendar_elapsed_seconds"], known["detail"]["calendar_known_floor_seconds"])
        self.assertEqual(unknown["headline"]["calendar_estimate_status"], "unavailable_unknown_quota")
        self.assertEqual(unknown["detail"]["calendar_elapsed_seconds"], {"p50": None, "p80": None, "p95": None})
        self.assertEqual(unknown["detail"]["quota"]["delay_seconds"], {"p50": None, "p80": None, "p95": None})
        self.assertEqual(unknown["detail"]["wait_decomposition_seconds"]["total"], {"p50": None, "p80": None, "p95": None})
        self.assertTrue(all(type(value) is int for value in unknown["detail"]["calendar_known_floor_seconds"].values()))
        self.assertTrue(all(type(value) is int for value in unknown["detail"]["quota"]["known_delay_floor_seconds"].values()))
        self.assertEqual(unknown["detail"]["focused_agent_wall_clock_seconds"], known["detail"]["focused_agent_wall_clock_seconds"])
        self.assertEqual(unknown["detail"]["summed_agent_runtime_seconds"], known["detail"]["summed_agent_runtime_seconds"])
        self.assertEqual(unknown["headline"]["calibration"]["confidence"], known["headline"]["calibration"]["confidence"])
        self.assertEqual(unknown["headline"]["critical_path"], known["headline"]["critical_path"])
        self.assertEqual(unknown["headline"]["critical_path_basis"], "dag_makespan_p80")
        self.assertIn("resolve_unknown_quota", unknown["headline"]["prerequisites"])

    def test_quota_applicability_is_cross_checked_and_tpm_has_usage_fallback(self):
        module = _load()
        request = _json("request-enhancement.json")
        quota = _json("quota-small.json")
        quota["providers"]["provider-a"]["values"].append(_approved({
            "record_id": "five", "model": "m", "modality": "text", "tier": "standard",
            "limit_kind": "subscription_5_hour", "limit_value": 1,
            "window_seconds": 18_000, "cooldown_seconds": 0, "modifiers": [],
        }))
        _rehash_provider(quota)
        missing_request_usage = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), quota)
        self.assertEqual(missing_request_usage["detail"]["quota"]["status"], "unavailable_unknown_quota")

        request_usage = _json("request-enhancement.json")
        request_usage["routes"][0]["quota_usage"].append({"limit_kind": "subscription_5_hour", "quantity": 2})
        missing_snapshot = module.estimate(request_usage, _json("prior-small.json"), _json("pricing-small.json"), _json("quota-small.json"))
        self.assertEqual(missing_snapshot["detail"]["quota"]["status"], "unavailable_unknown_quota")

        no_tokens_prior = _json("prior-small.json")
        no_tokens_prior["nodes"][0]["token_class_quantiles"] = []
        tpm_request = _json("request-enhancement.json")
        tpm_request["routes"][0]["quota_usage"][0]["quantity"] = 2_000_000
        fallback = module.estimate(tpm_request, no_tokens_prior, _json("pricing-small.json"), _json("quota-small.json"))
        self.assertEqual(fallback["detail"]["quota"]["status"], "complete")
        self.assertEqual(fallback["detail"]["quota"]["delay_seconds"]["p50"], 60)

    def test_ambiguous_zero_and_missing_concurrency_quota_are_unknown(self):
        module = _load()
        request = _json("request-enhancement.json")
        request["routes"][0]["quota_usage"].append({"limit_kind": "concurrency", "quantity": 1})
        missing = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), _json("quota-small.json"))
        self.assertEqual(missing["detail"]["quota"]["status"], "unavailable_unknown_quota")

        request = _json("request-enhancement.json")
        quota = _json("quota-small.json")
        quota["providers"]["provider-a"]["values"][0]["limit_value"] = 0
        quota["providers"]["provider-a"]["values"][0] = _approved({
            key: value for key, value in quota["providers"]["provider-a"]["values"][0].items()
            if key != "approved_value_sha256"
        })
        _rehash_provider(quota)
        zero = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), quota)
        self.assertEqual(zero["detail"]["quota"]["status"], "unavailable_unknown_quota")

        quota = _json("quota-small.json")
        duplicate = _approved({**{key: value for key, value in quota["providers"]["provider-a"]["values"][0].items()
                                           if key != "approved_value_sha256"}, "record_id": "duplicate-tpm"})
        quota["providers"]["provider-a"]["values"].append(duplicate)
        _rehash_provider(quota)
        ambiguous = module.estimate(request, _json("prior-small.json"), _json("pricing-small.json"), quota)
        self.assertEqual(ambiguous["detail"]["quota"]["status"], "unavailable_unknown_quota")


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

    def test_repricing_is_bound_to_full_route_identity_and_rejects_unknown_routes(self):
        module = _load()
        pricing = _json("pricing-small.json")
        prior_result = module.estimate(
            _json("request-enhancement.json"), _json("prior-small.json"), pricing, _json("quota-small.json"),
        )
        route = prior_result["detail"]["route_costs"][0]
        self.assertEqual(
            {key: route[key] for key in ("provider", "model", "modality", "tier")},
            {"provider": "provider-a", "model": "m", "modality": "text", "tier": "standard"},
        )
        for dimension, wrong_value in (
            ("model", "wrong-model"),
            ("modality", "audio"),
            ("tier", "premium"),
        ):
            with self.subTest(dimension=dimension):
                mismatched = copy.deepcopy(pricing)
                record = mismatched["providers"]["provider-a"]["values"][0]
                record[dimension] = wrong_value
                record["approved_value_sha256"] = hashlib.sha256(_canonical({
                    key: value for key, value in record.items()
                    if key != "approved_value_sha256"
                })).hexdigest()
                _rehash_provider(mismatched)
                reconciled = module.reconcile(prior_result, _actual(), mismatched)
                self.assertIsNone(reconciled["cost_views"]["current_api_equivalent"]["known_microusd"])
                self.assertEqual(reconciled["cost_error_current"]["status"], "incomparable_coverage")
        with self.assertRaisesRegex(module.EstimationError, "unknown route"):
            module.reconcile(prior_result, _actual(route_id="not-planned"), pricing)

    def test_reconciliation_cost_comparability_and_duration_intervals_are_auditable(self):
        module = _load()
        pricing = _json("pricing-small.json")
        prior_result = module.estimate(
            _json("request-enhancement.json"), _json("prior-small.json"), pricing, _json("quota-small.json"),
        )
        full = module.reconcile(prior_result, _actual(), pricing)
        focused = full["duration_errors"]["focused"]
        self.assertEqual(focused["status"], "comparable")
        self.assertEqual(focused["planned_p95_seconds"], prior_result["detail"]["focused_agent_wall_clock_seconds"]["p95"])
        cost = full["cost_error_current"]
        self.assertEqual(cost["status"], "comparable_full")
        self.assertEqual(cost["planned_p95_microusd"], prior_result["headline"]["api_equivalent_cost_current"]["known_microusd"]["p95"])
        self.assertEqual(cost["planned_known_basis_points"], 10_000)
        self.assertEqual(cost["actual_known_basis_points"], 10_000)
        self.assertIs(type(cost["within_p50_p95"]), bool)

        wrong_model = copy.deepcopy(pricing)
        record = wrong_model["providers"]["provider-a"]["values"][0]
        record["model"] = "wrong-model"
        record["approved_value_sha256"] = hashlib.sha256(_canonical({key: value for key, value in record.items() if key != "approved_value_sha256"})).hexdigest()
        _rehash_provider(wrong_model)
        partial = module.reconcile(prior_result, _actual(), wrong_model)["cost_error_current"]
        self.assertEqual(partial["status"], "incomparable_coverage")
        for field in ("signed_error_microusd", "absolute_error_microusd", "log_ratio_millionths", "within_p50_p95"):
            self.assertIsNone(partial[field])

    def test_unknown_quota_reconciliation_never_uses_known_floor_as_interval(self):
        module = _load()
        prior_result = module.estimate(
            _json("request-enhancement.json"), _json("prior-small.json"),
            _json("pricing-small.json"), _unknown_quota(),
        )
        result = module.reconcile(prior_result, _actual(), _json("pricing-small.json"))
        calendar = result["duration_errors"]["calendar"]
        self.assertEqual(calendar["status"], "prior_unavailable")
        self.assertEqual(calendar["actual_seconds"], 5000)
        for field in ("planned_p50_seconds", "planned_p95_seconds", "signed_error_seconds", "absolute_error_seconds", "log_ratio_millionths", "within_p50_p95"):
            self.assertIsNone(calendar[field])
        self.assertEqual(result["wait_errors"]["quota"]["status"], "prior_unavailable")
        self.assertEqual(result["quota_error"]["status"], "prior_unavailable")

    def test_reconciliation_validation_recomputes_derived_interval_claims(self):
        module = _load()
        prior_result = module.estimate(
            _json("request-enhancement.json"), _json("prior-small.json"),
            _json("pricing-small.json"), _json("quota-small.json"),
        )
        result = module.reconcile(prior_result, _actual(), _json("pricing-small.json"))
        forged = copy.deepcopy(result)
        forged["duration_errors"]["focused"]["signed_error_seconds"] += 1
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)
        forged = copy.deepcopy(result)
        forged["cost_error_current"]["within_p50_p95"] = not forged["cost_error_current"]["within_p50_p95"]
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)

    def test_reconciliation_cost_status_is_iff_and_bound_to_current_view(self):
        module = _load()
        prior_result = module.estimate(
            _json("request-enhancement.json"), _json("prior-small.json"),
            _json("pricing-small.json"), _json("quota-small.json"),
        )
        result = module.reconcile(prior_result, _actual(), _json("pricing-small.json"))

        def make_incomparable(value: dict[str, object]) -> None:
            error = value["cost_error_current"]
            error["status"] = "incomparable_coverage"
            for field in (
                "signed_error_microusd", "absolute_error_microusd",
                "log_ratio_millionths", "within_p50_p95",
            ):
                error[field] = None

        forged = copy.deepcopy(result)
        make_incomparable(forged)
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)

        forged = copy.deepcopy(result)
        make_incomparable(forged)
        forged["cost_error_current"]["actual_known_basis_points"] = 9999
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)

        forged = copy.deepcopy(result)
        make_incomparable(forged)
        forged["cost_error_current"]["actual_repriced_microusd"] = None
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)

    def test_reconciliation_timeline_statuses_and_quota_coverage_are_cross_bound(self):
        module = _load()
        prior_result = module.estimate(
            _json("request-enhancement.json"), _json("prior-small.json"),
            _json("pricing-small.json"), _json("quota-small.json"),
        )
        complete = module.reconcile(prior_result, _actual(), _json("pricing-small.json"))

        forged = copy.deepcopy(complete)
        calendar = forged["duration_errors"]["calendar"]
        calendar["status"] = "prior_unavailable"
        for field in (
            "planned_p50_seconds", "planned_p95_seconds", "signed_error_seconds",
            "absolute_error_seconds", "log_ratio_millionths", "within_p50_p95",
        ):
            calendar[field] = None
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)

        forged = copy.deepcopy(complete)
        calendar = forged["duration_errors"]["calendar"]
        calendar["status"] = "prior_unavailable"
        for field in (
            "planned_p50_seconds", "planned_p95_seconds", "signed_error_seconds",
            "absolute_error_seconds", "log_ratio_millionths", "within_p50_p95",
        ):
            calendar[field] = None
        for field in ("wait_errors", "quota_error"):
            quota = forged[field]["quota"] if field == "wait_errors" else forged[field]
            quota["status"] = "prior_unavailable"
            for name in ("planned_p50_seconds", "signed_error_seconds", "absolute_error_seconds"):
                quota[name] = None
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)

        unknown_prior = module.estimate(
            _json("request-enhancement.json"), _json("prior-small.json"),
            _json("pricing-small.json"), _unknown_quota(),
        )
        forged = module.reconcile(unknown_prior, _actual(), _json("pricing-small.json"))
        calendar = forged["duration_errors"]["calendar"]
        calendar.update({
            "status": "comparable", "planned_p50_seconds": 1,
            "planned_p95_seconds": 1, "signed_error_seconds": 4999,
            "absolute_error_seconds": 4999,
            "log_ratio_millionths": module._log_ratio_millionths(5000, 1),
            "within_p50_p95": False,
        })
        quota_wait = forged["wait_errors"]["quota"]
        quota_wait.update({
            "status": "comparable", "planned_p50_seconds": 0,
            "signed_error_seconds": 1000, "absolute_error_seconds": 1000,
        })
        forged["quota_error"].update(quota_wait)
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)

    def test_unknown_quota_status_requires_resolution_driver_and_prerequisite(self):
        module = _load()
        result = module.estimate(
            _json("request-enhancement.json"), _json("prior-small.json"),
            _json("pricing-small.json"), _unknown_quota(),
        )
        forged = copy.deepcopy(result)
        forged["headline"]["prerequisites"] = []
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)
        forged = copy.deepcopy(result)
        forged["headline"]["uncertainty_drivers"].remove("unknown_quota")
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)

    def test_result_validation_rejects_invalid_enums_mixed_cost_and_path_inconsistency(self):
        module = _load()
        result = module.estimate(
            _json("request-enhancement.json"), _json("prior-small.json"),
            _json("pricing-small.json"), _json("quota-small.json"),
        )
        invalid = copy.deepcopy(result)
        invalid["headline"]["scope"]["project_type"] = "invalid"
        with self.assertRaises(module.EstimationError):
            module.validate_result(invalid)
        invalid = copy.deepcopy(result)
        invalid["headline"]["api_equivalent_cost_current"]["known_microusd"]["p80"] = None
        with self.assertRaises(module.EstimationError):
            module.validate_result(invalid)
        invalid = copy.deepcopy(result)
        invalid["headline"]["critical_path"].append("not-a-phase")
        with self.assertRaises(module.EstimationError):
            module.validate_result(invalid)
        invalid = copy.deepcopy(result)
        invalid["detail"]["cohort"]["selected_node"] = "project_type.greenfield"
        with self.assertRaises(module.EstimationError):
            module.validate_result(invalid)

    def test_estimate_evidence_coverage_is_bound_to_cost_and_quota_detail(self):
        module = _load()
        result = module.estimate(
            _json("request-enhancement.json"), _json("prior-small.json"),
            _json("pricing-small.json"), _json("quota-small.json"),
        )
        forged = copy.deepcopy(result)
        forged["headline"]["evidence_coverage"]["quota_basis_points"] -= 1
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)
        forged = copy.deepcopy(result)
        forged["headline"]["evidence_coverage"]["pricing_basis_points"] -= 1
        with self.assertRaises(module.EstimationError):
            module.validate_result(forged)


if __name__ == "__main__":
    unittest.main()
