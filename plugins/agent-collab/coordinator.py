#!/usr/bin/env python3
"""Bounded routing-only CLI for the co-packaged native runtime.

The caller supplies a routing request. Before passing it through once, this
shim repairs mechanical request-construction mistakes that would otherwise
fail before any provider starts: it fills the signed wire digest and omitted
defaults, maps common field aliases and value synonyms, clamps the deadline,
and binds a read-only repository action to the repository it is about. Every
repair is listed in the response. It adds no semantic schema, provider
command, retry, fallback, receipt, verdict, or output parser, never changes a
named target or action, and never binds a code-generation action to a
caller's repository.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import uuid
from types import ModuleType
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parent
MAX_INPUT_BYTES = 48 * 1024 * 1024
MAX_DEADLINE_MS = 86_400_000
MAX_WORK_UNITS = 128
_PATH_SCAN_BYTES = 256 * 1024
_PATH_SCAN_LIMIT = 256
_ABSOLUTE_PATH = re.compile(r"(?<![\w.~/:])/(?:[\w.@+-]+/)*[\w.@+-]+")
_TOP_ALIASES = {
    "quality": "quality_profile",
    "effort": "effort_class",
    "timeout_ms": "deadline_ms",
    "dispatch": "dispatch_requested",
    "units": "work_units",
    "parallel": "max_parallel",
}
_UNIT_ALIASES = {
    "action": "capability",
    "logical_action": "capability",
    "prompt": "payload",
    "input": "payload",
    "target": "explicit_target",
    "target_agent": "explicit_target",
    "agent": "explicit_target",
    "reviewer": "explicit_target",
    "provider": "explicit_target",
    "dependencies": "depends_on",
}
_CWD_ALIASES = ("cwd", "repository", "repo", "working_directory")
_TOP_FIELDS = {
    "wire_contract_sha256", "request_id", "quality_profile", "effort_class",
    "max_parallel", "dispatch_requested", "work_units", "budget_limit",
    "deadline_ms", "latency_value",
}
_UNIT_FIELDS = {
    "id", "capability", "depends_on", "payload", "payload_ref",
    "explicit_target", "native_restrictions", "context_size_estimate",
    "output_size_estimate",
}
_QUALITY = {
    "frontier": "frontier", "pro": "frontier", "high": "frontier",
    "max": "frontier", "maximum": "frontier", "best": "frontier",
    "standard": "standard", "default": "standard", "medium": "standard",
    "normal": "standard",
    "economical": "economical", "economy": "economical", "cheap": "economical",
    "low": "economical", "flash": "economical",
}
_EFFORT = {
    "maximum": "maximum", "max": "maximum", "high": "maximum",
    "xhigh": "maximum", "highest": "maximum",
    "standard": "standard", "default": "standard", "medium": "standard",
    "normal": "standard",
    "minimal": "minimal", "min": "minimal", "minimum": "minimal", "low": "minimal",
}
_AGENTS = {
    "google": "gemini", "antigravity": "gemini", "agy": "gemini",
    "openai": "codex", "xai": "grok", "anthropic": "claude",
}


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate request key")
        value[key] = item
    return value


def _reject_nonfinite(_value: str) -> None:
    raise ValueError("request contains a non-finite number")


def _load_client() -> ModuleType:
    path = PLUGIN_ROOT / "runtime_client.py"
    spec = importlib.util.spec_from_file_location("agent_collab_runtime_client", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("runtime client is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _label(value: object) -> str:
    text = str(value)
    return text[:64] if text.isascii() and text.isprintable() else "<non-printable>"


def _git_root(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _directory_identity(path: Path) -> dict[str, object] | None:
    try:
        observed = path.stat()
    except OSError:
        return None
    if not path.is_dir():
        return None
    return {"cwd": str(path), "cwd_device": observed.st_dev, "cwd_inode": observed.st_ino}


def _payload_roots(payload: object) -> set[Path]:
    """Repository roots of existing absolute paths the payload names."""

    if type(payload) is not str:
        try:
            payload = json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError, RecursionError):
            return set()
    roots: set[Path] = set()
    for index, match in enumerate(_ABSOLUTE_PATH.finditer(payload[:_PATH_SCAN_BYTES])):
        if index >= _PATH_SCAN_LIMIT:
            break
        path = Path(match.group(0).rstrip(".,:;"))
        try:
            if not path.exists():
                continue
            root = _git_root(path.resolve() if path.is_dir() else path.resolve().parent)
        except (OSError, RuntimeError):
            continue
        if root is not None:
            roots.add(root)
    return roots


def _bind_cwd(unit: dict[str, object], supplied: object, caller_cwd: Path, repairs: list[str]) -> None:
    """Give a unit a current cwd identity, or leave it unbound."""

    name = unit["id"]
    action = str(unit.get("capability", ""))
    if supplied is not None:
        path = Path(os.path.expanduser(str(supplied)))
        path = (caller_cwd / path) if not path.is_absolute() else path
        identity = _directory_identity(path.resolve())
        if identity is None:
            repairs.append(f"work unit {_label(name)}: working directory is not an existing directory")
            unit["native_restrictions"] = {"cwd": str(path)}
            return
        previous = unit.get("native_restrictions")
        if previous != identity:
            repairs.append(f"work unit {_label(name)}: working directory identity read at dispatch")
        unit["native_restrictions"] = identity
        return
    if unit.pop("native_restrictions", None) is not None:
        repairs.append(f"work unit {_label(name)}: dropped native restrictions without a cwd")
    if ".repository" not in action or "codegen" in action:
        return
    # A read-only repository action run in an empty private directory cannot
    # see its source, so bind it to the repository the request is about.
    here = _git_root(caller_cwd)
    named = _payload_roots(unit.get("payload"))
    root = here if here in named or len(named) != 1 else next(iter(named))
    identity = None if root is None else _directory_identity(root)
    if identity is None:
        repairs.append(f"work unit {_label(name)}: no repository found for its read-only repository action")
        return
    unit["native_restrictions"] = identity
    repairs.append(f"work unit {_label(name)}: bound to repository {root}")


def _normalize_unit(
    raw: object, index: int, wire: object, caller_cwd: Path, repairs: list[str],
) -> object:
    if type(raw) is not dict:
        return raw
    unit: dict[str, object] = {}
    cwd = None
    for key, value in raw.items():
        if key in _CWD_ALIASES:
            cwd = value
        elif key == "native_restrictions" and type(value) is dict:
            cwd = value.get("cwd", cwd)
            unit[key] = value
            if set(value) - {"cwd", "cwd_device", "cwd_inode"}:
                repairs.append(f"work unit {index + 1}: ignored extra native restrictions")
        elif _UNIT_ALIASES.get(key, key) in _UNIT_FIELDS:
            target = _UNIT_ALIASES.get(key, key)
            if target not in unit or key == target:
                unit[target] = value
                if key != target:
                    repairs.append(f"work unit {index + 1}: read {_label(key)} as {target}")
        else:
            repairs.append(f"work unit {index + 1}: ignored unknown field {_label(key)}")
    identifier = unit.get("id")
    if type(identifier) is not str or not 1 <= len(identifier) <= 128:
        unit["id"] = f"unit-{index + 1}"
        repairs.append(f"work unit {index + 1}: assigned id {unit['id']}")
    action = unit.get("capability")
    actions = wire.logical_actions
    if type(action) is str and action not in actions:
        wanted = action.strip().lower()
        matches = sorted(item for item in actions if item == wanted or item.startswith(wanted + "."))
        if len(matches) == 1:
            unit["capability"] = matches[0]
            repairs.append(f"work unit {unit['id']}: action {_label(action)} resolved to {matches[0]}")
    depends = unit.get("depends_on")
    if depends is None:
        unit["depends_on"] = []
    elif type(depends) is str:
        unit["depends_on"] = [depends]
    if "payload" in unit and "payload_ref" in unit:
        del unit["payload_ref"]
        repairs.append(f"work unit {unit['id']}: used payload and ignored payload_ref")
    target = unit.get("explicit_target")
    if target is None or (type(target) is str and not target.strip()):
        unit.pop("explicit_target", None)
    elif type(target) is str:
        wanted = target.strip().lower()
        wanted = _AGENTS.get(wanted, wanted)
        if wanted != target:
            unit["explicit_target"] = wanted
            repairs.append(f"work unit {unit['id']}: target {_label(target)} read as {wanted}")
    for name in ("context_size_estimate", "output_size_estimate"):
        value = unit.get(name)
        if value is None or (type(value) is int and value >= 0):
            continue
        try:
            unit[name] = max(0, int(float(value)))
        except (TypeError, ValueError, OverflowError):
            del unit[name]
    _bind_cwd(unit, cwd, caller_cwd, repairs)
    return unit


def _normalize_request(
    request: dict[str, object], wire: object, caller_cwd: Path,
) -> tuple[dict[str, object], list[str]]:
    """Repair mechanical construction mistakes; never change intent."""

    repairs: list[str] = []
    document: dict[str, object] = {}
    for key, value in request.items():
        target = _TOP_ALIASES.get(key, key)
        if target in _TOP_FIELDS:
            if target not in document or key == target:
                document[target] = value
                if key != target:
                    repairs.append(f"read {_label(key)} as {target}")
    units = document.get("work_units")
    extra = {key: value for key, value in request.items() if key not in _TOP_FIELDS and key not in _TOP_ALIASES}
    if units is None and extra:
        units = [extra]
        repairs.append("read top-level fields as one work unit")
    else:
        repairs.extend(f"ignored unknown field {_label(key)}" for key in sorted(extra))
        if type(units) is dict:
            units = [units]
    if type(units) is list:
        units = [_normalize_unit(unit, index, wire, caller_cwd, repairs) for index, unit in enumerate(units)]
        seen: set[object] = set()
        for index, unit in enumerate(units):
            if type(unit) is dict:
                if unit["id"] in seen:
                    unit["id"] = f"{unit['id']}-{index + 1}"[:128]
                    repairs.append(f"work unit {index + 1}: renamed duplicate id to {_label(unit['id'])}")
                seen.add(unit["id"])
        document["work_units"] = units
    if document.get("wire_contract_sha256") != wire.sha256:
        if "wire_contract_sha256" in document:
            repairs.append("replaced a stale wire_contract_sha256 with the installed one")
        document["wire_contract_sha256"] = wire.sha256
    request_id = document.get("request_id")
    if type(request_id) is not str or not 1 <= len(request_id) <= 128:
        document["request_id"] = str(uuid.uuid4())
        repairs.append("assigned request_id")
    for field, table in (("quality_profile", _QUALITY), ("effort_class", _EFFORT)):
        value = document.get(field)
        chosen = table.get(str(value).strip().lower()) if value is not None else None
        if chosen is None:
            chosen = "standard"
            repairs.append(f"{field} {'omitted' if value is None else 'unrecognized'}; used standard")
        elif chosen != value:
            repairs.append(f"{field} {_label(value)} read as {chosen}")
        document[field] = chosen
    count = len(units) if type(units) is list else 1
    parallel = document.get("max_parallel")
    if type(parallel) is not int or not 1 <= parallel <= MAX_WORK_UNITS:
        document["max_parallel"] = max(1, min(count, MAX_WORK_UNITS))
        if parallel is not None:
            repairs.append(f"max_parallel set to {document['max_parallel']}")
    dispatch = document.get("dispatch_requested")
    if type(dispatch) is str and dispatch.strip().lower() in {"true", "false"}:
        document["dispatch_requested"] = dispatch.strip().lower() == "true"
    elif type(dispatch) is not bool:
        document["dispatch_requested"] = type(units) is list and all(
            type(unit) is dict and "payload" in unit for unit in units
        )
        repairs.append(f"dispatch_requested set to {str(document['dispatch_requested']).lower()}")
    deadline = document.get("deadline_ms")
    if deadline is not None and not (type(deadline) is int and 1 <= deadline <= MAX_DEADLINE_MS):
        try:
            value = int(float(deadline))
        except (TypeError, ValueError, OverflowError):
            value = 0
        if value < 1:
            del document["deadline_ms"]
            repairs.append("deadline_ms was not a positive integer; used the runtime default")
        else:
            document["deadline_ms"] = min(value, MAX_DEADLINE_MS)
            if value > MAX_DEADLINE_MS:
                repairs.append(f"deadline_ms clamped to {MAX_DEADLINE_MS}")
    return document, repairs


def _read_request() -> object:
    if sys.stdin.isatty():
        raise ValueError("tty input is unsupported")
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if not raw:
        raise ValueError("request is empty")
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("request exceeds input bound")
    fenced = raw.strip()
    if fenced.startswith(b"```") and fenced.endswith(b"```") and b"\n" in fenced:
        # One Markdown-fenced JSON value is still exactly one JSON value.
        raw = fenced[fenced.index(b"\n") + 1:-3]
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("request is not one JSON value") from exc


def _response(result: object) -> dict[str, object]:
    if not is_dataclass(result):
        raise RuntimeError("runtime client returned an invalid result")
    value = asdict(result)
    status = value.get("status")
    value["status"] = getattr(status, "value", status)
    return value


def _write(value: object) -> None:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def main() -> int:
    try:
        try:
            request = _read_request()
            if type(request) is not dict:
                raise ValueError("request root must be an object")
        except ValueError as exc:
            _write({"status": "invalid_request", "result": [], "error": str(exc)})
            return 2
        client = _load_client()
        repairs: list[str] = []
        snapshot = getattr(client, "runtime_contract_snapshot", None)
        wire = snapshot()[0] if snapshot is not None else None
        if wire is not None:
            try:
                request, repairs = _normalize_request(request, wire, Path.cwd())
            except Exception:
                repairs = ["request repair was skipped; the request passed through unchanged"]
        response = _response(client.invoke(envelope=request))
        if repairs:
            response["repairs"] = repairs
        _write(response)
        return 0
    except Exception:
        _write({
            "status": "client_error",
            "result": [],
            "error": "routing client failed; provider execution and state are unknown",
        })
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
