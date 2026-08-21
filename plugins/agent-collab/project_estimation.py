#!/usr/bin/env python3
"""Deterministic, offline public project estimator and reconciler.

This module is the single semantic authority for the public request, prior,
snapshot, actual-evidence, and result contracts.  It is standard-library only,
import safe, bounded, and performs no network, provider, secret, subprocess, or
project-discovery operation.
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import hashlib
import json
import math
import os
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Any


MAX_BYTES = 1_048_576
SIMULATION_COUNT = 2_048
BACKOFF_PENALTY_BASIS_POINTS = 1_000
UNKNOWN_QUOTA_FLOOR_BASIS_POINTS = 1_000
_MASK64 = (1 << 64) - 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_NODE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_VERSION = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_DATE = re.compile(r"^(?:(?:(?:000[1-9]|00[1-9][0-9]|0[1-9][0-9]{2}|[1-9][0-9]{3})-(?:(?:01|03|05|07|08|10|12)-(?:0[1-9]|[12][0-9]|3[01])|(?:04|06|09|11)-(?:0[1-9]|[12][0-9]|30)|02-(?:0[1-9]|1[0-9]|2[0-8])))|(?:(?:(?:(?!0000)[0-9]{2}(?:0[48]|[2468][048]|[13579][26]))|(?:0[48]|[2468][048]|[13579][26])00)-02-29))$")
_BOUNDARIES = ("planned", "source_present", "executed_unverified", "gate_verified", "merged", "released", "deployed", "operationally_verified")
_PHASE_PRIORS = {"primary", "delegation", "review", "test", "release", "deployment", "rework"}
_OWNERS = {"autonomous_agent", "operator", "vendor_external"}
_SCENARIOS = {"single", "mvp", "production_pilot", "full_production"}
_DELIVERY = {"reusable_core", "first_client", "subsequent_client", "project_specific"}
_REUSABLE = _DELIVERY | {"unknown"}
_REQUIREMENT = {"none", "standard", "high", "unknown"}
_QUOTA_KINDS = {"rpm", "tpm", "concurrency", "subscription_5_hour", "subscription_weekly", "subscription_monthly", "cooldown"}
_LABELS = {
    "api_equivalent": "not billed cash",
    "non_additivity": "current_execution_api_equivalent_and_actual_cash_are_non_additive",
}


class EstimationError(ValueError):
    """A fail-closed public input, computation, or filesystem error."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EstimationError("value is not finite JSON") from exc


def _mapping(value: object, field: str) -> dict[str, object]:
    if type(value) is not dict:
        raise EstimationError(f"{field} must be an object")
    return value


def _exact(value: object, fields: set[str], field: str, required: set[str] | None = None) -> dict[str, object]:
    row = _mapping(value, field)
    unknown = sorted(set(row) - fields)
    missing = sorted((fields if required is None else required) - set(row))
    if unknown:
        raise EstimationError(f"{field} has unknown field {unknown[0]}")
    if missing:
        raise EstimationError(f"{field} is missing field {missing[0]}")
    return row


