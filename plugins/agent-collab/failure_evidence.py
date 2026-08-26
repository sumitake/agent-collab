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
_SAFE_SURFACES = frozenset({"plugin_coordinator", "grok_build_delegate"})
_SAFE_QUALITY = frozenset({"economical", "standard", "frontier"})
_SAFE_EFFORT = frozenset({"minimal", "standard", "maximum"})
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
    "logical_agent",
    "provider_surface",
    "model_lineage",
    "model_resolution_method",
    "effective_effort",
)
_TRACE_CODE_KEYS = ("failure_phase", "adapter_code", "terminal_state")
_TRACE_COUNT_MAPS = ("tool_outcomes", "failed_operation_counts")
_EVENT_STATES = ("pending", "held", "sending", "uncertain")
_MAX_EVENT_FILES = 10_000
_CAPTURE_LOCK_TIMEOUT_SECONDS = 5.0
_CAPTURE_LOCK_POLL_SECONDS = 0.01


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
    if error_code is not None:
        stable["error_code"] = error_code
    if type(request_trusted) is not bool:
        raise ValueError("request_trusted must be a boolean")
    invocation = _safe_invocation(request) if request_trusted else {}
    if invocation:
        stable["invocation"] = invocation
    diagnostics = _safe_diagnostics(response)
    if diagnostics:
        stable["diagnostics"] = diagnostics
    manifest_digest = _safe_hash(response.get("manifest_digest"))
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
    if type(request_id) is str and 0 < len(request_id.encode("utf-8")) <= 4096:
        event["request_id_sha256"] = hashlib.sha256(
            request_id.encode("utf-8")
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


def _private_directory(path: Path) -> None:
    if path.is_symlink():
        raise OSError("failure-evidence directory cannot be a symlink")
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        pass
    metadata = path.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise OSError("failure-evidence directory identity is unsafe")


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


def _publish_event(event: Mapping[str, object], root: Path) -> Path:
    _private_directory(root)
    with _open_capture_lock(root / ".capture.lock") as lock:
        _acquire_capture_lock(lock)
        pending = root / "pending"
        _private_directory(pending)
        event_files = 0
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
                for entry in entries:
                    if entry.name.endswith(".json") and entry.is_file(
                        follow_symlinks=False
                    ):
                        event_files += 1
                        if event_files >= _MAX_EVENT_FILES:
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
            directory_descriptor = os.open(pending, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
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
) -> Path | None:
    """Atomically publish a sanitized event without interpreting its outcome."""

    event = build_event(
        surface=surface,
        response=response,
        request=request,
        request_trusted=request_trusted,
    )
    if event is None:
        return None
    configured = os.environ.get("AGENT_COLLAB_FAILURE_EVIDENCE_ROOT")
    root = Path(configured).expanduser() if configured else _DEFAULT_ROOT
    return _publish_event(event, root)
