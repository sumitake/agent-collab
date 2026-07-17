#!/usr/bin/env python3
"""Dynamic host policy and sealed native-runtime request decisions.

This module contains public coordination policy only.  It never discovers or
invokes a provider binary.  Runtime availability is observed from the verified
plugin-relative manifest through ``runtime_client``; callers cannot advertise
capabilities or assert reviewer-family independence themselves.

The in-process seal protects normal coordinator/client hand-off from accidental
or ad-hoc mutation.  The same-UID operator account is trusted and can replace
this public module, so this is deliberately not described as a hostile-local-
process security boundary.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import os
import re
import secrets
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


PLUGIN_ROOT = Path(__file__).resolve().parent
KNOWN_FAMILIES = frozenset({"anthropic", "google", "openai", "xai", "zhipu"})
DEFAULT_OPENCODE_MODEL = "opencode/glm-5.2"
GEMINI_GOVERNANCE_MODEL = "google/gemini-3.1-pro"
GEMINI_GOVERNANCE_EFFORTS = frozenset({"high", "xhigh"})
ROUTE_ACTIONS = frozenset(
    {
        ("gemini", "advisory"),
        ("gemini", "governance"),
        ("gemini", "long_context"),
        ("codex", "advisory"),
        ("opencode", "plan"),
        ("opencode", "build"),
        ("grok", "architecture"),
        ("grok", "governance"),
        ("grok", "huge_context"),
        ("composer", "codegen"),
    }
)
DECLARED_UNAVAILABLE_CONTRACTS = frozenset({("codex", "build")})
ROUTE_FAMILIES = {
    "gemini": "google",
    "codex": "openai",
    "grok": "xai",
    "composer": "xai",
    "inbox": "anthropic",
}
ASYNC_INBOX_TARGET_FAMILIES = {
    "claude": "anthropic",
    "antigravity": "google",
}
_PRIMARY_ID_FAMILIES = {
    "claude": "anthropic",
    "codex": "openai",
    "antigravity": "google",
}
_PRIMARY_ID_RUNTIMES = {
    "claude": "claude-code",
    "codex": "codex",
    "antigravity": "antigravity",
    "zcode": "opencode",
}
AUTHORITIES = {
    ("gemini", "advisory"): "read_only",
    ("gemini", "governance"): "read_only",
    ("gemini", "long_context"): "read_only",
    ("codex", "advisory"): "read_only",
    ("opencode", "plan"): "read_only",
    ("opencode", "build"): "workspace_write",
    ("grok", "architecture"): "read_only",
    ("grok", "governance"): "read_only",
    ("grok", "huge_context"): "read_only",
    ("composer", "codegen"): "output_only",
}
GOVERNANCE_CONTRACTS = frozenset(
    {("gemini", "governance"), ("codex", "advisory"), ("grok", "governance")}
)
_GROK_REVIEW_SEALS = {
    ("grok", "architecture"): ("architecture", "high"),
    ("grok", "governance"): ("governance", "high"),
    ("grok", "huge_context"): ("huge_context", "medium"),
}
_GROK_EFFORT_ORDER = {"low": 0, "medium": 1, "high": 2}
_GROK_CODEGEN_MINIMUMS = {
    "simple_codegen": "low",
    "standard_codegen": "medium",
    "complex_codegen": "high",
}
MAX_TIMEOUT_MS = 600_000
MAX_PROMPT_BYTES = 1024 * 1024
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_DOCUMENTS = 64
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SEAL_KEY = secrets.token_bytes(32)
_PROVIDER_FAMILIES = {
    "anthropic": "anthropic",
    "google": "google",
    "openai": "openai",
    "xai": "xai",
    "zhipu": "zhipu",
}
_MODEL_FAMILY_PATTERNS = (
    (re.compile(r"^claude(?:[-_.].*)?$"), "anthropic"),
    (re.compile(r"^gemini(?:[-_.].*)?$"), "google"),
    (re.compile(r"^(?:codex(?:[-_.].*)?|gpt(?:[-_.].*)?|o[34](?:[-_.].*)?)$"), "openai"),
    (re.compile(r"^(?:grok|composer)(?:[-_.].*)?$"), "xai"),
    (re.compile(r"^(?:glm|zhipu)(?:[-_.].*)?$"), "zhipu"),
)


class PreflightStatus(str, Enum):
    OK = "ok"
    DUPLICATE_BLOCKED = "duplicate_blocked"
    UNKNOWN_BLOCKED = "unknown_blocked"
    UNAVAILABLE = "unavailable"
    SAME_FAMILY_BLOCKED = "same_family_blocked"
    CONFIG_ERROR = "config_error"


@dataclass(frozen=True)
class HostProfile:
    primary_id: str
    primary_family: str
    active_model: str
    host_runtime: str
    session_identifier: str
    explicit: bool
    governance_ready: bool = False
    identity_conflict: bool = False


@dataclass(frozen=True)
class AsyncInboxTarget:
    target_id: str
    target_family: str
    target_session_identifier: str
    trustworthy: bool


@dataclass(frozen=True)
class ArtifactSnapshot:
    present: bool
    content_base64: str
    content_sha256: str
    content_size: int
    author_model: str
    author_family: str


@dataclass(frozen=True)
class PolicyEnvelope:
    request_id: str
    operation: str
    route: str
    action: str
    authority: str
    timeout_ms: int
    prompt: str
    row_json: str
    primary_id: str
    primary_family: str
    primary_model: str
    primary_host_runtime: str
    primary_session_identifier: str
    artifact_present: bool
    artifact_content_base64: str
    artifact_size: int
    artifact_sha256: str
    artifact_author_model: str
    artifact_author_family: str
    target_author_family: str
    runtime_manifest_digest: str
    governance: bool
    explicit_target: bool
    nonce: str
    seal: str


@dataclass(frozen=True)
class PreflightOutcome:
    status: PreflightStatus
    profile: HostProfile
    eligible_routes: tuple[str, ...]
    warning: str = ""


@dataclass(frozen=True)
class PolicyIssueOutcome:
    status: PreflightStatus
    profile: HostProfile
    envelope: PolicyEnvelope | None
    warning: str = ""


def _model_family_signals(model: str) -> frozenset[str]:
    if not isinstance(model, str):
        return frozenset()
    value = model.strip().lower()
    if not value or value.startswith("/") or value.endswith("/") or "//" in value:
        return frozenset()
    signals: set[str] = set()
    for segment in value.split("/"):
        provider_family = _PROVIDER_FAMILIES.get(segment)
        if provider_family is not None:
            signals.add(provider_family)
        for pattern, family in _MODEL_FAMILY_PATTERNS:
            if pattern.fullmatch(segment):
                signals.add(family)
    return frozenset(signals)


def resolve_model_family(model: str) -> str:
    signals = _model_family_signals(model)
    return next(iter(signals)) if len(signals) == 1 else "unknown"


_PROFILE_KEYS = (
    "primary_id",
    "primary_family",
    "active_model",
    "host_runtime",
    "session_identifier",
    "opencode_model",
)


def _overlay_profile_values(
    observed: Mapping[str, str], overrides: Mapping[str, str]
) -> dict[str, str]:
    base = {key: str(observed.get(key, "")) for key in _PROFILE_KEYS}
    conflict = str(observed.get("_identity_conflict", "")).strip() == "1"
    normalized = {
        key: str(overrides.get(key, "")).strip()
        for key in _PROFILE_KEYS
        if str(overrides.get(key, "")).strip()
    }
    for key, override in normalized.items():
        if key == "opencode_model":
            continue
        current = base.get(key, "").strip()
        if not current:
            continue
        current_cmp = current if key == "session_identifier" else current.lower()
        override_cmp = override if key == "session_identifier" else override.lower()
        if current_cmp != override_cmp:
            conflict = True
    if not conflict:
        base.update(normalized)
    else:
        # Strong current-session evidence is authoritative.  A conflicting
        # explicit descriptor cannot replace or splice into it.
        for key, value in normalized.items():
            if not base.get(key, "").strip():
                base[key] = value
    base["_identity_conflict"] = "1" if conflict else ""
    return base


def _environment_profile() -> dict[str, str]:
    env = os.environ
    overrides = {
        "primary_id": env.get("AGENT_COLLAB_PRIMARY_ID", ""),
        "primary_family": env.get("AGENT_COLLAB_PRIMARY_FAMILY", ""),
        "active_model": env.get("AGENT_COLLAB_ACTIVE_MODEL", ""),
        "host_runtime": env.get("AGENT_COLLAB_HOST_RUNTIME", ""),
        "session_identifier": env.get("AGENT_COLLAB_SESSION_ID", ""),
        "opencode_model": env.get("AGENT_COLLAB_OPENCODE_MODEL", ""),
    }
    detected: list[dict[str, str]] = []
    if env.get("CLAUDE_CODE_SESSION_ID") or env.get("CLAUDE_CODE_ENTRYPOINT"):
        detected.append(
            {
                "primary_id": "claude",
                "primary_family": "anthropic",
                "active_model": env.get("CLAUDE_CODE_MODEL", ""),
                "host_runtime": "claude-code",
                "session_identifier": env.get("CLAUDE_CODE_SESSION_ID", ""),
            }
        )
    if env.get("CODEX_THREAD_ID"):
        detected.append(
            {
                "primary_id": "codex",
                "primary_family": "openai",
                "active_model": env.get("CODEX_ACTIVE_MODEL", ""),
                "host_runtime": "codex",
                "session_identifier": env.get("CODEX_THREAD_ID", ""),
            }
        )
    if env.get("ANTIGRAVITY_SESSION_ID"):
        detected.append(
            {
                "primary_id": "antigravity",
                "primary_family": "google",
                "active_model": env.get("ANTIGRAVITY_ACTIVE_MODEL", ""),
                "host_runtime": "antigravity",
                "session_identifier": env.get("ANTIGRAVITY_SESSION_ID", ""),
            }
        )
    if env.get("ZCODE_SESSION_ID"):
        detected.append(
            {
                "primary_id": "zcode",
                "primary_family": "",
                "active_model": env.get("OPENCODE_ACTIVE_MODEL", ""),
                "host_runtime": "opencode",
                "session_identifier": env.get("ZCODE_SESSION_ID", ""),
                "opencode_model": env.get("OPENCODE_ACTIVE_MODEL", ""),
            }
        )
    observed = detected[0] if len(detected) == 1 else {
        key: "" for key in _PROFILE_KEYS
    }
    if len(detected) > 1:
        observed["_identity_conflict"] = "1"
    return _overlay_profile_values(observed, overrides)


def resolve_profile(explicit_config: Mapping[str, str] | None = None) -> HostProfile:
    explicit = explicit_config is not None and bool(explicit_config)
    observed = _environment_profile()
    values = (
        _overlay_profile_values(observed, explicit_config or {})
        if explicit
        else observed
    )
    primary_id = str(values.get("primary_id", "")).strip().lower() or "unknown"
    active_model = str(values.get("active_model", "")).strip()
    model_signals = _model_family_signals(active_model)
    model_family = next(iter(model_signals)) if len(model_signals) == 1 else "unknown"
    asserted_family = str(values.get("primary_family", "")).strip().lower()
    if asserted_family not in KNOWN_FAMILIES:
        asserted_family = "unknown"

    identity_conflict = str(values.get("_identity_conflict", "")).strip() == "1"
    if len(model_signals) > 1:
        identity_conflict = True
    if (
        model_family in KNOWN_FAMILIES
        and asserted_family in KNOWN_FAMILIES
        and model_family != asserted_family
    ):
        identity_conflict = True

    # A recognized current model is stronger lineage evidence than a stale
    # family field.  This is load-bearing for ZCode/OpenCode model switches.
    if len(model_signals) > 1:
        family = "unknown"
    elif model_family in KNOWN_FAMILIES:
        family = model_family
    elif asserted_family in KNOWN_FAMILIES:
        family = asserted_family
    else:
        family = "unknown"
    fixed_family = _PRIMARY_ID_FAMILIES.get(primary_id)
    fixed_runtime = _PRIMARY_ID_RUNTIMES.get(primary_id)
    host_runtime = str(values.get("host_runtime", "")).strip().lower() or "unknown"
    session_identifier = str(values.get("session_identifier", "")).strip() or "unknown"
    if fixed_family is not None and family in KNOWN_FAMILIES and family != fixed_family:
        identity_conflict = True
    if fixed_runtime is not None and host_runtime != "unknown" and host_runtime != fixed_runtime:
        identity_conflict = True
    governance_ready = (
        not identity_conflict
        and primary_id != "unknown"
        and family in KNOWN_FAMILIES
        and bool(active_model)
        and model_family in KNOWN_FAMILIES
        and host_runtime != "unknown"
        and session_identifier != "unknown"
    )
    return HostProfile(
        primary_id=primary_id,
        primary_family=family,
        active_model=active_model or "unknown",
        host_runtime=host_runtime,
        session_identifier=session_identifier,
        explicit=explicit,
        governance_ready=governance_ready,
        identity_conflict=identity_conflict,
    )


def _load_runtime_client():
    name = "agent_collab_runtime_client"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = PLUGIN_ROOT / "runtime_client.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("runtime client cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _runtime_contracts() -> tuple[frozenset[tuple[str, str]], str]:
    try:
        client = _load_runtime_client()
        return client.runtime_contract_snapshot()
    except (OSError, RuntimeError, ValueError):
        return frozenset(), ""


def _capture_artifact(content: str | bytes, author_model: str) -> ArtifactSnapshot:
    if isinstance(content, str):
        encoded = content.encode("utf-8")
    elif isinstance(content, bytes):
        encoded = content
    else:
        raise ValueError("artifact content must be text or bytes")
    if len(encoded) > MAX_ARTIFACT_BYTES:
        raise ValueError("artifact content exceeds the policy limit")
    if not isinstance(author_model, str):
        raise ValueError("artifact author model must be text")
    model = author_model.strip()
    return ArtifactSnapshot(
        present=bool(encoded.strip()),
        content_base64=base64.b64encode(encoded).decode("ascii"),
        content_sha256=hashlib.sha256(encoded).hexdigest(),
        content_size=len(encoded),
        author_model=model,
        author_family=resolve_model_family(model),
    )


def _safe_mode_enabled() -> bool:
    return os.environ.get("AGENT_COLLAB_SAFE_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def async_inbox_available(
    explicit_config: Mapping[str, str] | None = None,
) -> bool:
    values = explicit_config or {}
    observed = str(values.get("async_inbox", "")).strip().lower()
    if not observed:
        observed = os.environ.get("AGENT_COLLAB_ASYNC_INBOX", "").strip().lower()
    return observed in {"1", "true", "available", "yes", "on"}


def resolve_async_inbox_target(
    target_config: Mapping[str, str] | None,
) -> AsyncInboxTarget:
    values = target_config or {}
    target_id = str(values.get("target_id", "")).strip().lower()
    target_family = str(values.get("target_family", "")).strip().lower()
    target_session = str(values.get("target_session_identifier", "")).strip()
    expected_family = ASYNC_INBOX_TARGET_FAMILIES.get(target_id)
    trustworthy = (
        expected_family is not None
        and target_family == expected_family
        and bool(target_session)
        and target_session.lower() != "unknown"
    )
    return AsyncInboxTarget(
        target_id=target_id or "unknown",
        target_family=target_family if target_family in KNOWN_FAMILIES else "unknown",
        target_session_identifier=target_session or "unknown",
        trustworthy=trustworthy,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _validate_documents(value: object) -> bool:
    if not isinstance(value, list) or not value or len(value) > MAX_DOCUMENTS:
        return False
    total = 0
    for item in value:
        if not isinstance(item, dict) or set(item) != {"label", "content"}:
            return False
        label, content = item["label"], item["content"]
        if not isinstance(label, str) or not 1 <= len(label.encode("utf-8")) <= 256:
            return False
        if not isinstance(content, str):
            return False
        total += len(content.encode("utf-8"))
        if total > MAX_DOCUMENT_BYTES:
            return False
    return True


def _is_safe_cwd(value: object) -> bool:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > 4096:
        return False
    path = Path(value)
    return path.is_absolute() and ".git" not in path.parts


def _resolve_opencode_model(
    profile: HostProfile,
    explicit_config: Mapping[str, str] | None,
    row: Mapping[str, Any],
) -> str:
    values = explicit_config or {}
    if profile.host_runtime == "opencode" and profile.active_model != "unknown":
        return profile.active_model
    configured = str(values.get("opencode_model", "")).strip()
    if configured:
        return configured
    return DEFAULT_OPENCODE_MODEL


def _validate_row(
    route: str,
    action: str,
    row_config: Mapping[str, Any],
    profile: HostProfile,
    explicit_config: Mapping[str, str] | None,
    *,
    sealed: bool = False,
) -> tuple[dict[str, Any] | None, str, str]:
    row = dict(row_config)
    contract = (route, action)
    family = ROUTE_FAMILIES.get(route, "unknown")
    if contract in {("gemini", "advisory"), ("gemini", "long_context")}:
        required = {"model", "effort"}
        if action == "long_context":
            required.add("documents")
        if set(row) != required:
            return None, "unknown", "Gemini row fields are invalid"
        if (
            not isinstance(row["model"], str)
            or resolve_model_family(row["model"]) != "google"
            or not isinstance(row["effort"], str)
            or row["effort"] not in {"low", "medium", "high", "xhigh"}
            or (action == "long_context" and not _validate_documents(row["documents"]))
        ):
            return None, "unknown", "Gemini row values are invalid"
    elif contract == ("gemini", "governance"):
        if set(row) != {"model", "effort"}:
            return None, "unknown", "Gemini governance row fields are invalid"
        if (
            type(row["model"]) is not str
            or row["model"] != GEMINI_GOVERNANCE_MODEL
            or type(row["effort"]) is not str
            or row["effort"] not in GEMINI_GOVERNANCE_EFFORTS
        ):
            return None, "unknown", "Gemini governance row values are invalid"
    elif contract == ("codex", "advisory"):
        allowed = {"model", "effort", "mode", "cwd"}
        required = {"model", "effort", "mode"}
        if not required.issubset(row) or not set(row).issubset(allowed):
            return None, "unknown", "Codex row fields are invalid"
        if (
            not isinstance(row["model"], str)
            or resolve_model_family(row["model"]) != "openai"
            or not isinstance(row["effort"], str)
            or row["effort"] not in {"low", "medium", "high", "xhigh"}
            or not isinstance(row["mode"], str)
            or row["mode"] not in {"prompt-only", "repo-review"}
            or (row["mode"] == "prompt-only" and "cwd" in row)
            or (row["mode"] == "repo-review" and not _is_safe_cwd(row.get("cwd")))
        ):
            return None, "unknown", "Codex row values are invalid"
    elif contract in {("opencode", "plan"), ("opencode", "build")}:
        if not {"cwd"}.issubset(row) or not set(row).issubset({"model", "variant", "cwd"}):
            return None, "unknown", "OpenCode row fields are invalid"
        model = _resolve_opencode_model(profile, explicit_config, row)
        model_family = resolve_model_family(model)
        if not model:
            return None, "unknown", "OpenCode model is not observed"
        if model_family == "anthropic":
            return None, "anthropic", "Anthropic routing through OpenCode is prohibited"
        if model_family == "unknown":
            return None, "unknown", "OpenCode model family is unknown"
        if not _is_safe_cwd(row.get("cwd")):
            return None, model_family, "OpenCode cwd is invalid"
        if "variant" in row and (
            not isinstance(row["variant"], str) or len(row["variant"]) > 128
        ):
            return None, model_family, "OpenCode variant is invalid"
        row["model"] = model
        family = model_family
    elif contract in {("grok", "architecture"), ("grok", "governance")}:
        task_class, effort = _GROK_REVIEW_SEALS[contract]
        allowed = {"mode", "cwd", "task_class", "effort"} if sealed else {"mode", "cwd"}
        if not {"mode"}.issubset(row) or not set(row).issubset(allowed):
            return None, "unknown", "Grok row fields are invalid"
        if (
            not isinstance(row["mode"], str)
            or row["mode"] not in {"prompt-only", "repo-review"}
            or (row["mode"] == "prompt-only" and "cwd" in row)
            or (row["mode"] == "repo-review" and not _is_safe_cwd(row.get("cwd")))
            or (
                sealed
                and (
                    row.get("task_class") != task_class
                    or row.get("effort") != effort
                )
            )
        ):
            return None, "unknown", "Grok row values are invalid"
        if not sealed:
            row.update({"task_class": task_class, "effort": effort})
    elif contract == ("grok", "huge_context"):
        task_class, effort = _GROK_REVIEW_SEALS[contract]
        expected = (
            {"documents", "task_class", "effort"}
            if sealed
            else {"documents"}
        )
        if (
            set(row) != expected
            or not _validate_documents(row.get("documents"))
            or (
                sealed
                and (
                    row.get("task_class") != task_class
                    or row.get("effort") != effort
                )
            )
        ):
            return None, "unknown", "Grok huge-context row is invalid"
        if not sealed:
            row.update({"task_class": task_class, "effort": effort})
    elif contract == ("composer", "codegen"):
        if set(row) != {"task_class", "effort"}:
            return None, "unknown", "Grok 4.5 codegen row fields are invalid"
        task_class = row.get("task_class")
        effort = row.get("effort")
        minimum = (
            _GROK_CODEGEN_MINIMUMS.get(task_class)
            if isinstance(task_class, str)
            else None
        )
        if (
            minimum is None
            or not isinstance(effort, str)
            or effort not in _GROK_EFFORT_ORDER
            or _GROK_EFFORT_ORDER[effort] < _GROK_EFFORT_ORDER[minimum]
        ):
            return None, "unknown", "Grok 4.5 codegen task or effort is invalid"
    else:
        return None, "unknown", "route/action contract is unsupported"
    return row, family, ""


def _unsigned_envelope(envelope: PolicyEnvelope) -> bytes:
    values = asdict(envelope)
    values.pop("seal", None)
    return _canonical_json(values).encode("utf-8")


def verify_policy_envelope(envelope: object) -> bool:
    if not isinstance(envelope, PolicyEnvelope):
        return False
    expected = hmac.new(_SEAL_KEY, _unsigned_envelope(envelope), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, envelope.seal)


def startup_preflight(
    *,
    governance: bool,
    explicit_config: Mapping[str, str] | None,
    active_legacy_packages: Sequence[str],
    safe_mode: bool,
    artifact_author_model: str = "",
    artifact_content: str | bytes = b"",
    route_models: Mapping[str, str] | None = None,
    async_inbox_target: Mapping[str, str] | None = None,
    **_ignored_legacy_assertions: object,
) -> PreflightOutcome:
    """Return current eligible routes using verified runtime state only.

    Unknown keyword arguments are ignored solely so an older host cannot turn a
    caller-supplied ``native_capabilities`` list into readiness.  They never
    influence the result and are not used by the public coordinator.
    """

    profile = resolve_profile(explicit_config)
    if active_legacy_packages:
        return PreflightOutcome(
            PreflightStatus.DUPLICATE_BLOCKED,
            profile,
            (),
            "installed or active legacy package state blocks all provider routing",
        )
    if profile.identity_conflict:
        return PreflightOutcome(
            PreflightStatus.CONFIG_ERROR,
            profile,
            (),
            "current-session and explicit primary identity evidence conflict",
        )
    try:
        artifact = _capture_artifact(artifact_content, artifact_author_model)
    except ValueError as exc:
        return PreflightOutcome(
            PreflightStatus.CONFIG_ERROR, profile, (), str(exc)
        )
    if artifact.author_model and not artifact.present:
        return PreflightOutcome(
            PreflightStatus.CONFIG_ERROR,
            profile,
            (),
            "artifact author model requires nonblank artifact content",
        )
    artifact_family = artifact.author_family
    if governance and not profile.governance_ready:
        return PreflightOutcome(
            PreflightStatus.UNKNOWN_BLOCKED,
            profile,
            (),
            "governance review requires a complete trustworthy primary identity",
        )
    if governance and not artifact.present:
        return PreflightOutcome(
            PreflightStatus.CONFIG_ERROR,
            profile,
            (),
            "governance review requires nonblank captured artifact content",
        )
    if governance and artifact_family == "unknown":
        return PreflightOutcome(
            PreflightStatus.UNKNOWN_BLOCKED,
            profile,
            (),
            "governance review requires captured artifact-author model provenance",
        )
    inbox_observed = async_inbox_available(explicit_config)
    inbox_target = (
        resolve_async_inbox_target(async_inbox_target)
        if async_inbox_target is not None
        else None
    )
    if inbox_target is not None and not inbox_target.trustworthy:
        return PreflightOutcome(
            PreflightStatus.CONFIG_ERROR,
            profile,
            (),
            "async inbox target identity/family/session provenance is invalid",
        )
    inbox_family = (
        inbox_target.target_family if inbox_target is not None else ROUTE_FAMILIES["inbox"]
    )
    if (
        inbox_target is not None
        and profile.primary_family not in KNOWN_FAMILIES
    ):
        return PreflightOutcome(
            PreflightStatus.UNKNOWN_BLOCKED,
            profile,
            (),
            "async inbox independence requires a known primary family",
        )
    if inbox_target is not None and inbox_family == profile.primary_family:
        return PreflightOutcome(
            PreflightStatus.SAME_FAMILY_BLOCKED,
            profile,
            (),
            "async inbox target is not independent of the active primary family",
        )
    inbox = (
        ("inbox",)
        if inbox_observed
        and inbox_target is not None
        and profile.primary_family != inbox_family
        and artifact_family != inbox_family
        else ()
    )
    inbox_warning = (
        "async inbox is unavailable without an availability observation"
        if not inbox_observed
        else "async inbox target provenance is unavailable"
        if inbox_target is None
        else ""
    )
    if safe_mode or _safe_mode_enabled():
        return PreflightOutcome(
            PreflightStatus.OK,
            profile,
            inbox,
            "; ".join(
                part
                for part in (
                    "safe mode disables native routes",
                    (
                        "independence warning: incomplete or untrustworthy primary identity"
                        if not profile.governance_ready
                        else ""
                    ),
                    inbox_warning,
                )
                if part
            ),
        )
    contracts, _ = _runtime_contracts()
    if not contracts:
        warning = "native Gemini/Codex/OpenCode/Grok/Composer routes are typed unavailable"
        if not profile.governance_ready:
            warning += "; independence warning: incomplete or untrustworthy primary identity"
        if inbox_warning:
            warning += "; " + inbox_warning
        return PreflightOutcome(
            PreflightStatus.OK,
            profile,
            inbox,
            warning,
        )
    excluded = {profile.primary_family}
    if artifact_family in KNOWN_FAMILIES:
        excluded.add(artifact_family)
    rows = contracts.intersection(GOVERNANCE_CONTRACTS) if governance else contracts
    families: dict[str, str] = dict(ROUTE_FAMILIES)
    # Preflight and issuance must resolve the same selected OpenCode model.
    # Ambient variables and caller-supplied route rows are not central policy
    # and therefore cannot change either eligibility or artifact provenance.
    families["opencode"] = resolve_model_family(
        _resolve_opencode_model(profile, explicit_config, {})
    )
    native_routes = tuple(
        route
        for route in ("gemini", "codex", "opencode", "grok", "composer")
        if any(candidate == route for candidate, _ in rows)
        and families.get(route, "unknown") in KNOWN_FAMILIES
        and families[route] not in excluded
        and not (route == "opencode" and families[route] == "anthropic")
    )
    routes = inbox + native_routes
    warnings: list[str] = []
    if not profile.governance_ready and not governance:
        warnings.append("independence warning: incomplete or untrustworthy primary identity")
    if any(route == "opencode" for route, _ in rows) and families["opencode"] == "unknown":
        warnings.append("OpenCode model is not currently observed")
    if inbox_warning:
        warnings.append(inbox_warning)
    return PreflightOutcome(PreflightStatus.OK, profile, routes, "; ".join(warnings))


def issue_policy_envelope(
    *,
    request_id: str,
    route: str,
    action: str,
    governance: bool,
    explicit_target: bool = True,
    prompt: str,
    timeout_ms: int,
    explicit_config: Mapping[str, str] | None,
    row_config: Mapping[str, Any] | None = None,
    artifact_author_model: str = "",
    artifact_content: str | bytes = b"",
    operation: str = "execute",
    active_legacy_packages: Sequence[str] = (),
    safe_mode: bool = False,
) -> PolicyIssueOutcome:
    profile = resolve_profile(explicit_config)
    if active_legacy_packages:
        return PolicyIssueOutcome(
            PreflightStatus.DUPLICATE_BLOCKED,
            profile,
            None,
            "installed or active legacy package state blocks all provider routing",
        )
    if profile.identity_conflict:
        return PolicyIssueOutcome(
            PreflightStatus.CONFIG_ERROR,
            profile,
            None,
            "current-session and explicit primary identity evidence conflict",
        )
    if safe_mode or _safe_mode_enabled():
        return PolicyIssueOutcome(
            PreflightStatus.UNAVAILABLE,
            profile,
            None,
            "safe mode disables native routes; async inbox readiness requires "
            "a separate current host availability observation",
        )
    if (
        not isinstance(request_id, str)
        or not _REQUEST_ID_RE.fullmatch(request_id)
        or operation not in {"readiness", "execute"}
        or not isinstance(route, str)
        or not isinstance(action, str)
        or (route, action)
        not in ROUTE_ACTIONS.union(DECLARED_UNAVAILABLE_CONTRACTS)
        or type(governance) is not bool
        or type(explicit_target) is not bool
        or type(timeout_ms) is not int
        or not 1 <= timeout_ms <= MAX_TIMEOUT_MS
        or not isinstance(prompt, str)
        or len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES
        or (operation == "execute" and not prompt)
    ):
        return PolicyIssueOutcome(
            PreflightStatus.CONFIG_ERROR,
            profile,
            None,
            "request fields violate the closed policy protocol",
        )
    if governance and (route, action) not in GOVERNANCE_CONTRACTS:
        return PolicyIssueOutcome(
            PreflightStatus.CONFIG_ERROR,
            profile,
            None,
            "governance authority permits advisory reviewer routes only",
        )
    if not governance and action == "governance":
        return PolicyIssueOutcome(
            PreflightStatus.CONFIG_ERROR,
            profile,
            None,
            "governance action requires governance authority",
        )
    if row_config is not None and not isinstance(row_config, Mapping):
        return PolicyIssueOutcome(
            PreflightStatus.CONFIG_ERROR,
            profile,
            None,
            "route row must be an object",
        )
    if (route, action) in DECLARED_UNAVAILABLE_CONTRACTS:
        if row_config:
            return PolicyIssueOutcome(
                PreflightStatus.CONFIG_ERROR,
                profile,
                None,
                "Codex build accepts no row fields while unavailable",
            )
        return PolicyIssueOutcome(
            PreflightStatus.UNAVAILABLE,
            profile,
            None,
            "Codex build is unavailable until a hardened mutation backend exists",
        )
    try:
        artifact = _capture_artifact(artifact_content, artifact_author_model)
    except ValueError as exc:
        return PolicyIssueOutcome(PreflightStatus.CONFIG_ERROR, profile, None, str(exc))
    if artifact.author_model and not artifact.present:
        return PolicyIssueOutcome(
            PreflightStatus.CONFIG_ERROR,
            profile,
            None,
            "artifact author model requires nonblank artifact content",
        )
    if governance and not artifact.present:
        return PolicyIssueOutcome(
            PreflightStatus.CONFIG_ERROR,
            profile,
            None,
            "governance review requires nonblank captured artifact content",
        )
    if governance and not profile.governance_ready:
        return PolicyIssueOutcome(
            PreflightStatus.UNKNOWN_BLOCKED,
            profile,
            None,
            "governance review requires a complete trustworthy primary identity",
        )
    if governance and artifact.author_family == "unknown":
        return PolicyIssueOutcome(
            PreflightStatus.UNKNOWN_BLOCKED,
            profile,
            None,
            "governance review requires captured artifact-author model provenance",
        )
    row, target_family, row_error = _validate_row(
        route, action, row_config or {}, profile, explicit_config
    )
    if row is None:
        status = (
            PreflightStatus.UNKNOWN_BLOCKED
            if "unknown" in row_error.lower() or "not observed" in row_error.lower()
            else PreflightStatus.CONFIG_ERROR
        )
        return PolicyIssueOutcome(status, profile, None, row_error)
    contracts, manifest_digest = _runtime_contracts()
    if (route, action) not in contracts or not manifest_digest:
        return PolicyIssueOutcome(
            PreflightStatus.UNAVAILABLE,
            profile,
            None,
            f"native route {route}/{action} is typed unavailable",
        )
    excluded = {profile.primary_family}
    if artifact.author_family in KNOWN_FAMILIES:
        excluded.add(artifact.author_family)
    if target_family in excluded:
        return PolicyIssueOutcome(
            PreflightStatus.SAME_FAMILY_BLOCKED,
            profile,
            None,
            "selected route is not independent of the primary/artifact snapshots",
        )
    authority = AUTHORITIES[(route, action)]
    unsigned = PolicyEnvelope(
        request_id=request_id,
        operation=operation,
        route=route,
        action=action,
        authority=authority,
        timeout_ms=timeout_ms,
        prompt=prompt,
        row_json=_canonical_json(row),
        primary_id=profile.primary_id,
        primary_family=profile.primary_family,
        primary_model=profile.active_model,
        primary_host_runtime=profile.host_runtime,
        primary_session_identifier=profile.session_identifier,
        artifact_present=artifact.present,
        artifact_content_base64=artifact.content_base64,
        artifact_size=artifact.content_size,
        artifact_sha256=artifact.content_sha256,
        artifact_author_model=artifact.author_model,
        artifact_author_family=artifact.author_family,
        target_author_family=target_family,
        runtime_manifest_digest=manifest_digest,
        governance=governance,
        explicit_target=explicit_target,
        nonce=secrets.token_hex(16),
        seal="",
    )
    seal = hmac.new(_SEAL_KEY, _unsigned_envelope(unsigned), hashlib.sha256).hexdigest()
    envelope = PolicyEnvelope(**{**asdict(unsigned), "seal": seal})
    warnings: list[str] = []
    if not profile.governance_ready:
        warnings.append("independence warning: incomplete or untrustworthy primary identity")
    if artifact.present and artifact.author_family == "unknown":
        warnings.append("independence warning: unknown artifact-author family")
    return PolicyIssueOutcome(
        PreflightStatus.OK, profile, envelope, "; ".join(warnings)
    )