def _integer(value: object, field: str, minimum: int = 0, maximum: int = 1_000_000_000_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise EstimationError(f"{field} must be an integer between {minimum} and {maximum}")
    return value


def _boolean(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise EstimationError(f"{field} must be boolean")
    return value


def _string(value: object, field: str, maximum: int = 512) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise EstimationError(f"{field} must be a bounded string")
    return value


def _enum(value: object, choices: set[str] | tuple[str, ...], field: str) -> str:
    if type(value) is not str or value not in choices:
        raise EstimationError(f"{field} is unsupported")
    return value


def _identifier(value: object, field: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise EstimationError(f"{field} must be a bounded identifier")
    return value


def _node(value: object, field: str) -> str:
    if type(value) is not str or _NODE.fullmatch(value) is None:
        raise EstimationError(f"{field} must be a bounded hierarchy node")
    return value


def _date(value: object, field: str) -> str:
    if type(value) is not str or _DATE.fullmatch(value) is None:
        raise EstimationError(f"{field} must be a canonical UTC date")
    try:
        if _datetime.date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as exc:
        raise EstimationError(f"{field} must be a canonical UTC date") from exc
    return value


def _nullable_date(value: object, field: str) -> str | None:
    return None if value is None else _date(value, field)


def _sha(value: object, field: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise EstimationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _nullable_sha(value: object, field: str) -> str | None:
    return None if value is None else _sha(value, field)


def _version(value: object, field: str) -> str:
    if type(value) is not str or _VERSION.fullmatch(value) is None:
        raise EstimationError(f"{field} must be a bounded version")
    return value


def _quantiles(value: object, field: str) -> dict[str, int]:
    row = _exact(value, {"p50", "p80", "p95"}, field)
    result = {name: _integer(row[name], f"{field}.{name}") for name in ("p50", "p80", "p95")}
    if not result["p50"] <= result["p80"] <= result["p95"]:
        raise EstimationError(f"{field} quantiles are unordered")
    return result


def _hours_quantiles(value: object, field: str) -> dict[str, str]:
    row = _exact(value, {"p50", "p80", "p95"}, field)
    for name in ("p50", "p80", "p95"):
        if type(row[name]) is not str or re.fullmatch(r"[0-9]+\.[0-9]{6}", row[name]) is None:
            raise EstimationError(f"{field}.{name} must be a fixed six-decimal hour string")
    return row  # type: ignore[return-value]


def _inert_strings(value: object, field: str) -> list[str]:
    if type(value) is not list or len(value) > 128:
        raise EstimationError(f"{field} must be a bounded array")
    return [_string(item, f"{field}[{index}]") for index, item in enumerate(value)]


def _validated_dag(phases: list[dict[str, object]], edges: object) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    if type(edges) is not list or len(edges) > 512:
        raise EstimationError("request.dependency_edges must be a bounded array")
    ids = {str(phase["id"]) for phase in phases}
    parents = {ident: [] for ident in ids}
    children = {ident: [] for ident in ids}
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(edges):
        edge = _exact(item, {"from", "to"}, f"request.dependency_edges[{index}]")
        source = _identifier(edge["from"], f"request.dependency_edges[{index}].from")
        target = _identifier(edge["to"], f"request.dependency_edges[{index}].to")
        if source not in ids or target not in ids:
            raise EstimationError("dependency edge references unknown phase")
        if source == target or (source, target) in seen:
            raise EstimationError("dependency edge is duplicate or self-referential")
        seen.add((source, target)); parents[target].append(source); children[source].append(target)
    counts = {key: len(value) for key, value in parents.items()}
    ready = sorted(key for key, count in counts.items() if count == 0)
    consumed = 0
    while ready:
        current = ready.pop(0); consumed += 1
        for child in sorted(children[current]):
            counts[child] -= 1
            if counts[child] == 0:
                ready.append(child); ready.sort()
    if consumed != len(ids):
        raise EstimationError("dependency graph contains cycle")
    return parents, children


def _scope_projection_validated(row: Mapping[str, object]) -> dict[str, object]:
    phases = []
    for phase in row["phases"]:
        projected = {key: phase[key] for key in ("id", "kind", "prior_phase", "owner", "scenario", "delivery_class", "effort_weight", "route_id", "external_wait_seconds") if key in phase}
        phases.append(projected)
    routes = []
    for route in row["routes"]:
        projected = {key: route[key] for key in ("id", "provider", "model", "modality", "tier", "token_share_basis_points")}
        if "quota_usage" in route:
            projected["quota_usage"] = sorted((dict(item) for item in route["quota_usage"]), key=lambda item: item["limit_kind"])
        routes.append(projected)
    return {
        "artifact_kind": row["artifact_kind"], "project_type": row["project_type"],
        "repository_class": row["repository_class"], "project_maturity": row["project_maturity"],
        "risk_tier": row["risk_tier"], "requested_completion_boundary": row["requested_completion_boundary"],
        "reusable_classification": row["reusable_classification"], "subsystem_count": row["subsystem_count"],
        "integration_count": row["integration_count"], "migration_burden": row["migration_burden"],
        "operator_gate_profile": row["operator_gate_profile"], "requirements": row["requirements"],
        "max_agent_concurrency": row["max_agent_concurrency"],
        "phases": sorted(phases, key=lambda item: item["id"]),
        "dependency_edges": sorted((dict(item) for item in row["dependency_edges"]), key=lambda item: (item["from"], item["to"])),
        "routes": sorted(routes, key=lambda item: item["id"]),
    }


def validate_request(value: object) -> dict[str, object]:
    fields = {"schema_version", "as_of_date", "artifact_kind", "invocation_source", "auto_invocation_depth", "project_type", "repository_class", "project_maturity", "risk_tier", "requested_completion_boundary", "reusable_classification", "subsystem_count", "integration_count", "migration_burden", "operator_gate_profile", "requirements", "max_agent_concurrency", "phases", "dependency_edges", "routes", "assumptions", "exclusions", "persistence_consent", "request_id", "artifact_scope_hash", "seed"}
    row = _exact(value, fields, "request", fields - {"request_id", "artifact_scope_hash", "seed"})
    if row["schema_version"] != 1:
        raise EstimationError("request.schema_version is unsupported")
    _date(row["as_of_date"], "request.as_of_date")
    _enum(row["artifact_kind"], {"standalone", "implementation_design", "implementation_plan"}, "request.artifact_kind")
    _enum(row["invocation_source"], {"explicit", "situational_auto", "composed_checkpoint"}, "request.invocation_source")
    if _integer(row["auto_invocation_depth"], "request.auto_invocation_depth", 0, 1) != 0:
        raise EstimationError("recursive_invocation")
    _enum(row["project_type"], {"greenfield", "enhancement"}, "request.project_type")
    _enum(row["repository_class"], {"workspace", "plugin", "project_local", "unknown"}, "request.repository_class")
    _enum(row["project_maturity"], {"new", "established", "legacy", "unknown"}, "request.project_maturity")
    _enum(row["risk_tier"], {"low", "medium", "high", "critical", "unknown"}, "request.risk_tier")
    _enum(row["requested_completion_boundary"], _BOUNDARIES, "request.requested_completion_boundary")
    _enum(row["reusable_classification"], _REUSABLE, "request.reusable_classification")
    _integer(row["subsystem_count"], "request.subsystem_count", 0, 128)
    _integer(row["integration_count"], "request.integration_count", 0, 512)
    _enum(row["migration_burden"], {"none", "low", "medium", "high", "unknown"}, "request.migration_burden")
    _enum(row["operator_gate_profile"], {"none", "single", "multiple", "unknown"}, "request.operator_gate_profile")
    requirements = _exact(row["requirements"], {"security_privacy", "reliability_load", "observability", "documentation", "ci_cd", "rollout_rollback", "evaluation"}, "request.requirements")
    for name, setting in requirements.items():
        _enum(setting, _REQUIREMENT, f"request.requirements.{name}")
    _integer(row["max_agent_concurrency"], "request.max_agent_concurrency", 1, 32)
    _inert_strings(row["assumptions"], "request.assumptions"); _inert_strings(row["exclusions"], "request.exclusions")
    _boolean(row["persistence_consent"], "request.persistence_consent")
    if "request_id" in row: _identifier(row["request_id"], "request.request_id")
    if "seed" in row: _integer(row["seed"], "request.seed", 0, 2_147_483_647)
    if type(row["phases"]) is not list or len(row["phases"]) > 128:
        raise EstimationError("request.phases must be a bounded array")
    phases: list[dict[str, object]] = []
    phase_ids: set[str] = set(); route_refs: set[str] = set()
    phase_fields = {"id", "kind", "prior_phase", "owner", "scenario", "delivery_class", "effort_weight", "route_id", "external_wait_seconds"}
    phase_required = {"id", "kind", "prior_phase", "owner", "scenario", "delivery_class", "effort_weight"}
    for index, item in enumerate(row["phases"]):
        phase = _exact(item, phase_fields, f"request.phases[{index}]", phase_required)
        ident = _identifier(phase["id"], f"request.phases[{index}].id")
        if ident in phase_ids: raise EstimationError("request phase ids must be unique")
        phase_ids.add(ident); phases.append(phase)
        _identifier(phase["kind"], f"request.phases[{index}].kind")
        _enum(phase["prior_phase"], _PHASE_PRIORS, f"request.phases[{index}].prior_phase")
        owner = _enum(phase["owner"], _OWNERS, f"request.phases[{index}].owner")
        _enum(phase["scenario"], _SCENARIOS, f"request.phases[{index}].scenario")
        _enum(phase["delivery_class"], _DELIVERY, f"request.phases[{index}].delivery_class")
        _integer(phase["effort_weight"], f"request.phases[{index}].effort_weight", 1, 100)
        if "route_id" in phase:
            if owner != "autonomous_agent": raise EstimationError("external phase may not use an agent route")
            route_refs.add(_identifier(phase["route_id"], f"request.phases[{index}].route_id"))
        if owner == "autonomous_agent":
            if "external_wait_seconds" in phase: raise EstimationError("autonomous phase may not have external wait")
        elif "external_wait_seconds" not in phase:
            raise EstimationError("operator/vendor phase requires external wait")
        else:
            _quantiles(phase["external_wait_seconds"], f"request.phases[{index}].external_wait_seconds")
    _validated_dag(phases, row["dependency_edges"])
    if type(row["routes"]) is not list or len(row["routes"]) > 32:
        raise EstimationError("request.routes must be a bounded array")
    route_ids: set[str] = set(); shares = 0
    route_fields = {"id", "provider", "model", "modality", "tier", "token_share_basis_points", "quota_usage"}
    for index, item in enumerate(row["routes"]):
        route = _exact(item, route_fields, f"request.routes[{index}]", route_fields - {"quota_usage"})
        ident = _identifier(route["id"], f"request.routes[{index}].id")
        if ident in route_ids: raise EstimationError("route ids must be unique")
        route_ids.add(ident)
        for name in ("provider", "model", "modality", "tier"): _identifier(route[name], f"request.routes[{index}].{name}")
        shares += _integer(route["token_share_basis_points"], f"request.routes[{index}].token_share_basis_points", 0, 10_000)
        usage = route.get("quota_usage", [])
        if type(usage) is not list or len(usage) > 16: raise EstimationError("route quota usage is invalid")
        kinds: set[str] = set()
        for usage_index, item2 in enumerate(usage):
            usage_row = _exact(item2, {"limit_kind", "quantity"}, f"request.routes[{index}].quota_usage[{usage_index}]")
            kind = _enum(usage_row["limit_kind"], _QUOTA_KINDS, f"request.routes[{index}].quota_usage[{usage_index}].limit_kind")
            if kind in kinds: raise EstimationError("route quota limit kinds must be unique")
            kinds.add(kind); _integer(usage_row["quantity"], f"request.routes[{index}].quota_usage[{usage_index}].quantity")
    if row["routes"] and shares != 10_000: raise EstimationError("route token shares must total 10000")
    if not route_refs <= route_ids: raise EstimationError("phase references unknown route")
    if "artifact_scope_hash" in row:
        supplied = _sha(row["artifact_scope_hash"], "request.artifact_scope_hash")
        computed = hashlib.sha256(_canonical(_scope_projection_validated(row))).hexdigest()
        if supplied != computed: raise EstimationError("artifact_scope_hash does not match request")
    return row


def scope_projection(request: Mapping[str, object]) -> dict[str, object]:
    return _scope_projection_validated(validate_request(request))


def artifact_scope_hash(request: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical(scope_projection(request))).hexdigest()


def _quantile_family(value: object, field: str, identity: str, choices: set[str] | None = None) -> None:
    if type(value) is not list or len(value) > 10_000: raise EstimationError(f"{field} must be a bounded array")
    seen: set[str] = set()
    for index, item in enumerate(value):
        row = _exact(item, {identity, "p50", "p80", "p95"}, f"{field}[{index}]")
        ident = _identifier(row[identity], f"{field}[{index}].{identity}")
        if choices is not None and ident not in choices: raise EstimationError(f"{field} contains an unsupported identity")
        if ident in seen: raise EstimationError(f"{field} identities must be unique")
        seen.add(ident)
        quantiles = _quantiles({name: row[name] for name in ("p50", "p80", "p95")}, f"{field}[{index}]")
        if any(number > 1_000_000_000 for number in quantiles.values()):
            raise EstimationError(f"{field}[{index}] exceeds the public aggregate bound")


def validate_aggregate(value: object) -> dict[str, object]:
    fields = {"schema_version", "estimator_method_version", "generated_date", "source_cutoff_date", "policy_version", "policy_sha256", "seed", "source_manifest_sha256", "nodes"}
    row = _exact(value, fields, "aggregate-prior")
    if row["schema_version"] != 1 or row["estimator_method_version"] != "empirical-v2": raise EstimationError("aggregate-prior version is unsupported")
    generated = _date(row["generated_date"], "aggregate.generated_date"); cutoff = _date(row["source_cutoff_date"], "aggregate.source_cutoff_date")
    if cutoff > generated: raise EstimationError("aggregate source cutoff follows generated date")
    _version(row["policy_version"], "aggregate.policy_version"); _sha(row["policy_sha256"], "aggregate.policy_sha256")
    _integer(row["seed"], "aggregate.seed", 0, 2_147_483_647); _sha(row["source_manifest_sha256"], "aggregate.source_manifest_sha256")
    if type(row["nodes"]) is not list or not row["nodes"] or len(row["nodes"]) > 10_000: raise EstimationError("aggregate nodes are invalid")
    allowed = {"schema_version", "estimator_method_version", "generated_date", "source_cutoff_date", "hierarchy_node", "fallback_parent", "sample_count", "effective_sample_size", "aggregate_sha256", "release_manifest_sha256", "source_eras", "phase_duration_quantiles", "token_class_quantiles", "rework_review_quantiles", "wait_class_quantiles", "calibration_quality", "drift_indicators", "uncertainty_floors", "pricing_snapshot"}
    required = {"schema_version", "estimator_method_version", "generated_date", "source_cutoff_date", "hierarchy_node", "sample_count", "effective_sample_size", "aggregate_sha256", "release_manifest_sha256"}
    names: list[str] = []; parents: dict[str, str | None] = {}
    metric_fields = {"calibration_quality": {"holdout_count", "p80_coverage_basis_points", "p95_coverage_basis_points"}, "drift_indicators": {"duration_drift_basis_points", "token_drift_basis_points"}, "uncertainty_floors": {"duration_basis_points", "token_basis_points"}}
    for index, item in enumerate(row["nodes"]):
        node_row = _exact(item, allowed, f"aggregate.nodes[{index}]", required)
        if node_row["schema_version"] != 1 or node_row["estimator_method_version"] != "empirical-v2": raise EstimationError("aggregate node version is unsupported")
        if _date(node_row["generated_date"], "aggregate.node.generated_date") != generated or _date(node_row["source_cutoff_date"], "aggregate.node.source_cutoff_date") != cutoff: raise EstimationError("aggregate node dates do not match aggregate")
        name = _node(node_row["hierarchy_node"], "aggregate.hierarchy_node")
        names.append(name); parent = node_row.get("fallback_parent")
        parents[name] = None if parent is None else _node(parent, "aggregate.fallback_parent")
        _integer(node_row["sample_count"], "aggregate.sample_count", 20, 1_000_000_000); _integer(node_row["effective_sample_size"], "aggregate.effective_sample_size", 0, 1_000_000_000)
        _sha(node_row["aggregate_sha256"], "aggregate.aggregate_sha256"); _sha(node_row["release_manifest_sha256"], "aggregate.release_manifest_sha256")
        if "source_eras" in node_row:
            if type(node_row["source_eras"]) is not list or len(node_row["source_eras"]) > 10_000: raise EstimationError("aggregate.source_eras is invalid")
            for era in node_row["source_eras"]: _version(era, "aggregate.source_era")
        families = (("phase_duration_quantiles", "phase", _PHASE_PRIORS | {"overall"}), ("token_class_quantiles", "token_class", None), ("rework_review_quantiles", "kind", {"review", "rework"}), ("wait_class_quantiles", "wait_class", None))
        for field, identity, choices in families:
            if field in node_row: _quantile_family(node_row[field], f"aggregate.{field}", identity, choices)
        for field, permitted in metric_fields.items():
            if field in node_row:
                metric = _exact(node_row[field], permitted, f"aggregate.{field}", set(node_row[field]))
                for key, number in metric.items(): _integer(number, f"aggregate.{field}.{key}", 0, 1_000_000_000)
        if "pricing_snapshot" in node_row:
            nested = _exact(node_row["pricing_snapshot"], {"sha256", "retrieved_date", "status"}, "aggregate.pricing_snapshot")
            _sha(nested["sha256"], "aggregate.pricing_snapshot.sha256"); _date(nested["retrieved_date"], "aggregate.pricing_snapshot.retrieved_date")
            _enum(nested["status"], {"official", "estimated_stale", "unpriced"}, "aggregate.pricing_snapshot.status")
    if names != sorted(names) or len(names) != len(set(names)): raise EstimationError("aggregate hierarchy nodes must be sorted and unique")
    roots = [name for name, parent in parents.items() if parent is None]
    if not roots: raise EstimationError("aggregate requires a fallback root")
    for root in roots:
        if root not in {"project_type.greenfield", "project_type.enhancement"}: raise EstimationError("aggregate fallback root is unsupported")
    for name, parent in parents.items():
        if parent is not None and parent not in parents: raise EstimationError("aggregate fallback parent is absent")
        seen: set[str] = set(); current: str | None = name
        while current is not None:
            if current in seen: raise EstimationError("aggregate fallback cycle detected")
            seen.add(current); current = parents[current]
    return row


def _record(value: object, kind: str, field: str) -> dict[str, object]:
    common = {"record_id", "model", "modality", "tier", "modifiers", "approved_value_sha256"}
    extra = {"token_class", "currency", "unit", "amount_microusd", "amount_text"} if kind == "pricing" else {"limit_kind", "limit_value", "window_seconds", "cooldown_seconds"}
    row = _exact(value, common | extra, field)
    for name in ("record_id", "model", "modality", "tier"): _identifier(row[name], f"{field}.{name}")
    if type(row["modifiers"]) is not list or len(row["modifiers"]) > 100: raise EstimationError(f"{field}.modifiers is invalid")
    for index, modifier in enumerate(row["modifiers"]): _string(modifier, f"{field}.modifiers[{index}]", 128)
    if kind == "pricing":
        _identifier(row["token_class"], f"{field}.token_class"); _enum(row["currency"], {"USD"}, f"{field}.currency")
        _enum(row["unit"], {"per_million_tokens"}, f"{field}.unit"); _integer(row["amount_microusd"], f"{field}.amount_microusd")
        _string(row["amount_text"], f"{field}.amount_text", 128)
    else:
        kind2 = _enum(row["limit_kind"], _QUOTA_KINDS, f"{field}.limit_kind")
        _integer(row["limit_value"], f"{field}.limit_value")
        if row["window_seconds"] is not None: _integer(row["window_seconds"], f"{field}.window_seconds", 1)
        _integer(row["cooldown_seconds"], f"{field}.cooldown_seconds")
        expected = {"subscription_5_hour": 18_000, "subscription_weekly": 604_800, "subscription_monthly": 2_592_000}
        if kind2 in expected and row["window_seconds"] != expected[kind2]: raise EstimationError(f"{field}.window_seconds does not match subscription window")
        if kind2 in {"rpm", "tpm"} and row["window_seconds"] != 60: raise EstimationError(f"{field}.window_seconds must be 60")
        if kind2 == "concurrency" and row["window_seconds"] is not None: raise EstimationError(f"{field}.window_seconds must be null")
        if kind2 == "cooldown" and row["cooldown_seconds"] <= 0: raise EstimationError(f"{field}.cooldown_seconds must be positive")
    expected_digest = hashlib.sha256(_canonical({key: item for key, item in row.items() if key != "approved_value_sha256"})).hexdigest()
    if _sha(row["approved_value_sha256"], f"{field}.approved_value_sha256") != expected_digest: raise EstimationError(f"{field}.approved_value_sha256 does not match record")
    return row


def _validate_snapshot(value: object, kind: str) -> dict[str, object]:
    fields = {"schema_version", "kind", "policy_version", "policy_sha256", "retrieved_date", "providers", "operator_notification_required", "material_unpriced", "uncertainty_basis_points"}
    row = _exact(value, fields, f"{kind}-snapshot")
    if row["schema_version"] != 1 or row["kind"] != kind: raise EstimationError(f"{kind} snapshot version is unsupported")
    _version(row["policy_version"], f"{kind}.policy_version"); _sha(row["policy_sha256"], f"{kind}.policy_sha256"); retrieved = _date(row["retrieved_date"], f"{kind}.retrieved_date")
    notification = _boolean(row["operator_notification_required"], f"{kind}.operator_notification_required")
    material = _boolean(row["material_unpriced"], f"{kind}.material_unpriced")
    uncertainty = _integer(row["uncertainty_basis_points"], f"{kind}.uncertainty_basis_points", 0, 10_000)
    providers = _mapping(row["providers"], f"{kind}.providers")
    if not providers or len(providers) > 100: raise EstimationError(f"{kind} providers are invalid")
    provider_fields = {"provider", "status", "retrieved_date", "last_successful_official_date", "original_last_good_date", "values", "value_sha256", "source_url_sha256", "final_url_sha256", "redirect_chain_sha256", "content_type", "elapsed_class", "failure_class", "material_share_basis_points"}
    unresolved = False; unresolved_share = 0; total_share = 0
    for provider_name, item in sorted(providers.items()):
        _identifier(provider_name, f"{kind}.provider-name")
        provider = _exact(item, provider_fields, f"{kind}.providers.{provider_name}")
        if provider["provider"] != provider_name: raise EstimationError(f"{kind} provider identity is invalid")
        statuses = {"official", "estimated_stale", "review_required", "unpriced"} | ({"unknown"} if kind == "quota" else set())
        status = _enum(provider["status"], statuses, f"{kind}.{provider_name}.status")
        dates = {name: _nullable_date(provider[name], f"{kind}.{provider_name}.{name}") for name in ("retrieved_date", "last_successful_official_date", "original_last_good_date")}
        if any(date is not None and date > retrieved for date in dates.values()): raise EstimationError(f"{kind}.{provider_name} evidence date follows snapshot")
        values = provider["values"]
        if type(values) is not list or len(values) > 10_000: raise EstimationError(f"{kind}.{provider_name}.values is invalid")
        ids: set[str] = set()
        for index, record in enumerate(values):
            parsed = _record(record, kind, f"{kind}.{provider_name}.values[{index}]")
            ident = str(parsed["record_id"])
            if ident in ids: raise EstimationError(f"{kind}.{provider_name} record identities must be unique")
            ids.add(ident)
        value_hash = _nullable_sha(provider["value_sha256"], f"{kind}.{provider_name}.value_sha256")
        if values and value_hash != hashlib.sha256(_canonical(values)).hexdigest(): raise EstimationError(f"{kind}.{provider_name}.value_sha256 is incorrect")
        if not values and value_hash is not None: raise EstimationError(f"{kind}.{provider_name}.empty values must have null hash")
        provenance = [provider[name] for name in ("source_url_sha256", "final_url_sha256", "redirect_chain_sha256")]
        for index, digest in enumerate(provenance): _nullable_sha(digest, f"{kind}.{provider_name}.provenance[{index}]")
        for name in ("content_type", "elapsed_class", "failure_class"):
            if provider[name] is not None: _string(provider[name], f"{kind}.{provider_name}.{name}", 128)
        share = _integer(provider["material_share_basis_points"], f"{kind}.{provider_name}.material_share_basis_points", 0, 10_000)
        total_share += share
        if status == "official":
            if not values or dates["retrieved_date"] != retrieved or dates["last_successful_official_date"] != retrieved or dates["original_last_good_date"] is not None or provider["failure_class"] is not None or any(item2 is None for item2 in (*provenance, provider["content_type"], provider["elapsed_class"])):
                raise EstimationError(f"{kind}.{provider_name} official evidence is incomplete")
        elif status == "estimated_stale":
            if not values or dates["retrieved_date"] is None or dates["last_successful_official_date"] is None or dates["original_last_good_date"] != dates["last_successful_official_date"] or provider["failure_class"] is None or any(item2 is None for item2 in (*provenance, provider["content_type"], provider["elapsed_class"])):
                raise EstimationError(f"{kind}.{provider_name} stale evidence is incomplete")
            unresolved = True
        else:
            if values or any(value2 is not None for value2 in dates.values()) or provider["failure_class"] is None or any(item2 is not None for item2 in (*provenance, provider["content_type"], provider["elapsed_class"])):
                raise EstimationError(f"{kind}.{provider_name} unresolved evidence is inconsistent")
            unresolved = True; unresolved_share += share
    if kind == "pricing" and total_share != 10_000: raise EstimationError("pricing material shares must total 10000")
    if notification is not unresolved or ((uncertainty > 0) is not unresolved): raise EstimationError(f"{kind} notification or uncertainty flags are inconsistent")
    # ``material_unpriced`` is a release-policy conclusion.  The public
    # validator proves its exact type, while the maintenance verifier applies
    # the release's configured materiality threshold.
    del material, unresolved_share
    return row


def validate_pricing(value: object) -> dict[str, object]: return _validate_snapshot(value, "pricing")
def validate_quota(value: object) -> dict[str, object]: return _validate_snapshot(value, "quota")


def validate_actual(value: object) -> dict[str, object]:
    fields = {"schema_version", "completion_boundary", "focused_agent_wall_clock_seconds", "calendar_elapsed_seconds", "summed_agent_runtime_seconds", "token_usage", "wait_decomposition", "actual_marginal_cash", "execution_era_pricing", "persistence_consent"}
    row = _exact(value, fields, "actual", fields - {"execution_era_pricing"})
    if row["schema_version"] != 1: raise EstimationError("actual.schema_version is unsupported")
    _enum(row["completion_boundary"], _BOUNDARIES, "actual.completion_boundary")
    for name in ("focused_agent_wall_clock_seconds", "calendar_elapsed_seconds", "summed_agent_runtime_seconds"): _integer(row[name], f"actual.{name}")
    if row["focused_agent_wall_clock_seconds"] > row["summed_agent_runtime_seconds"]: raise EstimationError("actual focused time exceeds summed runtime")
    if type(row["token_usage"]) is not list or len(row["token_usage"]) > 4096: raise EstimationError("actual.token_usage is invalid")
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(row["token_usage"]):
        token = _exact(item, {"route_id", "token_class", "quantity"}, f"actual.token_usage[{index}]")
        identity = (_identifier(token["route_id"], "actual.route_id"), _identifier(token["token_class"], "actual.token_class"))
        if identity in seen: raise EstimationError("actual token identities must be unique")
        seen.add(identity); _integer(token["quantity"], "actual.token.quantity")
    waits = _exact(row["wait_decomposition"], {"operator_seconds", "vendor_seconds", "quota_seconds"}, "actual.wait_decomposition")
    for name, amount in waits.items(): _integer(amount, f"actual.wait_decomposition.{name}")
    cash = _exact(row["actual_marginal_cash"], {"status", "amount_microusd", "evidence_sha256"}, "actual.actual_marginal_cash", {"status"})
    status = _enum(cash["status"], {"authoritative", "operator_supplied", "subscription_zero", "unknown"}, "actual.actual_marginal_cash.status")
    if status in {"authoritative", "operator_supplied", "subscription_zero"}:
        amount = _integer(cash.get("amount_microusd"), "actual.actual_marginal_cash.amount_microusd")
        _sha(cash.get("evidence_sha256"), "actual.actual_marginal_cash.evidence_sha256")
        if status == "subscription_zero" and amount != 0: raise EstimationError("subscription_zero cash must be zero")
    elif set(cash) != {"status"}:
        raise EstimationError("unknown actual cash may not carry amount or evidence")
    if "execution_era_pricing" in row: validate_pricing(row["execution_era_pricing"])
    _boolean(row["persistence_consent"], "actual.persistence_consent")
    return row


def _band(value: object, *, zero: str, low: int, high: int) -> str:
    number = value if type(value) is int and value >= 0 else 0
    if number == 0: return zero
    if number <= low: return "low"
    if number <= high: return "medium"
    return "high"


def _hierarchy_names(request: Mapping[str, object]) -> list[str]:
    project_type = request.get("project_type")
    if type(project_type) is not str: return []
    routes = request.get("routes", [])
    providers = {str(route.get("provider")) for route in routes if isinstance(route, Mapping)} if isinstance(routes, list) else set()
    values = [
        ("cb", request.get("requested_completion_boundary", "unknown")),
        ("rc", request.get("repository_class", "unknown")),
        ("pm", request.get("project_maturity", "unknown")),
        ("si", f"{_band(request.get('subsystem_count'), zero='s0', low=2, high=5)}-{_band(len(request.get('dependency_edges', [])) if isinstance(request.get('dependency_edges'), list) else 0, zero='i0', low=2, high=5)}"),
        ("risk", request.get("risk_tier", "unknown")),
        ("burden", "reviewed" if request.get("risk_tier") in {"high", "critical"} else "ordinary"),
        ("ep", f"{_band(len(providers), zero='e0', low=2, high=5)}-{request.get('operator_gate_profile', 'unknown')}"),
        ("orch", "multi" if isinstance(routes, list) and len(routes) > 1 else "single"),
    ]
    root = f"project_type.{project_type}"; names = [root]; cumulative: list[tuple[str, str]] = [("project_type", project_type)]
    for depth, (field, raw) in enumerate(values, 2):
        safe = re.sub(r"[^A-Za-z0-9_-]", "-", str(raw))[:24] or "unknown"
        cumulative.append((field, safe))
        identity = hashlib.sha256(_canonical([[key, item] for key, item in cumulative])).hexdigest()[:16]
        names.append(f"h{depth}.{identity}.{field}-{safe}")
    return names


def _resolve_hierarchy(request: Mapping[str, object], prior: Mapping[str, object]) -> tuple[dict[str, object], list[str], list[str], int] | None:
    nodes = {str(item["hierarchy_node"]): item for item in prior["nodes"]}
    expected = _hierarchy_names(request); root = expected[0]
    selected_index = next((index for index in range(len(expected) - 1, -1, -1) if expected[index] in nodes), None)
    if selected_index is None: return None
    selected = expected[selected_index]; path = [selected]
    while nodes[path[-1]].get("fallback_parent") is not None:
        parent = str(nodes[path[-1]]["fallback_parent"])
        if parent in path or parent not in nodes: raise EstimationError("aggregate fallback chain is invalid")
        path.append(parent)
    if path[-1] != root: return None
    missing_levels = len(expected) - 1 - selected_index
    return nodes[selected], path, expected, missing_levels


def _splitmix64(value: int) -> int:
    value = (value + 0x9E3779B97F4A7C15) & _MASK64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK64
    return (value ^ (value >> 31)) & _MASK64


def _draw(seed: int, stream: str, index: int) -> int:
    key = int.from_bytes(hashlib.sha256(f"{seed}:{stream}".encode()).digest()[:8], "big")
    return _splitmix64((key + index) & _MASK64)


def _sample(q: Mapping[str, int], index: int, seed: int, stream: str) -> int:
    draw = _draw(seed, stream, index) % 10_000
    return int(q["p50"] if draw < 5_000 else q["p80"] if draw < 8_000 else q["p95"])


def _nearest(values: Sequence[int], percentile: int) -> int:
    if not values: raise EstimationError("cannot take a quantile of an empty sequence")
    return sorted(values)[max(0, math.ceil(len(values) * percentile / 100) - 1)]


def _q(values: Sequence[int]) -> dict[str, int]:
    return {name: _nearest(values, percentile) for name, percentile in (("p50", 50), ("p80", 80), ("p95", 95))}


def _hours(seconds: int) -> str:
    quotient, remainder = divmod(seconds * 1_000_000, 3600)
    if remainder * 2 >= 3600: quotient += 1
    return f"{quotient // 1_000_000}.{quotient % 1_000_000:06d}"


def _hours_q(seconds: Mapping[str, int]) -> dict[str, str]: return {name: _hours(int(seconds[name])) for name in ("p50", "p80", "p95")}


def _largest_remainder(total: int, weights: Sequence[tuple[str, int]]) -> dict[str, int]:
    if total < 0 or not weights: return {key: 0 for key, _ in weights}
    denominator = sum(max(0, weight) for _, weight in weights)
    if denominator <= 0: weights = [(key, 1) for key, _ in weights]; denominator = len(weights)
    result: dict[str, int] = {}; remainders: list[tuple[int, str]] = []
    for key, weight in weights:
        numerator = total * max(0, weight); result[key] = numerator // denominator; remainders.append((numerator % denominator, key))
    for _, key in sorted(remainders, key=lambda item: (-item[0], item[1]))[: total - sum(result.values())]: result[key] += 1
    return result


def _allocated_durations(phases: list[dict[str, object]], rows: Mapping[str, Mapping[str, int]], overall: Mapping[str, int], index: int, seed: int) -> tuple[dict[str, int], int, bool]:
    autonomous = [phase for phase in phases if phase["owner"] == "autonomous_agent"]
    total = _sample(overall, index, seed, "duration:overall")
    if all(str(phase["prior_phase"]) in rows for phase in autonomous):
        direct = {str(phase["id"]): _sample(rows[str(phase["prior_phase"])], index, seed, f"duration:{phase['id']}") for phase in autonomous}
        return direct, sum(direct.values()), False
    known_units = [int(rows[str(phase["prior_phase"])]["p50"]) // int(phase["effort_weight"]) for phase in autonomous if str(phase["prior_phase"]) in rows]
    fallback_unit = sum(known_units) // len(known_units) if known_units else max(1, int(overall["p50"]) // max(1, sum(int(phase["effort_weight"]) for phase in autonomous)))
    weights = []
    for phase in autonomous:
        weight = int(rows[str(phase["prior_phase"])]["p50"]) if str(phase["prior_phase"]) in rows else fallback_unit * int(phase["effort_weight"])
        weights.append((str(phase["id"]), max(1, weight)))
    return _largest_remainder(total, weights), total, True


@dataclass(frozen=True)
class _Schedule:
    focused: int
    runtime: int
    makespan: int
    starts: dict[str, int]
    ends: dict[str, int]
    dag_predecessors: dict[str, str | None]
    resource_predecessors: dict[str, str | None]
    critical_path: list[str]


def _schedule(request: Mapping[str, object], durations: Mapping[str, int], worker_cap: int) -> _Schedule:
    phases = {str(item["id"]): item for item in request["phases"]}
    parents = {key: [] for key in phases}
    for edge in request["dependency_edges"]: parents[str(edge["to"])].append(str(edge["from"]))
    starts: dict[str, int] = {}; ends: dict[str, int] = {}; dominant: dict[str, str | None] = {}
    dag_predecessors: dict[str, str | None] = {}; resource_predecessors: dict[str, str | None] = {}
    slots = [(0, None) for _ in range(worker_cap)]; remaining = set(phases)
    while remaining:
        ready = sorted(key for key in remaining if all(parent in ends for parent in parents[key]))
        if not ready: raise EstimationError("dependency graph contains cycle")
        for ident in ready:
            phase = phases[ident]
            dag_parent = max(parents[ident], key=lambda key: (ends[key], key)) if parents[ident] else None
            dag_predecessors[ident] = dag_parent
            dag_ready = ends[dag_parent] if dag_parent is not None else 0
            if phase["owner"] == "autonomous_agent":
                slot_index = min(range(worker_cap), key=lambda idx: (slots[idx][0], idx))
                slot_ready, slot_parent = slots[slot_index]
                resource_predecessors[ident] = slot_parent
                start = max(dag_ready, slot_ready)
                dominant[ident] = dag_parent if dag_ready >= slot_ready else slot_parent
                slots[slot_index] = (start + int(durations[ident]), ident)
            else:
                resource_predecessors[ident] = None; start = dag_ready; dominant[ident] = dag_parent
            starts[ident] = start; ends[ident] = start + int(durations[ident]); remaining.remove(ident)
    intervals = sorted((starts[key], ends[key]) for key, phase in phases.items() if phase["owner"] == "autonomous_agent" and ends[key] > starts[key])
    focused = 0
    if intervals:
        left, right = intervals[0]
        for start, end in intervals[1:]:
            if start <= right: right = max(right, end)
            else: focused += right - left; left, right = start, end
        focused += right - left
    runtime = sum(ends[key] - starts[key] for key, phase in phases.items() if phase["owner"] == "autonomous_agent")
    terminal = max(ends, key=lambda key: (ends[key], key)); path: list[str] = []
    current: str | None = terminal
    while current is not None:
        path.append(current); current = dominant[current]
    path.reverse()
    return _Schedule(focused, runtime, max(ends.values(), default=0), starts, ends, dag_predecessors, resource_predecessors, path)


def _price_index(pricing: Mapping[str, object]) -> dict[tuple[str, str, str, str, str], int | None]:
    index: dict[tuple[str, str, str, str, str], int | None] = {}
    for provider_name, provider in pricing["providers"].items():
        if provider["status"] not in {"official", "estimated_stale"}: continue
        for record in provider["values"]:
            key = (provider_name, str(record["model"]), str(record["modality"]), str(record["tier"]), str(record["token_class"]))
            index[key] = None if key in index else int(record["amount_microusd"])
    return index


def _quota_cap(request: Mapping[str, object], quota: Mapping[str, object]) -> int:
    cap = int(request["max_agent_concurrency"])
    for route in request["routes"]:
        provider = quota["providers"].get(route["provider"])
        if not provider or provider["status"] not in {"official", "estimated_stale"}: continue
        candidates = [record for record in provider["values"] if (record["model"], record["modality"], record["tier"], record["limit_kind"]) == (route["model"], route["modality"], route["tier"], "concurrency")]
        if len(candidates) == 1 and int(candidates[0]["limit_value"]) > 0:
            cap = min(cap, int(candidates[0]["limit_value"]))
    return max(1, cap)


def _quota_analysis(request: Mapping[str, object], quota: Mapping[str, object], route_tokens: Mapping[str, int]) -> tuple[int, int, list[dict[str, object]]]:
    provider_delays: dict[str, int] = {}; covered_share = 0; rows: list[dict[str, object]] = []
    for route in request["routes"]:
        provider = quota["providers"].get(route["provider"])
        resolved = bool(provider and provider["status"] in {"official", "estimated_stale"})
        records = provider["values"] if resolved else []
        grouped: dict[str, list[Mapping[str, object]]] = {}
        for item in records:
            if (item["model"], item["modality"], item["tier"]) == (route["model"], route["modality"], route["tier"]):
                grouped.setdefault(str(item["limit_kind"]), []).append(item)
        matches = {kind: items[0] for kind, items in grouped.items() if len(items) == 1}
        delay = 0; complete = resolved
        token_quantity = int(route_tokens.get(str(route["id"]), 0))
        tpm = matches.get("tpm")
        if token_quantity:
            if tpm is None or int(tpm["limit_value"]) <= 0: complete = False
            else: delay += max(0, math.ceil(token_quantity / int(tpm["limit_value"])) - 1) * 60
        for usage in route.get("quota_usage", []):
            kind = str(usage["limit_kind"])
            if kind in {"tpm", "concurrency"}: continue
            record = matches.get(kind); quantity = int(usage["quantity"])
            if record is None or int(record["limit_value"]) <= 0:
                complete = False; continue
            limit = int(record["limit_value"])
            if kind.startswith("subscription_"):
                excess_windows = max(0, math.ceil(quantity / limit) - 1)
                delay += excess_windows * (int(record["window_seconds"]) + int(record["cooldown_seconds"]))
            elif kind == "rpm":
                delay += max(0, math.ceil(quantity / limit) - 1) * int(record["window_seconds"])
            elif kind == "cooldown":
                delay += max(0, quantity - limit) * int(record["cooldown_seconds"])
        if complete: covered_share += int(route["token_share_basis_points"])
        provider_delays[str(route["provider"])] = provider_delays.get(str(route["provider"]), 0) + delay
        rows.append({"route_id": route["id"], "provider": route["provider"], "delay_seconds": delay, "coverage": "known" if complete else "unknown"})
    return max(provider_delays.values(), default=0), min(10_000, covered_share), rows


def _widen(value: int, basis_points: int) -> int:
    return (value * (10_000 + max(0, basis_points)) + 9_999) // 10_000


def _split_rows(phases: Sequence[Mapping[str, object]], phase_samples: Mapping[str, Sequence[int]], field: str) -> list[dict[str, object]]:
    categories = sorted({str(phase[field]) for phase in phases})
    output = []
    for category in categories:
        ids = [str(phase["id"]) for phase in phases if str(phase[field]) == category]
        values = [sum(int(phase_samples[ident][index]) for ident in ids) for index in range(SIMULATION_COUNT)]
        output.append({"name": category, "duration_seconds": _q(values)})
    return output


def _identities(request: Mapping[str, object], prior: Mapping[str, object], pricing: Mapping[str, object], quota: Mapping[str, object]) -> dict[str, object]:
    return {"schema_version": 1, "result_kind": "estimate", "estimator_method_version": "empirical-sim-v1", "scope_hash": artifact_scope_hash(request), "prior_sha256": hashlib.sha256(_canonical(prior)).hexdigest(), "pricing_sha256": hashlib.sha256(_canonical(pricing)).hexdigest(), "quota_sha256": hashlib.sha256(_canonical(quota)).hexdigest(), "seed": request.get("seed", prior["seed"]), "simulation_count": SIMULATION_COUNT, "generated_date": request["as_of_date"], "source_cutoff_date": prior["source_cutoff_date"]}


def estimate(request: Mapping[str, object], prior: Mapping[str, object], pricing: Mapping[str, object], quota: Mapping[str, object]) -> dict[str, object]:
    request2 = validate_request(request); prior2 = validate_aggregate(prior); pricing2 = validate_pricing(pricing); quota2 = validate_quota(quota)
    if any(provider["status"] == "review_required" for provider in pricing2["providers"].values()): raise EstimationError("pricing contains review_required evidence")
    identities = _identities(request2, prior2, pricing2, quota2)
    if not request2["phases"]:
        result = {**identities, "estimate_unavailable": "insufficient_scope", "labels": dict(_LABELS)}
        return validate_result(result)
    resolution = _resolve_hierarchy(request2, prior2)
    if resolution is None:
        result = {**identities, "estimate_unavailable": "no_compatible_prior", "labels": dict(_LABELS)}
        return validate_result(result)
    node, path, expected_path, missing_levels = resolution
    duration_rows = {str(item["phase"]): {name: int(item[name]) for name in ("p50", "p80", "p95")} for item in node.get("phase_duration_quantiles", [])}
    if "overall" not in duration_rows: raise EstimationError("aggregate lacks overall duration quantiles")
    token_rows = {str(item["token_class"]): {name: int(item[name]) for name in ("p50", "p80", "p95")} for item in node.get("token_class_quantiles", [])}
    seed = int(identities["seed"]); phases = request2["phases"]; routes = request2["routes"]
    cap = _quota_cap(request2, quota2); price_index = _price_index(pricing2)
    focused_samples: list[int] = []; runtime_samples: list[int] = []; calendar_samples: list[int] = []
    operator_wait_samples: list[int] = []; vendor_wait_samples: list[int] = []; quota_delay_samples: list[int] = []
    total_wait_samples: list[int] = []
    cost_samples: list[int] = []; known_token_samples: list[int] = []; unpriced_token_samples: list[int] = []
    allocated_overall_samples: list[int] = []; phase_samples = {str(phase["id"]): [] for phase in phases}
    token_samples = {token_class: [] for token_class in token_rows}
    route_known_cost_samples = {str(route["id"]): [] for route in routes}; route_known_token_samples = {str(route["id"]): [] for route in routes}; route_unpriced_token_samples = {str(route["id"]): [] for route in routes}
    quota_rows_representative: list[dict[str, object]] = []; quota_coverages: list[int] = []; schedules: list[_Schedule] = []; allocated_any = False
    for index in range(SIMULATION_COUNT):
        autonomous_durations, allocated_total, allocated = _allocated_durations(phases, duration_rows, duration_rows["overall"], index, seed)
        allocated_any = allocated_any or allocated; allocated_overall_samples.append(allocated_total)
        durations = dict(autonomous_durations); operator_wait = 0; vendor_wait = 0
        for phase in phases:
            ident = str(phase["id"])
            if phase["owner"] != "autonomous_agent":
                duration = _sample(phase["external_wait_seconds"], index, seed, f"wait:{ident}"); durations[ident] = duration
                if phase["owner"] == "operator": operator_wait += duration
                else: vendor_wait += duration
            phase_samples[ident].append(int(durations[ident]))
        class_quantities = {token_class: _sample(quantiles, index, seed, f"token:{token_class}") for token_class, quantiles in token_rows.items()}
        route_tokens = {str(route["id"]): 0 for route in routes}; known_tokens = 0; unpriced_tokens = 0; cost = 0
        route_known_tokens = {str(route["id"]): 0 for route in routes}
        route_unpriced_tokens = {str(route["id"]): 0 for route in routes}
        route_known_costs = {str(route["id"]): 0 for route in routes}
        for token_class, total in class_quantities.items():
            token_samples[token_class].append(total)
            allocations = _largest_remainder(total, [(str(route["id"]), int(route["token_share_basis_points"])) for route in routes]) if routes else {}
            for route in routes:
                route_id = str(route["id"]); quantity = allocations[route_id]; route_tokens[route_id] += quantity
                price = price_index.get((str(route["provider"]), str(route["model"]), str(route["modality"]), str(route["tier"]), token_class))
                if price is None:
                    unpriced_tokens += quantity; route_unpriced_tokens[route_id] += quantity
                else:
                    known_tokens += quantity; route_known_tokens[route_id] += quantity
                    route_cost = (quantity * price + 500_000) // 1_000_000; route_known_costs[route_id] += route_cost; cost += route_cost
        for route in routes:
            route_id = str(route["id"])
            route_known_token_samples[route_id].append(route_known_tokens[route_id])
            route_unpriced_token_samples[route_id].append(route_unpriced_tokens[route_id])
            route_known_cost_samples[route_id].append(route_known_costs[route_id])
        quota_delay, quota_coverage, quota_rows = _quota_analysis(request2, quota2, route_tokens)
        if index == 0: quota_rows_representative = quota_rows
        quota_coverages.append(quota_coverage); quota_delay_samples.append(quota_delay)
        schedule = _schedule(request2, durations, cap); schedules.append(schedule)
        focused_samples.append(schedule.focused); runtime_samples.append(schedule.runtime); calendar_samples.append(schedule.makespan + quota_delay)
        operator_wait_samples.append(operator_wait); vendor_wait_samples.append(vendor_wait)
        total_wait_samples.append(operator_wait + vendor_wait + quota_delay)
        known_token_samples.append(known_tokens); unpriced_token_samples.append(unpriced_tokens); cost_samples.append(cost)
    backoff_penalty = missing_levels * BACKOFF_PENALTY_BASIS_POINTS
    node_floors = node.get("uncertainty_floors", {})
    base_duration_floor = int(node_floors.get("duration_basis_points", 0)); base_token_floor = int(node_floors.get("token_basis_points", 0))
    duration_floor = base_duration_floor + backoff_penalty
    token_floor = base_token_floor + backoff_penalty + int(pricing2["uncertainty_basis_points"])
    quota_coverage = min(quota_coverages, default=0)
    quota_uncertainty = max(UNKNOWN_QUOTA_FLOOR_BASIS_POINTS, int(quota2["uncertainty_basis_points"])) if quota_coverage < 10_000 else 0
    duration_floor += quota_uncertainty
    focused_q = _q(focused_samples); runtime_q = _q(runtime_samples); calendar_q = _q(calendar_samples)
    focused_q["p95"] = _widen(focused_q["p95"], duration_floor); runtime_q["p95"] = _widen(runtime_q["p95"], duration_floor); calendar_q["p95"] = _widen(calendar_q["p95"], duration_floor)
    operator_q = _q(operator_wait_samples); vendor_q = _q(vendor_wait_samples); quota_q = _q(quota_delay_samples)
    total_wait_q = _q(total_wait_samples)
    total_tokens = sum(known_token_samples) + sum(unpriced_token_samples)
    known_basis = 0 if total_tokens == 0 else sum(known_token_samples) * 10_000 // total_tokens
    unpriced_basis = 10_000 - known_basis
    known_cost_q = {"p50": None, "p80": None, "p95": None} if not routes or not token_rows or sum(known_token_samples) == 0 else _q(cost_samples)
    if known_cost_q["p95"] is not None: known_cost_q["p95"] = _widen(int(known_cost_q["p95"]), token_floor)
    p80_calendar = _nearest(calendar_samples, 80); p80_index = min(range(SIMULATION_COUNT), key=lambda item: (abs(calendar_samples[item] - p80_calendar), item))
    critical_path = schedules[p80_index].critical_path
    calibration_age = (_datetime.date.fromisoformat(str(request2["as_of_date"])) - _datetime.date.fromisoformat(str(node["generated_date"]))).days
    if calibration_age < 0: raise EstimationError("request as_of_date precedes calibration")
    uncertainty_drivers = []
    if allocated_any: uncertainty_drivers.append("overall_allocated")
    if missing_levels: uncertainty_drivers.append("hierarchy_backoff")
    if unpriced_basis: uncertainty_drivers.append("unpriced_routes")
    if quota_coverage < 10_000: uncertainty_drivers.append("unknown_quota")
    pricing_providers = [{"provider": name, "state": provider["status"], "last_successful_official_retrieval_date": provider["last_successful_official_date"]} for name, provider in sorted(pricing2["providers"].items())]
    aggregate_pricing_state = "unpriced" if any(row["state"] == "unpriced" for row in pricing_providers) else "estimated_stale" if any(row["state"] == "estimated_stale" for row in pricing_providers) else "official"
    phase_rows = [{"id": phase["id"], "kind": phase["kind"], "prior_phase": phase["prior_phase"], "owner": phase["owner"], "scenario": phase["scenario"], "delivery_class": phase["delivery_class"], "duration_seconds": _q(phase_samples[str(phase["id"])])} for phase in sorted(phases, key=lambda item: str(item["id"]))]
    token_detail = []
    for name, values in sorted(token_samples.items()):
        quantity = _q(values); quantity["p95"] = _widen(quantity["p95"], token_floor)
        token_detail.append({"token_class": name, "quantity": quantity})
    route_costs = []
    for route in sorted(routes, key=lambda item: str(item["id"])):
        route_id = str(route["id"]); known_values = route_known_token_samples[route_id]; unpriced_values = route_unpriced_token_samples[route_id]
        denominator = sum(known_values) + sum(unpriced_values); coverage = 0 if denominator == 0 else sum(known_values) * 10_000 // denominator
        known_quantity = _q(known_values); unpriced_quantity = _q(unpriced_values)
        known_quantity["p95"] = _widen(known_quantity["p95"], token_floor); unpriced_quantity["p95"] = _widen(unpriced_quantity["p95"], token_floor)
        route_known_cost = _q(route_known_cost_samples[route_id]) if sum(known_values) else {"p50": None, "p80": None, "p95": None}
        if route_known_cost["p95"] is not None: route_known_cost["p95"] = _widen(int(route_known_cost["p95"]), token_floor)
        route_costs.append({"route_id": route_id, "provider": route["provider"], "known_microusd": route_known_cost, "known_token_quantity": known_quantity, "unpriced_token_quantity": unpriced_quantity, "coverage_basis_points": coverage})
    splits = {field: _split_rows(phases, phase_samples, field) for field in ("prior_phase", "scenario", "delivery_class", "owner")}
    result = {**identities,
        "headline": {
            "scope": {key: request2[key] for key in ("artifact_kind", "project_type", "repository_class", "project_maturity", "risk_tier", "reusable_classification")},
            "completion_boundary": request2["requested_completion_boundary"],
            "focused_agent_wall_clock_hours": _hours_q(focused_q), "calendar_elapsed_hours": _hours_q(calendar_q),
            "wait_decomposition_hours": {"operator": _hours_q(operator_q), "vendor": _hours_q(vendor_q), "quota": _hours_q(quota_q), "total": _hours_q(total_wait_q)},
            "api_equivalent_cost_current": {"known_microusd": known_cost_q, "known_basis_points": known_basis, "unpriced_basis_points": unpriced_basis},
            "calibration": {"selected_node": node["hierarchy_node"], "path": path, "sample_count": node["sample_count"], "effective_sample_size": node["effective_sample_size"], "age_days": calibration_age, "confidence": "high" if not missing_levels and duration_floor < 1000 else "moderate" if duration_floor < 3000 else "low", "base_duration_uncertainty_basis_points": base_duration_floor, "base_token_uncertainty_basis_points": base_token_floor, "snapshot_pricing_uncertainty_basis_points": pricing2["uncertainty_basis_points"], "snapshot_quota_uncertainty_basis_points": quota2["uncertainty_basis_points"], "uncertainty_floor_basis_points": duration_floor, "token_uncertainty_floor_basis_points": token_floor, "backoff_penalty_basis_points": backoff_penalty},
            "pricing": {"aggregate_state": aggregate_pricing_state, "providers": pricing_providers},
            "assumptions": list(request2["assumptions"]), "critical_path": critical_path, "planned_concurrency": cap,
            "uncertainty_drivers": uncertainty_drivers, "prerequisites": [], "splits": splits,
            "evidence_coverage": {"duration_basis_points": 10_000, "token_basis_points": 10_000 if token_rows else 0, "pricing_basis_points": known_basis, "quota_basis_points": quota_coverage},
        },
        "detail": {
            "focused_agent_wall_clock_seconds": focused_q, "summed_agent_runtime_seconds": runtime_q, "calendar_elapsed_seconds": calendar_q,
            "wait_decomposition_seconds": {"operator": operator_q, "vendor": vendor_q, "quota": quota_q, "total": total_wait_q},
            "allocated_overall_seconds": _q(allocated_overall_samples), "phase_rows": phase_rows, "token_class_quantities": token_detail,
            "route_costs": route_costs, "quota": {"delay_seconds": quota_q, "coverage_basis_points": quota_coverage, "provider_aggregation_rule": "sum_within_provider_max_across_providers", "routes": quota_rows_representative},
            "cohort": {"expected_path": expected_path, "selected_node": node["hierarchy_node"], "fallback_path": path, "backoff_levels": missing_levels},
            "actual_marginal_cash_status": "unknown",
        }, "labels": dict(_LABELS)}
    return validate_result(result)


def _validate_seconds_q(value: object, field: str, nullable: bool = False) -> None:
    row = _exact(value, {"p50", "p80", "p95"}, field)
    values = []
    for name in ("p50", "p80", "p95"):
        if nullable and row[name] is None: continue
        values.append(_integer(row[name], f"{field}.{name}"))
    if values and values != sorted(values): raise EstimationError(f"{field} quantiles are unordered")


def _validate_labels(value: object) -> None:
    labels = _exact(value, set(_LABELS), "result.labels")
    if labels != _LABELS: raise EstimationError("result labels are invalid")


def _validate_available_result(row: dict[str, object]) -> None:
    headline_fields = {"scope", "completion_boundary", "focused_agent_wall_clock_hours", "calendar_elapsed_hours", "wait_decomposition_hours", "api_equivalent_cost_current", "calibration", "pricing", "assumptions", "critical_path", "planned_concurrency", "uncertainty_drivers", "prerequisites", "splits", "evidence_coverage"}
    headline = _exact(row["headline"], headline_fields, "result.headline")
    scope = _exact(headline["scope"], {"artifact_kind", "project_type", "repository_class", "project_maturity", "risk_tier", "reusable_classification"}, "result.headline.scope")
    for key, value in scope.items(): _string(value, f"result.headline.scope.{key}", 128)
    _enum(headline["completion_boundary"], _BOUNDARIES, "result.headline.completion_boundary")
    _hours_quantiles(headline["focused_agent_wall_clock_hours"], "result.headline.focused_hours"); _hours_quantiles(headline["calendar_elapsed_hours"], "result.headline.calendar_hours")
    waits = _exact(headline["wait_decomposition_hours"], {"operator", "vendor", "quota", "total"}, "result.headline.wait_decomposition_hours")
    for name, item in waits.items(): _hours_quantiles(item, f"result.headline.wait.{name}")
    cost = _exact(headline["api_equivalent_cost_current"], {"known_microusd", "known_basis_points", "unpriced_basis_points"}, "result.headline.cost")
    _validate_seconds_q(cost["known_microusd"], "result.headline.cost.known", True)
    known = _integer(cost["known_basis_points"], "result.headline.cost.known_basis_points", 0, 10_000); unpriced = _integer(cost["unpriced_basis_points"], "result.headline.cost.unpriced_basis_points", 0, 10_000)
    if known + unpriced != 10_000: raise EstimationError("result cost coverage is inconsistent")
    calibration_fields = {"selected_node", "path", "sample_count", "effective_sample_size", "age_days", "confidence", "base_duration_uncertainty_basis_points", "base_token_uncertainty_basis_points", "snapshot_pricing_uncertainty_basis_points", "snapshot_quota_uncertainty_basis_points", "uncertainty_floor_basis_points", "token_uncertainty_floor_basis_points", "backoff_penalty_basis_points"}
    calibration = _exact(headline["calibration"], calibration_fields, "result.headline.calibration")
    _node(calibration["selected_node"], "result.calibration.selected_node")
    if type(calibration["path"]) is not list or not calibration["path"]: raise EstimationError("result calibration path is invalid")
    for item in calibration["path"]: _node(item, "result.calibration.path")
    for key in calibration_fields - {"selected_node", "path", "confidence"}: _integer(calibration[key], f"result.calibration.{key}")
    _enum(calibration["confidence"], {"high", "moderate", "low"}, "result.calibration.confidence")
    pricing = _exact(headline["pricing"], {"aggregate_state", "providers"}, "result.headline.pricing")
    _enum(pricing["aggregate_state"], {"official", "estimated_stale", "unpriced"}, "result.pricing.aggregate_state")
    if type(pricing["providers"]) is not list or len(pricing["providers"]) > 100: raise EstimationError("result pricing providers are invalid")
    for item in pricing["providers"]:
        provider = _exact(item, {"provider", "state", "last_successful_official_retrieval_date"}, "result.pricing.provider")
        _identifier(provider["provider"], "result.pricing.provider"); _enum(provider["state"], {"official", "estimated_stale", "unpriced"}, "result.pricing.state"); _nullable_date(provider["last_successful_official_retrieval_date"], "result.pricing.last_official")
    for field in ("assumptions", "uncertainty_drivers", "prerequisites", "critical_path"):
        if type(headline[field]) is not list or len(headline[field]) > 256: raise EstimationError(f"result.{field} is invalid")
        for item in headline[field]: _string(item, f"result.{field}")
    _integer(headline["planned_concurrency"], "result.planned_concurrency", 1, 32)
    splits = _exact(headline["splits"], {"prior_phase", "scenario", "delivery_class", "owner"}, "result.headline.splits")
    for field, items in splits.items():
        if type(items) is not list or len(items) > 128: raise EstimationError(f"result.splits.{field} is invalid")
        for item in items:
            split = _exact(item, {"name", "duration_seconds"}, f"result.splits.{field}"); _string(split["name"], f"result.splits.{field}.name"); _validate_seconds_q(split["duration_seconds"], f"result.splits.{field}.duration")
    coverage = _exact(headline["evidence_coverage"], {"duration_basis_points", "token_basis_points", "pricing_basis_points", "quota_basis_points"}, "result.headline.evidence_coverage")
    for key, value in coverage.items(): _integer(value, f"result.coverage.{key}", 0, 10_000)
    detail_fields = {"focused_agent_wall_clock_seconds", "summed_agent_runtime_seconds", "calendar_elapsed_seconds", "wait_decomposition_seconds", "allocated_overall_seconds", "phase_rows", "token_class_quantities", "route_costs", "quota", "cohort", "actual_marginal_cash_status"}
    detail = _exact(row["detail"], detail_fields, "result.detail")
    for field in ("focused_agent_wall_clock_seconds", "summed_agent_runtime_seconds", "calendar_elapsed_seconds", "allocated_overall_seconds"): _validate_seconds_q(detail[field], f"result.detail.{field}")
    waits2 = _exact(detail["wait_decomposition_seconds"], {"operator", "vendor", "quota", "total"}, "result.detail.waits")
    for name, item in waits2.items(): _validate_seconds_q(item, f"result.detail.waits.{name}")
    if type(detail["phase_rows"]) is not list or len(detail["phase_rows"]) > 128: raise EstimationError("result phase rows are invalid")
    for item in detail["phase_rows"]:
        phase = _exact(item, {"id", "kind", "prior_phase", "owner", "scenario", "delivery_class", "duration_seconds"}, "result.phase_row")
        for name in ("id", "kind", "prior_phase", "owner", "scenario", "delivery_class"): _string(phase[name], f"result.phase.{name}", 128)
        _validate_seconds_q(phase["duration_seconds"], "result.phase.duration")
    if type(detail["token_class_quantities"]) is not list or len(detail["token_class_quantities"]) > 128: raise EstimationError("result token rows are invalid")
    for item in detail["token_class_quantities"]:
        token = _exact(item, {"token_class", "quantity"}, "result.token"); _identifier(token["token_class"], "result.token_class"); _validate_seconds_q(token["quantity"], "result.token.quantity")
    if type(detail["route_costs"]) is not list or len(detail["route_costs"]) > 32: raise EstimationError("result route costs are invalid")
    for item in detail["route_costs"]:
        route = _exact(item, {"route_id", "provider", "known_microusd", "known_token_quantity", "unpriced_token_quantity", "coverage_basis_points"}, "result.route_cost")
        _identifier(route["route_id"], "result.route_id"); _identifier(route["provider"], "result.route.provider")
        _validate_seconds_q(route["known_microusd"], "result.route.known_cost", True); _validate_seconds_q(route["known_token_quantity"], "result.route.known_tokens"); _validate_seconds_q(route["unpriced_token_quantity"], "result.route.unpriced_tokens"); _integer(route["coverage_basis_points"], "result.route.coverage", 0, 10_000)
    quota = _exact(detail["quota"], {"delay_seconds", "coverage_basis_points", "provider_aggregation_rule", "routes"}, "result.detail.quota")
    _validate_seconds_q(quota["delay_seconds"], "result.quota.delay"); _integer(quota["coverage_basis_points"], "result.quota.coverage", 0, 10_000)
    if quota["provider_aggregation_rule"] != "sum_within_provider_max_across_providers": raise EstimationError("result quota aggregation rule is invalid")
    if type(quota["routes"]) is not list or len(quota["routes"]) > 32: raise EstimationError("result quota routes are invalid")
    for item in quota["routes"]:
        route = _exact(item, {"route_id", "provider", "delay_seconds", "coverage"}, "result.quota.route"); _identifier(route["route_id"], "result.quota.route_id"); _identifier(route["provider"], "result.quota.provider"); _integer(route["delay_seconds"], "result.quota.delay_seconds"); _enum(route["coverage"], {"known", "unknown"}, "result.quota.coverage")
    cohort = _exact(detail["cohort"], {"expected_path", "selected_node", "fallback_path", "backoff_levels"}, "result.detail.cohort")
    for field in ("expected_path", "fallback_path"):
        if type(cohort[field]) is not list or not cohort[field]: raise EstimationError(f"result cohort {field} is invalid")
        for item in cohort[field]: _node(item, f"result.cohort.{field}")
    _node(cohort["selected_node"], "result.cohort.selected_node"); _integer(cohort["backoff_levels"], "result.cohort.backoff_levels")
    if detail["actual_marginal_cash_status"] != "unknown": raise EstimationError("estimate actual cash status must be unknown")


def _validate_reconciliation_result(row: dict[str, object]) -> None:
    duration = _mapping(row["duration_errors"], "reconciliation.duration_errors")
    if set(duration) != {"focused", "calendar", "summed_runtime"}: raise EstimationError("reconciliation duration errors are invalid")
    for name, item in duration.items():
        error = _exact(item, {"planned_p50_seconds", "actual_seconds", "signed_error_seconds", "absolute_error_seconds", "log_ratio_millionths", "within_p50_p95"}, f"reconciliation.duration_errors.{name}")
        for field in ("planned_p50_seconds", "actual_seconds", "absolute_error_seconds"): _integer(error[field], f"reconciliation.{name}.{field}")
        _integer(error["signed_error_seconds"], f"reconciliation.{name}.signed", -1_000_000_000_000_000, 1_000_000_000_000_000); _integer(error["log_ratio_millionths"], f"reconciliation.{name}.log", -1_000_000_000_000_000, 1_000_000_000_000_000); _boolean(error["within_p50_p95"], f"reconciliation.{name}.coverage")
    wait = _mapping(row["wait_errors"], "reconciliation.wait_errors")
    if set(wait) != {"operator", "vendor", "quota"}: raise EstimationError("reconciliation wait errors are invalid")
    for name, item in wait.items():
        error = _exact(item, {"planned_p50_seconds", "actual_seconds", "signed_error_seconds", "absolute_error_seconds"}, f"reconciliation.wait_errors.{name}")
        for field in ("planned_p50_seconds", "actual_seconds", "absolute_error_seconds"): _integer(error[field], f"reconciliation.wait.{field}")
        _integer(error["signed_error_seconds"], "reconciliation.wait.signed", -1_000_000_000_000_000, 1_000_000_000_000_000)
    concurrency = _exact(row["concurrency_error"], {"planned_concurrency", "observed_peak_concurrency", "status"}, "reconciliation.concurrency_error")
    _integer(concurrency["planned_concurrency"], "reconciliation.planned_concurrency", 1, 32)
    if concurrency["observed_peak_concurrency"] is not None: _integer(concurrency["observed_peak_concurrency"], "reconciliation.observed_concurrency", 1, 32)
    _enum(concurrency["status"], {"unavailable"}, "reconciliation.concurrency.status")
    quota = _exact(row["quota_error"], {"planned_p50_seconds", "actual_seconds", "signed_error_seconds", "absolute_error_seconds", "coverage_basis_points"}, "reconciliation.quota_error")
    for field in ("planned_p50_seconds", "actual_seconds", "absolute_error_seconds"): _integer(quota[field], f"reconciliation.quota.{field}")
    _integer(quota["signed_error_seconds"], "reconciliation.quota.signed", -1_000_000_000_000_000, 1_000_000_000_000_000); _integer(quota["coverage_basis_points"], "reconciliation.quota.coverage", 0, 10_000)
    cohort = _exact(row["cohort"], {"selected_node", "fallback_path", "backoff_levels"}, "reconciliation.cohort")
    _node(cohort["selected_node"], "reconciliation.cohort.selected"); _integer(cohort["backoff_levels"], "reconciliation.cohort.backoff")
    if type(cohort["fallback_path"]) is not list: raise EstimationError("reconciliation fallback path is invalid")
    for item in cohort["fallback_path"]: _node(item, "reconciliation.fallback_path")
    cost_views = _exact(row["cost_views"], {"current_api_equivalent", "execution_era_api_equivalent", "actual_marginal_cash"}, "reconciliation.cost_views")
    for name in ("current_api_equivalent", "execution_era_api_equivalent"):
        view = _exact(cost_views[name], {"known_microusd", "known_basis_points", "unpriced_basis_points"}, f"reconciliation.cost_views.{name}")
        if view["known_microusd"] is not None: _integer(view["known_microusd"], f"reconciliation.{name}.known")
        known = _integer(view["known_basis_points"], f"reconciliation.{name}.known_bp", 0, 10_000); unpriced = _integer(view["unpriced_basis_points"], f"reconciliation.{name}.unpriced_bp", 0, 10_000)
        if known + unpriced != 10_000: raise EstimationError("reconciliation cost coverage is inconsistent")
    cash = _mapping(cost_views["actual_marginal_cash"], "reconciliation.actual_cash")
    _enum(cash.get("status"), {"authoritative", "operator_supplied", "subscription_zero", "unknown"}, "reconciliation.actual_cash.status")
    if cash["status"] == "unknown":
        if set(cash) != {"status"}: raise EstimationError("unknown reconciliation cash is invalid")
    else:
        _exact(cash, {"status", "amount_microusd", "evidence_sha256"}, "reconciliation.actual_cash"); _integer(cash["amount_microusd"], "reconciliation.actual_cash.amount"); _sha(cash["evidence_sha256"], "reconciliation.actual_cash.evidence")
    cost_error = _exact(row["cost_error_current"], {"planned_p50_microusd", "actual_repriced_microusd", "signed_error_microusd", "absolute_error_microusd", "log_ratio_millionths", "coverage_basis_points"}, "reconciliation.cost_error_current")
    for field in ("planned_p50_microusd", "actual_repriced_microusd", "signed_error_microusd", "absolute_error_microusd", "log_ratio_millionths"):
        if cost_error[field] is not None: _integer(cost_error[field], f"reconciliation.cost_error.{field}", -1_000_000_000_000_000 if "signed" in field or "log" in field else 0, 1_000_000_000_000_000)
    _integer(cost_error["coverage_basis_points"], "reconciliation.cost_error.coverage", 0, 10_000)


def validate_result(value: object) -> dict[str, object]:
    row = _mapping(value, "result")
    common = {"schema_version", "result_kind", "labels"}
    if row.get("schema_version") != 1: raise EstimationError("result.schema_version is unsupported")
    kind = _enum(row.get("result_kind"), {"estimate", "reconciliation"}, "result.result_kind")
    _validate_labels(row.get("labels"))
    if kind == "estimate":
        identities = {"estimator_method_version", "scope_hash", "prior_sha256", "pricing_sha256", "quota_sha256", "seed", "simulation_count", "generated_date", "source_cutoff_date"}
        unavailable_fields = common | identities | {"estimate_unavailable"}
        available_fields = common | identities | {"headline", "detail"}
        if "estimate_unavailable" in row:
            _exact(row, unavailable_fields, "result"); _enum(row["estimate_unavailable"], {"insufficient_scope", "no_compatible_prior"}, "result.estimate_unavailable")
        else:
            _exact(row, available_fields, "result"); _validate_available_result(row)
        _version(row["estimator_method_version"], "result.estimator_method_version")
        for name in ("scope_hash", "prior_sha256", "pricing_sha256", "quota_sha256"): _sha(row[name], f"result.{name}")
        _integer(row["seed"], "result.seed", 0, 2_147_483_647)
        if row["simulation_count"] != SIMULATION_COUNT: raise EstimationError("result simulation count is unsupported")
        _date(row["generated_date"], "result.generated_date"); _date(row["source_cutoff_date"], "result.source_cutoff_date")
    else:
        fields = common | {"scope_hash", "prior_result_sha256", "current_pricing_sha256", "execution_pricing_sha256", "completion_boundary", "duration_errors", "wait_errors", "concurrency_error", "quota_error", "cohort", "cost_views", "cost_error_current"}
        _exact(row, fields, "reconciliation-result")
        for name in ("scope_hash", "prior_result_sha256", "current_pricing_sha256"): _sha(row[name], f"reconciliation.{name}")
        _nullable_sha(row["execution_pricing_sha256"], "reconciliation.execution_pricing_sha256")
        _enum(row["completion_boundary"], _BOUNDARIES, "reconciliation.completion_boundary"); _validate_reconciliation_result(row)
    return row


def _log_ratio_millionths(actual: int, planned: int) -> int:
    with localcontext() as context:
        context.prec = 40
        ratio = (Decimal(max(1, actual)).ln() - Decimal(max(1, planned)).ln()) * Decimal(1_000_000)
        return int(ratio.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _signed_error(planned: int, actual: int, p95: int) -> dict[str, object]:
    signed = actual - planned
    ratio = _log_ratio_millionths(actual, planned)
    return {"planned_p50_seconds": planned, "actual_seconds": actual, "signed_error_seconds": signed, "absolute_error_seconds": abs(signed), "log_ratio_millionths": ratio, "within_p50_p95": planned <= actual <= p95}


def _reprice_actual(actual: Mapping[str, object], pricing: Mapping[str, object], prior: Mapping[str, object]) -> dict[str, object]:
    route_meta = {str(item["route_id"]): (str(item["provider"]),) for item in prior["detail"]["route_costs"]}
    # The estimate intentionally stores provider but not model dimensions in its
    # route-cost rows.  Repricing therefore uses the unique matching provider +
    # token-class record; ambiguity remains unpriced rather than guessed.
    providers = pricing["providers"]; known = 0; known_quantity = 0; total = 0
    for token in actual["token_usage"]:
        quantity = int(token["quantity"]); total += quantity
        meta = route_meta.get(str(token["route_id"])); candidates = []
        if meta and meta[0] in providers and providers[meta[0]]["status"] in {"official", "estimated_stale"}:
            candidates = [record for record in providers[meta[0]]["values"] if record.get("token_class") == token["token_class"] and record.get("unit") == "per_million_tokens"]
        if len(candidates) == 1:
            known += (quantity * int(candidates[0]["amount_microusd"]) + 500_000) // 1_000_000; known_quantity += quantity
    coverage = 0 if total == 0 else known_quantity * 10_000 // total
    return {"known_microusd": known if known_quantity else None, "known_basis_points": coverage, "unpriced_basis_points": 10_000 - coverage}


def reconcile(prior_result: Mapping[str, object], actual: Mapping[str, object], pricing: Mapping[str, object]) -> dict[str, object]:
    prior = validate_result(prior_result); actual2 = validate_actual(actual); pricing2 = validate_pricing(pricing)
    if prior["result_kind"] != "estimate" or "detail" not in prior: raise EstimationError("prior result must be an available estimate")
    duration_errors = {}
    for name, actual_field, detail_field in (("focused", "focused_agent_wall_clock_seconds", "focused_agent_wall_clock_seconds"), ("calendar", "calendar_elapsed_seconds", "calendar_elapsed_seconds"), ("summed_runtime", "summed_agent_runtime_seconds", "summed_agent_runtime_seconds")):
        planned = prior["detail"][detail_field]; duration_errors[name] = _signed_error(int(planned["p50"]), int(actual2[actual_field]), int(planned["p95"]))
    wait_errors = {}
    for name, actual_field in (("operator", "operator_seconds"), ("vendor", "vendor_seconds"), ("quota", "quota_seconds")):
        planned = int(prior["detail"]["wait_decomposition_seconds"][name]["p50"]); observed = int(actual2["wait_decomposition"][actual_field]); signed = observed - planned
        wait_errors[name] = {"planned_p50_seconds": planned, "actual_seconds": observed, "signed_error_seconds": signed, "absolute_error_seconds": abs(signed)}
    current_view = _reprice_actual(actual2, pricing2, prior)
    execution = actual2.get("execution_era_pricing")
    execution_view = _reprice_actual(actual2, execution, prior) if execution is not None else {"known_microusd": None, "known_basis_points": 0, "unpriced_basis_points": 10_000}
    planned_cost = prior["headline"]["api_equivalent_cost_current"]["known_microusd"]["p50"]
    actual_cost = current_view["known_microusd"]
    if planned_cost is None or actual_cost is None:
        cost_error = {"planned_p50_microusd": planned_cost, "actual_repriced_microusd": actual_cost, "signed_error_microusd": None, "absolute_error_microusd": None, "log_ratio_millionths": None, "coverage_basis_points": current_view["known_basis_points"]}
    else:
        signed = int(actual_cost) - int(planned_cost)
        cost_error = {"planned_p50_microusd": planned_cost, "actual_repriced_microusd": actual_cost, "signed_error_microusd": signed, "absolute_error_microusd": abs(signed), "log_ratio_millionths": _log_ratio_millionths(int(actual_cost), int(planned_cost)), "coverage_basis_points": current_view["known_basis_points"]}
    cohort = prior["detail"]["cohort"]
    result = {"schema_version": 1, "result_kind": "reconciliation", "scope_hash": prior["scope_hash"], "prior_result_sha256": hashlib.sha256(_canonical(prior)).hexdigest(), "current_pricing_sha256": hashlib.sha256(_canonical(pricing2)).hexdigest(), "execution_pricing_sha256": hashlib.sha256(_canonical(execution)).hexdigest() if execution is not None else None, "completion_boundary": actual2["completion_boundary"], "duration_errors": duration_errors, "wait_errors": wait_errors, "concurrency_error": {"planned_concurrency": prior["headline"]["planned_concurrency"], "observed_peak_concurrency": None, "status": "unavailable"}, "quota_error": {**wait_errors["quota"], "coverage_basis_points": prior["detail"]["quota"]["coverage_basis_points"]}, "cohort": {"selected_node": cohort["selected_node"], "fallback_path": cohort["fallback_path"], "backoff_levels": cohort["backoff_levels"]}, "cost_views": {"current_api_equivalent": current_view, "execution_era_api_equivalent": execution_view, "actual_marginal_cash": dict(actual2["actual_marginal_cash"])}, "cost_error_current": cost_error, "labels": dict(_LABELS)}
    return validate_result(result)


class _DuplicateKey(ValueError): pass


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result: raise _DuplicateKey("duplicate JSON key")
        result[key] = value
    return result


def _open_parent(path: str) -> tuple[int, str]:
    if not path or "\x00" in path: raise EstimationError("path is invalid")
    if any(part == ".." for part in path.split(os.sep)): raise EstimationError("path may not contain ..")
    candidate = os.path.normpath(path)
    parts = candidate.split(os.sep)
    if any(part == ".." for part in parts): raise EstimationError("path may not contain ..")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    if os.path.isabs(candidate):
        fd = os.open(os.sep, flags); components = [part for part in parts[:-1] if part]
    else:
        fd = os.open(".", flags); components = [part for part in parts[:-1] if part not in {"", "."}]
    try:
        for component in components:
            next_fd = os.open(component, flags, dir_fd=fd); os.close(fd); fd = next_fd
        name = parts[-1]
        if name in {"", ".", ".."}: raise EstimationError("path final component is invalid")
        return fd, name
    except BaseException:
        os.close(fd); raise


def _read_bounded_fd(fd: int, field: str) -> bytes:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES: raise EstimationError(f"{field} is not a bounded regular file")
    identity = (before.st_dev, before.st_ino, before.st_mode, before.st_uid, before.st_gid, before.st_nlink, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    payload = bytearray(); remaining = before.st_size
    while remaining:
        chunk = os.read(fd, min(65_536, remaining))
        if not chunk: raise EstimationError(f"{field} was truncated during read")
        payload.extend(chunk); remaining -= len(chunk)
    if os.read(fd, 1): raise EstimationError(f"{field} grew during read")
    after = os.fstat(fd); after_identity = (after.st_dev, after.st_ino, after.st_mode, after.st_uid, after.st_gid, after.st_nlink, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    if identity != after_identity: raise EstimationError(f"{field} changed during read")
    return bytes(payload)


def _decode_json(payload: bytes) -> object:
    if len(payload) > MAX_BYTES: raise EstimationError("input exceeds byte bound")
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise EstimationError("input is not finite duplicate-free JSON") from exc
    if type(value) is not dict: raise EstimationError("input JSON must contain one object")
    return value


def _read_json(path: str) -> object:
    if path == "-": return _decode_json(sys.stdin.buffer.read(MAX_BYTES + 1))
    directory, name = _open_parent(path)
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(name, flags, dir_fd=directory)
        try: payload = _read_bounded_fd(fd, "input")
        finally: os.close(fd)
    finally: os.close(directory)
    return _decode_json(payload)


def _write_exclusive(path: str, payload: bytes) -> None:
    directory, name = _open_parent(path); created = False; fd: int | None = None
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(name, flags, 0o600, dir_fd=directory); created = True; remaining = memoryview(payload)
        while remaining:
            count = os.write(fd, remaining)
            if count <= 0: raise EstimationError("output write was short")
            remaining = remaining[count:]
        os.fsync(fd); os.lseek(fd, 0, os.SEEK_SET)
        if _read_bounded_fd(fd, "output") != payload: raise EstimationError("output readback failed")
    except BaseException:
        if fd is not None:
            try: os.close(fd)
            except OSError: pass
            fd = None
        if created:
            try: os.unlink(name, dir_fd=directory)
            except OSError: pass
        raise
    finally:
        if fd is not None: os.close(fd)
        os.close(directory)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="project_estimation.py"); sub = parser.add_subparsers(dest="command", required=True)
    estimate_parser = sub.add_parser("estimate")
    for name in ("request", "prior", "pricing", "quota"): estimate_parser.add_argument(f"--{name}", required=True)
    estimate_parser.add_argument("--out")
    reconcile_parser = sub.add_parser("reconcile")
    for name in ("prior-result", "actual", "pricing"): reconcile_parser.add_argument(f"--{name}", required=True)
    reconcile_parser.add_argument("--out")
    try:
        args = parser.parse_args(argv); paths = [value for key, value in vars(args).items() if key not in {"command", "out"}]
        if paths.count("-") > 1: raise EstimationError("at most one input may be stdin")
        if args.command == "estimate":
            request = _read_json(args.request); result = estimate(request, _read_json(args.prior), _read_json(args.pricing), _read_json(args.quota))
            if args.out and not request.get("persistence_consent", False): raise EstimationError("output requires persistence consent")
        else:
            actual = _read_json(args.actual); result = reconcile(_read_json(args.prior_result), actual, _read_json(args.pricing))
            if args.out and not actual.get("persistence_consent", False): raise EstimationError("output requires persistence consent")
        validate_result(result); payload = _canonical(result) + b"\n"
        if args.out: _write_exclusive(args.out, payload)
        else: sys.stdout.buffer.write(payload)
        return 0
    except (EstimationError, OSError) as exc:
        print(f"project_estimation: {exc}", file=sys.stderr); return 2


if __name__ == "__main__": raise SystemExit(main())
