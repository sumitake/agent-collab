#!/usr/bin/env python3
"""Closed semantic coordinator for the co-packaged direct runtime.

The coordinator owns no route-health, exclusion, cooldown, or quarantine
state. Every accepted call delegates once to the direct runtime, so an
attempt-local failure cannot suppress a later caller-authorized request.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import select
import sys
import termios
import time
from typing import Any, Mapping


PLUGIN_ROOT = Path(__file__).resolve().parent
MAX_INPUT_BYTES = 48 * 1024 * 1024
MAX_DOCUMENTS = 64
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_PROMPT_BYTES = 1024 * 1024
MAX_TIMEOUT_MS = 600_000
_TTY_READ_CHUNK_BYTES = 64 * 1024
_TTY_FRAME_TIMEOUT_SECONDS = 120.0
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_COMMON_KEYS = {
    "request_id",
    "logical_action",
    "quality_profile",
    "effort_class",
    "target_agent",
    "timeout_ms",
    "prompt",
}
_READINESS_KEYS = {
    "operation",
    "request_id",
    "quality_profile",
    "effort_class",
    "timeout_ms",
}
_QUALITY_PROFILES = ("economical", "standard", "frontier")
_EFFORT_CLASSES = ("minimal", "standard", "maximum")
_EFFORT_RANK = {name: index for index, name in enumerate(_EFFORT_CLASSES)}
_CANONICAL_LOGICAL_AGENTS = frozenset(
    {
        "alibaba",
        "claude",
        "codex",
        "deepseek",
        "gemini",
        "grok",
        "moonshot",
        "zhipu",
    }
)
_OPTIONAL_CONTEXT_KEYS = frozenset(
    {"occupied_model_lineages", "evidence_anchors"}
)
_MAX_CONTEXT_ITEMS = 16
_MAX_REPOSITORY_PATH_BYTES = 4096
_MAX_DETAIL_FIELD = 64
_MAX_DETAIL_LIST = 16


class _InvalidRequest(ValueError):
    """A rejected request carrying an actionable, bounded reason.

    ``detail`` is a small, closed mapping (field name plus scalar constraints or
    a fixed admitted-value list) so a caller can correct the request in place
    instead of re-deriving it. It never echoes unbounded or untrusted content.
    """

    def __init__(self, error_code: str, detail: dict[str, object]) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.detail = detail


class _IncompleteTTYFrame(RuntimeError):
    """The terminal frame reached EOF or its total deadline before newline."""


def _field_name(value: object) -> str:
    """Return a bounded ASCII-printable rendering of a request key for diagnostics.

    Only ASCII printables (0x20-0x7E) survive, so a rejection can never reflect a
    C1 control or arbitrary Unicode from an attacker-controlled key back to the
    caller; the result is also length-bounded.
    """

    text = value if type(value) is str else repr(value)
    text = "".join(character for character in text if 0x20 <= ord(character) < 0x7F)
    return text[:_MAX_DETAIL_FIELD]


def _bounded_key_list(keys: object) -> list[str]:
    """Bounded, sorted, ASCII-printable key list for a 'detail' diagnostic.

    Bounds both each key (length) and the list cardinality, so a request with a
    huge or hostile key set cannot produce an oversized rejection payload.
    """

    names = sorted(_field_name(key) for key in keys)
    if len(names) > _MAX_DETAIL_LIST:
        return names[:_MAX_DETAIL_LIST] + [f"...(+{len(names) - _MAX_DETAIL_LIST} more)"]
    return names


def _bounded_scalar(value: object) -> object:
    """Return a bounded, safe echo of a caller value for the 'detail.given' field.

    Only small scalars pass through verbatim; anything unbounded, structured, or
    malformed collapses to a type label so a rejection can never reflect an
    arbitrary or oversized input payload back to the caller.
    """

    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        return value if -(10**15) <= value <= 10**15 else "int_out_of_range"
    if type(value) is str:
        return _field_name(value)
    return type(value).__name__


def _disposition(status: str) -> tuple[str, str]:
    """Classify a non-usable outcome so a caller cannot misread it.

    The single load-bearing invariant: an *attempt-local* outcome
    (``provider_error``/``teardown_error``) and an *overloaded* one
    (``protocol_error``) are never ``unavailable``; this matches the runtime
    contract that they do not establish route or provider unavailability, and is
    what stops a recoverable invocation error being reported as an outage.
    """

    if status in {"invalid_request", "capability_error", "output_limit"}:
        return "fix_request", (
            "The request as sent is not accepted (shape, target, action, effort, or size); "
            "adjust it per any 'detail'. This is not a provider outage; do not retry it unchanged."
        )
    if status in {"provider_error", "teardown_error"}:
        return "retry", (
            "Attempt-local failure. Per the runtime contract this does NOT establish provider "
            "unavailability; a fresh request may succeed. Do not report an outage from this alone."
        )
    if status in {"timeout", "cancelled"}:
        return "retry", (
            "The attempt did not finish. Retry with more time (raise timeout_ms toward the 600000ms "
            "cap) or a smaller scope. This is not a route-down signal."
        )
    if status == "protocol_error":
        return "inspect", (
            "Overloaded outcome: a transient broker-exchange failure OR a deterministic contract "
            "rejection. Inspect the specific diagnostic; do not assume an outage and do not blind-retry."
        )
    if status in {"auth_error", "quota_error"}:
        return "unavailable", (
            "Provider auth or quota is unavailable (operator action). Confirm with a direct probe "
            "before declaring a sustained outage."
        )
    if status in {
        "integrity_error",
        "manifest_invalid",
        "path_invalid",
        "signature_error",
        "platform_unsupported",
    }:
        return "unavailable", "Runtime integrity, identity, or platform is unavailable; not a request problem."
    if status == "unavailable":
        return "unavailable", (
            "Runtime, host, or route is unavailable, OR the request is ineligible at the requested "
            "depth. Check readiness for this action at effort_class=maximum before concluding an outage."
        )
    return "inspect", "Unrecognized outcome; inspect the diagnostic. Do not assume provider unavailability."


def _reject_nonfinite(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def _closed_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("duplicate JSON object key")
        document[key] = value
    return document


def _decode_request(raw: bytes) -> object:
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_closed_json_object,
        parse_constant=_reject_nonfinite,
    )


def _record_normalization(
    normalized: list | None,
    *,
    field: str,
    before: object,
    after: object,
    reason: str,
) -> None:
    if normalized is not None:
        normalized.append(
            {
                "field": field,
                "from": _bounded_scalar(before),
                "to": after,
                "reason": reason,
            }
        )


def _ascii_token(value: object, admitted: object) -> object:
    """Normalize harmless ASCII presentation only when it lands exactly."""

    if type(value) is not str or not value.isascii():
        return value
    candidate = value.strip(" \t\r\n").lower()
    return candidate if candidate in admitted else value


def _is_one_edit_apart(left: str, right: str) -> bool:
    """Return whether two ASCII tokens differ by one bounded typing edit."""

    if left == right or abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences: list[int] = []
        for index, (left_character, right_character) in enumerate(zip(left, right)):
            if left_character != right_character:
                differences.append(index)
                if len(differences) > 2:
                    return False
        if len(differences) == 1:
            return True
        if len(differences) != 2:
            return False
        first, second = differences
        return (
            second == first + 1
            and left[first] == right[second]
            and left[second] == right[first]
        )

    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    short_index = long_index = 0
    skipped = False
    while short_index < len(shorter) and long_index < len(longer):
        if shorter[short_index] == longer[long_index]:
            short_index += 1
            long_index += 1
            continue
        if skipped:
            return False
        skipped = True
        long_index += 1
    return True


def _invocation_token(
    value: object, admitted: object
) -> tuple[object, str | None]:
    """Normalize a closed invocation token only when its meaning is unique."""

    if type(value) is not str or not value.isascii():
        return value, None
    candidate = value.strip(" \t\r\n").lower()
    if candidate in admitted:
        reason = None if candidate == value else "ascii_token_matches_closed_value"
        return candidate, reason

    canonical_values = tuple(
        token for token in admitted if type(token) is str and token.isascii()
    )
    if not canonical_values:
        return value, None
    shortest = min(len(token) for token in canonical_values)
    longest = max(len(token) for token in canonical_values)
    if len(candidate) < shortest - 1 or len(candidate) > longest + 1:
        return value, None
    matches = [
        token
        for token in canonical_values
        if _is_one_edit_apart(candidate, token)
    ]
    if len(matches) == 1:
        return matches[0], "unique_one_edit_closed_value"
    return value, None


def _logical_agents(wire: object) -> frozenset[str]:
    """Use the signed descriptor projection when present, else the v6 set."""

    projected = getattr(wire, "logical_agents", frozenset())
    return projected or _CANONICAL_LOGICAL_AGENTS


def _merge_legacy_field(
    document: dict[str, object],
    *,
    legacy: str,
    canonical: str,
    admitted: object,
    normalized: list | None,
) -> None:
    if legacy not in document:
        return
    legacy_raw = document[legacy]
    legacy_value, legacy_reason = _invocation_token(legacy_raw, admitted)
    if canonical in document:
        canonical_value, _canonical_reason = _invocation_token(
            document[canonical], admitted
        )
        if canonical_value != legacy_value:
            raise _InvalidRequest(
                "conflicting_fields",
                {"field": canonical, "conflicts_with": legacy},
            )
    else:
        document[canonical] = legacy_value
    document.pop(legacy)
    _record_normalization(
        normalized,
        field=canonical,
        before=(
            legacy_raw
            if legacy_reason == "unique_one_edit_closed_value"
            else f"legacy:{legacy}"
        ),
        after=legacy_value,
        reason=(
            legacy_reason
            if legacy_reason == "unique_one_edit_closed_value"
            else "exact_legacy_semantic_field"
        ),
    )


def _flatten_source(
    document: dict[str, object], *, normalized: list | None
) -> None:
    if "source" not in document:
        return
    source = document.pop("source")
    if type(source) is not dict:
        raise _InvalidRequest(
            "source_invalid", {"field": "source", "constraint": "closed object"}
        )
    raw_mode = source.get("mode")
    mode, mode_reason = _invocation_token(
        raw_mode, {"conceptual_prompt", "documents", "repository"}
    )
    if mode_reason == "unique_one_edit_closed_value":
        _record_normalization(
            normalized,
            field="source.mode",
            before=raw_mode,
            after=mode,
            reason=mode_reason,
        )
    if mode == "repository" and set(source) == {"mode", "repo_root"}:
        field, value = "repo_root", source["repo_root"]
    elif mode == "documents" and set(source) == {"mode", "documents"}:
        field, value = "documents", source["documents"]
    elif mode == "conceptual_prompt" and set(source) == {"mode"}:
        field, value = None, None
    else:
        raise _InvalidRequest(
            "source_invalid",
            {
                "field": "source",
                "constraint": "one exact repository, documents, or conceptual source",
            },
        )
    if field is not None:
        if field in document and document[field] != value:
            raise _InvalidRequest(
                "conflicting_fields", {"field": field, "conflicts_with": "source"}
            )
        document[field] = value
    _record_normalization(
        normalized,
        field="source",
        before="closed_source_object",
        after=mode,
        reason="flattened_public_source",
    )


def _canonicalize_request(
    document: object, wire: object, *, normalized: list | None
) -> dict[str, object]:
    """Recover identity-preserving request representations before validation."""

    if type(document) is not dict:
        raise _InvalidRequest(
            "request_not_object", {"reason": "request must be a JSON object"}
        )
    result = dict(document)
    operation_before = result.get("operation")
    operation, operation_reason = _invocation_token(operation_before, {"invoke"})
    if operation == "invoke":
        result.pop("operation")
        _record_normalization(
            normalized,
            field="operation",
            before=operation_before,
            after=None,
            reason=operation_reason or "default_invoke_operation",
        )
    _merge_legacy_field(
        result,
        legacy="action",
        canonical="logical_action",
        admitted=wire.logical_actions,
        normalized=normalized,
    )
    admitted_agents = _logical_agents(wire)
    _merge_legacy_field(
        result,
        legacy="route",
        canonical="target_agent",
        admitted=admitted_agents,
        normalized=normalized,
    )
    if "target_agent" not in result:
        result["target_agent"] = None
        _record_normalization(
            normalized,
            field="target_agent",
            before="missing",
            after=None,
            reason="missing_target_is_untargeted",
        )
    for field, admitted in (
        ("logical_action", wire.logical_actions),
        ("quality_profile", _QUALITY_PROFILES),
        ("effort_class", _EFFORT_CLASSES),
        ("target_agent", admitted_agents),
    ):
        if field not in result:
            continue
        before = result[field]
        after, reason = _invocation_token(before, admitted)
        if after != before:
            result[field] = after
            _record_normalization(
                normalized,
                field=field,
                before=before,
                after=after,
                reason=reason or "ascii_token_matches_closed_value",
            )
    _flatten_source(result, normalized=normalized)
    return result


def _verification_context(
    document: Mapping[str, object], wire: object, *, normalized: list | None
) -> tuple[list[str], list[dict[str, str]]]:
    occupied = document.get("occupied_model_lineages", [])
    anchors = document.get("evidence_anchors", [])
    if type(occupied) is not list or len(occupied) > _MAX_CONTEXT_ITEMS:
        raise _InvalidRequest(
            "occupied_model_lineages_invalid",
            {"field": "occupied_model_lineages", "constraint": "bounded unique array"},
        )
    admitted_lineages = getattr(wire, "model_lineages", frozenset())
    normalized_occupied: list[str] = []
    for index, raw_value in enumerate(occupied):
        value = _ascii_token(raw_value, admitted_lineages)
        if type(value) is not str or value not in admitted_lineages:
            if not admitted_lineages:
                raise _InvalidRequest(
                    "runtime_feature_unavailable",
                    {"field": "occupied_model_lineages", "required_wire_schema": 7},
                )
            raise _InvalidRequest(
                "occupied_model_lineages_invalid",
                {
                    "field": "occupied_model_lineages",
                    "admitted": _bounded_key_list(admitted_lineages),
                },
            )
        if value != raw_value:
            _record_normalization(
                normalized,
                field=f"occupied_model_lineages[{index}]",
                before=raw_value,
                after=value,
                reason="ascii_token_matches_closed_value",
            )
        if value in normalized_occupied:
            raise _InvalidRequest(
                "occupied_model_lineages_invalid",
                {"field": "occupied_model_lineages", "constraint": "unique values"},
            )
        normalized_occupied.append(value)

    if type(anchors) is not list or len(anchors) > _MAX_CONTEXT_ITEMS:
        raise _InvalidRequest(
            "evidence_anchors_invalid",
            {"field": "evidence_anchors", "constraint": "bounded unique array"},
        )
    normalized_anchors: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    if anchors and not getattr(wire, "logical_agents", frozenset()):
        raise _InvalidRequest(
            "runtime_feature_unavailable",
            {"field": "evidence_anchors", "required_wire_schema": 7},
        )
    for item in anchors:
        if type(item) is not dict or set(item) != {"id", "path"}:
            raise _InvalidRequest(
                "evidence_anchors_invalid",
                {"field": "evidence_anchors", "constraint": "closed id/path objects"},
            )
        anchor_id, path = item["id"], item["path"]
        if (
            type(anchor_id) is not str
            or _REQUEST_ID_RE.fullmatch(anchor_id) is None
            or anchor_id in seen_ids
            or type(path) is not str
            or not path
            or not path.isascii()
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in path)
            or len(path.encode("utf-8")) > _MAX_REPOSITORY_PATH_BYTES
        ):
            raise _InvalidRequest(
                "evidence_anchors_invalid",
                {"field": "evidence_anchors", "constraint": "unique id and safe relative path"},
            )
        relative = PurePosixPath(path)
        if (
            relative.is_absolute()
            or relative.as_posix() != path
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise _InvalidRequest(
                "evidence_anchors_invalid",
                {"field": "evidence_anchors", "constraint": "safe relative path"},
            )
        seen_ids.add(anchor_id)
        normalized_anchors.append({"id": anchor_id, "path": relative.as_posix()})
    return normalized_occupied, normalized_anchors


def _load(name: str, filename: str):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, PLUGIN_ROOT / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_runtime():
    return _load("agent_collab_semantic_runtime", "runtime_client.py")


def _load_host_policy():
    return _load("agent_collab_semantic_host_policy", "host_policy.py")


def _canonical_repo_root(value: object) -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise ValueError("repository action requires repo_root")
    path = Path(value)
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError("repo_root must be an absolute canonical path")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError("repo_root is unavailable") from None
    if resolved != path or not resolved.is_dir():
        raise ValueError("repo_root must be canonical and name a directory")
    return str(resolved)


def _documents(value: object) -> list[dict[str, str]]:
    if type(value) is not list or not 1 <= len(value) <= MAX_DOCUMENTS:
        raise ValueError("documents must be a non-empty bounded array")
    result: list[dict[str, str]] = []
    total = 0
    for item in value:
        if type(item) is not dict or set(item) != {"label", "content"}:
            raise ValueError("each document must contain only label and content")
        label, content = item["label"], item["content"]
        if type(label) is not str or not label or type(content) is not str:
            raise ValueError("document label and content must be UTF-8 strings")
        try:
            label_size = len(label.encode("utf-8"))
            content_size = len(content.encode("utf-8"))
        except UnicodeError:
            raise ValueError("document label and content must be valid UTF-8") from None
        if label_size > 4096 or any(ord(character) < 0x20 or ord(character) == 0x7F for character in label):
            raise ValueError("document label is invalid")
        if any((ord(character) < 0x20 and character not in "\t\n\r") or ord(character) == 0x7F for character in content):
            raise ValueError("document content contains a prohibited control")
        total += content_size
        if content_size > MAX_DOCUMENT_BYTES or total > MAX_DOCUMENT_BYTES:
            raise ValueError("documents exceed the content byte bound")
        result.append({"label": label, "content": content})
    return result


def _closure_error(
    document: dict, expected: set, action: str, primary_source: str | None
) -> _InvalidRequest:
    """Build an actionable 'not closed' rejection naming missing/unexpected keys."""

    keys = set(document)
    detail: dict[str, object] = {
        "field": "request_keys",
        "action": action,
        "missing": _bounded_key_list(expected - keys),
        "unexpected": _bounded_key_list(keys - expected),
    }
    if primary_source is not None and primary_source not in keys:
        detail["required_source"] = primary_source
        detail["expected_source_mode"] = (
            "repository" if primary_source == "repo_root" else "documents"
        )
    return _InvalidRequest("request_not_closed", detail)


def validate_request(
    document: object, wire: object, host: object, *, normalized: list | None = None
) -> dict[str, Any]:
    """Convert the closed coordinator request to the descriptor's native request.

    Rejections raise ``_InvalidRequest`` with a bounded, actionable ``detail`` so
    a caller can correct the request in place instead of re-deriving it.
    Identity-preserving compatibility rewrites are recorded in ``normalized``.
    Only an exact or uniquely one-edit-identifiable closed invocation value is
    rewritten. Open content, ambiguous values, aliases, authority, and security
    decisions are never guessed.
    """

    document = _canonicalize_request(document, wire, normalized=normalized)
    if not _COMMON_KEYS.issubset(document):
        raise _InvalidRequest(
            "missing_common_fields",
            {"missing": _bounded_key_list(_COMMON_KEYS - set(document))},
        )
    action = document.get("logical_action")
    if type(action) is not str or action not in wire.logical_actions:
        raise _InvalidRequest(
            "unknown_logical_action",
            {
                "field": "logical_action",
                "given": _bounded_scalar(action),
                "admitted": sorted(wire.logical_actions),
            },
        )
    source_mode = wire.logical_action_source_modes[action]
    optional = set(document) & _OPTIONAL_CONTEXT_KEYS
    if source_mode == "repository":
        expected = _COMMON_KEYS | {"repo_root"} | optional
        if set(document) != expected:
            raise _closure_error(document, expected, action, "repo_root")
        source = {"mode": "repository", "repo_root": _canonical_repo_root(document["repo_root"])}
    elif source_mode == "documents":
        expected = _COMMON_KEYS | {"documents"} | optional
        if set(document) != expected:
            raise _closure_error(document, expected, action, "documents")
        source = {"mode": "documents", "documents": _documents(document["documents"])}
    elif source_mode == "conceptual_prompt":
        expected = _COMMON_KEYS | optional
        if set(document) != expected:
            raise _closure_error(document, expected, action, None)
        source = {"mode": "conceptual_prompt"}
    else:
        raise _InvalidRequest(
            "unsupported_source_mode",
            {"field": "logical_action", "given": _bounded_scalar(action)},
        )

    request_id = document["request_id"]
    prompt = document["prompt"]
    timeout_ms = document["timeout_ms"]
    quality_profile = document["quality_profile"]
    effort_class = document["effort_class"]
    target_agent = document["target_agent"]
    author_lineage = getattr(host, "primary_family", "unknown")
    if type(request_id) is not str or _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise _InvalidRequest(
            "request_id_invalid",
            {"field": "request_id", "constraint": "1-128 chars of A-Za-z0-9._:-"},
        )
    if type(prompt) is not str or not prompt or len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise _InvalidRequest(
            "prompt_invalid",
            {"field": "prompt", "constraint": "non-empty UTF-8", "max_bytes": MAX_PROMPT_BYTES},
        )
    if type(timeout_ms) is not int or type(timeout_ms) is bool or timeout_ms <= 0:
        raise _InvalidRequest(
            "timeout_ms_invalid",
            {
                "field": "timeout_ms",
                "constraint": "positive integer milliseconds",
                "min": 1,
                "max": MAX_TIMEOUT_MS,
                "given": _bounded_scalar(timeout_ms),
            },
        )
    if timeout_ms > MAX_TIMEOUT_MS:
        raise _InvalidRequest(
            "timeout_ms_over_cap",
            {
                "field": "timeout_ms",
                "constraint": "max",
                "max": MAX_TIMEOUT_MS,
                "given": _bounded_scalar(timeout_ms),
            },
        )
    if quality_profile not in _QUALITY_PROFILES:
        raise _InvalidRequest(
            "quality_profile_invalid",
            {
                "field": "quality_profile",
                "given": _bounded_scalar(quality_profile),
                "admitted": list(_QUALITY_PROFILES),
            },
        )
    if effort_class not in _EFFORT_CLASSES:
        raise _InvalidRequest(
            "effort_class_invalid",
            {
                "field": "effort_class",
                "given": _bounded_scalar(effort_class),
                "admitted": list(_EFFORT_CLASSES),
            },
        )
    if target_agent == "":
        target_agent = None
        _record_normalization(
            normalized,
            field="target_agent",
            before="",
            after=None,
            reason="empty_target_is_untargeted",
        )
    admitted_agents = _logical_agents(wire)
    if (
        target_agent is not None
        and (
            type(target_agent) is not str
            or target_agent not in admitted_agents
        )
    ):
        raise _InvalidRequest(
            "target_agent_invalid",
            {
                "field": "target_agent",
                "constraint": "null or a canonical logical agent name",
                "admitted": _bounded_key_list(admitted_agents),
            },
        )
    action_targets = getattr(wire, "logical_action_targets", {})
    if target_agent is not None and action_targets:
        compatible = list(action_targets[action])
        if target_agent not in compatible:
            raise _InvalidRequest(
                "unsupported_target_action",
                {
                    "field": "target_agent",
                    "logical_action": action,
                    "given": target_agent,
                    "admitted": _bounded_key_list(compatible),
                },
            )
    effort_floors = getattr(wire, "logical_action_effort_floors", {})
    if effort_floors:
        required_effort = effort_floors[action]
        if _EFFORT_RANK[effort_class] < _EFFORT_RANK[required_effort]:
            raise _InvalidRequest(
                "effort_below_floor",
                {
                    "field": "effort_class",
                    "logical_action": action,
                    "given": effort_class,
                    "required": required_effort,
                },
            )
    occupied_model_lineages, evidence_anchors = _verification_context(
        document, wire, normalized=normalized
    )
    if getattr(host, "identity_conflict", False):
        author_lineage = None
    elif type(author_lineage) is not str or author_lineage == "unknown":
        author_lineage = None
    if action == "governance.repository" and (
        author_lineage is None or not getattr(host, "governance_ready", False)
    ):
        raise RuntimeError("governance host identity is unavailable")
    native = {
        "wire_contract_sha256": wire.sha256,
        "request_id": request_id,
        "logical_action": action,
        "quality_profile": quality_profile,
        "effort_class": effort_class,
        "target_agent": target_agent,
        "author_lineage": author_lineage,
        "timeout_ms": timeout_ms,
        "prompt": prompt,
        "source": source,
    }
    if getattr(wire, "logical_agents", frozenset()):
        native["occupied_model_lineages"] = occupied_model_lineages
        native["evidence_anchors"] = evidence_anchors
    # The runtime client performs the descriptor-schema validation immediately
    # before launch.  This construction keeps the coordinator boundary smaller.
    return native


def validate_readiness_request(
    document: object, wire: object, host: object, *, normalized: list | None = None
) -> dict[str, Any]:
    """Add trusted host lineage to one closed all-action readiness request.

    ``normalized`` is accepted for signature symmetry with ``validate_request``;
    a readiness request carries no in-place-recoverable field.
    """

    if type(document) is not dict or set(document) != _READINESS_KEYS:
        keys = set(document) if type(document) is dict else set()
        raise _InvalidRequest(
            "readiness_not_closed",
            {
                "field": "request_keys",
                "missing": _bounded_key_list(_READINESS_KEYS - keys),
                "unexpected": _bounded_key_list(keys - _READINESS_KEYS),
            },
        )
    if document.get("operation") != "readiness":
        raise _InvalidRequest(
            "readiness_operation_invalid",
            {"field": "operation", "admitted": ["readiness"]},
        )
    request_id = document.get("request_id")
    quality_profile = document.get("quality_profile")
    effort_class = document.get("effort_class")
    timeout_ms = document.get("timeout_ms")
    if type(request_id) is not str or _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise _InvalidRequest(
            "request_id_invalid",
            {"field": "request_id", "constraint": "1-128 chars of A-Za-z0-9._:-"},
        )
    if type(timeout_ms) is not int or type(timeout_ms) is bool or timeout_ms <= 0:
        raise _InvalidRequest(
            "timeout_ms_invalid",
            {
                "field": "timeout_ms",
                "constraint": "positive integer milliseconds",
                "min": 1,
                "max": MAX_TIMEOUT_MS,
                "given": _bounded_scalar(timeout_ms),
            },
        )
    if timeout_ms > MAX_TIMEOUT_MS:
        raise _InvalidRequest(
            "timeout_ms_over_cap",
            {
                "field": "timeout_ms",
                "constraint": "max",
                "max": MAX_TIMEOUT_MS,
                "given": _bounded_scalar(timeout_ms),
            },
        )
    if quality_profile not in _QUALITY_PROFILES:
        raise _InvalidRequest(
            "quality_profile_invalid",
            {
                "field": "quality_profile",
                "given": _bounded_scalar(quality_profile),
                "admitted": list(_QUALITY_PROFILES),
            },
        )
    if effort_class not in _EFFORT_CLASSES:
        raise _InvalidRequest(
            "effort_class_invalid",
            {
                "field": "effort_class",
                "given": _bounded_scalar(effort_class),
                "admitted": list(_EFFORT_CLASSES),
            },
        )
    author_lineage = getattr(host, "primary_family", "unknown")
    if (
        getattr(host, "identity_conflict", False)
        or type(author_lineage) is not str
        or author_lineage == "unknown"
        or not getattr(host, "governance_ready", False)
    ):
        raise RuntimeError("readiness host identity is unavailable")
    return {
        "operation": "readiness",
        "wire_contract_sha256": wire.sha256,
        "request_id": request_id,
        "author_lineage": author_lineage,
        "quality_profile": quality_profile,
        "effort_class": effort_class,
        "timeout_ms": timeout_ms,
    }


def _response(
    request_id: object,
    status: str,
    error_code: str = "",
    **extra: object,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "request_id": request_id if type(request_id) is str else None,
        "status": status,
    }
    if error_code:
        if _ERROR_CODE_RE.fullmatch(error_code) is None:
            raise ValueError("coordinator error code is invalid")
        response["error_code"] = error_code
    response.update(extra)
    return response


def _runtime_error_code(result: object) -> str:
    error = getattr(result, "error", None)
    if type(error) is str and _ERROR_CODE_RE.fullmatch(error) is not None:
        return error
    status = getattr(getattr(result, "status", None), "value", None)
    if type(status) is str and _ERROR_CODE_RE.fullmatch(status) is not None:
        return f"runtime_{status}"
    return "runtime_failure"


def _bounded_reason(text: str) -> str:
    """Bound an internal message for the 'detail.reason' diagnostic field.

    ASCII-printable and length-bounded, so even the last-resort fallback never
    reflects a C1 control or arbitrary Unicode back to the caller.
    """

    text = "".join(character for character in text if 0x20 <= ord(character) < 0x7F)
    return text[:200]


def _failure_response(
    request_id: object, status: str, error_code: str, **extra: object
) -> dict[str, Any]:
    """A non-usable response carrying its classified disposition and recovery hint."""

    disposition, recovery = _disposition(status)
    return _response(
        request_id, status, error_code, disposition=disposition, recovery=recovery, **extra
    )


def process(document: object) -> tuple[dict[str, Any], int]:
    runtime = _load_runtime()
    wire, manifest_digest, descriptor_error = runtime.runtime_contract_snapshot()
    request_id = document.get("request_id") if isinstance(document, Mapping) else None
    if wire is None:
        return _failure_response(
            request_id,
            "unavailable",
            "runtime_descriptor_unavailable",
            manifest_digest=manifest_digest,
        ), 0
    normalized: list[dict[str, Any]] = []
    try:
        host = _load_host_policy().resolve_profile()
        readiness_requested = (
            type(document) is dict and document.get("operation") == "readiness"
        )
        envelope = (
            validate_readiness_request(document, wire, host, normalized=normalized)
            if readiness_requested
            else validate_request(document, wire, host, normalized=normalized)
        )
    except _InvalidRequest as exc:
        return _failure_response(
            request_id, "invalid_request", exc.error_code, detail=exc.detail
        ), 2
    except RuntimeError:
        return _failure_response(request_id, "unavailable", "host_identity_unavailable"), 0
    except (KeyError, TypeError, UnicodeError, ValueError) as exc:
        # Last-resort catch for validators (repo_root, documents) that still
        # raise a plain ValueError. The cause may be request-shape OR
        # environmental (e.g. an unavailable repo_root), so this is deliberately
        # NOT asserted as 'fix_request'; the caller inspects detail.reason.
        return _response(
            request_id,
            "invalid_request",
            "invalid_request",
            disposition="inspect",
            recovery=(
                "Inspect detail.reason. This rejection was not pre-classified and may be a "
                "request-shape or an environmental problem (for example an unavailable repo_root)."
            ),
            detail={"reason": _bounded_reason(str(exc))},
        ), 2
    result = (
        runtime.readiness(envelope=envelope)
        if readiness_requested
        else runtime.invoke(envelope=envelope)
    )
    usable = result.status in {
        runtime.RuntimeStatus.OK,
        runtime.RuntimeStatus.ADVISORY,
    }
    if usable:
        response = _response(envelope["request_id"], result.status.value)
    else:
        response = _failure_response(
            envelope["request_id"], result.status.value, _runtime_error_code(result)
        )
    if normalized:
        response["normalized"] = normalized
    if result.result is not None:
        response["result"] = result.result
    if result.provenance is not None:
        response["provenance"] = result.provenance
    if result.manifest_digest:
        response["manifest_digest"] = result.manifest_digest
    return response, 0


def _read_tty_request(stream: object) -> bytes:
    """Read one bounded newline frame without a terminal canonical-buffer limit."""

    fileno = getattr(stream, "fileno", None)
    if not callable(fileno):
        raise OSError("coordinator TTY is unreadable")
    descriptor = fileno()
    original = termios.tcgetattr(descriptor)
    configured = list(original)
    configured[6] = list(original[6])
    configured[3] &= ~(
        termios.ICANON | termios.ECHO | getattr(termios, "ECHONL", 0)
    )
    configured[6][termios.VMIN] = 1
    configured[6][termios.VTIME] = 0
    termios.tcsetattr(descriptor, termios.TCSANOW, configured)
    try:
        frame = bytearray()
        deadline = time.monotonic() + _TTY_FRAME_TIMEOUT_SECONDS
        while len(frame) <= MAX_INPUT_BYTES:
            wait_seconds = deadline - time.monotonic()
            if wait_seconds <= 0:
                raise _IncompleteTTYFrame
            readable, _, _ = select.select([descriptor], [], [], wait_seconds)
            if not readable:
                raise _IncompleteTTYFrame
            remaining = MAX_INPUT_BYTES + 1 - len(frame)
            chunk = os.read(descriptor, min(_TTY_READ_CHUNK_BYTES, remaining))
            if not chunk:
                if frame:
                    raise _IncompleteTTYFrame
                break
            newline = chunk.find(b"\n")
            if newline >= 0:
                frame.extend(chunk[: newline + 1])
                break
            frame.extend(chunk)
        return bytes(frame)
    finally:
        termios.tcsetattr(descriptor, termios.TCSANOW, original)


def _read_one_request(stream: object) -> bytes:
    """Read one EOF-framed pipe request or one newline-framed TTY request."""

    is_tty = False
    probe = getattr(stream, "isatty", None)
    if callable(probe):
        try:
            is_tty = probe() is True
        except (OSError, ValueError):
            is_tty = False
    if is_tty:
        return _read_tty_request(stream)
    reader = getattr(stream, "read", None)
    if not callable(reader):
        raise OSError("coordinator stdin is unreadable")
    return reader(MAX_INPUT_BYTES + 1)


def main() -> int:
    try:
        raw = _read_one_request(sys.stdin.buffer)
    except _IncompleteTTYFrame:
        response, code = _failure_response(
            None,
            "invalid_request",
            "tty_frame_incomplete",
            detail={
                "field": "request",
                "constraint": "newline_terminated_tty_frame",
                "max_wait_ms": int(_TTY_FRAME_TIMEOUT_SECONDS * 1000),
            },
        ), 2
    except (OSError, RuntimeError, ValueError):
        response, code = _failure_response(
            None, "unavailable", "coordinator_unavailable"
        ), 0
    else:
        if len(raw) > MAX_INPUT_BYTES:
            response, code = _failure_response(
                None, "invalid_request", "input_limit_exceeded",
                detail={"field": "request", "constraint": "max_bytes", "max": MAX_INPUT_BYTES},
            ), 2
        else:
            try:
                document = _decode_request(raw)
            except (UnicodeError, ValueError, RecursionError):
                response, code = _failure_response(
                    None, "invalid_request", "invalid_json_request",
                    detail={"reason": "request body must be one closed UTF-8 JSON object"},
                ), 2
            else:
                try:
                    response, code = process(document)
                except (OSError, RuntimeError, ValueError):
                    response, code = _failure_response(
                        None, "unavailable", "coordinator_unavailable"
                    ), 0
    sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
