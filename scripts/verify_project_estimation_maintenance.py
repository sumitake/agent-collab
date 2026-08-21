#!/usr/bin/env python3
"""Fail-closed admission of the public project-estimation maintenance set.

The verifier intentionally uses direct, bounded semantic checks instead of a
partial JSON-Schema interpreter.  The schema files remain part of the closed
archive and are checked for closedness; this module is the executable contract.
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping


PLUGIN = "agent-collab"
SCHEMA_NAMES = (
    "estimate-request.schema.json", "estimate-result.schema.json", "aggregate-prior.schema.json",
    "pricing-snapshot.schema.json", "quota-snapshot.schema.json", "maintenance-receipt.schema.json",
    "operator-notification.schema.json",
)
DATA_NAMES = ("aggregate-prior.json", "pricing-snapshot.json", "quota-snapshot.json", "maintenance-receipt.json")
OPTIONAL_DATA_NAME = "operator-notification.json"
PUBLIC_ESTIMATION_MEMBERS: tuple[Path, ...] = tuple(Path("project-estimation-data") / name for name in (*SCHEMA_NAMES, *DATA_NAMES, OPTIONAL_DATA_NAME))
_MAX_BYTES = 1_048_576
_MAX_ENTRIES = 64
_MAX_DEPTH = 32
_MAX_ARRAY = 10_000
_SHA_HEX = set("0123456789abcdef")


class _DuplicateKey(ValueError):
    pass


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _json(payload: bytes, *, name: str) -> object:
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_object_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON value {value}")))
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{name} is not bounded, finite JSON") from exc
    stack: list[tuple[object, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > _MAX_DEPTH:
            raise ValueError(f"{name} exceeds JSON depth bound")
        if isinstance(item, dict):
            if len(item) > _MAX_ARRAY:
                raise ValueError(f"{name} exceeds object bound")
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            if len(item) > _MAX_ARRAY:
                raise ValueError(f"{name} exceeds array bound")
            stack.extend((child, depth + 1) for child in item)
    return value


def _sha(value: object, *, field: str) -> str:
    if type(value) is not str or len(value) != 64 or any(char not in _SHA_HEX for char in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _string(value: object, *, field: str, maximum: int = 256) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise ValueError(f"{field} must be a bounded string")
    return value


def _integer(value: object, *, field: str, minimum: int = 0, maximum: int = 1_000_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{field} must be an integer between {minimum} and {maximum}")
    return value


def _date(value: object, *, field: str) -> _datetime.date:
    if type(value) is not str:
        raise ValueError(f"{field} must be a canonical ISO date")
    try:
        parsed = _datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a canonical ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be a canonical ISO date")
    return parsed


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _exact(value: Mapping[str, object], fields: set[str], *, required: set[str] | None = None, field: str) -> None:
    unknown = sorted(set(value) - fields)
    missing = sorted((required or fields) - set(value))
    if unknown:
        raise ValueError(f"{field} has unknown field {unknown[0]}")
    if missing:
        raise ValueError(f"{field} is missing field {missing[0]}")


def _open_dir_chain(root: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    raw = os.fspath(root)
    if "\x00" in raw:
        raise ValueError("project-estimation root contains NUL")
    parts = list(root.parts)
    if root.is_absolute():
        fd = os.open(os.sep, flags)
        parts = [part for part in parts if part not in {os.sep, ""}]
    else:
        if ".." in parts:
            raise ValueError("relative project-estimation root may not contain ..")
        fd = os.open(".", flags)
        parts = [part for part in parts if part not in {"", "."}]
    try:
        for component in (*parts, "plugins", PLUGIN, "project-estimation-data"):
            try:
                next_fd = os.open(component, flags, dir_fd=fd)
            except OSError as exc:
                raise ValueError(f"project-estimation root component is not a real directory: {component}") from exc
            os.close(fd)
            fd = next_fd
            if not stat.S_ISDIR(os.fstat(fd).st_mode):
                raise ValueError(f"project-estimation component is not a directory: {component}")
        return fd
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _names(directory_fd: int) -> set[str]:
    found: set[str] = set()
    try:
        iterator = os.scandir(directory_fd)
        try:
            for entry in iterator:
                if len(found) >= _MAX_ENTRIES:
                    raise ValueError("project-estimation directory exceeds entry bound")
                found.add(entry.name)
        finally:
            iterator.close()
    except OSError as exc:
        raise ValueError("project-estimation directory cannot be enumerated") from exc
    return found


def _read(directory_fd: int, name: str) -> tuple[bytes, str, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise ValueError(f"cannot open public member: {name}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_BYTES:
            raise ValueError(f"public member is not a bounded regular file: {name}")
        remaining = before.st_size
        payload = bytearray()
        digest = hashlib.sha256()
        while remaining:
            chunk = os.read(fd, min(65_536, remaining))
            if not chunk:
                raise ValueError(f"public member was truncated: {name}")
            payload.extend(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise ValueError(f"public member grew during admission: {name}")
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise ValueError(f"public member changed during admission: {name}")
        return bytes(payload), digest.hexdigest(), len(payload)
    except OSError as exc:
        raise ValueError(f"cannot read public member: {name}") from exc
    finally:
        os.close(fd)


def _closed_schema(value: object, *, name: str) -> None:
    schema = _mapping(value, field=name)
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise ValueError(f"{name} must be a closed object schema")
    allowed = {"$schema", "$id", "$ref", "type", "additionalProperties", "required", "properties", "patternProperties", "$defs", "const", "enum", "pattern", "format", "minimum", "maximum", "minItems", "maxItems", "minLength", "maxLength", "uniqueItems", "items", "anyOf", "minProperties", "maxProperties"}
    stack: list[object] = [schema]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if set(item) - allowed:
                raise ValueError(f"{name} contains unsupported schema keyword")
            if item.get("type") == "object" and item.get("additionalProperties") is not False:
                raise ValueError(f"{name} contains an open object")
            if item.get("type") == "object" and isinstance(item.get("required"), list) and isinstance(item.get("properties"), dict):
                missing = sorted(set(item["required"]) - set(item["properties"]))
                if missing:
                    raise ValueError(f"{name} required field is not declared: {missing[0]}")
            stack.extend(item["properties"].values()) if isinstance(item.get("properties"), dict) else None
            stack.extend(item["patternProperties"].values()) if isinstance(item.get("patternProperties"), dict) else None
            stack.extend(item["$defs"].values()) if isinstance(item.get("$defs"), dict) else None
            for key, child in item.items():
                if key not in {"properties", "patternProperties", "$defs"}:
                    stack.append(child)
        elif isinstance(item, list):
            stack.extend(item)


def _quantiles(value: object, *, field: str, category: str) -> None:
    rows = value if isinstance(value, list) else None
    if rows is None or len(rows) > _MAX_ARRAY:
        raise ValueError(f"{field} must be a bounded array")
    seen: set[str] = set()
    for index, raw in enumerate(rows):
        row = _mapping(raw, field=f"{field}[{index}]")
        _exact(row, {category, "p50", "p80", "p95"}, field=f"{field}[{index}]")
        identity = _string(row[category], field=f"{field}[{index}].{category}")
        if category == "phase" and identity not in {"overall", "primary", "delegation", "review", "test", "release", "deployment", "rework"}:
            raise ValueError(f"{field} contains an unsupported phase")
        if category == "kind" and identity not in {"review", "rework"}:
            raise ValueError(f"{field} contains an unsupported kind")
        if identity in seen:
            raise ValueError(f"{field} identities must be unique")
        seen.add(identity)
        p50, p80, p95 = (_integer(row[name], field=f"{field}[{index}].{name}") for name in ("p50", "p80", "p95"))
        if not p50 <= p80 <= p95:
            raise ValueError(f"{field} quantiles are unordered")


def _aggregate(value: object, *, release_hash: str, today: _datetime.date, receipt: Mapping[str, object]) -> None:
    top = _mapping(value, field="aggregate-prior")
    fields = {"schema_version", "estimator_method_version", "generated_date", "source_cutoff_date", "policy_version", "policy_sha256", "seed", "source_manifest_sha256", "nodes"}
    _exact(top, fields, field="aggregate-prior")
    if top["schema_version"] != 1 or top["estimator_method_version"] != "empirical-v2":
        raise ValueError("aggregate-prior version is unsupported")
    generated = _date(top["generated_date"], field="aggregate.generated_date")
    cutoff = _date(top["source_cutoff_date"], field="aggregate.source_cutoff_date")
    if cutoff > generated or generated > today:
        raise ValueError("aggregate dates are outside the release window")
    if (top["estimator_method_version"], top["policy_version"], top["policy_sha256"], top["seed"], top["source_manifest_sha256"], top["generated_date"], top["source_cutoff_date"]) != (receipt["estimator_method_version"], receipt["calibration_policy_version"], receipt["calibration_policy_sha256"], receipt["seed"], receipt["source_manifest_sha256"], receipt["original_calibration_date"], receipt["source_cutoff_date"]):
        raise ValueError("aggregate identity does not match receipt")
    _string(top["policy_version"], field="aggregate.policy_version")
    _sha(top["policy_sha256"], field="aggregate.policy_sha256")
    _integer(top["seed"], field="aggregate.seed", maximum=2_147_483_647)
    _sha(top["source_manifest_sha256"], field="aggregate.source_manifest_sha256")
    nodes = top["nodes"]
    if not isinstance(nodes, list) or not nodes or len(nodes) > _MAX_ARRAY:
        raise ValueError("aggregate nodes must be a bounded non-empty array")
    names: list[str] = []
    parents: dict[str, str | None] = {}
    for index, raw in enumerate(nodes):
        node = _mapping(raw, field=f"aggregate.nodes[{index}]")
        allowed = {"schema_version", "estimator_method_version", "generated_date", "source_cutoff_date", "hierarchy_node", "fallback_parent", "sample_count", "effective_sample_size", "aggregate_sha256", "release_manifest_sha256", "source_eras", "phase_duration_quantiles", "token_class_quantiles", "rework_review_quantiles", "wait_class_quantiles", "calibration_quality", "drift_indicators", "uncertainty_floors", "pricing_snapshot"}
        required = {"schema_version", "estimator_method_version", "generated_date", "source_cutoff_date", "hierarchy_node", "sample_count", "effective_sample_size", "aggregate_sha256", "release_manifest_sha256"}
        _exact(node, allowed, required=required, field=f"aggregate.nodes[{index}]")
        if node["schema_version"] != 1 or node["estimator_method_version"] != receipt["estimator_method_version"]:
            raise ValueError("aggregate node schema version is unsupported")
        _string(node["estimator_method_version"], field="aggregate.node.method")
        original_date = _date(receipt["original_calibration_date"], field="receipt.original_calibration_date")
        if _date(node["generated_date"], field="aggregate.node.generated_date") != original_date:
            raise ValueError("aggregate node generated date does not match receipt")
        if _date(node["source_cutoff_date"], field="aggregate.node.source_cutoff_date") != _date(receipt["source_cutoff_date"], field="receipt.source_cutoff_date"):
            raise ValueError("aggregate node source cutoff does not match receipt")
        name = _string(node["hierarchy_node"], field="aggregate.hierarchy_node")
        names.append(name)
        parent = node.get("fallback_parent")
        if parent is not None:
            parent = _string(parent, field="aggregate.fallback_parent")
        parents[name] = parent
        if _integer(node["sample_count"], field="aggregate.sample_count") < 20:
            raise ValueError("aggregate sample_count is below privacy floor")
        _integer(node["effective_sample_size"], field="aggregate.effective_sample_size")
        _sha(node["aggregate_sha256"], field="aggregate.aggregate_sha256")
        if node["release_manifest_sha256"] != release_hash:
            raise ValueError("aggregate release binding does not match receipt")
        for field, category in (("phase_duration_quantiles", "phase"), ("token_class_quantiles", "token_class"), ("rework_review_quantiles", "kind"), ("wait_class_quantiles", "wait_class")):
            if field in node:
                _quantiles(node[field], field=f"aggregate.{field}", category=category)
    if names != sorted(names) or len(names) != len(set(names)):
        raise ValueError("aggregate hierarchy nodes must be sorted and unique")
    state: dict[str, int] = {}
    for name in parents:
        state.setdefault(name, 0)
    for name in parents:
        parent = parents[name]
        if parent is not None and parent not in parents:
            raise ValueError("aggregate fallback parent is absent")
    for origin in parents:
        if state[origin] != 0:
            continue
        path: list[str] = []
        current: str | None = origin
        while current is not None and state[current] == 0:
            state[current] = 1
            path.append(current)
            current = parents[current]
        if current is not None and state[current] == 1:
            raise ValueError("aggregate fallback cycle detected")
        for item in reversed(path):
            state[item] = 2


def _record(value: object, *, field: str, kind: str) -> None:
    row = _mapping(value, field=field)
    common = {"record_id", "model", "modality", "tier", "modifiers", "approved_value_sha256"}
    fields = common | ({"token_class", "currency", "unit", "amount_microusd", "amount_text"} if kind == "pricing" else {"limit_kind", "limit_value", "window_seconds", "cooldown_seconds"})
    _exact(row, fields, field=field)
    for name in ("record_id", "model", "modality", "tier"):
        _string(row[name], field=f"{field}.{name}", maximum=128)
    if kind == "pricing":
        for name in ("token_class", "currency", "unit", "amount_text"):
            _string(row[name], field=f"{field}.{name}", maximum=128)
        _integer(row["amount_microusd"], field=f"{field}.amount_microusd", maximum=1_000_000_000_000_000)
    else:
        _string(row["limit_kind"], field=f"{field}.limit_kind", maximum=64)
        if row["limit_kind"] not in {"rpm", "tpm", "concurrency", "subscription_5_hour", "subscription_weekly", "subscription_monthly", "cooldown"}:
            raise ValueError(f"{field}.limit_kind is unsupported")
        expected_window = {"subscription_5_hour": 18_000, "subscription_weekly": 604_800, "subscription_monthly": 2_592_000}
        if row["limit_kind"] in expected_window and row["window_seconds"] != expected_window[row["limit_kind"]]:
            raise ValueError(f"{field}.window_seconds does not match subscription window")
        if row["limit_kind"] == "cooldown" and row["cooldown_seconds"] <= 0:
            raise ValueError(f"{field}.cooldown_seconds must be positive for cooldown")
        if row["limit_kind"] in {"rpm", "tpm"} and row["window_seconds"] != 60:
            raise ValueError(f"{field}.window_seconds must be 60")
        if row["limit_kind"] == "concurrency" and row["window_seconds"] is not None:
            raise ValueError(f"{field}.window_seconds must be null")
        _integer(row["limit_value"], field=f"{field}.limit_value")
        if row["window_seconds"] is not None:
            _integer(row["window_seconds"], field=f"{field}.window_seconds", minimum=1)
        _integer(row["cooldown_seconds"], field=f"{field}.cooldown_seconds")
    modifiers = row["modifiers"]
    if not isinstance(modifiers, list) or len(modifiers) > 100 or any(type(item) is not str or not item or len(item) > 128 for item in modifiers):
        raise ValueError(f"{field}.modifiers is invalid")
    projected = {key: item for key, item in row.items() if key != "approved_value_sha256"}
    if row["approved_value_sha256"] != hashlib.sha256(_canonical(projected)).hexdigest():
        raise ValueError(f"{field}.approved_value_sha256 does not match record")


def _snapshot(value: object, *, kind: str, today: _datetime.date, threshold: int) -> tuple[dict[str, object], bool]:
    result = _mapping(value, field=f"{kind}-snapshot")
    fields = {"schema_version", "kind", "policy_version", "policy_sha256", "retrieved_date", "providers", "operator_notification_required", "material_unpriced", "uncertainty_basis_points"}
    _exact(result, fields, field=f"{kind}-snapshot")
    if result["schema_version"] != 1 or result["kind"] != kind:
        raise ValueError(f"{kind} snapshot version or kind is invalid")
    _string(result["policy_version"], field=f"{kind}.policy_version")
    _sha(result["policy_sha256"], field=f"{kind}.policy_sha256")
    retrieved = _date(result["retrieved_date"], field=f"{kind}.retrieved_date")
    if retrieved > today:
        raise ValueError(f"{kind} retrieved date is in the future")
    if type(result["operator_notification_required"]) is not bool or type(result["material_unpriced"]) is not bool:
        raise ValueError(f"{kind} flags must be boolean")
    _integer(result["uncertainty_basis_points"], field=f"{kind}.uncertainty_basis_points", maximum=10_000)
    providers = _mapping(result["providers"], field=f"{kind}.providers")
    if not providers or len(providers) > 100:
        raise ValueError(f"{kind} providers are invalid")
    unresolved = False
    unresolved_share = 0
    total_share = 0
    provider_fields = {"provider", "status", "retrieved_date", "last_successful_official_date", "original_last_good_date", "values", "value_sha256", "source_url_sha256", "final_url_sha256", "redirect_chain_sha256", "content_type", "elapsed_class", "failure_class", "material_share_basis_points"}
    statuses = {"official", "estimated_stale", "review_required", "unpriced", "unknown"}
    for provider, raw in sorted(providers.items()):
        row = _mapping(raw, field=f"{kind}.{provider}")
        _exact(row, provider_fields, field=f"{kind}.{provider}")
        if row["provider"] != provider or row["status"] not in statuses:
            raise ValueError(f"{kind}.{provider} identity or status is invalid")
        status = str(row["status"])
        for name in ("retrieved_date", "last_successful_official_date", "original_last_good_date"):
            item = row[name]
            if item is not None:
                item_date = _date(item, field=f"{kind}.{provider}.{name}")
                if item_date > retrieved:
                    raise ValueError(f"{kind}.{provider}.{name} is after retrieval")
        values = row["values"]
        if not isinstance(values, list) or len(values) > _MAX_ARRAY:
            raise ValueError(f"{kind}.{provider}.values is invalid")
        ids: set[str] = set()
        for index, item in enumerate(values):
            _record(item, field=f"{kind}.{provider}.values[{index}]", kind=kind)
            record_id = str(item["record_id"])
            if record_id in ids:
                raise ValueError(f"{kind}.{provider} record identities are not unique")
            ids.add(record_id)
        if values:
            if row["value_sha256"] != hashlib.sha256(_canonical(values)).hexdigest():
                raise ValueError(f"{kind}.{provider}.value_sha256 is incorrect")
        elif row["value_sha256"] is not None:
            raise ValueError(f"{kind}.{provider}.empty values must have null hash")
        for name in ("source_url_sha256", "final_url_sha256", "redirect_chain_sha256"):
            if row[name] is not None:
                _sha(row[name], field=f"{kind}.{provider}.{name}")
        for name in ("content_type", "elapsed_class", "failure_class"):
            if row[name] is not None:
                _string(row[name], field=f"{kind}.{provider}.{name}", maximum=128)
        share = _integer(row["material_share_basis_points"], field=f"{kind}.{provider}.material_share_basis_points", maximum=10_000)
        total_share += share
        if status == "official":
            if not values or row["retrieved_date"] != result["retrieved_date"] or row["last_successful_official_date"] != row["retrieved_date"] or row["original_last_good_date"] is not None or row["failure_class"] is not None or any(row[name] is None for name in ("source_url_sha256", "final_url_sha256", "redirect_chain_sha256", "content_type", "elapsed_class")):
                raise ValueError(f"{kind}.{provider} official evidence is incomplete")
            if (today - _date(row["retrieved_date"], field="retrieved_date")).days > 90:
                raise ValueError(f"{kind}.{provider} official evidence is stale")
        elif status == "estimated_stale":
            if not values or row["retrieved_date"] is None or row["last_successful_official_date"] is None or row["original_last_good_date"] != row["last_successful_official_date"] or row["failure_class"] is None or any(row[name] is None for name in ("source_url_sha256", "final_url_sha256", "redirect_chain_sha256", "content_type", "elapsed_class")):
                raise ValueError(f"{kind}.{provider} stale evidence is incomplete")
            if (today - _date(row["original_last_good_date"], field="original_last_good_date")).days > 90:
                raise ValueError(f"{kind}.{provider} stale evidence is expired")
            unresolved = True
        else:
            if values or row["retrieved_date"] is not None or row["last_successful_official_date"] is not None or row["original_last_good_date"] is not None or row["failure_class"] is None or any(row[name] is not None for name in ("source_url_sha256", "final_url_sha256", "redirect_chain_sha256", "content_type", "elapsed_class")):
                raise ValueError(f"{kind}.{provider} unresolved evidence is inconsistent")
            if kind == "pricing" and status == "unknown":
                raise ValueError("pricing cannot use unknown status")
            if kind == "quota" and status not in {"unknown", "review_required"}:
                raise ValueError("quota unresolved status is invalid")
            unresolved = True
        if status in {"unpriced", "review_required"}:
            unresolved_share += share
    if kind == "pricing" and total_share != 10_000:
        raise ValueError("pricing material shares must total 10000")
    expected_material = kind == "pricing" and unresolved_share >= threshold and unresolved_share > 0
    if result["material_unpriced"] is not expected_material or result["material_unpriced"]:
        raise ValueError(f"{kind}.material_unpriced is inconsistent or material")
    if any(row["status"] == "review_required" for row in providers.values()):
        raise ValueError(f"{kind} contains review_required evidence")
    if result["operator_notification_required"] is not unresolved or ((result["uncertainty_basis_points"] == 0) is unresolved):
        raise ValueError(f"{kind} notification or uncertainty flags are inconsistent")
    return dict(result), unresolved


def _notification(value: object, *, pricing: Mapping[str, object], quota: Mapping[str, object], today: _datetime.date) -> None:
    row = _mapping(value, field="operator-notification")
    fields = {"schema_version", "generated_date", "unresolved", "pricing_coverage_basis_points", "quota_coverage_basis_points", "decision"}
    _exact(row, fields, field="operator-notification")
    if row["schema_version"] != 1 or _date(row["generated_date"], field="notification.generated_date") > today:
        raise ValueError("operator notification version/date is invalid")
    for name in ("pricing_coverage_basis_points", "quota_coverage_basis_points"):
        _integer(row[name], field=f"notification.{name}", maximum=10_000)
    if row["decision"] not in {"stale_fallback", "unpriced_block", "unpriced_immaterial", "review_required_block", "quota_unknown", "mixed_fallback"}:
        raise ValueError("operator notification decision is invalid")
    unresolved = row["unresolved"]
    if not isinstance(unresolved, list) or not unresolved or len(unresolved) > 100:
        raise ValueError("operator notification unresolved list is invalid")
    expected: list[dict[str, object]] = []
    for kind, result in (("pricing", pricing), ("quota", quota)):
        for provider, item in sorted(_mapping(result["providers"], field=f"{kind}.providers").items()):
            if item["status"] != "official":
                expected.append({"provider": provider, "kind": kind, "original_date": item["original_last_good_date"], "failure_class": item["failure_class"], "decision": item["status"]})
    for index, item in enumerate(unresolved):
        candidate = _mapping(item, field=f"notification.unresolved[{index}]")
        _exact(candidate, {"provider", "kind", "original_date", "failure_class", "decision"}, field=f"notification.unresolved[{index}]")
        _string(candidate["provider"], field="notification.provider", maximum=128)
        if candidate["kind"] not in {"pricing", "quota"} or candidate["decision"] not in {"estimated_stale", "unpriced", "unknown", "review_required"}:
            raise ValueError("operator notification unresolved row is invalid")
        if candidate["original_date"] is not None:
            _date(candidate["original_date"], field="notification.original_date")
        _string(candidate["failure_class"], field="notification.failure_class", maximum=128)
    if unresolved != sorted(unresolved, key=lambda item: (str(item["kind"]), str(item["provider"]))):
        raise ValueError("operator notification unresolved rows must be sorted")
    if unresolved != expected:
        raise ValueError("operator notification does not cross-bind provider states")
    pricing_rows = list(_mapping(pricing["providers"], field="pricing.providers").values())
    quota_rows = list(_mapping(quota["providers"], field="quota.providers").values())
    pricing_coverage = min(10_000, sum(int(item["material_share_basis_points"]) for item in pricing_rows if item["status"] in {"official", "estimated_stale"}))
    quota_coverage = sum(item["status"] in {"official", "estimated_stale"} for item in quota_rows) * 10_000 // max(1, len(quota_rows))
    if row["pricing_coverage_basis_points"] != pricing_coverage or row["quota_coverage_basis_points"] != quota_coverage:
        raise ValueError("operator notification coverage does not cross-match provider results")
    decisions = {str(item["decision"]) for item in expected}
    if "review_required" in decisions:
        expected_decision = "review_required_block"
    elif "unpriced" in decisions:
        expected_decision = "unpriced_block" if pricing.get("material_unpriced") is True else "unpriced_immaterial"
    elif "unknown" in decisions and "estimated_stale" not in decisions:
        expected_decision = "quota_unknown"
    elif decisions == {"estimated_stale"}:
        expected_decision = "stale_fallback"
    else:
        expected_decision = "mixed_fallback"
    if row["decision"] != expected_decision:
        raise ValueError("operator notification decision does not cross-match provider results")


def verify_maintenance(root: Path, *, expected_version: str, today: _datetime.date | None = None) -> tuple[bool, list[str]]:
    today = today or _datetime.date.today()
    errors: list[str] = []
    fd: int | None = None
    try:
        fd = _open_dir_chain(root)
        actual = _names(fd)
        allowed_names = set(SCHEMA_NAMES) | set(DATA_NAMES) | {OPTIONAL_DATA_NAME}
        unexpected = sorted(actual - allowed_names)
        if unexpected:
            raise ValueError(f"maintenance inventory contains undeclared member: {unexpected[0]}")
        minimum = set(SCHEMA_NAMES) | set(DATA_NAMES)
        if not minimum <= actual:
            raise ValueError(f"maintenance inventory is missing {sorted(minimum - actual)[0]}")
        raw: dict[str, bytes] = {}
        digests: dict[str, str] = {}
        sizes: dict[str, int] = {}
        for name in sorted(actual):
            if name.lower().find("raw") >= 0 or name.lower().find("private") >= 0:
                raise ValueError(f"forbidden public member: {name}")
            payload, digest, size = _read(fd, name)
            raw[name], digests[name], sizes[name] = payload, digest, size
        schemas: dict[str, object] = {}
        for name in SCHEMA_NAMES:
            value = _json(raw[name], name=name)
            _closed_schema(value, name=name)
            schemas[name] = value
        receipt = _mapping(_json(raw["maintenance-receipt.json"], name="maintenance-receipt.json"), field="maintenance-receipt")
        if raw["maintenance-receipt.json"] != _canonical(receipt):
            raise ValueError("maintenance-receipt.json is not canonical JSON")
        _exact(receipt, {"schema_version", "version", "estimator_method_version", "calibration_policy_version", "calibration_policy_sha256", "pricing_policy_version", "pricing_policy_sha256", "pricing_registry_sha256", "quota_registry_sha256", "pricing_material_unpriced_threshold_basis_points", "seed", "repository_sha256", "collection_cutoff_date", "collection_result_sha256", "linkage_manifest_sha256", "completion_evidence_scope", "source_cutoff_date", "generated_date", "calibration_status", "original_calibration_date", "source_manifest_sha256", "calibration_candidate_sha256", "calibration_source_receipt_sha256", "backtest_outcome", "pricing_result_sha256", "quota_result_sha256", "notification_result", "release_manifest_sha256", "inventory", "receipt_sha256"}, field="maintenance-receipt")
        if receipt["schema_version"] != 2 or receipt["version"] != expected_version or receipt["estimator_method_version"] != "empirical-v2" or receipt["completion_evidence_scope"] != "github_merged_or_earlier":
            raise ValueError("maintenance receipt schema/version is invalid")
        for name in ("version", "estimator_method_version", "calibration_policy_version", "pricing_policy_version", "completion_evidence_scope"):
            _string(receipt[name], field=f"receipt.{name}", maximum=128)
        for name in ("calibration_policy_sha256", "pricing_policy_sha256", "pricing_registry_sha256", "quota_registry_sha256", "repository_sha256", "collection_result_sha256", "linkage_manifest_sha256", "source_manifest_sha256", "calibration_candidate_sha256", "pricing_result_sha256", "quota_result_sha256", "release_manifest_sha256", "receipt_sha256"):
            _sha(receipt[name], field=f"receipt.{name}")
        threshold = _integer(receipt["pricing_material_unpriced_threshold_basis_points"], field="receipt.threshold", minimum=1, maximum=10_000)
        _integer(receipt["seed"], field="receipt.seed", maximum=2_147_483_647)
        original = _date(receipt["original_calibration_date"], field="receipt.original_calibration_date")
        generated = _date(receipt["generated_date"], field="receipt.generated_date")
        source = _date(receipt["source_cutoff_date"], field="receipt.source_cutoff_date")
        collection = _date(receipt["collection_cutoff_date"], field="receipt.collection_cutoff_date")
        if collection > source or source > generated or generated > today or original > generated or (today - original).days > 60:
            raise ValueError("calibration/source dates violate freshness policy")
        if receipt["calibration_status"] not in {"fresh", "last_good"} or (receipt["calibration_status"] == "fresh" and (original != generated or receipt["calibration_source_receipt_sha256"] is not None)) or (receipt["calibration_status"] == "last_good" and receipt["calibration_source_receipt_sha256"] is None):
            raise ValueError("calibration status is inconsistent")
        if receipt["calibration_source_receipt_sha256"] is not None:
            _sha(receipt["calibration_source_receipt_sha256"], field="receipt.calibration_source_receipt_sha256")
        outcome = _mapping(receipt["backtest_outcome"], field="receipt.backtest_outcome")
        _exact(outcome, {"promotion_allowed", "baseline_duration_comparison", "baseline_token_comparison"}, field="receipt.backtest_outcome")
        if outcome["promotion_allowed"] is not True or outcome["baseline_duration_comparison"] not in {"performed", "not_applicable"} or outcome["baseline_token_comparison"] not in {"performed", "not_applicable", "no_shared_token_class"}:
            raise ValueError("receipt backtest outcome is invalid")
        pricing_document = _json(raw["pricing-snapshot.json"], name="pricing-snapshot.json")
        quota_document = _json(raw["quota-snapshot.json"], name="quota-snapshot.json")
        aggregate_document = _json(raw["aggregate-prior.json"], name="aggregate-prior.json")
        for name, document in (("pricing-snapshot.json", pricing_document), ("quota-snapshot.json", quota_document), ("aggregate-prior.json", aggregate_document)):
            if raw[name] != _canonical(document):
                raise ValueError(f"{name} is not canonical JSON")
        pricing, pricing_unresolved = _snapshot(pricing_document, kind="pricing", today=today, threshold=threshold)
        quota, quota_unresolved = _snapshot(quota_document, kind="quota", today=today, threshold=threshold)
        if pricing["policy_version"] != receipt["pricing_policy_version"] or pricing["policy_sha256"] != receipt["pricing_policy_sha256"] or quota["policy_version"] != receipt["pricing_policy_version"] or quota["policy_sha256"] != receipt["pricing_policy_sha256"]:
            raise ValueError("snapshot policy identity does not match receipt")
        if receipt["pricing_result_sha256"] != hashlib.sha256(_canonical(pricing)).hexdigest() or receipt["quota_result_sha256"] != hashlib.sha256(_canonical(quota)).hexdigest():
            raise ValueError("receipt snapshot result hash does not match")
        manifest_core = {key: value for key, value in receipt.items() if key not in {"release_manifest_sha256", "inventory", "receipt_sha256"}}
        if receipt["release_manifest_sha256"] != hashlib.sha256(_canonical(manifest_core)).hexdigest():
            raise ValueError("receipt release manifest digest is incorrect")
        release_hash = str(receipt["release_manifest_sha256"])
        _aggregate(aggregate_document, release_hash=release_hash, today=today, receipt=receipt)
        expected_notification = pricing_unresolved or quota_unresolved
        if receipt["notification_result"] not in {"not_required", "delivered"} or ((receipt["notification_result"] == "delivered") != expected_notification):
            raise ValueError("receipt notification result is inconsistent")
        if expected_notification:
            if OPTIONAL_DATA_NAME not in actual:
                raise ValueError("operator notification is required")
            notification_document = _json(raw[OPTIONAL_DATA_NAME], name=OPTIONAL_DATA_NAME)
            if raw[OPTIONAL_DATA_NAME] != _canonical(notification_document):
                raise ValueError("operator-notification.json is not canonical JSON")
            _notification(notification_document, pricing=pricing, quota=quota, today=today)
        elif OPTIONAL_DATA_NAME in actual:
            raise ValueError("operator notification is not permitted for an all-official snapshot")
        expected = set(SCHEMA_NAMES) | set(DATA_NAMES) | ({OPTIONAL_DATA_NAME} if expected_notification else set())
        if actual != expected:
            raise ValueError(f"maintenance inventory mismatch: expected {sorted(expected)}, got {sorted(actual)}")
        inventory = receipt["inventory"]
        if not isinstance(inventory, list) or len(inventory) > 4:
            raise ValueError("receipt inventory is invalid")
        inventory_names: list[str] = []
        for index, item in enumerate(inventory):
            row = _mapping(item, field=f"receipt.inventory[{index}]")
            _exact(row, {"name", "sha256", "size"}, field=f"receipt.inventory[{index}]")
            name = _string(row["name"], field="receipt.inventory.name", maximum=128)
            if name not in DATA_NAMES and name != OPTIONAL_DATA_NAME:
                raise ValueError("receipt inventory names an undeclared member")
            _sha(row["sha256"], field="receipt.inventory.sha256")
            _integer(row["size"], field="receipt.inventory.size", maximum=_MAX_BYTES)
            if row["sha256"] != digests[name] or row["size"] != sizes[name]:
                raise ValueError(f"receipt inventory binding is incorrect for {name}")
            inventory_names.append(name)
        expected_inventory = sorted(set(DATA_NAMES) - {"maintenance-receipt.json"} | ({OPTIONAL_DATA_NAME} if expected_notification else set()))
        if inventory_names != expected_inventory:
            raise ValueError("receipt inventory is not the exact data artifact set")
        if receipt["receipt_sha256"] != hashlib.sha256(_canonical({key: value for key, value in receipt.items() if key != "receipt_sha256"})).hexdigest():
            raise ValueError("maintenance receipt self hash is incorrect")
    except (OSError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"project-estimation maintenance verification failed: {exc}")
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
    return not errors, [f"FAIL  {error}" for error in errors] if errors else ["PASS  project-estimation maintenance receipt and closed inventory"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="verify public project-estimation maintenance evidence")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args(argv)
    ok, lines = verify_maintenance(args.root, expected_version=args.expected_version)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
