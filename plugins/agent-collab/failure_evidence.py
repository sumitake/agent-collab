#!/usr/bin/env python3
"""Sanitized, host-local capture for typed terminal failure evidence.

This module deliberately builds a new closed object. It never copies a request
or response subtree, so prompts, source paths, provider prose, and artifacts
cannot cross the capture boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from typing import Mapping
import uuid


SCHEMA = "agent-collab.failure-evidence/v1"
_DEFAULT_ROOT = Path.home() / ".agent-collab" / "failure-evidence"
_CODE_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PLUGIN_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
_SAFE_SURFACES = frozenset({"plugin_coordinator", "grok_build_delegate"})
_SAFE_QUALITY = frozenset({"economical", "standard", "frontier"})
_SAFE_EFFORT = frozenset({"minimal", "standard", "maximum"})
_SAFE_LOGICAL_AGENTS = frozenset(
    {"alibaba", "claude", "codex", "deepseek", "gemini", "grok", "moonshot", "zhipu"}
)
_SAFE_PROVIDER_SURFACES = frozenset(
    {"agy", "codex", "grok", "native_cli", "opencode_go"}
)
_SAFE_MODEL_LINEAGES = frozenset(
    {"alibaba", "anthropic", "deepseek", "google", "moonshot", "openai", "xai", "zhipu"}
)
_SAFE_ERROR_CODES = frozenset(
    {
        "artifact_integrity_failed",
        "auth_error",
        "authority_mismatch",
        "busy",
        "cancelled",
        "capability_error",
        "conflicting_fields",
        "coordinator_unavailable",
        "deadline_expired",
        "delegate_exception",
        "effort_below_floor",
        "effort_class_invalid",
        "evidence_anchors_invalid",
        "execution_contract_violation",
        "host_identity_unavailable",
        "input_limit_exceeded",
        "invalid_invocation",
        "invalid_json",
        "invalid_json_request",
        "invalid_request",
        "missing_common_fields",
        "missing_terminal",
        "no_eligible_route",
        "occupied_model_lineages_invalid",
        "output_limit",
        "prompt_invalid",
        "protocol_capability_drift",
        "protocol_error",
        "provider_error",
        "quality_profile_invalid",
        "quota_error",
        "readiness_contract_violation",
        "readiness_not_closed",
        "readiness_operation_invalid",
        "request_id_invalid",
        "request_not_closed",
        "request_not_object",
        "request_too_large",
        "response_encoding_failed",
        "response_too_large",
        "result_contract_violation",
        "runtime_auth_error",
        "runtime_cancelled",
        "runtime_capability_error",
        "runtime_descriptor_unavailable",
        "runtime_failure",
        "runtime_feature_unavailable",
        "runtime_invalid_request",
        "runtime_output_limit",
        "runtime_protocol_error",
        "runtime_provider_error",
        "runtime_quota_error",
        "runtime_temporarily_unavailable",
        "runtime_timeout",
        "runtime_unavailable",
        "selection_contract_mismatch",
        "selection_invalid",
        "source_containment_failed",
        "source_invalid",
        "source_seal_failed",
        "target_agent_invalid",
        "temporarily_unavailable",
        "timeout",
        "timeout_ms_invalid",
        "timeout_ms_over_cap",
        "tty_frame_incomplete",
        "unavailable",
        "unknown_logical_action",
        "unsupported_host",
        "unsupported_logical_action",
        "unsupported_source_mode",
        "unsupported_target_action",
        "wire_contract_mismatch",
    }
)
_CLOSED_DIAGNOSTIC_VALUES = {
    "logical_agent": _SAFE_LOGICAL_AGENTS,
    "provider_surface": _SAFE_PROVIDER_SURFACES,
    "model_lineage": _SAFE_MODEL_LINEAGES,
}
_COUNT_KEYS = (
    "metadata_process_count",
    "provider_processes",
    "provider_model_calls",
    "provider_turns",
)
_HASH_KEYS = (
    "implementation_fingerprint",
    "executable_content_sha256",
    "adapter_wire_sha256",
    "catalog_digest",
)
_CODE_KEYS = (
    "model_resolution_method",
    "effective_effort",
)
_TRACE_CODE_KEYS = ("failure_phase", "adapter_code", "terminal_state")
_TRACE_COUNT_MAPS = ("tool_outcomes", "failed_operation_counts")
_EVENT_STATES = ("pending", "held", "sending", "uncertain")
_MAX_EVENT_FILES = 10_000
_CAPTURE_TEMP_RE = re.compile(r"^\.[0-9a-f]{32}\.[A-Za-z0-9_-]{1,64}\.tmp$")
_CAPTURE_LOCK_TIMEOUT_SECONDS = 5.0
_CAPTURE_LOCK_POLL_SECONDS = 0.01
_PUBLIC_REQUEST_FIELDS = frozenset(
    {
        "operation",
        "request_id",
        "logical_action",
        "action",
        "quality_profile",
        "effort_class",
        "target_agent",
        "route",
        "timeout_ms",
        "prompt",
        "repo_root",
        "documents",
        "source",
        "occupied_model_lineages",
        "evidence_anchors",
    }
)
_PUBLIC_DETAIL_FIELDS = _PUBLIC_REQUEST_FIELDS | frozenset(
    {"request", "request_keys", "source.mode"}
)
_SOURCE_MODES = frozenset({"repository", "documents", "conceptual_prompt"})


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _safe_code(value: object) -> str | None:
    return value if type(value) is str and _CODE_RE.fullmatch(value) else None


def _safe_hash(value: object) -> str | None:
    return value if type(value) is str and _SHA256_RE.fullmatch(value) else None


def _safe_count(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= 1_000_000_000 else None


def _copy_count_map(value: object) -> dict[str, int] | None:
    if type(value) is not dict or len(value) > 16:
        return None
    copied: dict[str, int] = {}
    for key, item in value.items():
        safe_key = _safe_code(key)
        safe_value = _safe_count(item)
        if safe_key is None or safe_value is None:
            continue
        copied[safe_key] = safe_value
    return copied or None


def _regular_bytes(path: Path, *, maximum: int) -> bytes | None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or not 0 <= metadata.st_size <= maximum:
            return None
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(maximum + 1)
        return data if len(data) <= maximum else None
    except OSError:
        return None
    finally:
        os.close(descriptor)


def _plugin_identity() -> tuple[str | None, str | None]:
    """Return bounded public distribution identity, never request content."""

    root = Path(__file__).resolve().parent
    version: str | None = None
    descriptor = _regular_bytes(
        root / ".claude-plugin" / "plugin.json", maximum=64 * 1024
    )
    if descriptor is not None:
        try:
            value = json.loads(descriptor)
        except (UnicodeError, json.JSONDecodeError):
            value = None
        candidate = value.get("version") if isinstance(value, Mapping) else None
        if type(candidate) is str and _PLUGIN_VERSION_RE.fullmatch(candidate):
            version = candidate
    manifest = _regular_bytes(root / "runtime-manifest.json", maximum=1024 * 1024)
    digest = hashlib.sha256(manifest).hexdigest() if manifest is not None else None
    return version, digest


def _safe_field_list(value: object) -> list[str]:
    if type(value) is not list:
        return []
    return sorted(
        {
            item
            for item in value
            if type(item) is str and item in _PUBLIC_REQUEST_FIELDS
        }
    )


def _safe_request_shape(request: object, response: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {
        "kind": "object" if isinstance(request, Mapping) else "non_object"
    }
    if isinstance(request, Mapping):
        keys = list(request)
        result["present_fields"] = sorted(
            key
            for key in keys
            if type(key) is str and key in _PUBLIC_REQUEST_FIELDS
        )
        result["unknown_field_count"] = sum(
            type(key) is not str or key not in _PUBLIC_REQUEST_FIELDS for key in keys
        )
    detail = response.get("detail")
    if not isinstance(detail, Mapping):
        return result
    difference: dict[str, object] = {}
    for key in ("field", "conflicts_with", "required_source"):
        value = detail.get(key)
        if type(value) is str and value in _PUBLIC_DETAIL_FIELDS:
            difference[key] = value
    missing = _safe_field_list(detail.get("missing"))
    if missing:
        difference["missing_fields"] = missing
    unexpected_raw = detail.get("unexpected")
    unexpected = _safe_field_list(unexpected_raw)
    if unexpected:
        difference["unexpected_fields"] = unexpected
    if type(unexpected_raw) is list:
        difference["unexpected_field_count"] = len(unexpected_raw)
    source_mode = detail.get("expected_source_mode")
    if source_mode in _SOURCE_MODES:
        difference["expected_source_mode"] = source_mode
    if difference:
        result["difference"] = difference
    return result


def _diagnostics(response: Mapping[str, object]) -> Mapping[str, object]:
    direct = response.get("diagnostics")
    if isinstance(direct, Mapping):
        return direct
    provenance = response.get("provenance")
    if isinstance(provenance, Mapping):
        nested = provenance.get("diagnostics")
        if isinstance(nested, Mapping):
            return nested
    return {}


def _safe_diagnostics(response: Mapping[str, object]) -> dict[str, object]:
    source = _diagnostics(response)
    result: dict[str, object] = {}
    for key, allowed in _CLOSED_DIAGNOSTIC_VALUES.items():
        value = source.get(key)
        if value in allowed:
            result[key] = value
    for key in _CODE_KEYS:
        value = _safe_code(source.get(key))
        if value is not None:
            result[key] = value
    for key in _HASH_KEYS:
        value = _safe_hash(source.get(key))
        if value is not None:
            result[key] = value
    for key in _COUNT_KEYS:
        raw = source.get(key)
        if raw is None:
            result[key] = None
            continue
        value = _safe_count(raw)
        if value is not None:
            result[key] = value
    trace = source.get("failure_trace")
    if isinstance(trace, Mapping):
        safe_trace: dict[str, object] = {}
        for key in _TRACE_CODE_KEYS:
            value = _safe_code(trace.get(key))
            if value is not None:
                safe_trace[key] = value
        for key in _TRACE_COUNT_MAPS:
            value = _copy_count_map(trace.get(key))
            if value is not None:
                safe_trace[key] = value
        for key in ("outside_source_observed", "cleanup_confirmed"):
            value = trace.get(key)
            if type(value) is bool:
                safe_trace[key] = value
        envelope_hash = _safe_hash(trace.get("native_envelope_sha256"))
        if envelope_hash is not None:
            safe_trace["native_envelope_sha256"] = envelope_hash
        if safe_trace:
            result["failure_trace"] = safe_trace
    return result


def _safe_invocation(request: object) -> dict[str, object]:
    if not isinstance(request, Mapping):
        return {}
    result: dict[str, object] = {}
    for key in ("logical_action", "target_agent"):
        value = _safe_code(request.get(key))
        if value is not None:
            result[key] = value
    quality = request.get("quality_profile")
    if quality in _SAFE_QUALITY:
        result["quality_profile"] = quality
    effort = request.get("effort_class")
    if effort in _SAFE_EFFORT:
        result["effort_class"] = effort
    return result


def build_event(
    *,
    surface: str,
    response: object,
    request: object = None,
    request_trusted: bool = False,
    request_shape: object = None,
    event_id: str | None = None,
    occurred_at: str | None = None,
) -> dict[str, object] | None:
    """Return one allowlist-built event, or None for usable outcomes."""

    if surface not in _SAFE_SURFACES:
        raise ValueError("unsupported failure-evidence surface")
    if not isinstance(response, Mapping):
        raise ValueError("failure-evidence response must be a mapping")
    status = _safe_code(response.get("status"))
    if status in {"ok", "advisory"}:
        return None
    if status is None:
        raise ValueError("failure-evidence status is invalid")

    stable: dict[str, object] = {
        "schema": SCHEMA,
        "surface": surface,
        "status": status,
    }
    error_code = _safe_code(response.get("error_code"))
    if error_code in _SAFE_ERROR_CODES:
        stable["error_code"] = error_code
    if type(request_trusted) is not bool:
        raise ValueError("request_trusted must be a boolean")
    invocation = _safe_invocation(request) if request_trusted else {}
    if invocation:
        stable["invocation"] = invocation
    installed_version: str | None = None
    installed_manifest: str | None = None
    if surface == "plugin_coordinator":
        installed_version, installed_manifest = _plugin_identity()
        if installed_version is not None:
            stable["plugin_version"] = installed_version
        stable["request_shape"] = _safe_request_shape(request_shape, response)
    diagnostics = _safe_diagnostics(response)
    if diagnostics:
        stable["diagnostics"] = diagnostics
    manifest_digest = _safe_hash(response.get("manifest_digest")) or installed_manifest
    if manifest_digest is not None:
        stable["manifest_digest"] = manifest_digest
    wire_digest = _safe_hash(response.get("wire_contract_sha256"))
    if wire_digest is None:
        provenance = response.get("provenance")
        if isinstance(provenance, Mapping):
            wire_digest = _safe_hash(provenance.get("wire_contract_sha256"))
    if wire_digest is not None:
        stable["wire_contract_sha256"] = wire_digest

    event = dict(stable)
    request_id = response.get("request_id")
    if type(request_id) is str:
        try:
            encoded_request_id = request_id.encode("utf-8")
        except UnicodeEncodeError:
            encoded_request_id = b""
        if 0 < len(encoded_request_id) <= 4096:
            event["request_id_sha256"] = hashlib.sha256(
                encoded_request_id
            ).hexdigest()
    identifier = event_id or uuid.uuid4().hex
    if re.fullmatch(r"^[0-9a-f]{32}$", identifier) is None:
        raise ValueError("failure-evidence event identifier is invalid")
    event["event_id"] = identifier
    event["occurred_at"] = occurred_at or datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    event["fingerprint"] = hashlib.sha256(_canonical_bytes(stable)).hexdigest()
    return event


def _validate_private_directory(path: Path) -> None:
    metadata = path.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise OSError("failure-evidence directory identity is unsafe")


def _fsync_directory(path: Path) -> None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _private_directory(path: Path) -> None:
    missing: list[Path] = []
    current = path
    while True:
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            missing.append(current)
            parent = current.parent
            if parent == current:
                raise OSError("failure-evidence directory parent is unavailable")
            current = parent
            continue
        if not stat.S_ISDIR(metadata.st_mode):
            raise OSError("failure-evidence directory parent is unsafe")
        break
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700, exist_ok=False)
        except FileExistsError:
            pass
        _validate_private_directory(directory)
        _fsync_directory(directory.parent)
    _validate_private_directory(path)


def _open_capture_lock(path: Path):
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise OSError("failure-evidence capture lock is unsafe")
        return os.fdopen(descriptor, "a+", encoding="utf-8")
    except Exception:
        os.close(descriptor)
        raise


def _acquire_capture_lock(lock) -> None:
    deadline = time.monotonic() + _CAPTURE_LOCK_TIMEOUT_SECONDS
    while True:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OSError("failure-evidence capture lock timed out") from exc
            time.sleep(min(_CAPTURE_LOCK_POLL_SECONDS, remaining))


def _remove_abandoned_capture_temporaries(pending: Path) -> None:
    removed = False
    with os.scandir(pending) as entries:
        for entry in entries:
            if not _CAPTURE_TEMP_RE.fullmatch(entry.name):
                continue
            if not entry.is_file(follow_symlinks=False):
                continue
            os.unlink(entry.path)
            removed = True
    if removed:
        _fsync_directory(pending)


def _publish_event(event: Mapping[str, object], root: Path) -> Path:
    _private_directory(root)
    with _open_capture_lock(root / ".capture.lock") as lock:
        _acquire_capture_lock(lock)
        pending = root / "pending"
        _private_directory(pending)
        _remove_abandoned_capture_temporaries(pending)
        store_entries = 0
        for state in _EVENT_STATES:
            directory = root / state
            if not directory.exists():
                continue
            metadata = directory.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700
            ):
                raise OSError("failure-evidence state directory is unsafe")
            with os.scandir(directory) as entries:
                for _entry in entries:
                    store_entries += 1
                    if store_entries >= _MAX_EVENT_FILES:
                        raise OSError("failure-evidence local store is full")
        payload = _canonical_bytes(event) + b"\n"
        final = pending / f"{event['event_id']}.json"
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{event['event_id']}.", suffix=".tmp", dir=pending
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            descriptor = -1
            os.replace(temporary, final)
            _fsync_directory(pending)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return final


def capture_terminal_failure(
    *,
    surface: str,
    response: object,
    request: object = None,
    request_trusted: bool = False,
    request_shape: object = None,
) -> Path | None:
    """Atomically publish a sanitized event without interpreting its outcome."""

    event = build_event(
        surface=surface,
        response=response,
        request=request,
        request_trusted=request_trusted,
        request_shape=request_shape,
    )
    if event is None:
        return None
    configured = os.environ.get("AGENT_COLLAB_FAILURE_EVIDENCE_ROOT")
    root = Path(configured).expanduser() if configured else _DEFAULT_ROOT
    return _publish_event(event, root)
