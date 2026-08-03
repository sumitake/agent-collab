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
_COMMON_KEYS = {
    "request_id",
    "logical_action",
    "target_agent",
    "author_lineage",
    "timeout_ms",
    "prompt",
}


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


def validate_request(document: object, wire: object) -> dict[str, Any]:
    """Convert the closed coordinator request to the descriptor's native request."""

    if type(document) is not dict:
        raise ValueError("coordinator request is not an object")
    if not _COMMON_KEYS.issubset(document):
        raise ValueError("coordinator request is not closed")
    action = document.get("logical_action")
    if type(action) is not str or action not in wire.logical_actions:
        raise ValueError("logical_action is not admitted by the wire descriptor")
    if action.endswith(".repository"):
        expected = _COMMON_KEYS | {"repo_root"}
        if set(document) != expected:
            if "repo_root" not in document:
                raise ValueError("repository action requires repo_root")
            raise ValueError("coordinator request is not closed")
        source = {"mode": "repository", "repo_root": _canonical_repo_root(document["repo_root"])}
    elif action.startswith("context.documents."):
        expected = _COMMON_KEYS | {"documents"}
        if set(document) != expected:
            raise ValueError("coordinator request is not closed")
        source = {"mode": "documents", "documents": _documents(document["documents"])}
    elif action == "architecture.conceptual":
        if set(document) != _COMMON_KEYS:
            raise ValueError("coordinator request is not closed")
        source = {"mode": "conceptual_prompt"}
    else:
        raise ValueError("logical_action has no supported source mode")

    request_id = document["request_id"]
    prompt = document["prompt"]
    timeout_ms = document["timeout_ms"]
    target_agent = document["target_agent"]
    author_lineage = document["author_lineage"]
    if type(request_id) is not str or _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise ValueError("request_id is invalid")
    if type(prompt) is not str or not prompt or len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise ValueError("prompt is invalid")
    if type(timeout_ms) is not int or not 0 < timeout_ms <= MAX_TIMEOUT_MS:
        raise ValueError("timeout_ms is invalid")
    if target_agent is not None and (type(target_agent) is not str or not target_agent):
        raise ValueError("target_agent is invalid")
    if author_lineage is not None and (type(author_lineage) is not str or not author_lineage):
        raise ValueError("author_lineage is invalid")
    native = {
        "wire_contract_sha256": wire.sha256,
        "request_id": request_id,
        "logical_action": action,
        "target_agent": target_agent,
        "author_lineage": author_lineage,
        "timeout_ms": timeout_ms,
        "prompt": prompt,
        "source": source,
    }
    # The runtime client performs the descriptor-schema validation immediately
    # before launch.  This construction keeps the coordinator boundary smaller.
    return native


def _response(request_id: object, status: str, error: str = "", **extra: object) -> dict[str, Any]:
    response: dict[str, Any] = {
        "request_id": request_id if type(request_id) is str else None,
        "status": status,
    }
    if error:
        response["error"] = error
    response.update(extra)
    return response


def process(document: object) -> tuple[dict[str, Any], int]:
    runtime = _load_runtime()
    wire, manifest_digest, descriptor_error = runtime.runtime_contract_snapshot()
    if wire is None:
        request_id = document.get("request_id") if isinstance(document, Mapping) else None
        return _response(
            request_id,
            "unavailable",
            descriptor_error or "direct runtime descriptor is unavailable",
            manifest_digest=manifest_digest,
        ), 0
    try:
        envelope = validate_request(document, wire)
    except (KeyError, TypeError, UnicodeError, ValueError) as exc:
        request_id = document.get("request_id") if isinstance(document, Mapping) else None
        return _response(request_id, "invalid_request", str(exc)), 2
    result = runtime.invoke(envelope=envelope)
    response = _response(envelope["request_id"], result.status.value, result.error)
    if result.result is not None:
        response["result"] = result.result
    if result.provenance is not None:
        response["provenance"] = result.provenance
    if result.manifest_digest:
        response["manifest_digest"] = result.manifest_digest
    return response, 0 if result.status not in {runtime.RuntimeStatus.INVALID_REQUEST, runtime.RuntimeStatus.PROTOCOL_ERROR} else 2


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        response, code = _response(None, "invalid_request", "coordinator input limit exceeded"), 2
    else:
        try:
            document = json.loads(raw.decode("utf-8"))
            response, code = process(document)
        except (UnicodeError, ValueError, RecursionError):
            response, code = _response(None, "invalid_request", "invalid JSON request"), 2
        except (OSError, RuntimeError):
            response, code = _response(None, "unavailable", "coordinator could not load the direct runtime"), 0
    sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
