#!/usr/bin/env python3
"""Deterministic, offline public project-estimation helper.

The module deliberately has no package imports: it is shipped as a single
standard-library-only artifact and can be imported by release admission tests.
All input is explicit JSON; descriptive strings remain data and are never
interpreted as commands, paths, URLs, or executable configuration.
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
from typing import Any


MAX_BYTES = 1_048_576
SIMULATION_COUNT = 2_048
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
_REQUIREMENT = {"none", "standard", "high", "unknown"}


class EstimationError(ValueError):
    """A fail-closed public input or filesystem contract error."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _mapping(value: object, field: str) -> dict[str, object]:
    if type(value) is not dict:
        raise EstimationError(f"{field} must be an object")
    return value


def _exact(value: object, fields: set[str], field: str, required: set[str] | None = None) -> dict[str, object]:
    row = _mapping(value, field)
    unknown = sorted(set(row) - fields)
    missing = sorted((required if required is not None else fields) - set(row))
    if unknown:
        raise EstimationError(f"{field} has unknown field {unknown[0]}")
    if missing:
        raise EstimationError(f"{field} is missing field {missing[0]}")
    return row


def _integer(value: object, field: str, minimum: int = 0, maximum: int = 1_000_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise EstimationError(f"{field} must be an integer between {minimum} and {maximum}")
    return value


def _string(value: object, field: str, maximum: int = 512) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise EstimationError(f"{field} must be a bounded string")
    return value


def _identifier(value: object, field: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise EstimationError(f"{field} must be a bounded identifier")
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


def _sha(value: object, field: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise EstimationError(f"{field} must be a lowercase SHA-256 digest")
    return value


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


def _inert_strings(value: object, field: str) -> list[str]:
    if type(value) is not list or len(value) > 128:
        raise EstimationError(f"{field} must be a bounded array")
    return [_string(item, f"{field}[{index}]") for index, item in enumerate(value)]


def validate_request(value: object) -> dict[str, object]:
    """Validate the closed v1 public request, including the complete DAG."""
    fields = {"schema_version", "as_of_date", "artifact_kind", "invocation_source", "auto_invocation_depth", "project_type", "repository_class", "project_maturity", "risk_tier", "requested_completion_boundary", "reusable_classification", "subsystem_count", "integration_count", "migration_burden", "operator_gate_profile", "requirements", "max_agent_concurrency", "phases", "dependency_edges", "routes", "assumptions", "exclusions", "persistence_consent", "request_id", "artifact_scope_hash", "seed"}
    required = fields - {"request_id", "artifact_scope_hash", "seed"}
    row = _exact(value, fields, "request", required)
    if row["schema_version"] != 1:
        raise EstimationError("request.schema_version is unsupported")
    _date(row["as_of_date"], "request.as_of_date")
    if row["artifact_kind"] not in {"standalone", "implementation_design", "implementation_plan"}:
        raise EstimationError("request.artifact_kind is unsupported")
    if row["invocation_source"] not in {"explicit", "situational_auto", "composed_checkpoint"}:
        raise EstimationError("request.invocation_source is unsupported")
    depth = _integer(row["auto_invocation_depth"], "request.auto_invocation_depth", 0, 1)
    if depth != 0:
        raise EstimationError("recursive_invocation")
    if row["project_type"] not in {"greenfield", "enhancement"} or row["repository_class"] not in {"workspace", "plugin", "project_local", "unknown"} or row["project_maturity"] not in {"new", "established", "legacy", "unknown"} or row["risk_tier"] not in {"low", "medium", "high", "critical", "unknown"}:
        raise EstimationError("request cohort field is unsupported")
    if row["requested_completion_boundary"] not in _BOUNDARIES or row["reusable_classification"] not in _DELIVERY:
        raise EstimationError("request boundary or delivery classification is unsupported")
    _integer(row["subsystem_count"], "request.subsystem_count", 0, 128)
    _integer(row["integration_count"], "request.integration_count", 0, 512)
    if row["migration_burden"] not in {"none", "low", "medium", "high", "unknown"} or row["operator_gate_profile"] not in {"none", "single", "multiple", "unknown"}:
        raise EstimationError("request burden or gate profile is unsupported")
    requirements = _exact(row["requirements"], {"security_privacy", "reliability_load", "observability", "documentation", "ci_cd", "rollout_rollback", "evaluation"}, "request.requirements")
    if any(item not in _REQUIREMENT for item in requirements.values()):
        raise EstimationError("request requirement is unsupported")
    _integer(row["max_agent_concurrency"], "request.max_agent_concurrency", 1, 32)
    _inert_strings(row["assumptions"], "request.assumptions")
    _inert_strings(row["exclusions"], "request.exclusions")
    if type(row["persistence_consent"]) is not bool:
        raise EstimationError("request.persistence_consent must be boolean")
    if "request_id" in row:
        _identifier(row["request_id"], "request.request_id")
    if "artifact_scope_hash" in row:
        _sha(row["artifact_scope_hash"], "request.artifact_scope_hash")
    if "seed" in row:
        _integer(row["seed"], "request.seed", 0, 2_147_483_647)
    phases = row["phases"]
    if type(phases) is not list or len(phases) > 128:
        raise EstimationError("request.phases must be a bounded array")
    ids: set[str] = set()
    route_refs: set[str] = set()
    for index, item in enumerate(phases):
        phase = _exact(item, {"id", "kind", "prior_phase", "owner", "scenario", "delivery_class", "effort_weight", "route_id", "external_wait_seconds"}, f"request.phases[{index}]", {"id", "kind", "prior_phase", "owner", "scenario", "delivery_class", "effort_weight"})
        ident = _identifier(phase["id"], f"request.phases[{index}].id")
        if ident in ids:
            raise EstimationError("request phase ids must be unique")
        ids.add(ident)
        _identifier(phase["kind"], f"request.phases[{index}].kind")
        if phase["prior_phase"] not in _PHASE_PRIORS or phase["owner"] not in _OWNERS or phase["scenario"] not in _SCENARIOS or phase["delivery_class"] not in _DELIVERY:
            raise EstimationError("request phase category is unsupported")
        _integer(phase["effort_weight"], f"request.phases[{index}].effort_weight", 1, 100)
        if "route_id" in phase:
            if phase["owner"] != "autonomous_agent":
                raise EstimationError("external phase may not use an agent route")
            route_refs.add(_identifier(phase["route_id"], f"request.phases[{index}].route_id"))
        if phase["owner"] == "autonomous_agent":
            if "external_wait_seconds" in phase:
                raise EstimationError("autonomous phase may not have external wait")
        elif "external_wait_seconds" not in phase:
            raise EstimationError("operator/vendor phase requires external wait")
        else:
            _quantiles(phase["external_wait_seconds"], f"request.phases[{index}].external_wait_seconds")
    edges = row["dependency_edges"]
    if type(edges) is not list or len(edges) > 512:
        raise EstimationError("request.dependency_edges must be a bounded array")
    seen_edges: set[tuple[str, str]] = set()
    parents: dict[str, list[str]] = {ident: [] for ident in ids}
    children: dict[str, list[str]] = {ident: [] for ident in ids}
    for index, item in enumerate(edges):
        edge = _exact(item, {"from", "to"}, f"request.dependency_edges[{index}]")
        source, target = _identifier(edge["from"], "edge.from"), _identifier(edge["to"], "edge.to")
        if source not in ids or target not in ids:
            raise EstimationError("dependency edge references unknown phase")
        if source == target or (source, target) in seen_edges:
            raise EstimationError("dependency edge is duplicate or self-referential")
        seen_edges.add((source, target)); parents[target].append(source); children[source].append(target)
    ready = sorted(key for key, value2 in parents.items() if not value2)
    consumed = 0
    parent_counts = {key: len(value2) for key, value2 in parents.items()}
    while ready:
        current = ready.pop(0); consumed += 1
        for child in sorted(children[current]):
            parent_counts[child] -= 1
            if parent_counts[child] == 0: ready.append(child)
        ready.sort()
    if consumed != len(ids):
        raise EstimationError("dependency graph contains cycle")
    routes = row["routes"]
    if type(routes) is not list or len(routes) > 32:
        raise EstimationError("request.routes must be a bounded array")
    route_ids: set[str] = set(); shares = 0
    for index, item in enumerate(routes):
        route = _exact(item, {"id", "provider", "model", "modality", "tier", "token_share_basis_points", "quota_usage"}, f"request.routes[{index}]", {"id", "provider", "model", "modality", "tier", "token_share_basis_points"})
        ident = _identifier(route["id"], f"request.routes[{index}].id")
        if ident in route_ids:
            raise EstimationError("route ids must be unique")
        route_ids.add(ident)
        for name in ("provider", "model", "modality", "tier"):
            _identifier(route[name], f"request.routes[{index}].{name}")
        shares += _integer(route["token_share_basis_points"], f"request.routes[{index}].token_share_basis_points", 0, 10_000)
        usage = route.get("quota_usage", [])
        if type(usage) is not list or len(usage) > 16:
            raise EstimationError("route quota usage is invalid")
        kinds: set[str] = set()
        for usage_index, record in enumerate(usage):
            record = _exact(record, {"limit_kind", "quantity"}, f"request.routes[{index}].quota_usage[{usage_index}]")
            kind = _identifier(record["limit_kind"], "quota_usage.limit_kind")
            if kind in kinds:
                raise EstimationError("route quota limit kinds must be unique")
            kinds.add(kind); _integer(record["quantity"], "quota_usage.quantity")
    if routes and shares != 10_000:
        raise EstimationError("route token shares must total 10000")
    if not route_refs <= route_ids:
        raise EstimationError("phase references unknown route")
    return row


def scope_projection(request: Mapping[str, object]) -> dict[str, object]:
    row = validate_request(dict(request))
    phases = sorted(({key: phase[key] for key in ("id", "kind", "prior_phase", "owner", "scenario", "delivery_class", "effort_weight", "route_id") if key in phase} for phase in row["phases"]), key=lambda value: value["id"])
    edges = sorted(({"from": item["from"], "to": item["to"]} for item in row["dependency_edges"]), key=lambda value: (value["from"], value["to"]))
    routes = sorted(({key: route[key] for key in ("id", "provider", "model", "modality", "tier", "token_share_basis_points") } for route in row["routes"]), key=lambda value: value["id"])
    return {"artifact_kind": row["artifact_kind"], "project_type": row["project_type"], "repository_class": row["repository_class"], "project_maturity": row["project_maturity"], "risk_tier": row["risk_tier"], "requested_completion_boundary": row["requested_completion_boundary"], "reusable_classification": row["reusable_classification"], "subsystem_count": row["subsystem_count"], "integration_count": row["integration_count"], "migration_burden": row["migration_burden"], "operator_gate_profile": row["operator_gate_profile"], "requirements": row["requirements"], "max_agent_concurrency": row["max_agent_concurrency"], "phases": phases, "dependency_edges": edges, "routes": routes}


def artifact_scope_hash(request: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical(scope_projection(request))).hexdigest()


def _validate_aggregate(value: object) -> dict[str, object]:
    fields = {"schema_version", "estimator_method_version", "generated_date", "source_cutoff_date", "policy_version", "policy_sha256", "seed", "source_manifest_sha256", "nodes"}
    row = _exact(value, fields, "aggregate-prior")
    if row["schema_version"] != 1 or row["estimator_method_version"] != "empirical-v2":
        raise EstimationError("aggregate-prior version is unsupported")
    for name in ("generated_date", "source_cutoff_date"): _date(row[name], f"aggregate.{name}")
    _version(row["policy_version"], "aggregate.policy_version"); _sha(row["policy_sha256"], "aggregate.policy_sha256"); _integer(row["seed"], "aggregate.seed", 0, 2_147_483_647); _sha(row["source_manifest_sha256"], "aggregate.source_manifest_sha256")
    nodes = row["nodes"]
    if type(nodes) is not list or not nodes or len(nodes) > 10_000:
        raise EstimationError("aggregate nodes are invalid")
    names: set[str] = set()
    for index, item in enumerate(nodes):
        allowed = {"schema_version", "estimator_method_version", "generated_date", "source_cutoff_date", "hierarchy_node", "fallback_parent", "sample_count", "effective_sample_size", "aggregate_sha256", "release_manifest_sha256", "source_eras", "phase_duration_quantiles", "token_class_quantiles", "rework_review_quantiles", "wait_class_quantiles", "calibration_quality", "drift_indicators", "uncertainty_floors", "pricing_snapshot"}
        required = {"schema_version", "estimator_method_version", "generated_date", "source_cutoff_date", "hierarchy_node", "sample_count", "effective_sample_size", "aggregate_sha256", "release_manifest_sha256"}
        node = _exact(item, allowed, f"aggregate.nodes[{index}]", required)
        if node["schema_version"] != 1 or node["estimator_method_version"] != "empirical-v2": raise EstimationError("aggregate node version is unsupported")
        name = node["hierarchy_node"]
        if type(name) is not str or _NODE.fullmatch(name) is None or name in names: raise EstimationError("aggregate hierarchy nodes are invalid")
        names.add(name)
        if node.get("fallback_parent") is not None and (type(node["fallback_parent"]) is not str or _NODE.fullmatch(node["fallback_parent"]) is None): raise EstimationError("aggregate fallback parent is invalid")
        _integer(node["sample_count"], "aggregate.sample_count", 20); _integer(node["effective_sample_size"], "aggregate.effective_sample_size"); _sha(node["aggregate_sha256"], "aggregate.aggregate_sha256"); _sha(node["release_manifest_sha256"], "aggregate.release_manifest_sha256")
        for name2 in ("generated_date", "source_cutoff_date"): _date(node[name2], f"aggregate.node.{name2}")
        for field, identity in (("phase_duration_quantiles", "phase"), ("token_class_quantiles", "token_class"), ("rework_review_quantiles", "kind"), ("wait_class_quantiles", "wait_class")):
            if field not in node: continue
            rows = node[field]
            if type(rows) is not list or len(rows) > 128: raise EstimationError(f"aggregate {field} is invalid")
            seen: set[str] = set()
            for q_index, q in enumerate(rows):
                q = _exact(q, {identity, "p50", "p80", "p95"}, f"aggregate.{field}[{q_index}]")
                ident = _identifier(q[identity], f"aggregate.{field}.{identity}")
                if ident in seen: raise EstimationError("aggregate quantile identities must be unique")
                seen.add(ident); _quantiles({name: q[name] for name in ("p50", "p80", "p95")}, f"aggregate.{field}[{q_index}]")
        for field in ("calibration_quality", "drift_indicators", "uncertainty_floors"):
            if field in node:
                metric = _mapping(node[field], f"aggregate.{field}")
                for key, item2 in metric.items(): _integer(item2, f"aggregate.{field}.{key}", 0, 10_000)
    for node in nodes:
        parent = node.get("fallback_parent")
        if parent is not None and parent not in names: raise EstimationError("aggregate fallback parent is absent")
    return row


def _validate_snapshot(value: object, kind: str) -> dict[str, object]:
    fields = {"schema_version", "kind", "policy_version", "policy_sha256", "retrieved_date", "providers", "operator_notification_required", "material_unpriced", "uncertainty_basis_points"}
    row = _exact(value, fields, f"{kind}-snapshot")
    if row["schema_version"] != 1 or row["kind"] != kind: raise EstimationError(f"{kind} snapshot version is unsupported")
    _version(row["policy_version"], f"{kind}.policy_version"); _sha(row["policy_sha256"], f"{kind}.policy_sha256"); _date(row["retrieved_date"], f"{kind}.retrieved_date")
    if type(row["operator_notification_required"]) is not bool or type(row["material_unpriced"]) is not bool: raise EstimationError(f"{kind} flags must be boolean")
    _integer(row["uncertainty_basis_points"], f"{kind}.uncertainty", 0, 10_000)
    providers = _mapping(row["providers"], f"{kind}.providers")
    if not providers or len(providers) > 100: raise EstimationError(f"{kind} providers are invalid")
    for name, item in providers.items():
        _identifier(name, f"{kind}.provider-name")
        provider = _mapping(item, f"{kind}.providers.{name}")
        required = {"provider", "status", "retrieved_date", "last_successful_official_date", "original_last_good_date", "values", "value_sha256", "source_url_sha256", "final_url_sha256", "redirect_chain_sha256", "content_type", "elapsed_class", "failure_class", "material_share_basis_points"}
        _exact(provider, required, f"{kind}.provider")
        if provider["provider"] != name or provider["status"] not in {"official", "estimated_stale", "review_required", "unpriced", "unknown"}: raise EstimationError(f"{kind} provider is invalid")
        _integer(provider["material_share_basis_points"], f"{kind}.material_share", 0, 10_000)
        values = provider["values"]
        if type(values) is not list or len(values) > 10_000: raise EstimationError(f"{kind} values are invalid")
        for record in values:
            common = {"record_id", "model", "modality", "tier", "modifiers", "approved_value_sha256"}
            extra = {"token_class", "currency", "unit", "amount_microusd", "amount_text"} if kind == "pricing" else {"limit_kind", "limit_value", "window_seconds", "cooldown_seconds"}
            record = _exact(record, common | extra, f"{kind}.record")
            for key in ("record_id", "model", "modality", "tier"): _identifier(record[key], f"{kind}.record.{key}")
            _sha(record["approved_value_sha256"], f"{kind}.record.approved_value_sha256")
            if kind == "pricing":
                _identifier(record["token_class"], "pricing.token_class")
                if record["currency"] != "USD" or record["unit"] != "per_million_tokens": raise EstimationError("pricing record unit is unsupported")
                _integer(record["amount_microusd"], "pricing.amount_microusd")
            else:
                _identifier(record["limit_kind"], "quota.limit_kind"); _integer(record["limit_value"], "quota.limit_value")
                if record["window_seconds"] is not None: _integer(record["window_seconds"], "quota.window_seconds", 1)
                _integer(record["cooldown_seconds"], "quota.cooldown_seconds")
    return row


def validate_aggregate(value: object) -> dict[str, object]: return _validate_aggregate(value)
def validate_pricing(value: object) -> dict[str, object]: return _validate_snapshot(value, "pricing")
def validate_quota(value: object) -> dict[str, object]: return _validate_snapshot(value, "quota")


def _sample(q: Mapping[str, int], index: int, seed: int, stream: str) -> int:
    digest = hashlib.sha256(f"{seed}:{stream}:{index}".encode()).digest()
    draw = int.from_bytes(digest[:8], "big") % 100
    return q["p50"] if draw < 50 else q["p80"] if draw < 80 else q["p95"]


def _nearest(values: list[int], numerator: int) -> int:
    return sorted(values)[max(0, math.ceil(len(values) * numerator / 100) - 1)]


def _hierarchy(request: Mapping[str, object], prior: Mapping[str, object]) -> tuple[dict[str, object], list[str]]:
    nodes = {item["hierarchy_node"]: item for item in prior["nodes"]}
    # A published node may be more specific than the current small fixture. Exact
    # matching follows a deterministic projection while never crossing project type.
    candidates = [f"{request['project_type']}.{request['requested_completion_boundary']}", str(request["project_type"]), "all"]
    selected = next((name for name in candidates if name in nodes), None)
    if selected is None or (selected != "all" and not selected.startswith(str(request["project_type"]))):
        raise EstimationError("no compatible prior")
    path = [selected]
    while nodes[path[-1]].get("fallback_parent") is not None:
        parent = nodes[path[-1]]["fallback_parent"]
        if parent in path: raise EstimationError("aggregate fallback cycle")
        path.append(parent)
    return nodes[selected], path


def _phase_quantiles(node: Mapping[str, object]) -> dict[str, dict[str, int]]:
    return {item["phase"]: {name: item[name] for name in ("p50", "p80", "p95")} for item in node.get("phase_duration_quantiles", [])}


def _schedule(request: Mapping[str, object], durations: Mapping[str, int]) -> tuple[int, int, int, list[str]]:
    phases = {item["id"]: item for item in request["phases"]}
    predecessors: dict[str, list[str]] = {key: [] for key in phases}
    for edge in request["dependency_edges"]: predecessors[edge["to"]].append(edge["from"])
    starts: dict[str, int] = {}; ends: dict[str, int] = {}; agent_slots: list[int] = [0] * request["max_agent_concurrency"]
    remaining = set(phases)
    while remaining:
        ready = sorted(key for key in remaining if all(parent in ends for parent in predecessors[key]))
        if not ready: raise EstimationError("dependency graph contains cycle")
        for ident in ready:
            phase = phases[ident]; base = max((ends[parent] for parent in predecessors[ident]), default=0)
            if phase["owner"] == "autonomous_agent":
                slot = min(range(len(agent_slots)), key=lambda index: agent_slots[index])
                start = max(base, agent_slots[slot]); agent_slots[slot] = start + durations[ident]
            else: start = base
            starts[ident] = start; ends[ident] = start + durations[ident]; remaining.remove(ident)
    autonomous = [(starts[key], ends[key]) for key, phase in phases.items() if phase["owner"] == "autonomous_agent"]
    points = sorted({point for pair in autonomous for point in pair})
    focused = sum(max(0, points[index + 1] - points[index]) for index in range(len(points) - 1) if any(start <= points[index] and end >= points[index + 1] for start, end in autonomous))
    runtime = sum(end - start for start, end in autonomous)
    critical = [key for key in sorted(phases, key=lambda item: (ends[item], item)) if ends[key] == max(ends.values(), default=0)]
    return focused, runtime, max(ends.values(), default=0), critical


def _quota_worker_cap(request: Mapping[str, object], quota: Mapping[str, object]) -> int:
    cap = request["max_agent_concurrency"]
    for route in request["routes"]:
        provider = quota["providers"].get(route["provider"], {})
        for record in provider.get("values", []):
            if (record.get("model"), record.get("modality"), record.get("tier"), record.get("limit_kind")) == (route["model"], route["modality"], route["tier"], "concurrency"):
                cap = min(cap, record["limit_value"])
    return max(1, cap)


def _quota_delay_seconds(request: Mapping[str, object], quota: Mapping[str, object], token_total: int) -> int:
    """Return only comparable TPM delay; unknown data stays visible, not invented."""
    delay = 0
    for route in request["routes"]:
        provider = quota["providers"].get(route["provider"], {})
        planned = token_total * route["token_share_basis_points"] // 10_000
        for record in provider.get("values", []):
            if (record.get("model"), record.get("modality"), record.get("tier"), record.get("limit_kind")) != (route["model"], route["modality"], route["tier"], "tpm"):
                continue
            windows = (planned + record["limit_value"] - 1) // max(1, record["limit_value"])
            delay += max(0, windows - 1) * 60
    return delay


def _hours(seconds: int) -> str: return f"{seconds / 3600:.6f}"


def estimate(request: Mapping[str, object], prior: Mapping[str, object], pricing: Mapping[str, object], quota: Mapping[str, object]) -> dict[str, object]:
    request2 = validate_request(dict(request)); prior2 = validate_aggregate(dict(prior)); pricing2 = validate_pricing(dict(pricing)); quota2 = validate_quota(dict(quota))
    scope_hash = artifact_scope_hash(request2)
    if request2.get("artifact_scope_hash") is not None and request2["artifact_scope_hash"] != scope_hash: raise EstimationError("artifact_scope_hash does not match request")
    identities = {"schema_version": 1, "estimator_method_version": "empirical-sim-v1", "scope_hash": scope_hash, "prior_sha256": hashlib.sha256(_canonical(prior2)).hexdigest(), "pricing_sha256": hashlib.sha256(_canonical(pricing2)).hexdigest(), "quota_sha256": hashlib.sha256(_canonical(quota2)).hexdigest(), "seed": request2.get("seed", prior2["seed"]), "simulation_count": SIMULATION_COUNT, "generated_date": request2["as_of_date"], "source_cutoff_date": prior2["source_cutoff_date"]}
    if not request2["phases"]:
        return {**identities, "estimate_unavailable": "insufficient_scope", "labels": {"api_equivalent": "not billed cash", "non_additivity": "current_api_equivalent_and_actual_cash_are_separate"}}
    node, path = _hierarchy(request2, prior2)
    phase_rows = _phase_quantiles(node)
    overall = phase_rows.get("overall")
    if overall is None: raise EstimationError("aggregate lacks overall duration quantiles")
    phases = request2["phases"]
    provider_records = pricing2["providers"]
    duration_samples: list[tuple[int, int, int]] = []; token_samples: list[int | None] = []; quota_delays: list[int] = []
    scheduled_request = dict(request2); scheduled_request["max_agent_concurrency"] = _quota_worker_cap(request2, quota2)
    for index in range(SIMULATION_COUNT):
        total = _sample(overall, index, identities["seed"], "duration")
        autonomous = [phase for phase in phases if phase["owner"] == "autonomous_agent"]
        known = all(phase["prior_phase"] in phase_rows for phase in autonomous)
        durations: dict[str, int] = {}
        weights = sum(phase["effort_weight"] for phase in autonomous) or 1
        for phase in phases:
            if phase["owner"] == "autonomous_agent":
                durations[phase["id"]] = _sample(phase_rows[phase["prior_phase"]], index, identities["seed"], phase["id"]) if known else total * phase["effort_weight"] // weights
            else:
                durations[phase["id"]] = _sample(_quantiles(phase["external_wait_seconds"], "wait"), index, identities["seed"], phase["id"])
        focused_seconds, runtime_seconds, calendar_seconds, _ = _schedule(scheduled_request, durations)
        token_rows = {item["token_class"]: {name: item[name] for name in ("p50", "p80", "p95")} for item in node.get("token_class_quantiles", [])}
        total_cost = 0; total_tokens = 0; priced = True
        for token_class, quantile in token_rows.items():
            amount = _sample(quantile, index, identities["seed"], f"token:{token_class}"); total_tokens += amount
            for route in request2["routes"]:
                quantity = amount * route["token_share_basis_points"] // 10_000
                values = provider_records.get(route["provider"], {}).get("values", [])
                price = next((record for record in values if record.get("model") == route["model"] and record.get("modality") == route["modality"] and record.get("tier") == route["tier"] and record.get("token_class") == token_class and record.get("unit") == "per_million_tokens"), None)
                if price is None: priced = False
                else: total_cost += (quantity * price["amount_microusd"] + 500_000) // 1_000_000
        quota_delay = _quota_delay_seconds(request2, quota2, total_tokens)
        quota_delays.append(quota_delay)
        duration_samples.append((focused_seconds, runtime_seconds, calendar_seconds + quota_delay))
        token_samples.append(total_cost if priced else None)
    focused, runtime, calendar = zip(*duration_samples)
    available_costs = [item for item in token_samples if item is not None]
    unpriced = 0 if len(available_costs) == len(token_samples) else 10_000
    cost = ({"p50_microusd": None, "p80_microusd": None, "p95_microusd": None}
            if not available_costs else {"p50_microusd": _nearest(available_costs, 50), "p80_microusd": _nearest(available_costs, 80), "p95_microusd": _nearest(available_costs, 95)})
    p80_index = min(range(SIMULATION_COUNT), key=lambda index: abs(calendar[index] - _nearest(list(calendar), 80)))
    _, _, _, critical = _schedule(request2, {phase["id"]: (_sample(phase_rows.get(phase["prior_phase"], overall), p80_index, identities["seed"], phase["id"]) if phase["owner"] == "autonomous_agent" else _sample(_quantiles(phase["external_wait_seconds"], "wait"), p80_index, identities["seed"], phase["id"])) for phase in phases})
    return {**identities, "headline": {"scope_summary": f"{request2['project_type']} {request2['artifact_kind']}", "completion_boundary": request2["requested_completion_boundary"], "focused_agent_wall_clock_hours": {"p50": _hours(_nearest(list(focused), 50)), "p80": _hours(_nearest(list(focused), 80)), "p95": _hours(_nearest(list(focused), 95))}, "calendar_elapsed_hours": {"p50": _hours(_nearest(list(calendar), 50)), "p80": _hours(_nearest(list(calendar), 80)), "p95": _hours(_nearest(list(calendar), 95))}, "api_equivalent_cost_current": cost, "unpriced_basis_points": unpriced, "calibration": {"cohort": node["hierarchy_node"], "path": path, "sample_count": node["sample_count"], "effective_sample_size": node["effective_sample_size"], "confidence": "empirical"}, "pricing": {"state": sorted({provider["status"] for provider in pricing2["providers"].values()}), "last_successful_official_retrieval_date": max((provider["last_successful_official_date"] for provider in pricing2["providers"].values() if provider["last_successful_official_date"] is not None), default=None)}, "assumptions": list(request2["assumptions"]), "critical_path": critical, "planned_concurrency": scheduled_request["max_agent_concurrency"], "uncertainty_drivers": (["overall_allocated"] if any(phase["prior_phase"] not in phase_rows for phase in phases if phase["owner"] == "autonomous_agent") else []) + (["unpriced_routes"] if unpriced else []), "prerequisites": [], "evidence_coverage_basis_points": 10_000 - unpriced}, "detail": {"focused_agent_wall_clock_seconds": {"p50": _nearest(list(focused), 50), "p80": _nearest(list(focused), 80), "p95": _nearest(list(focused), 95)}, "summed_agent_runtime_seconds": {"p50": _nearest(list(runtime), 50), "p80": _nearest(list(runtime), 80), "p95": _nearest(list(runtime), 95)}, "calendar_elapsed_seconds": {"p50": _nearest(list(calendar), 50), "p80": _nearest(list(calendar), 80), "p95": _nearest(list(calendar), 95)}, "quota_delay_seconds": {"p50": _nearest(quota_delays, 50), "p80": _nearest(quota_delays, 80), "p95": _nearest(quota_delays, 95)}, "actual_marginal_cash_status": "unknown", "quota_coverage": "known" if all(provider["status"] in {"official", "estimated_stale"} for provider in quota2["providers"].values()) else "unknown", "cohort_path": path}, "labels": {"api_equivalent": "not billed cash", "non_additivity": "current_api_equivalent_and_actual_cash_are_separate"}}


def reconcile(prior_result: Mapping[str, object], actual: Mapping[str, object], pricing: Mapping[str, object]) -> dict[str, object]:
    prior = _mapping(dict(prior_result), "prior_result"); actual2 = _exact(dict(actual), {"schema_version", "completion_boundary", "focused_agent_wall_clock_seconds", "calendar_elapsed_seconds", "summed_agent_runtime_seconds", "token_usage", "wait_seconds", "actual_marginal_cash", "execution_era_pricing", "persistence_consent"}, "actual", {"schema_version", "completion_boundary", "focused_agent_wall_clock_seconds", "calendar_elapsed_seconds", "summed_agent_runtime_seconds", "token_usage", "wait_seconds", "actual_marginal_cash", "persistence_consent"})
    if actual2["schema_version"] != 1 or actual2["completion_boundary"] not in _BOUNDARIES or type(actual2["persistence_consent"]) is not bool: raise EstimationError("actual evidence is invalid")
    for field in ("focused_agent_wall_clock_seconds", "calendar_elapsed_seconds", "summed_agent_runtime_seconds", "wait_seconds"): _integer(actual2[field], f"actual.{field}")
    cash = _exact(actual2["actual_marginal_cash"], {"status", "amount_microusd", "evidence"}, "actual.actual_marginal_cash", {"status"})
    if cash["status"] not in {"authoritative", "operator_supplied", "subscription_zero", "unknown"}: raise EstimationError("actual cash status is invalid")
    if cash["status"] in {"authoritative", "operator_supplied"}: _integer(cash.get("amount_microusd"), "actual cash amount")
    if cash["status"] == "subscription_zero" and cash.get("amount_microusd", 0) != 0: raise EstimationError("subscription zero cash must be zero")
    validate_pricing(dict(pricing))
    planned = prior.get("detail", {}).get("calendar_elapsed_seconds", {}).get("p50")
    if type(planned) is not int: raise EstimationError("prior result lacks calendar estimate")
    return {"schema_version": 1, "status": "reconciled", "scope_hash": prior.get("scope_hash"), "duration_error_seconds": actual2["calendar_elapsed_seconds"] - planned, "absolute_duration_error_seconds": abs(actual2["calendar_elapsed_seconds"] - planned), "actual_marginal_cash_status": cash["status"], "labels": {"api_equivalent": "not billed cash", "non_additivity": "current_api_equivalent_and_actual_cash_are_separate"}}


class _DuplicateKey(ValueError): pass
def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result: raise _DuplicateKey("duplicate JSON key")
        result[key] = value
    return result


def _read_json(path: str) -> object:
    if path == "-":
        payload = sys.stdin.buffer.read(MAX_BYTES + 1)
    else:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES: raise EstimationError("input path is not a bounded regular file")
            payload = os.read(fd, MAX_BYTES + 1)
            if len(payload) > MAX_BYTES or os.read(fd, 1): raise EstimationError("input exceeds byte bound")
        finally: os.close(fd)
    if len(payload) > MAX_BYTES: raise EstimationError("input exceeds byte bound")
    try: return json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc: raise EstimationError("input is not finite JSON") from exc


def _write_exclusive(path: str, payload: bytes) -> None:
    if not path or "\x00" in path: raise EstimationError("output path is invalid")
    parent, name = os.path.split(path)
    if not name or name in {".", ".."}:
        raise EstimationError("output path is invalid")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    directory = os.open(parent or ".", directory_flags)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(name, flags, 0o600, dir_fd=directory)
    except BaseException:
        os.close(directory)
        raise
    try:
        written = os.write(fd, payload)
        if written != len(payload): raise EstimationError("output write was short")
        os.fsync(fd)
    except BaseException:
        os.close(fd); os.unlink(name, dir_fd=directory); os.close(directory); raise
    else:
        os.close(fd)
    try:
        read_fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), dir_fd=directory)
        try:
            if not stat.S_ISREG(os.fstat(read_fd).st_mode) or os.read(read_fd, len(payload) + 1) != payload:
                raise EstimationError("output readback failed")
        finally:
            os.close(read_fd)
    except BaseException:
        os.unlink(name, dir_fd=directory); os.close(directory); raise
    os.close(directory)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="project_estimation.py")
    sub = parser.add_subparsers(dest="command", required=True)
    estimate_parser = sub.add_parser("estimate")
    for name in ("request", "prior", "pricing", "quota"): estimate_parser.add_argument(f"--{name}", required=True)
    estimate_parser.add_argument("--out")
    reconcile_parser = sub.add_parser("reconcile")
    for name in ("prior-result", "actual", "pricing"): reconcile_parser.add_argument(f"--{name}", required=True)
    reconcile_parser.add_argument("--out")
    try:
        args = parser.parse_args(argv)
        paths = [value for key, value in vars(args).items() if key not in {"command", "out"}]
        if paths.count("-") > 1: raise EstimationError("at most one input may be stdin")
        if args.command == "estimate":
            request = _read_json(args.request); result = estimate(request, _read_json(args.prior), _read_json(args.pricing), _read_json(args.quota))
            if args.out and not request.get("persistence_consent", False): raise EstimationError("output requires persistence consent")
        else:
            actual = _read_json(args.actual); result = reconcile(_read_json(args.prior_result), actual, _read_json(args.pricing))
            if args.out and not actual.get("persistence_consent", False): raise EstimationError("output requires persistence consent")
        payload = _canonical(result) + b"\n"
        if args.out: _write_exclusive(args.out, payload)
        else: sys.stdout.buffer.write(payload)
        return 0
    except (EstimationError, OSError) as exc:
        print(f"project_estimation: {exc}", file=sys.stderr); return 2


if __name__ == "__main__": raise SystemExit(main())
