#!/usr/bin/env python3
"""Closed semantic coordinator for the co-packaged direct runtime."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


PLUGIN_ROOT = Path(__file__).resolve().parent
MAX_INPUT_BYTES = 48 * 1024 * 1024
MAX_DOCUMENTS = 64
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_PROMPT_BYTES = 1024 * 1024
MAX_TIMEOUT_MS = 600_000
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


def validate_request(document: object, wire: object, host: object) -> dict[str, Any]:
    """Convert the closed coordinator request to the descriptor's native request."""

    if type(document) is not dict:
        raise ValueError("coordinator request is not an object")
    if not _COMMON_KEYS.issubset(document):
        raise ValueError("coordinator request is not closed")
    action = document.get("logical_action")
    if type(action) is not str or action not in wire.logical_actions:
        raise ValueError("logical_action is not admitted by the wire descriptor")
    source_mode = wire.logical_action_source_modes[action]
    if source_mode == "repository":
        expected = _COMMON_KEYS | {"repo_root"}
        if set(document) != expected:
            if "repo_root" not in document:
                raise ValueError("repository action requires repo_root")
            raise ValueError("coordinator request is not closed")
        source = {"mode": "repository", "repo_root": _canonical_repo_root(document["repo_root"])}
    elif source_mode == "documents":
        expected = _COMMON_KEYS | {"documents"}
        if set(document) != expected:
            raise ValueError("coordinator request is not closed")
        source = {"mode": "documents", "documents": _documents(document["documents"])}
    elif source_mode == "conceptual_prompt":
        if set(document) != _COMMON_KEYS:
            raise ValueError("coordinator request is not closed")
        source = {"mode": "conceptual_prompt"}
    else:
        raise ValueError("logical_action has no supported source mode")

    request_id = document["request_id"]
    prompt = document["prompt"]
    timeout_ms = document["timeout_ms"]
    quality_profile = document["quality_profile"]
    effort_class = document["effort_class"]
    target_agent = document["target_agent"]
    author_lineage = getattr(host, "primary_family", "unknown")
    if type(request_id) is not str or _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise ValueError("request_id is invalid")
    if type(prompt) is not str or not prompt or len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise ValueError("prompt is invalid")
    if type(timeout_ms) is not int or not 0 < timeout_ms <= MAX_TIMEOUT_MS:
        raise ValueError("timeout_ms is invalid")
    if quality_profile not in {"economical", "standard", "frontier"}:
        raise ValueError("quality_profile is invalid")
    if effort_class not in {"minimal", "standard", "maximum"}:
        raise ValueError("effort_class is invalid")
    if target_agent is not None and (type(target_agent) is not str or not target_agent):
        raise ValueError("target_agent is invalid")
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
    # The runtime client performs the descriptor-schema validation immediately
    # before launch.  This construction keeps the coordinator boundary smaller.
    return native


def validate_readiness_request(
    document: object, wire: object, host: object
) -> dict[str, Any]:
    """Add trusted host lineage to one closed all-action readiness request."""

    if type(document) is not dict or set(document) != _READINESS_KEYS:
        raise ValueError("coordinator readiness request is not closed")
    if document.get("operation") != "readiness":
        raise ValueError("coordinator readiness operation is invalid")
    request_id = document.get("request_id")
    quality_profile = document.get("quality_profile")
    effort_class = document.get("effort_class")
    timeout_ms = document.get("timeout_ms")
    if type(request_id) is not str or _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise ValueError("request_id is invalid")
    if (
        type(timeout_ms) is not int
        or type(timeout_ms) is bool
        or not 1 <= timeout_ms <= 600_000
    ):
        raise ValueError("timeout_ms is invalid")
    if quality_profile not in {"economical", "standard", "frontier"}:
        raise ValueError("quality_profile is invalid")
    if effort_class not in {"minimal", "standard", "maximum"}:
        raise ValueError("effort_class is invalid")
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


def process(document: object) -> tuple[dict[str, Any], int]:
    runtime = _load_runtime()
    wire, manifest_digest, descriptor_error = runtime.runtime_contract_snapshot()
    if wire is None:
        request_id = document.get("request_id") if isinstance(document, Mapping) else None
        return _response(
            request_id,
            "unavailable",
            "runtime_descriptor_unavailable",
            manifest_digest=manifest_digest,
        ), 0
    try:
        host = _load_host_policy().resolve_profile()
        readiness_requested = (
            type(document) is dict and document.get("operation") == "readiness"
        )
        envelope = (
            validate_readiness_request(document, wire, host)
            if readiness_requested
            else validate_request(document, wire, host)
        )
    except RuntimeError as exc:
        request_id = document.get("request_id") if isinstance(document, Mapping) else None
        return _response(request_id, "unavailable", "host_identity_unavailable"), 0
    except (KeyError, TypeError, UnicodeError, ValueError) as exc:
        request_id = document.get("request_id") if isinstance(document, Mapping) else None
        return _response(request_id, "invalid_request", "invalid_request"), 2
    result = (
        runtime.readiness(envelope=envelope)
        if readiness_requested
        else runtime.invoke(envelope=envelope)
    )
    usable = result.status in {
        runtime.RuntimeStatus.OK,
        runtime.RuntimeStatus.ADVISORY,
    }
    response = _response(
        envelope["request_id"],
        result.status.value,
        "" if usable else _runtime_error_code(result),
    )
    if result.result is not None:
        response["result"] = result.result
    if result.provenance is not None:
        response["provenance"] = result.provenance
    if result.manifest_digest:
        response["manifest_digest"] = result.manifest_digest
    return response, 0


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        response, code = _response(None, "invalid_request", "input_limit_exceeded"), 2
    else:
        try:
            document = _decode_request(raw)
            response, code = process(document)
        except (UnicodeError, ValueError, RecursionError):
            response, code = _response(None, "invalid_request", "invalid_json_request"), 2
        except (OSError, RuntimeError):
            response, code = _response(None, "unavailable", "coordinator_unavailable"), 0
    sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
