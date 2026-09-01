#!/usr/bin/env python3
"""Validate and invoke the co-packaged direct native runtime.

The public client owns the outer deadline and process lifecycle.  It has no
provider command, broker, socket, lane, daemon, setup, or replay surface.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
import hashlib
import importlib.util
import json
import os
import platform
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from types import MappingProxyType
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping, Sequence


PLUGIN_ROOT = Path(__file__).resolve().parent
MANIFEST_NAME = "runtime-manifest.json"
MANIFEST_SCHEMA_VERSION = 4
PROTOCOL_VERSION = 4
CONTRACT_VERSION = 4
PROVIDER_RUNTIME_VERSION = "5.0.3"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 48 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_STDERR_BYTES = 256 * 1024
MAX_TIMEOUT_MS = 86_400_000
TERM_GRACE_SECONDS = 0.5
# Teardown proof gets its own small bounded budget, independent of the
# (possibly already exhausted) request deadline. A SIGKILLed process group
# normally vanishes in milliseconds; sharing the request deadline starved
# the proof after long provider calls and minted frequent false
# teardown_error results, most visibly on long Agy runs.
TEARDOWN_REAP_SECONDS = 5.0
PROCESS_CLEANUP_RESERVE_SECONDS = TERM_GRACE_SECONDS * 4
_PROGRESS_FD_ENV = "AGENT_COLLAB_RUNTIME_PROGRESS_FD"
_PROGRESS_MARK = b"\x01"
EXPECTED_MINIMUM_MACOS = "14.0"
RUNTIME_ENTRYPOINT = "agent-collab-runtime"
SUPPORTED_ARTIFACT_PATHS = MappingProxyType({
    ("darwin", "arm64"): "runtime/darwin-arm64/agent-collab-runtime.bundle",
    ("darwin", "x86_64"): "runtime/darwin-x86_64/agent-collab-runtime.bundle",
})
_HOST_ARCH_ALIASES = {
    "arm64": "arm64",
    "aarch64": "arm64",
    "x86_64": "x86_64",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){1,2}$")
_TEAM_ID_RE = re.compile(r"^[A-Z0-9]{10}$")
_CODESIGN_TEAM_RE = re.compile(r"(?m)^TeamIdentifier=([A-Z0-9]{10})(?=\s|$)")
_CODESIGN_FLAGS_RE = re.compile(r"\bflags=(0x[0-9a-f]+)(?:\([^)]*\))?", re.I)
_CODESIGN_TIMESTAMP_RE = re.compile(r"(?m)^Timestamp=(.+)$")
_WIRE_KEYS_V6 = frozenset(
    {
        "artifacts",
        "advisory_response",
        "base_transport_actions",
        "bounded_diagnostics",
        "execution_receipt",
        "failure_response",
        "logical_action_source_modes",
        "logical_actions",
        "routing_source_sha256",
        "runtime_protocol_version",
        "schema_version",
        "semantic_request",
        "success_response",
        "valid_action_source_pairs",
        "zero_inference_readiness",
    }
)
_WIRE_IDENTITY_KEYS_V7 = frozenset(
    {
        "logical_agents",
        "model_lineages",
        "logical_action_targets",
        "logical_action_effort_floors",
    }
)
_WIRE_IDENTITY_KEYS_V9 = _WIRE_IDENTITY_KEYS_V7 | {"logical_action_timeout_modes"}
_EFFORT_CLASSES = frozenset({"minimal", "standard", "maximum"})
_TIMEOUT_MODES = frozenset({"total_deadline", "admitted_progress_inactivity"})
_MAX_DESCRIPTOR_IDENTITIES = 64
_ARTIFACT_SCHEMAS = frozenset(
    {"review_findings", "governance_verdict", "context_text", "private_patch"}
)
_SOURCE_MODES = frozenset({"conceptual_prompt", "documents", "repository"})
_SCHEMA_KEYWORDS = frozenset(
    {
        "additionalProperties",
        "allOf",
        "const",
        "enum",
        "items",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "not",
        "oneOf",
        "pattern",
        "prefixItems",
        "properties",
        "required",
        "type",
        "uniqueItems",
        "x-inspectedPathsEqualSuccessfulEvidence",
        "x-maxCanonicalUtf8Bytes",
        "x-maxTotalContentUtf8Bytes",
        "x-maxTotalDeclaredBytes",
        "x-maxTotalFindingUtf8Bytes",
        "x-maxTotalLabelUtf8Bytes",
        "x-maxTotalPathUtf8Bytes",
        "x-maxTotalUtf8Bytes",
        "x-maxUtf8Bytes",
        "x-maxUtf8ComponentBytes",
        "x-uniqueSuccessfulPaths",
    }
)
_SCHEMA_TYPES = frozenset(
    {"array", "boolean", "integer", "null", "number", "object", "string"}
)
_SCHEMA_INTEGER_KEYWORDS = frozenset(
    {
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "x-maxCanonicalUtf8Bytes",
        "x-maxTotalContentUtf8Bytes",
        "x-maxTotalDeclaredBytes",
        "x-maxTotalFindingUtf8Bytes",
        "x-maxTotalLabelUtf8Bytes",
        "x-maxTotalPathUtf8Bytes",
        "x-maxTotalUtf8Bytes",
        "x-maxUtf8Bytes",
        "x-maxUtf8ComponentBytes",
    }
)
_SCHEMA_TRUE_KEYWORDS = frozenset(
    {
        "uniqueItems",
        "x-inspectedPathsEqualSuccessfulEvidence",
        "x-uniqueSuccessfulPaths",
    }
)


def _load_runtime_bundle():
    name = "agent_collab_direct_runtime_bundle"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, PLUGIN_ROOT / "runtime_bundle.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("runtime bundle verifier cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime_bundle = _load_runtime_bundle()


class RuntimeStatus(str, Enum):
    OK = "ok"
    ADVISORY = "advisory"
    INVALID_REQUEST = "invalid_request"
    UNAVAILABLE = "unavailable"
    AUTH_ERROR = "auth_error"
    QUOTA_ERROR = "quota_error"
    CAPABILITY_ERROR = "capability_error"
    PROTOCOL_ERROR = "protocol_error"
    PROVIDER_ERROR = "provider_error"
    OUTPUT_LIMIT = "output_limit"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PLATFORM_UNSUPPORTED = "platform_unsupported"
    MANIFEST_INVALID = "manifest_invalid"
    PATH_INVALID = "path_invalid"
    INTEGRITY_ERROR = "integrity_error"
    SIGNATURE_ERROR = "signature_error"
    TEARDOWN_ERROR = "teardown_error"


_RUNTIME_RESPONSE_STATUSES = frozenset(
    {
        RuntimeStatus.OK,
        RuntimeStatus.ADVISORY,
        RuntimeStatus.INVALID_REQUEST,
        RuntimeStatus.UNAVAILABLE,
        RuntimeStatus.AUTH_ERROR,
        RuntimeStatus.QUOTA_ERROR,
        RuntimeStatus.CAPABILITY_ERROR,
        RuntimeStatus.PROTOCOL_ERROR,
        RuntimeStatus.PROVIDER_ERROR,
        RuntimeStatus.OUTPUT_LIMIT,
        RuntimeStatus.TIMEOUT,
        RuntimeStatus.CANCELLED,
    }
)


@dataclass(frozen=True)
class WireDescriptorSnapshot:
    sha256: str
    logical_actions: frozenset[str]
    logical_action_source_modes: Mapping[str, str]
    transport_actions: frozenset[tuple[str, str]]
    action_source_pairs: frozenset[tuple[str, str, str]]
    semantic_request: Mapping[str, Any]
    success_response: Mapping[str, Any]
    advisory_response: Mapping[str, Any]
    failure_response: Mapping[str, Any]
    artifact_schemas: Mapping[str, Any]
    execution_receipt: Mapping[str, Any]
    readiness_request: Mapping[str, Any]
    readiness_response: Mapping[str, Any]
    bounded_diagnostics: Mapping[str, Any]
    routing_source_sha256: str
    logical_agents: frozenset[str]
    model_lineages: frozenset[str]
    logical_action_targets: Mapping[str, tuple[str, ...]]
    logical_action_effort_floors: Mapping[str, str]
    logical_action_timeout_modes: Mapping[str, str]


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    mode: int
    links: int
    uid: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass(frozen=True)
class RuntimeResolution:
    status: RuntimeStatus
    path: Path | None = None
    bundle_path: Path | None = None
    files: tuple[Mapping[str, Any], ...] = ()
    manifest_digest: str = ""
    artifact_digest: str = ""
    identity: FileIdentity | None = None
    wire: WireDescriptorSnapshot | None = None
    error: str = ""


@dataclass(frozen=True)
class RuntimeResult:
    status: RuntimeStatus
    result: object | None = None
    provenance: Mapping[str, Any] | None = None
    error: str = ""
    manifest_digest: str = ""
    artifact_digest: str = ""


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _exact_int(value: object, expected: int | None = None) -> bool:
    return type(value) is int and (expected is None or value == expected)


def _unique_rows(value: object, width: int) -> frozenset[tuple[str, ...]]:
    if type(value) is not list:
        raise ValueError("wire descriptor projection is not an array")
    rows: list[tuple[str, ...]] = []
    for item in value:
        if (
            type(item) is not list
            or len(item) != width
            or any(type(part) is not str or not part for part in item)
        ):
            raise ValueError("wire descriptor projection row is invalid")
        rows.append(tuple(item))
    if len(rows) != len(set(rows)):
        raise ValueError("wire descriptor projection contains duplicates")
    return frozenset(rows)


def validate_wire_descriptor(
    descriptor: object, *, expected_sha256: str
) -> WireDescriptorSnapshot:
    """Validate one closed workspace-generated descriptor and derive projections."""

    if type(expected_sha256) is not str or _SHA256_RE.fullmatch(expected_sha256) is None:
        raise ValueError("wire descriptor digest is invalid")
    if type(descriptor) is not dict:
        raise ValueError("wire descriptor is not closed")
    schema_version = descriptor.get("schema_version")
    if (
        not _exact_int(schema_version)
        or schema_version < 1
        or schema_version > 10
    ):
        raise ValueError("wire descriptor schema version is invalid")
    expected_keys = (
        _WIRE_KEYS_V6 | _WIRE_IDENTITY_KEYS_V9
        if schema_version in {9, 10}
        else _WIRE_KEYS_V6 | _WIRE_IDENTITY_KEYS_V7
        if schema_version in {7, 8}
        else _WIRE_KEYS_V6
    )
    if frozenset(descriptor) != expected_keys:
        raise ValueError("wire descriptor is not closed")
    try:
        encoded = _canonical_json(descriptor)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("wire descriptor is not canonical JSON") from exc
    if hashlib.sha256(encoded).hexdigest() != expected_sha256:
        raise ValueError("wire descriptor digest does not match")
    if not _exact_int(descriptor["runtime_protocol_version"], PROTOCOL_VERSION):
        raise ValueError("wire descriptor runtime protocol is unsupported")
    routing_sha = descriptor["routing_source_sha256"]
    if type(routing_sha) is not str or _SHA256_RE.fullmatch(routing_sha) is None:
        raise ValueError("wire descriptor routing digest is invalid")

    actions_value = descriptor["logical_actions"]
    if (
        type(actions_value) is not list
        or len(actions_value) != 12
        or any(type(action) is not str or not action for action in actions_value)
        or len(set(actions_value)) != 12
    ):
        raise ValueError("wire descriptor logical actions are invalid")
    action_source_modes = descriptor["logical_action_source_modes"]
    if (
        type(action_source_modes) is not dict
        or set(action_source_modes) != set(actions_value)
        or any(
            type(mode) is not str or mode not in _SOURCE_MODES
            for mode in action_source_modes.values()
        )
    ):
        raise ValueError("wire descriptor logical action sources are invalid")
    transports = _unique_rows(descriptor["base_transport_actions"], 2)
    pairs = _unique_rows(descriptor["valid_action_source_pairs"], 3)
    if len(transports) != 15 or len(pairs) != 19:
        raise ValueError("wire descriptor projections have wrong cardinality")
    if any(row[:2] not in transports or row[2] not in _SOURCE_MODES for row in pairs):
        raise ValueError("wire descriptor source projection is inconsistent")

    logical_agents: frozenset[str] = frozenset()
    model_lineages: frozenset[str] = frozenset()
    action_targets: dict[str, tuple[str, ...]] = {}
    effort_floors: dict[str, str] = {}
    timeout_modes: dict[str, str] = {}
    if schema_version in {7, 8, 9, 10}:
        raw_agents = descriptor["logical_agents"]
        raw_lineages = descriptor["model_lineages"]
        if (
            type(raw_agents) is not list
            or not raw_agents
            or len(raw_agents) > _MAX_DESCRIPTOR_IDENTITIES
            or any(
                type(item) is not str
                or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", item) is None
                for item in raw_agents
            )
            or len(raw_agents) != len(set(raw_agents))
        ):
            raise ValueError("wire descriptor logical agents are invalid")
        if (
            type(raw_lineages) is not list
            or not raw_lineages
            or len(raw_lineages) > _MAX_DESCRIPTOR_IDENTITIES
            or any(
                type(item) is not str
                or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", item) is None
                for item in raw_lineages
            )
            or len(raw_lineages) != len(set(raw_lineages))
        ):
            raise ValueError("wire descriptor model lineages are invalid")
        logical_agents = frozenset(raw_agents)
        model_lineages = frozenset(raw_lineages)
        raw_targets = descriptor["logical_action_targets"]
        raw_floors = descriptor["logical_action_effort_floors"]
        if (
            type(raw_targets) is not dict
            or set(raw_targets) != set(actions_value)
            or type(raw_floors) is not dict
            or set(raw_floors) != set(actions_value)
        ):
            raise ValueError("wire descriptor action recovery projections are invalid")
        for action in actions_value:
            targets = raw_targets[action]
            if (
                type(targets) is not list
                or not targets
                or len(targets) > _MAX_DESCRIPTOR_IDENTITIES
                or any(type(item) is not str or item not in logical_agents for item in targets)
                or len(targets) != len(set(targets))
                or type(raw_floors[action]) is not str
                or raw_floors[action] not in _EFFORT_CLASSES
            ):
                raise ValueError("wire descriptor action recovery projections are invalid")
            action_targets[action] = tuple(targets)
            effort_floors[action] = raw_floors[action]
        if schema_version >= 9:
            raw_timeout_modes = descriptor["logical_action_timeout_modes"]
            if (
                type(raw_timeout_modes) is not dict
                or set(raw_timeout_modes) != set(actions_value)
                or any(
                    type(mode) is not str or mode not in _TIMEOUT_MODES
                    for mode in raw_timeout_modes.values()
                )
            ):
                raise ValueError("wire descriptor action timeout modes are invalid")
            timeout_modes = dict(raw_timeout_modes)

    artifacts = descriptor["artifacts"]
    if type(artifacts) is not dict or frozenset(artifacts) != _ARTIFACT_SCHEMAS:
        raise ValueError("wire descriptor artifact schemas are invalid")
    schema_fields = (
        "semantic_request",
        "success_response",
        "advisory_response",
        "failure_response",
        "execution_receipt",
        "bounded_diagnostics",
    )
    if any(type(descriptor[name]) is not dict or not descriptor[name] for name in schema_fields):
        raise ValueError("wire descriptor contains an invalid JSON schema")
    if any(type(schema) is not dict or not schema for schema in artifacts.values()):
        raise ValueError("wire descriptor contains an invalid artifact schema")
    for name in schema_fields:
        _validate_schema_document(descriptor[name])
    for schema in artifacts.values():
        _validate_schema_document(schema)
    if schema_version in {7, 8, 9, 10}:
        repository_probe = {"mode": "repository", "repo_root": "/"}
        for variant in descriptor["semantic_request"]["properties"]["source"]["oneOf"]:
            if variant.get("properties", {}).get("mode") == {"const": "repository"}:
                if "expected_repo_head" in variant["properties"]:
                    repository_probe["expected_repo_head"] = "1" * 40
                break
        if (
            schema_version in {8, 9, 10}
            and "expected_repo_head" not in repository_probe
        ):
            raise ValueError(
                f"wire descriptor v{schema_version} repository source is not head-bound"
            )
        semantic_probe = {
            "wire_contract_sha256": expected_sha256,
            "request_id": f"descriptor-v{schema_version}-probe",
            "logical_action": "review.repository",
            "quality_profile": "frontier",
            "effort_class": "maximum",
            "target_agent": None,
            "author_lineage": None,
            "timeout_ms": 1,
            "prompt": "Probe.",
            "source": repository_probe,
            "occupied_model_lineages": [next(iter(model_lineages))],
            "evidence_anchors": [{"id": "probe", "path": "README.md"}],
        }
        try:
            _validate_schema(semantic_probe, descriptor["semantic_request"])
        except ValueError as exc:
            raise ValueError(
                "wire descriptor semantic request is inconsistent with identity projections"
            ) from exc
        if schema_version in {8, 9, 10}:
            for invalid_head in (None, "0" * 40, "0" * 64):
                invalid_probe = dict(semantic_probe)
                invalid_source = dict(repository_probe)
                if invalid_head is None:
                    invalid_source.pop("expected_repo_head")
                else:
                    invalid_source["expected_repo_head"] = invalid_head
                invalid_probe["source"] = invalid_source
                try:
                    _validate_schema(invalid_probe, descriptor["semantic_request"])
                except ValueError:
                    continue
                raise ValueError(
                    f"wire descriptor v{schema_version} repository source admits an unbound head"
                )
    readiness = descriptor["zero_inference_readiness"]
    if (
        type(readiness) is not dict
        or set(readiness) != {"request", "response"}
        or any(type(readiness[name]) is not dict or not readiness[name] for name in readiness)
    ):
        raise ValueError("wire descriptor readiness contract is invalid")
    _validate_schema_document(readiness["request"])
    _validate_schema_document(readiness["response"])
    return WireDescriptorSnapshot(
        sha256=expected_sha256,
        logical_actions=frozenset(actions_value),
        logical_action_source_modes=dict(action_source_modes),
        transport_actions=frozenset(transports),
        action_source_pairs=frozenset(pairs),
        semantic_request=descriptor["semantic_request"],
        success_response=descriptor["success_response"],
        advisory_response=descriptor["advisory_response"],
        failure_response=descriptor["failure_response"],
        artifact_schemas=artifacts,
        execution_receipt=descriptor["execution_receipt"],
        readiness_request=readiness["request"],
        readiness_response=readiness["response"],
        bounded_diagnostics=descriptor["bounded_diagnostics"],
        routing_source_sha256=routing_sha,
        logical_agents=logical_agents,
        model_lineages=model_lineages,
        logical_action_targets=action_targets,
        logical_action_effort_floors=effort_floors,
        logical_action_timeout_modes=timeout_modes,
    )


def _identity(path: Path, *, directory: bool = False, executable: bool = False) -> FileIdentity | None:
    try:
        info = path.lstat()
    except OSError:
        return None
    wanted = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if (
        not wanted
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.geteuid()
        or (not directory and info.st_nlink != 1)
        or (executable and not info.st_mode & stat.S_IXUSR)
        or info.st_mode & 0o7000
    ):
        return None
    return FileIdentity(
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_regular(path: Path, *, limit: int) -> tuple[bytes, FileIdentity] | None:
    before = _identity(path)
    if before is None or before.size > limit:
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            raw = bytearray()
            while len(raw) <= limit:
                chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
        finally:
            os.close(descriptor)
    except OSError:
        return None
    if len(raw) > limit or _identity(path) != before or opened.st_ino != before.inode:
        return None
    return bytes(raw), before


def _path_beneath(root: Path, relative: object) -> Path | None:
    if type(relative) is not str:
        return None
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    candidate = root.joinpath(*pure.parts)
    try:
        if candidate.resolve(strict=False).is_relative_to(root.resolve(strict=True)):
            return candidate
    except (OSError, RuntimeError):
        pass
    return None


def _manifest_entries(
    data: object,
) -> tuple[tuple[Mapping[str, Any], ...] | None, WireDescriptorSnapshot | None, str]:
    keys = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "wire_contract",
        "wire_contract_sha256",
        "channel",
        "artifacts",
    }
    if type(data) is not dict or set(data) != keys:
        return None, None, "runtime manifest is not schema 4"
    if not (
        _exact_int(data["schema_version"], MANIFEST_SCHEMA_VERSION)
        and _exact_int(data["protocol_version"], PROTOCOL_VERSION)
        and _exact_int(data["contract_version"], CONTRACT_VERSION)
        and data["channel"] == "production"
    ):
        return None, None, "runtime manifest version unit is unsupported"
    try:
        wire = validate_wire_descriptor(
            data["wire_contract"], expected_sha256=data["wire_contract_sha256"]
        )
    except ValueError as exc:
        return None, None, str(exc)
    artifacts = data["artifacts"]
    if type(artifacts) is not list or len(artifacts) > len(SUPPORTED_ARTIFACT_PATHS):
        return None, wire, "runtime manifest artifact cardinality is invalid"
    if not artifacts:
        return (), wire, "runtime artifact is absent"
    required = {
        "platform",
        "arch",
        "kind",
        "minimum_macos",
        "path",
        "entrypoint",
        "size",
        "sha256",
        "provider_runtime_version",
        "wire_contract_sha256",
        "signing",
        "files",
    }
    signing_keys = {
        "mode",
        "identity",
        "team_id",
        "require_notarization",
        "hardened_runtime",
        "secure_timestamp",
    }
    normalized_entries = []
    seen_hosts: set[tuple[str, str]] = set()
    for item in artifacts:
        if type(item) is not dict or set(item) != required:
            return None, wire, "runtime artifact record is not closed"
        if type(item["platform"]) is not str or type(item["arch"]) is not str:
            return None, wire, "runtime artifact identity is invalid"
        host = (item["platform"], item["arch"])
        if host in seen_hosts:
            return None, wire, "runtime manifest has a duplicate host row"
        seen_hosts.add(host)
        if not (
            host in SUPPORTED_ARTIFACT_PATHS
            and item["kind"] == "standalone_bundle"
            and item["minimum_macos"] == EXPECTED_MINIMUM_MACOS
            and item["path"] == SUPPORTED_ARTIFACT_PATHS[host]
            and item["entrypoint"] == RUNTIME_ENTRYPOINT
            and _exact_int(item["size"])
            and 0 < item["size"] <= runtime_bundle.MAX_BUNDLE_BYTES
            and type(item["sha256"]) is str
            and _SHA256_RE.fullmatch(item["sha256"])
            and item["provider_runtime_version"] == PROVIDER_RUNTIME_VERSION
        ):
            return None, wire, "runtime artifact identity is invalid"
        if item["wire_contract_sha256"] != wire.sha256:
            return None, wire, "runtime artifact wire contract is inconsistent"
        signing = item["signing"]
        if (
            type(signing) is not dict
            or set(signing) != signing_keys
            or signing["mode"] != "developer_id"
            or type(signing["identity"]) is not str
            or type(signing["team_id"]) is not str
            or _TEAM_ID_RE.fullmatch(signing["team_id"]) is None
            or signing["require_notarization"] is not True
            or signing["hardened_runtime"] is not True
            or signing["secure_timestamp"] is not True
        ):
            return None, wire, "runtime signing policy is invalid"
        try:
            files = runtime_bundle.validate_file_records(item["files"])
        except runtime_bundle.BundleContractError as exc:
            return None, wire, str(exc)
        if any(record["architecture"] != item["arch"] for record in files):
            return None, wire, "runtime artifact member architecture is invalid"
        entrypoints = [record for record in files if record["role"] == "entrypoint"]
        if len(entrypoints) != 1 or entrypoints[0]["path"] != RUNTIME_ENTRYPOINT:
            return None, wire, "runtime entrypoint membership is invalid"
        normalized = dict(item)
        normalized["files"] = files
        normalized_entries.append(normalized)
    return tuple(normalized_entries), wire, ""


def validate_manifest_document(
    data: object, *, require_artifact: bool = False
) -> tuple[tuple[Mapping[str, Any], ...], WireDescriptorSnapshot]:
    """Validate a manifest document for public archive/release consumers."""

    entries, wire, error = _manifest_entries(data)
    if entries is None or wire is None or (require_artifact and not entries):
        raise ValueError(error or "runtime artifact is required")
    return entries, wire


def parse_manifest_bytes(
    raw: bytes, *, require_artifact: bool = False
) -> tuple[tuple[Mapping[str, Any], ...], WireDescriptorSnapshot, Mapping[str, Any]]:
    """Strictly decode and validate the exact bytes every manifest consumer uses."""

    try:
        document = runtime_bundle.load_closed_json_object(
            raw, max_bytes=MAX_MANIFEST_BYTES
        )
        artifacts, wire = validate_manifest_document(
            document, require_artifact=require_artifact
        )
    except runtime_bundle.BundleContractError as exc:
        raise ValueError("runtime manifest is unreadable") from exc
    return artifacts, wire, document


def _inspect_member(path: Path, record: Mapping[str, Any], signing: Mapping[str, Any]) -> dict[str, str]:
    try:
        arch = subprocess.run(
            ["/usr/bin/lipo", "-archs", str(path)], capture_output=True, text=True, timeout=20
        )
        load = subprocess.run(
            ["/usr/bin/otool", "-l", str(path)], capture_output=True, text=True, timeout=20
        )
        verify = subprocess.run(
            ["/usr/bin/codesign", "--verify", "--strict", "--verbose=4", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        details = subprocess.run(
            ["/usr/bin/codesign", "-dv", "--verbose=4", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise runtime_bundle.BundleContractError("runtime signature inspection failed") from exc
    detail_text = details.stdout + details.stderr
    if (
        arch.returncode
        or arch.stdout.strip().split() != [record["architecture"]]
        or load.returncode
    ):
        raise runtime_bundle.BundleContractError("runtime Mach-O identity is invalid")
    if verify.returncode or details.returncode:
        raise runtime_bundle.BundleContractError("runtime Developer ID signature is invalid")
    teams = _CODESIGN_TEAM_RE.findall(detail_text)
    authorities = re.findall(r"(?m)^Authority=(.+)$", detail_text)
    timestamp = _CODESIGN_TIMESTAMP_RE.search(detail_text)
    hardened = any(
        int(match.group(1), 16) & 0x10000 for match in _CODESIGN_FLAGS_RE.finditer(detail_text)
    )
    if (
        teams != [signing["team_id"]]
        or not authorities
        or authorities[0] != signing["identity"]
        or not hardened
        or timestamp is None
        or timestamp.group(1).strip().casefold() in {"", "none", "not set", "unsigned"}
    ):
        raise runtime_bundle.BundleContractError("runtime Developer ID identity is invalid")
    build_blocks = [
        block
        for block in re.split(r"(?m)^Load command \d+\s*$", load.stdout)
        if re.search(r"(?m)^\s*cmd\s+LC_BUILD_VERSION\s*$", block)
    ]
    if len(build_blocks) != 1:
        raise runtime_bundle.BundleContractError("runtime minimum macOS identity is ambiguous")
    minimum = re.search(r"(?m)^\s*minos\s+(\S+)\s*$", build_blocks[0])
    if minimum is None or minimum.group(1) != record["minimum_macos"]:
        raise runtime_bundle.BundleContractError("runtime minimum macOS identity changed")
    return {
        "macho_type": record["macho_type"],
        "architecture": record["architecture"],
        "minimum_macos": record["minimum_macos"],
        "signing_profile": "production_developer_id",
    }


_CACHE_KEY: tuple[FileIdentity, FileIdentity] | None = None
_CACHE_VALUE: RuntimeResolution | None = None


def runtime_contract_snapshot() -> tuple[WireDescriptorSnapshot | None, str, str]:
    """Read the descriptor without inspecting or launching a provider runtime."""

    loaded = _read_regular(PLUGIN_ROOT / MANIFEST_NAME, limit=MAX_MANIFEST_BYTES)
    if loaded is None:
        return None, "", "runtime manifest is absent or unsafe"
    raw, _identity_value = loaded
    digest = hashlib.sha256(raw).hexdigest()
    try:
        artifacts, wire, _data = parse_manifest_bytes(raw)
    except ValueError as exc:
        return None, digest, str(exc)
    return wire, digest, "" if artifacts else "runtime artifact is absent"


def _select_artifact(
    artifacts: Sequence[Mapping[str, Any]], *, system: str, machine: str
) -> tuple[Mapping[str, Any] | None, RuntimeStatus, str]:
    """Select exactly one closed manifest row from local OS-provided host facts."""

    if not artifacts:
        return None, RuntimeStatus.UNAVAILABLE, "runtime artifact is absent"
    if type(system) is not str or type(machine) is not str:
        return None, RuntimeStatus.PLATFORM_UNSUPPORTED, "runtime host is unsupported"
    normalized_system = system.casefold()
    normalized_arch = _HOST_ARCH_ALIASES.get(machine.casefold())
    host = (normalized_system, normalized_arch)
    if normalized_arch is None or host not in SUPPORTED_ARTIFACT_PATHS:
        return None, RuntimeStatus.PLATFORM_UNSUPPORTED, "runtime host is unsupported"
    matches = [
        artifact
        for artifact in artifacts
        if (artifact["platform"], artifact["arch"]) == host
    ]
    if not matches:
        return None, RuntimeStatus.PLATFORM_UNSUPPORTED, "runtime host has no artifact"
    if len(matches) != 1:
        return None, RuntimeStatus.MANIFEST_INVALID, "runtime host row is ambiguous"
    return matches[0], RuntimeStatus.OK, ""


def resolve_runtime() -> RuntimeResolution:
    global _CACHE_KEY, _CACHE_VALUE

    loaded = _read_regular(PLUGIN_ROOT / MANIFEST_NAME, limit=MAX_MANIFEST_BYTES)
    if loaded is None:
        return RuntimeResolution(RuntimeStatus.UNAVAILABLE, error="runtime manifest is absent or unsafe")
    raw, manifest_identity = loaded
    manifest_digest = hashlib.sha256(raw).hexdigest()
    try:
        artifacts, wire, _data = parse_manifest_bytes(raw)
    except ValueError:
        return RuntimeResolution(RuntimeStatus.MANIFEST_INVALID, manifest_digest=manifest_digest, error="runtime manifest is unreadable")
    entry, status, error = _select_artifact(
        artifacts, system=platform.system(), machine=platform.machine()
    )
    if entry is None:
        return RuntimeResolution(
            status, manifest_digest=manifest_digest, wire=wire, error=error
        )
    root = PLUGIN_ROOT.resolve(strict=True)
    bundle_path = _path_beneath(root, entry["path"])
    if bundle_path is None or _identity(bundle_path, directory=True) is None:
        return RuntimeResolution(RuntimeStatus.PATH_INVALID, manifest_digest=manifest_digest, wire=wire, error="runtime bundle path is unsafe")
    entrypoint = bundle_path / entry["entrypoint"]
    entry_identity = _identity(entrypoint, executable=True)
    if entry_identity is None:
        return RuntimeResolution(RuntimeStatus.UNAVAILABLE, manifest_digest=manifest_digest, wire=wire, error="runtime artifact is absent or unsafe")
    cache_key = (manifest_identity, entry_identity)
    if cache_key == _CACHE_KEY and _CACHE_VALUE is not None:
        return _CACHE_VALUE
    by_name = {record["path"]: record for record in entry["files"]}
    try:
        digest = runtime_bundle.verify_bundle_tree(
            bundle_path,
            entry["files"],
            inspector=lambda member: _inspect_member(member, by_name[member.name], entry["signing"]),
        )
    except runtime_bundle.BundleContractError as exc:
        return RuntimeResolution(RuntimeStatus.INTEGRITY_ERROR, manifest_digest=manifest_digest, wire=wire, error=str(exc))
    if digest != entry["sha256"] or _identity(entrypoint, executable=True) != entry_identity:
        return RuntimeResolution(RuntimeStatus.INTEGRITY_ERROR, manifest_digest=manifest_digest, wire=wire, error="runtime bundle identity changed")
    result = RuntimeResolution(
        RuntimeStatus.OK,
        path=entrypoint,
        bundle_path=bundle_path,
        files=tuple(entry["files"]),
        manifest_digest=manifest_digest,
        artifact_digest=digest,
        identity=entry_identity,
        wire=wire,
    )
    _CACHE_KEY, _CACHE_VALUE = cache_key, result
    return result


def _json_type(value: object, expected: object) -> bool:
    values = expected if type(expected) is list else [expected]
    return any(
        (kind == "object" and type(value) is dict)
        or (kind == "array" and type(value) is list)
        or (kind == "string" and type(value) is str)
        or (kind == "integer" and type(value) is int)
        or (kind == "number" and type(value) in {int, float})
        or (kind == "boolean" and type(value) is bool)
        or (kind == "null" and value is None)
        for kind in values
    )


def _validate_schema_document(schema: object, *, depth: int = 0) -> None:
    """Reject schema vocabulary outside the canonical descriptor subset."""

    if depth > 128 or type(schema) is not dict:
        raise ValueError("wire descriptor contains an invalid JSON schema")
    unsupported = set(schema) - _SCHEMA_KEYWORDS
    if unsupported:
        raise ValueError("wire descriptor uses an unsupported JSON schema keyword")
    schema_type = schema.get("type")
    if schema_type is not None:
        values = schema_type if type(schema_type) is list else [schema_type]
        if (
            not values
            or any(type(value) is not str or value not in _SCHEMA_TYPES for value in values)
            or len(values) != len(set(values))
        ):
            raise ValueError("wire descriptor contains an invalid JSON schema type")
    if "additionalProperties" in schema and schema["additionalProperties"] is not False:
        raise ValueError("wire descriptor contains an invalid JSON schema closure")
    required = schema.get("required")
    if required is not None and (
        type(required) is not list
        or any(type(name) is not str or not name for name in required)
        or len(required) != len(set(required))
    ):
        raise ValueError("wire descriptor contains invalid JSON schema requirements")
    enum = schema.get("enum")
    if enum is not None and (
        type(enum) is not list
        or not enum
        or len(enum) != len({_canonical_json(value) for value in enum})
    ):
        raise ValueError("wire descriptor contains an invalid JSON schema enum")
    for key in _SCHEMA_INTEGER_KEYWORDS:
        if key in schema and not _exact_int(schema[key]):
            raise ValueError("wire descriptor contains an invalid JSON schema bound")
    for key in _SCHEMA_TRUE_KEYWORDS:
        if key in schema and schema[key] is not True:
            raise ValueError("wire descriptor contains an invalid JSON schema flag")
    pattern = schema.get("pattern")
    if pattern is not None:
        if type(pattern) is not str:
            raise ValueError("wire descriptor contains an invalid JSON schema pattern")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError("wire descriptor contains an invalid JSON schema pattern") from exc
    properties = schema.get("properties")
    if properties is not None:
        if type(properties) is not dict:
            raise ValueError("wire descriptor contains an invalid JSON schema")
        for child in properties.values():
            _validate_schema_document(child, depth=depth + 1)
    for key in ("oneOf", "allOf", "prefixItems"):
        children = schema.get(key)
        if children is None:
            continue
        if type(children) is not list or not children:
            raise ValueError("wire descriptor contains an invalid JSON schema")
        for child in children:
            _validate_schema_document(child, depth=depth + 1)
    for key in ("not", "items"):
        child = schema.get(key)
        if child is not None:
            _validate_schema_document(child, depth=depth + 1)


def _exact_json_value(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _utf8_total(value: object) -> int:
    if type(value) is str:
        return len(value.encode("utf-8"))
    if type(value) is list:
        return sum(_utf8_total(item) for item in value)
    if type(value) is dict:
        return sum(_utf8_total(item) for item in value.values())
    return 0


def _bounded_total(schema: Mapping[str, Any], name: str, total: int) -> None:
    limit = schema.get(name)
    if _exact_int(limit) and total > limit:
        raise ValueError(f"wire schema aggregate exceeds {name}")


def _validate_schema(value: object, schema: Mapping[str, Any], *, depth: int = 0) -> None:
    """Validate the JSON-Schema subset emitted by the fixed wire descriptor."""

    if depth > 128:
        raise ValueError("wire schema nesting limit exceeded")
    if "oneOf" in schema:
        matches = 0
        for variant in schema["oneOf"]:
            try:
                _validate_schema(value, variant, depth=depth + 1)
            except ValueError:
                continue
            matches += 1
        if matches != 1:
            raise ValueError("value does not match exactly one wire schema variant")
    for part in schema.get("allOf", []):
        _validate_schema(value, part, depth=depth + 1)
    if "not" in schema:
        try:
            _validate_schema(value, schema["not"], depth=depth + 1)
        except ValueError:
            pass
        else:
            raise ValueError("value matches a prohibited wire schema")
    if "const" in schema and not _exact_json_value(value, schema["const"]):
        raise ValueError("value differs from wire schema constant")
    if "enum" in schema and not any(
        _exact_json_value(value, item) for item in schema["enum"]
    ):
        raise ValueError("value is outside wire schema enum")
    if "type" in schema and not _json_type(value, schema["type"]):
        raise ValueError("value has wrong wire schema type")
    if type(value) is dict:
        required = schema.get("required", [])
        if any(name not in value for name in required):
            raise ValueError("wire schema required field is absent")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and not set(value) <= set(properties):
            raise ValueError("wire schema object is not closed")
        for name, item in value.items():
            if name in properties:
                _validate_schema(item, properties[name], depth=depth + 1)
        if schema.get("x-inspectedPathsEqualSuccessfulEvidence") is True:
            events = value.get("repository_evidence")
            inspected = value.get("inspected_paths")
            if type(events) is not list or inspected != [
                event.get("path") if type(event) is dict else None
                for event in events
            ]:
                raise ValueError("wire schema inspected paths differ from evidence")
    if type(value) is list:
        if _exact_int(schema.get("minItems")) and len(value) < schema["minItems"]:
            raise ValueError("wire schema array is too short")
        if _exact_int(schema.get("maxItems")) and len(value) > schema["maxItems"]:
            raise ValueError("wire schema array is too long")
        if schema.get("uniqueItems") is True and len({_canonical_json(item) for item in value}) != len(value):
            raise ValueError("wire schema array items are not unique")
        item_schema = schema.get("items")
        if type(item_schema) is dict:
            for item in value:
                _validate_schema(item, item_schema, depth=depth + 1)
        prefix_items = schema.get("prefixItems")
        if type(prefix_items) is list:
            for item, item_schema in zip(value, prefix_items):
                if type(item_schema) is not dict:
                    raise ValueError("wire schema prefix item is invalid")
                _validate_schema(item, item_schema, depth=depth + 1)
        if schema.get("x-uniqueSuccessfulPaths") is True:
            paths = [
                item.get("path") if type(item) is dict else None for item in value
            ]
            if None in paths or len(paths) != len(set(paths)):
                raise ValueError("wire schema evidence paths are not unique")
        _bounded_total(schema, "x-maxTotalUtf8Bytes", _utf8_total(value))
        _bounded_total(schema, "x-maxTotalFindingUtf8Bytes", _utf8_total(value))
        _bounded_total(
            schema,
            "x-maxTotalPathUtf8Bytes",
            sum(
                len(item["path"].encode("utf-8"))
                for item in value
                if type(item) is dict and type(item.get("path")) is str
            ),
        )
        _bounded_total(
            schema,
            "x-maxTotalLabelUtf8Bytes",
            sum(
                len(item["label"].encode("utf-8"))
                for item in value
                if type(item) is dict and type(item.get("label")) is str
            ),
        )
        _bounded_total(
            schema,
            "x-maxTotalContentUtf8Bytes",
            sum(
                len(item["content"].encode("utf-8"))
                for item in value
                if type(item) is dict and type(item.get("content")) is str
            ),
        )
        _bounded_total(
            schema,
            "x-maxTotalDeclaredBytes",
            sum(
                item["declared_bytes"]
                for item in value
                if type(item) is dict and _exact_int(item.get("declared_bytes"))
            ),
        )
    if type(value) is str:
        if _exact_int(schema.get("minLength")) and len(value) < schema["minLength"]:
            raise ValueError("wire schema string is too short")
        if _exact_int(schema.get("maxLength")) and len(value) > schema["maxLength"]:
            raise ValueError("wire schema string is too long")
        if _exact_int(schema.get("x-maxUtf8Bytes")) and len(value.encode("utf-8")) > schema["x-maxUtf8Bytes"]:
            raise ValueError("wire schema string exceeds UTF-8 bound")
        component_limit = schema.get("x-maxUtf8ComponentBytes")
        if _exact_int(component_limit) and any(
            len(component.encode("utf-8")) > component_limit
            for component in value.split("/")
        ):
            raise ValueError("wire schema string component exceeds UTF-8 bound")
        pattern = schema.get("pattern")
        if type(pattern) is str and re.search(pattern, value) is None:
            raise ValueError("wire schema string does not match pattern")
    if type(value) in {int, float}:
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError("wire schema number is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError("wire schema number exceeds maximum")
    canonical_limit = schema.get("x-maxCanonicalUtf8Bytes")
    if _exact_int(canonical_limit) and len(_canonical_json(value)) > canonical_limit:
        raise ValueError("wire schema canonical JSON exceeds UTF-8 bound")


def _envelope_document(envelope: object, wire: WireDescriptorSnapshot) -> dict[str, Any]:
    if is_dataclass(envelope):
        document = asdict(envelope)
    elif isinstance(envelope, Mapping):
        document = dict(envelope)
    else:
        raise ValueError("runtime envelope is not an object")
    if document.get("wire_contract_sha256") != wire.sha256:
        raise ValueError("runtime envelope wire discriminator differs")
    _validate_schema(document, wire.semantic_request)
    if document.get("logical_action") not in wire.logical_actions:
        raise ValueError("runtime envelope logical action is not admitted")
    return document


def _readiness_envelope_document(
    envelope: object, wire: WireDescriptorSnapshot
) -> dict[str, Any]:
    if is_dataclass(envelope):
        document = asdict(envelope)
    elif isinstance(envelope, Mapping):
        document = dict(envelope)
    else:
        raise ValueError("runtime readiness envelope is not an object")
    if document.get("wire_contract_sha256") != wire.sha256:
        raise ValueError("runtime readiness wire discriminator differs")
    _validate_schema(document, wire.readiness_request)
    return document


def validate_readiness_response(
    value: object,
    wire: WireDescriptorSnapshot,
    *,
    request_id: str,
    author_lineage: str,
) -> dict[str, Any]:
    """Validate one complete native all-action readiness response."""

    if type(value) is not dict:
        raise ValueError("runtime readiness response is not an object")
    _validate_schema(value, wire.readiness_response)
    if value.get("wire_contract_sha256") != wire.sha256:
        raise ValueError("runtime readiness wire discriminator differs")
    if value.get("request_id") != request_id:
        raise ValueError("runtime readiness request identifier differs")
    if value.get("author_lineage") != author_lineage:
        raise ValueError("runtime readiness author lineage differs")
    actions = value["result"]["actions"]
    if [group["logical_action"] for group in actions] != sorted(wire.logical_actions):
        raise ValueError("runtime readiness actions are not the admitted ordered set")
    for group in actions:
        logical_action = group["logical_action"]
        expected_source = wire.logical_action_source_modes[logical_action]
        if group["source_mode"] != expected_source:
            raise ValueError("runtime readiness source mode differs from its action")
        candidates = group["candidates"]
        agents = [candidate["logical_agent"] for candidate in candidates]
        if len(agents) != len(set(agents)):
            raise ValueError("runtime readiness contains duplicate logical agents")
        for candidate in candidates:
            ready = candidate["status"] == "ready"
            if not ready:
                continue
            if (
                any(
                    candidate[field] is None
                    for field in (
                        "implementation_fingerprint",
                        "executable_content_sha256",
                        "adapter_wire_sha256",
                    )
                )
                or candidate["diagnostic_code"] is not None
            ):
                raise ValueError("ready runtime identity is incomplete")
            resolution_method = candidate["model_resolution_method"]
            if resolution_method == "provider_catalog":
                catalog_identity_valid = (
                    candidate["observed_model"] is not None
                    and candidate["catalog_digest"] is not None
                )
            elif resolution_method == "provider_default":
                # Provider-default routes may still bind the provider's
                # observed catalog bytes (Gemini does) without selecting a
                # model from that catalog.  The model must remain unclaimed.
                catalog_identity_valid = candidate["observed_model"] is None
            else:
                catalog_identity_valid = False
            if not catalog_identity_valid:
                raise ValueError("runtime catalog identity is inconsistent")
    return dict(value)


@contextmanager
def _isolated_tmpdir() -> Iterator[Path]:
    path = Path(tempfile.mkdtemp(prefix="agent-collab-direct-", dir="/tmp"))
    os.chmod(path, 0o700)
    created = path.lstat()
    try:
        yield path
    finally:
        cleanup_confirmed = False
        try:
            current = path.lstat()
            if (
                path.parent == Path("/tmp")
                and path.name.startswith("agent-collab-direct-")
                and stat.S_ISDIR(current.st_mode)
                and not stat.S_ISLNK(current.st_mode)
                and (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino)
            ):
                shutil.rmtree(path)
                try:
                    path.lstat()
                except FileNotFoundError:
                    cleanup_confirmed = True
        except FileNotFoundError:
            cleanup_confirmed = True
        except OSError:
            cleanup_confirmed = False
        if not cleanup_confirmed:
            raise _PrivateTmpCleanupError(
                "private temporary directory cleanup unproven"
            )


class _PrivateTmpCleanupError(RuntimeError):
    pass


def _scrubbed_env(tmpdir: Path) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH") or "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "TMPDIR": str(tmpdir),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
    }
    for name in ("HOME", "USER", "LOGNAME", "SHELL"):
        value = os.environ.get(name)
        if value:
            env[name] = value
    return env


def _close_fd(descriptor: int | None) -> None:
    if descriptor is None:
        return
    try:
        os.close(descriptor)
    except OSError:
        pass


def _progress_pipe() -> tuple[int, int]:
    """Create one private, content-free admitted-progress channel."""

    try:
        reader, writer = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
    except AttributeError:
        reader, writer = os.pipe()
    try:
        for descriptor in (reader, writer):
            os.set_blocking(descriptor, False)
            os.set_inheritable(descriptor, False)
    except OSError:
        _close_fd(reader)
        _close_fd(writer)
        raise
    return reader, writer


def _terminate_and_reap(
    process: subprocess.Popen[bytes], *, deadline: float
) -> bool:
    group = process.pid
    try:
        try:
            os.killpg(group, signal.SIGTERM)
        except ProcessLookupError:
            pass
        term_deadline = min(
            deadline, time.monotonic() + TERM_GRACE_SECONDS
        )
        while time.monotonic() < term_deadline:
            leader_reaped = process.poll() is not None
            try:
                os.killpg(group, 0)
            except ProcessLookupError:
                return leader_reaped or process.poll() is not None
            time.sleep(
                min(0.01, max(0.0, term_deadline - time.monotonic()))
            )
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        remaining = max(0.0, deadline - time.monotonic())
        if process.poll() is None and remaining > 0:
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                return False
        while time.monotonic() < deadline:
            try:
                os.killpg(group, 0)
            except ProcessLookupError:
                return process.poll() is not None
            time.sleep(
                min(0.01, max(0.0, deadline - time.monotonic()))
            )
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return process.poll() is not None
        return False
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
            remaining = max(0.0, deadline - time.monotonic())
            if remaining <= 0:
                return False
            process.wait(timeout=remaining)
        except (OSError, subprocess.SubprocessError):
            return False
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return True
        except OSError:
            return False
        return False


def _collect_bounded(
    process: subprocess.Popen[bytes],
    request: bytes,
    deadline: float,
    *,
    progress_reader: int | None = None,
    stall_interval: float | None = None,
) -> tuple[bytes, bytes, str]:
    if (progress_reader is None) != (stall_interval is None):
        raise ValueError("progress reader and stall interval must be paired")
    if stall_interval is not None and (
        type(stall_interval) is bool or stall_interval <= 0
    ):
        raise ValueError("stall interval must be positive")
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    streams = (process.stdin, process.stdout, process.stderr)
    for stream in streams:
        if not getattr(stream, "closed", False):
            os.set_blocking(stream.fileno(), False)
    selector = selectors.DefaultSelector()
    sent = 0
    stdout = bytearray()
    stderr = bytearray()
    open_reads = {
        kind
        for kind, stream in (("stdout", process.stdout), ("stderr", process.stderr))
        if not getattr(stream, "closed", False)
    }
    try:
        if not getattr(process.stdin, "closed", False):
            selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
        if "stdout" in open_reads:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        if "stderr" in open_reads:
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        if progress_reader is not None:
            selector.register(progress_reader, selectors.EVENT_READ, "progress")
        while open_reads or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return bytes(stdout), bytes(stderr), "timeout"
            events = selector.select(min(remaining, 0.1))
            for key, _mask in events:
                stream = key.fileobj
                kind = key.data
                if kind == "stdin":
                    try:
                        written = os.write(stream.fileno(), request[sent : sent + 65536])
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        selector.unregister(stream)
                        stream.close()
                        continue
                    sent += written
                    if sent == len(request):
                        selector.unregister(stream)
                        stream.close()
                elif kind == "progress":
                    try:
                        mark = os.read(progress_reader, 65536)
                    except BlockingIOError:
                        continue
                    except OSError:
                        return bytes(stdout), bytes(stderr), "progress_pipe_lost"
                    if not mark:
                        try:
                            selector.unregister(progress_reader)
                        except KeyError:
                            pass
                        # The one-shot runtime may close its writer after its
                        # already-formed response but before stdout is flushed.
                        # Keep the current lease so that response can drain;
                        # EOF is not a progress mark and never renews it.
                        continue
                    if mark != _PROGRESS_MARK * len(mark):
                        return bytes(stdout), bytes(stderr), "progress_pipe_lost"
                    deadline = time.monotonic() + stall_interval
                else:
                    try:
                        chunk = os.read(stream.fileno(), 65536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(stream)
                        open_reads.discard(kind)
                        continue
                    target, limit = (stdout, MAX_RESPONSE_BYTES) if kind == "stdout" else (stderr, MAX_STDERR_BYTES)
                    target.extend(chunk)
                    if len(target) > limit:
                        return bytes(stdout), bytes(stderr), "output_limit"
            if process.poll() is not None and not events:
                for kind, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
                    if kind not in open_reads:
                        continue
                    try:
                        chunk = os.read(stream.fileno(), 65536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        try:
                            selector.unregister(stream)
                        except KeyError:
                            pass
                        open_reads.discard(kind)
                        continue
                    target, limit = (
                        (stdout, MAX_RESPONSE_BYTES)
                        if kind == "stdout"
                        else (stderr, MAX_STDERR_BYTES)
                    )
                    target.extend(chunk)
                    if len(target) > limit:
                        return bytes(stdout), bytes(stderr), "output_limit"
        return bytes(stdout), bytes(stderr), ""
    finally:
        selector.close()


def _call_runtime(*, envelope: object, operation: str) -> RuntimeResult:
    if operation not in {"invoke", "readiness"}:
        raise RuntimeError("unsupported internal runtime operation")
    resolution = resolve_runtime()
    if resolution.status is not RuntimeStatus.OK or resolution.wire is None or resolution.path is None:
        return RuntimeResult(
            resolution.status,
            error=resolution.error,
            manifest_digest=resolution.manifest_digest,
            artifact_digest=resolution.artifact_digest,
        )
    try:
        document = (
            _envelope_document(envelope, resolution.wire)
            if operation == "invoke"
            else _readiness_envelope_document(envelope, resolution.wire)
        )
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        return RuntimeResult(RuntimeStatus.INVALID_REQUEST, error=str(exc), manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
    timeout_ms = document.get("timeout_ms")
    if not _exact_int(timeout_ms) or not 0 < timeout_ms <= MAX_TIMEOUT_MS:
        return RuntimeResult(RuntimeStatus.INVALID_REQUEST, error="runtime timeout is invalid", manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
    deadline = time.monotonic() + timeout_ms / 1000.0
    admitted_progress = (
        operation == "invoke"
        and resolution.wire.logical_action_timeout_modes.get(
            document.get("logical_action")
        ) == "admitted_progress_inactivity"
    )
    reserve_ms = min(
        int(PROCESS_CLEANUP_RESERVE_SECONDS * 1000),
        max(1, timeout_ms // 2),
    )
    outer_cleanup_ms = max(1, reserve_ms // 2)
    runtime_deadline = deadline - reserve_ms / 1000.0
    collection_deadline = deadline - outer_cleanup_ms / 1000.0
    remaining_runtime_ms = int(max(
        0.0,
        (collection_deadline if admitted_progress else runtime_deadline)
        - time.monotonic(),
    ) * 1000)
    if remaining_runtime_ms < 1:
        return RuntimeResult(
            RuntimeStatus.TIMEOUT,
            error="deadline expired before runtime launch",
            manifest_digest=resolution.manifest_digest,
            artifact_digest=resolution.artifact_digest,
        )
    document = dict(document)
    if not admitted_progress:
        document["timeout_ms"] = remaining_runtime_ms
    try:
        request = _canonical_json(document) + b"\n"
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        return RuntimeResult(RuntimeStatus.INVALID_REQUEST, error=str(exc), manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
    if len(request) > MAX_REQUEST_BYTES:
        return RuntimeResult(RuntimeStatus.INVALID_REQUEST, error="runtime request exceeds input bound", manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
    if _identity(resolution.path, executable=True) != resolution.identity:
        return RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="runtime identity changed before launch", manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
    teardown_note = ""
    stdout = None
    terminal = None
    returncode = None
    progress_reader: int | None = None
    progress_writer: int | None = None
    try:
        with _isolated_tmpdir() as tmpdir:
            environment = _scrubbed_env(tmpdir)
            launch_kwargs: dict[str, object] = {}
            if admitted_progress:
                try:
                    progress_reader, progress_writer = _progress_pipe()
                except OSError:
                    return RuntimeResult(
                        RuntimeStatus.UNAVAILABLE,
                        error="runtime progress channel could not be created",
                        manifest_digest=resolution.manifest_digest,
                        artifact_digest=resolution.artifact_digest,
                    )
                environment[_PROGRESS_FD_ENV] = str(progress_writer)
                launch_kwargs["pass_fds"] = (progress_writer,)
            try:
                process = subprocess.Popen(
                    [str(resolution.path), "invoke", "--protocol", str(PROTOCOL_VERSION)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=tmpdir,
                    env=environment,
                    start_new_session=True,
                    **launch_kwargs,
                )
            except OSError:
                return RuntimeResult(RuntimeStatus.UNAVAILABLE, error="direct runtime could not be launched", manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
            finally:
                _close_fd(progress_writer)
                progress_writer = None
            try:
                if admitted_progress:
                    stdout, _stderr, terminal = _collect_bounded(
                        process,
                        request,
                        collection_deadline,
                        progress_reader=progress_reader,
                        stall_interval=timeout_ms / 1000.0,
                    )
                else:
                    stdout, _stderr, terminal = _collect_bounded(
                        process, request, collection_deadline
                    )
            except OSError:
                if not admitted_progress:
                    raise
                stdout, _stderr, terminal = b"", b"", "progress_pipe_lost"
            _close_fd(progress_reader)
            progress_reader = None
            if admitted_progress and terminal in {"progress_pipe_lost", "timeout"}:
                # Closing the read end is the cancellation signal.  The
                # runtime supervises its provider in a separate process
                # group, so let that supervisor observe EPIPE (or its own
                # stall), terminate/reap the provider, and flush a terminal
                # response before force-killing only the runtime group.
                try:
                    _collect_bounded(
                        process,
                        b"",
                        time.monotonic()
                        + PROCESS_CLEANUP_RESERVE_SECONDS,
                    )
                except Exception:
                    pass
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
            if terminal:
                reaped = _terminate_and_reap(
                    process,
                    deadline=time.monotonic() + TEARDOWN_REAP_SECONDS,
                )
                status = {
                    "timeout": RuntimeStatus.TIMEOUT,
                    "progress_pipe_lost": RuntimeStatus.CANCELLED,
                    "output_limit": RuntimeStatus.OUTPUT_LIMIT,
                }[terminal]
                if not reaped:
                    status = RuntimeStatus.TEARDOWN_ERROR
                return RuntimeResult(status, error=terminal.replace("_", " "), manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
            try:
                returncode = process.wait(
                    timeout=(
                        0
                        if admitted_progress
                        else max(0.0, deadline - time.monotonic())
                    )
                )
            except subprocess.TimeoutExpired:
                reaped = _terminate_and_reap(
                    process,
                    deadline=time.monotonic() + TEARDOWN_REAP_SECONDS,
                )
                return RuntimeResult(
                    RuntimeStatus.TIMEOUT if reaped else RuntimeStatus.TEARDOWN_ERROR,
                    error=(
                        "runtime exit exceeded its deadline"
                        if reaped
                        else "process group teardown unproven"
                    ),
                    manifest_digest=resolution.manifest_digest,
                    artifact_digest=resolution.artifact_digest,
                )
            # The runtime child exited on its own and the response bytes are
            # in hand. Teardown of any remaining process-group descendants is
            # bounded hygiene, never a reason to void a valid response: the
            # group is SIGTERM/SIGKILLed either way, and an unproven death
            # within the budget degrades to a client-side diagnostic note
            # (the wire's cleanup facts already model unproven cleanup).
            try:
                if not _terminate_and_reap(
                    process,
                    deadline=time.monotonic() + TEARDOWN_REAP_SECONDS,
                ):
                    teardown_note = "process group teardown unproven"
            except Exception:
                teardown_note = "process group teardown unproven"
    except _PrivateTmpCleanupError as exc:
        if not stdout or terminal is not None or returncode != 0:
            return RuntimeResult(
                RuntimeStatus.TEARDOWN_ERROR,
                error=str(exc),
                manifest_digest=resolution.manifest_digest,
                artifact_digest=resolution.artifact_digest,
            )
        # A collected, cleanly exited response survives a private-tmp
        # cleanup failure; the residue is recorded, not converted into a
        # false provider failure.
        teardown_note = teardown_note or str(exc)
    finally:
        _close_fd(progress_writer)
        _close_fd(progress_reader)
    try:
        response = runtime_bundle.load_closed_json_object(
            stdout, max_bytes=MAX_RESPONSE_BYTES
        )
        status = RuntimeStatus(response.get("status"))
        if status not in _RUNTIME_RESPONSE_STATUSES:
            raise ValueError("unknown runtime status")
        if response.get("request_id") != document["request_id"]:
            raise ValueError("runtime response request identifier differs")
        if status is RuntimeStatus.OK and operation == "readiness":
            validate_readiness_response(
                response,
                resolution.wire,
                request_id=document["request_id"],
                author_lineage=document["author_lineage"],
            )
        else:
            schema = (
                resolution.wire.success_response
                if status is RuntimeStatus.OK
                else (
                    resolution.wire.advisory_response
                    if status is RuntimeStatus.ADVISORY
                    else resolution.wire.failure_response
                )
            )
            _validate_schema(response, schema)
            if response.get("wire_contract_sha256") != resolution.wire.sha256:
                raise ValueError("runtime response wire discriminator differs")
    except (ValueError, runtime_bundle.BundleContractError, UnicodeError, RecursionError):
        status = (
            RuntimeStatus.PROVIDER_ERROR
            if returncode != 0
            else RuntimeStatus.PROTOCOL_ERROR
        )
        return RuntimeResult(status, error="direct runtime response is invalid", manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
    if status is RuntimeStatus.OK:
        if operation == "readiness":
            return RuntimeResult(
                status,
                result=response["result"],
                provenance={"wire_contract_sha256": resolution.wire.sha256},
                error=teardown_note,
                manifest_digest=resolution.manifest_digest,
                artifact_digest=resolution.artifact_digest,
            )
        return RuntimeResult(
            status,
            result=response["result"],
            provenance={
                "wire_contract_sha256": resolution.wire.sha256,
                "execution_receipt": response["execution_receipt"],
                "diagnostics": response["diagnostics"],
            },
            error=teardown_note,
            manifest_digest=resolution.manifest_digest,
            artifact_digest=resolution.artifact_digest,
        )
    if status is RuntimeStatus.ADVISORY:
        return RuntimeResult(
            status,
            result=response["advisory"],
            provenance={
                "wire_contract_sha256": resolution.wire.sha256,
                "diagnostics": response["diagnostics"],
            },
            manifest_digest=resolution.manifest_digest,
            artifact_digest=resolution.artifact_digest,
        )
    return RuntimeResult(
        status,
        provenance={"wire_contract_sha256": resolution.wire.sha256, "diagnostics": response["diagnostics"]},
        error=response["error_code"],
        manifest_digest=resolution.manifest_digest,
        artifact_digest=resolution.artifact_digest,
    )


def invoke(*, envelope: object) -> RuntimeResult:
    return _call_runtime(envelope=envelope, operation="invoke")


def readiness(*, envelope: object) -> RuntimeResult:
    return _call_runtime(envelope=envelope, operation="readiness")


if __name__ == "__main__":
    raise SystemExit("runtime_client.py is a library; use coordinator.py")
