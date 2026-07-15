#!/usr/bin/env python3
"""Standalone public agent-collab coordinator.

Reads exactly one bounded JSON object from stdin, applies dynamic host and
independence policy, then passes only a sealed route/action envelope to the
verified plugin-relative native client.  No workspace checkout is required.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parent
PROTOCOL_VERSION = 1
MAX_INPUT_BYTES = 40 * 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
BASE_FIELDS = {
    "protocol_version",
    "request_id",
    "operation",
    "route",
    "action",
    "timeout_ms",
    "governance",
    "primary",
    "row",
}
EXECUTE_FIELDS = BASE_FIELDS | {"prompt"}
GOVERNANCE_FIELDS = EXECUTE_FIELDS | {"artifact"}
WORKER_CONTRACTS = frozenset(
    {
        ("codex", "build"),
        ("opencode", "build"),
        ("composer", "codegen"),
        ("auto", "worker"),
    }
)
REVIEW_CONTRACTS = frozenset(
    {
        ("auto", "advisory"),
        ("auto", "architecture"),
        ("auto", "governance"),
        ("gemini", "advisory"),
        ("gemini", "governance"),
        ("codex", "advisory"),
        ("grok", "architecture"),
        ("grok", "governance"),
    }
)
ARTIFACT_AWARE_CONTRACTS = WORKER_CONTRACTS | REVIEW_CONTRACTS
DIRECT_CONTRACTS = frozenset(
    {
        ("gemini", "advisory"),
        ("gemini", "governance"),
        ("gemini", "long_context"),
        ("codex", "advisory"),
        ("codex", "build"),
        ("opencode", "plan"),
        ("opencode", "build"),
        ("grok", "architecture"),
        ("grok", "governance"),
        ("grok", "huge_context"),
        ("composer", "codegen"),
    }
)
PRIMARY_FIELDS = {
    "primary_id",
    "primary_family",
    "active_model",
    "host_runtime",
    "session_identifier",
    "opencode_model",
    "async_inbox",
}
ACTION_AUTHORITY_ERROR = "route action/authority mismatch"


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


def _response(request_id: str, status: str, error: str = "", **extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "status": status,
    }
    if error:
        document["error"] = error[:4096]
    document.update(extra)
    return document


def _emit(document: dict[str, Any]) -> None:
    encoded = (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(encoded) > MAX_OUTPUT_BYTES:
        encoded = b'{"protocol_version":1,"request_id":"unknown","status":"output_limit","error":"coordinator output limit exceeded"}\n'
    sys.stdout.buffer.write(encoded)


def _validate(document: object) -> tuple[dict[str, Any] | None, str, str]:
    if not isinstance(document, dict):
        return None, "unknown", "request must be a JSON object"
    request_id = document.get("request_id")
    request_label = request_id if isinstance(request_id, str) else "unknown"
    operation = document.get("operation")
    governance = document.get("governance")
    contract = (document.get("route"), document.get("action"))
    optional_artifact = (
        governance is False
        and operation == "execute"
        and contract in ARTIFACT_AWARE_CONTRACTS
        and "artifact" in document
    )
    expected = (
        GOVERNANCE_FIELDS
        if governance is True
        else (
            EXECUTE_FIELDS | ({"artifact"} if optional_artifact else set())
            if operation == "execute"
            else BASE_FIELDS
        )
    )
    if set(document) != expected:
        return None, request_label, "request fields violate the closed coordinator schema"
    if (
        type(document.get("protocol_version")) is not int
        or document["protocol_version"] != PROTOCOL_VERSION
        or type(document.get("timeout_ms")) is not int
        or not 1 <= document["timeout_ms"] <= 600_000
        or type(governance) is not bool
        or operation not in {"readiness", "execute"}
        or not isinstance(request_id, str)
        or not request_id
        or len(request_id.encode("utf-8")) > 128
        or not isinstance(document.get("route"), str)
        or not isinstance(document.get("action"), str)
        or not isinstance(document.get("row"), dict)
        or not isinstance(document.get("primary"), dict)
        or not set(document["primary"]).issubset(PRIMARY_FIELDS)
        or any(not isinstance(value, str) for value in document["primary"].values())
        or (operation == "execute" and not isinstance(document.get("prompt"), str))
    ):
        return None, request_label, "request values violate the closed coordinator schema"
    if document["route"] == "auto":
        if document["action"] == "worker":
            if governance or document["row"]:
                return None, request_label, "automatic worker row must be empty and non-governance"
        elif document["action"] in {"advisory", "architecture", "governance"}:
            required_routes = (
                {"gemini", "codex"}
                if document["action"] == "advisory"
                else {"gemini", "codex", "grok"}
            )
            if set(document["row"]) != required_routes or any(
                not isinstance(value, dict) for value in document["row"].values()
            ):
                return None, request_label, "automatic role row defines the wrong candidate set"
            if (document["action"] == "governance") is not governance:
                return None, request_label, ACTION_AUTHORITY_ERROR
        else:
            return None, request_label, "automatic action is unsupported"
    if document["route"] in {"gemini", "grok"} and (
        (document["action"] == "governance") is not governance
        if document["action"] in {"architecture", "governance"}
        else False
    ):
        return None, request_label, ACTION_AUTHORITY_ERROR
    if document["route"] == "inbox" and (
        document["action"] != "async"
        or governance
        or operation != "readiness"
    ):
        return None, request_label, "async inbox contract is non-governance readiness-only"
    if document["route"] == "inbox" and (
        set(document["row"])
        != {"target_id", "target_family", "target_session_identifier"}
        or any(not isinstance(value, str) for value in document["row"].values())
    ):
        return None, request_label, "async inbox target provenance is invalid"
    if document["route"] not in {"auto", "inbox"} and contract not in DIRECT_CONTRACTS:
        return None, request_label, "route/action contract is unsupported"
    if governance or optional_artifact:
        artifact = document.get("artifact")
        if (
            not isinstance(artifact, dict)
            or set(artifact) != {"content", "author_model"}
            or not isinstance(artifact.get("content"), str)
            or not isinstance(artifact.get("author_model"), str)
        ):
            return None, request_label, "artifact snapshot fields are invalid"
        content_present = bool(artifact["content"].encode("utf-8").strip())
        model_present = bool(artifact["author_model"].strip())
        if model_present and not content_present:
            return None, request_label, "artifact author model requires nonblank content"
        if governance and (not content_present or not model_present):
            return None, request_label, "governance artifact snapshot is blank"
    return document, request_label, ""


def _inventory_legacy() -> tuple[str, ...]:
    try:
        doctor = _load("agent_collab_migration_doctor", "migration_doctor.py")
        inventory = doctor.inventory_legacy_packages(Path.home())
        if getattr(inventory, "errors", ()):
            return ("inventory-unavailable",)
        return tuple(
            sorted(set(inventory.active_packages) | set(inventory.installed_packages))
        )
    except (OSError, RuntimeError, ValueError, KeyError):
        # Failure to prove inventory cleanliness fails closed as a conflict.
        return ("inventory-unavailable",)


def process(document: object) -> tuple[dict[str, Any], int]:
    validated, request_id, error = _validate(document)
    if validated is None:
        return _response(request_id, "config_error", error), 2
    policy = _load("agent_collab_host_policy", "host_policy.py")
    runtime = _load("agent_collab_runtime_client", "runtime_client.py")
    artifact = validated.get("artifact", {})
    legacy = _inventory_legacy()

    if validated["route"] == "inbox":
        preflight = policy.startup_preflight(
            governance=False,
            explicit_config=validated["primary"],
            active_legacy_packages=legacy,
            safe_mode=False,
            async_inbox_target=validated["row"],
        )
        if preflight.status != policy.PreflightStatus.OK:
            status = (
                "unknown_family"
                if preflight.status == policy.PreflightStatus.UNKNOWN_BLOCKED
                else preflight.status.value
            )
            return _response(
                validated["request_id"], status, preflight.warning
            ), 2 if preflight.status == policy.PreflightStatus.CONFIG_ERROR else 0
        if "inbox" not in preflight.eligible_routes:
            return _response(
                validated["request_id"],
                "unavailable",
                preflight.warning or "async inbox is unavailable",
            ), 0
        target = policy.resolve_async_inbox_target(validated["row"])
        response = _response(
            validated["request_id"],
            "ok",
            result={
                "available": True,
                "transport": "host_async_inbox",
                "target": {
                    "target_id": target.target_id,
                    "target_family": target.target_family,
                    "target_session_identifier": target.target_session_identifier,
                },
            },
        )
        if preflight.warning:
            response["warning"] = preflight.warning
        return response, 0

    def issue_for(route: str, row: dict[str, Any]):
        action = validated["action"]
        if validated["route"] == "auto" and action == "architecture":
            action = "architecture" if route == "grok" else "advisory"
        elif validated["route"] == "auto" and action == "governance":
            action = {
                "gemini": "governance",
                "codex": "advisory",
                "grok": "governance",
            }[route]
        return policy.issue_policy_envelope(
            request_id=validated["request_id"],
            operation=validated["operation"],
            route=route,
            action=action,
            governance=validated["governance"],
            explicit_target=validated["route"] != "auto",
            prompt=validated.get("prompt", ""),
            timeout_ms=validated["timeout_ms"],
            explicit_config=validated["primary"],
            row_config=row,
            artifact_author_model=artifact.get("author_model", ""),
            artifact_content=artifact.get("content", ""),
            active_legacy_packages=legacy,
        )

    if validated["route"] == "auto" and validated["action"] == "worker":
        preflight = policy.startup_preflight(
            governance=False,
            explicit_config=validated["primary"],
            active_legacy_packages=legacy,
            safe_mode=False,
        )
        if preflight.status == policy.PreflightStatus.DUPLICATE_BLOCKED:
            return _response(
                validated["request_id"], "duplicate_blocked", preflight.warning
            ), 0
        return _response(
            validated["request_id"],
            "unavailable",
            "automatic worker routing is temporarily unavailable; select an explicit managed worker target",
            attempts=[],
        ), 0

    if validated["route"] == "auto":
        preflight = policy.startup_preflight(
            governance=validated["governance"],
            explicit_config=validated["primary"],
            active_legacy_packages=legacy,
            safe_mode=False,
            artifact_author_model=artifact.get("author_model", ""),
            artifact_content=artifact.get("content", ""),
        )
        if preflight.status != policy.PreflightStatus.OK:
            status = (
                "unknown_family"
                if preflight.status == policy.PreflightStatus.UNKNOWN_BLOCKED
                else preflight.status.value
            )
            return _response(
                validated["request_id"], status, preflight.warning
            ), 0
        candidate_order = (
            ("gemini", "codex")
            if validated["action"] == "advisory"
            else ("gemini", "codex", "grok")
        )
        candidates = [
            route
            for route in candidate_order
            if route in preflight.eligible_routes
        ]
        if not candidates:
            return _response(
                validated["request_id"],
                "unavailable",
                f"no eligible independent {validated['action']} route",
                attempts=[],
            ), 0
        attempts: list[dict[str, str]] = []
        retryable = {
            runtime.RuntimeStatus.UNAVAILABLE,
            runtime.RuntimeStatus.AUTH_ERROR,
            runtime.RuntimeStatus.QUOTA_ERROR,
            runtime.RuntimeStatus.CONTAINMENT_ERROR,
            runtime.RuntimeStatus.TIMEOUT,
            runtime.RuntimeStatus.OUTPUT_LIMIT,
            runtime.RuntimeStatus.TEARDOWN_ERROR,
            runtime.RuntimeStatus.PROVIDER_ERROR,
        }
        for route in candidates:
            issue = issue_for(route, validated["row"][route])
            if issue.envelope is None:
                attempts.append({"route": route, "status": issue.status.value})
                if issue.status in {
                    policy.PreflightStatus.UNAVAILABLE,
                    policy.PreflightStatus.SAME_FAMILY_BLOCKED,
                }:
                    continue
                return _response(
                    validated["request_id"], issue.status.value, issue.warning, attempts=attempts
                ), 2 if issue.status == policy.PreflightStatus.CONFIG_ERROR else 0
            result = runtime.invoke(envelope=issue.envelope)
            attempts.append({"route": route, "status": result.status.value})
            if result.status == runtime.RuntimeStatus.OK:
                response = _response(
                    validated["request_id"],
                    "ok",
                    selected_route=route,
                    attempts=attempts,
                    result=result.result,
                    provenance=result.provenance,
                )
                if issue.warning:
                    response["warning"] = issue.warning
                return response, 0
            if result.status not in retryable:
                return _response(
                    validated["request_id"], result.status.value, result.error, attempts=attempts
                ), 2 if result.status in {runtime.RuntimeStatus.CONFIG_ERROR, runtime.RuntimeStatus.PROTOCOL_ERROR} else 0
        return _response(
            validated["request_id"],
            "unavailable",
            f"all eligible {validated['action']} routes failed",
            attempts=attempts,
        ), 0

    issue = issue_for(validated["route"], validated["row"])
    if issue.envelope is None:
        status_map = {
            policy.PreflightStatus.CONFIG_ERROR: "config_error",
            policy.PreflightStatus.UNKNOWN_BLOCKED: "unknown_family",
            policy.PreflightStatus.SAME_FAMILY_BLOCKED: "same_family_blocked",
            policy.PreflightStatus.DUPLICATE_BLOCKED: "duplicate_blocked",
            policy.PreflightStatus.UNAVAILABLE: "unavailable",
        }
        status = status_map.get(issue.status, "unavailable")
        operational = status in {"unavailable", "same_family_blocked", "duplicate_blocked", "unknown_family"}
        return _response(validated["request_id"], status, issue.warning), 0 if operational else 2
    result = runtime.invoke(envelope=issue.envelope)
    response = _response(
        validated["request_id"],
        result.status.value,
        result.error,
    )
    if result.result is not None:
        response["result"] = result.result
    if result.provenance is not None:
        response["provenance"] = result.provenance
    if issue.warning:
        response["warning"] = issue.warning
    return response, 0 if result.status not in {runtime.RuntimeStatus.CONFIG_ERROR, runtime.RuntimeStatus.PROTOCOL_ERROR} else 2


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        _emit(_response("unknown", "config_error", "coordinator input limit exceeded"))
        return 2
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        _emit(_response("unknown", "config_error", "invalid JSON request"))
        return 2
    try:
        response, code = process(document)
    except (OSError, RuntimeError, ValueError, KeyError, RecursionError):
        response, code = _response("unknown", "host_blocked", "coordinator could not load its plugin-relative policy/client"), 2
    _emit(response)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
