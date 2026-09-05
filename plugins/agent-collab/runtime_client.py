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
PROTOCOL_VERSION = 5
CONTRACT_VERSION = 4
PROVIDER_RUNTIME_VERSION = "5.0.5"
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
    CLIENT_ERROR = "client_error"
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
    logical_action_timeout_modes: Mapping[str, str]
    routing_source_sha256: str
    logical_agents: frozenset[str]
    routing_request: Mapping[str, Any]
    content_frame: Mapping[str, Any]
    terminal_planning_record: Mapping[str, Any]


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
    """Validate the closed routing-only descriptor bound by the manifest."""

    if type(expected_sha256) is not str or _SHA256_RE.fullmatch(expected_sha256) is None:
        raise ValueError("wire descriptor digest is invalid")
    if type(descriptor) is not dict:
        raise ValueError("wire descriptor is not closed")
    if frozenset(descriptor) != {
        "$defs",
        "content_frame",
        "logical_actions",
        "logical_action_timeout_modes",
        "logical_agents",
        "routing_request",
        "routing_source_sha256",
        "runtime_protocol_version",
        "schema_version",
        "terminal_planning_record",
    }:
        raise ValueError("wire descriptor is not closed")
    try:
        encoded = _canonical_json(descriptor)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("wire descriptor is not canonical JSON") from exc
    if hashlib.sha256(encoded).hexdigest() != expected_sha256:
        raise ValueError("wire descriptor digest does not match")
    if not _exact_int(descriptor["schema_version"], 12):
        raise ValueError("wire descriptor schema version is unsupported")
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
    timeout_modes = descriptor["logical_action_timeout_modes"]
    if (
        type(timeout_modes) is not dict
        or set(timeout_modes) != set(actions_value)
        or any(type(mode) is not str or mode not in _TIMEOUT_MODES
               for mode in timeout_modes.values())
    ):
        raise ValueError("wire descriptor action timeout modes are invalid")
    raw_agents = descriptor["logical_agents"]
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
    for name in ("routing_request", "content_frame", "terminal_planning_record"):
        if type(descriptor[name]) is not dict or not descriptor[name]:
            raise ValueError("wire descriptor routing schema is invalid")
    if type(descriptor["$defs"]) is not dict:
        raise ValueError("wire descriptor definitions are invalid")
    return WireDescriptorSnapshot(
        sha256=expected_sha256,
        logical_actions=frozenset(actions_value),
        logical_action_timeout_modes=MappingProxyType(dict(timeout_modes)),
        routing_source_sha256=routing_sha,
        logical_agents=frozenset(raw_agents),
        routing_request=descriptor["routing_request"],
        content_frame=descriptor["content_frame"],
        terminal_planning_record=descriptor["terminal_planning_record"],
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


def _envelope_document(envelope: object, wire: WireDescriptorSnapshot) -> dict[str, Any]:
    if is_dataclass(envelope):
        document = asdict(envelope)
    elif isinstance(envelope, Mapping):
        document = dict(envelope)
    else:
        raise ValueError("runtime envelope is not an object")
    if document.get("wire_contract_sha256") != wire.sha256:
        raise ValueError("runtime envelope wire discriminator differs")
    required = {
        "wire_contract_sha256", "request_id", "quality_profile",
        "effort_class", "max_parallel", "dispatch_requested", "work_units",
    }
    allowed = required | {"budget_limit", "deadline_ms", "latency_value"}
    if set(document) - allowed or not required.issubset(document):
        raise ValueError("runtime envelope fields are invalid")
    request_id = document.get("request_id")
    if type(request_id) is not str or not request_id or len(request_id) > 128:
        raise ValueError("runtime envelope request identifier is invalid")
    deadline_ms = document.get("deadline_ms")
    if deadline_ms is not None and (
        not _exact_int(deadline_ms) or not 0 <= deadline_ms <= MAX_TIMEOUT_MS
    ):
        raise ValueError("runtime envelope deadline is invalid")
    units = document.get("work_units")
    if type(units) is not list or not 1 <= len(units) <= 128:
        raise ValueError("runtime envelope work units are invalid")
    for unit in units:
        if (
            type(unit) is not dict
            or type(unit.get("id")) is not str
            or not unit["id"]
            or unit.get("capability") not in wire.logical_actions
        ):
            raise ValueError("runtime envelope work unit is invalid")
    return document


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
    # Preserve only native-client configuration locations.  These let the
    # packaged carrier locate the same subscription login and local catalog as
    # the operator's CLI without forwarding credential material or inline
    # provider configuration (which could select a metered API-key route).
    for name in (
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
        "GEMINI_HOME",
        "GROK_AUTH_PATH",
        "GROK_HOME",
        "OPENCODE_HOME",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
    ):
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
                    available = limit - len(target)
                    if len(chunk) > available:
                        target.extend(chunk[:available])
                        if kind == "stdout":
                            boundary = stdout.rfind(b"\n")
                            if boundary >= 0:
                                del stdout[boundary + 1:]
                            else:
                                stdout.clear()
                        return bytes(stdout), bytes(stderr), "output_limit"
                    target.extend(chunk)
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
                    available = limit - len(target)
                    if len(chunk) > available:
                        target.extend(chunk[:available])
                        if kind == "stdout":
                            boundary = stdout.rfind(b"\n")
                            if boundary >= 0:
                                del stdout[boundary + 1:]
                            else:
                                stdout.clear()
                        return bytes(stdout), bytes(stderr), "output_limit"
                    target.extend(chunk)
        return bytes(stdout), bytes(stderr), ""
    except OSError:
        # Transport failure cannot erase records collected before it.
        return bytes(stdout), bytes(stderr), "runtime_io_error"
    finally:
        selector.close()


def _reject_nonfinite(_value: str) -> None:
    raise ValueError("runtime output contains a non-finite number")


def _parse_routing_records(raw: bytes) -> tuple[list[dict[str, object]], str]:
    records: list[dict[str, object]] = []
    malformed = False
    lines = raw.split(b"\n")
    for encoded in lines:
        try:
            line = encoded.decode("utf-8")
        except UnicodeDecodeError:
            malformed = True
            continue
        if not line:
            continue
        try:
            record = json.loads(line, parse_constant=_reject_nonfinite)
            if type(record) is dict:
                json.dumps(
                    record,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")
        except (TypeError, ValueError, RecursionError):
            malformed = True
            continue
        if type(record) is dict:
            records.append(record)
        else:
            malformed = True
    return records, "malformed runtime output was excluded" if malformed else ""


def _call_runtime(*, envelope: object) -> RuntimeResult:
    resolution = resolve_runtime()
    if resolution.status is not RuntimeStatus.OK or resolution.wire is None or resolution.path is None:
        return RuntimeResult(
            resolution.status,
            error=resolution.error,
            manifest_digest=resolution.manifest_digest,
            artifact_digest=resolution.artifact_digest,
        )
    try:
        document = _envelope_document(envelope, resolution.wire)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        return RuntimeResult(RuntimeStatus.INVALID_REQUEST, error=str(exc), manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
    timeout_ms = document.get("deadline_ms")
    if timeout_ms is None:
        timeout_ms = MAX_TIMEOUT_MS
    # One process carries every selected work unit, so it cannot safely combine
    # lifecycle contracts. Reject mixed mode envelopes before Popen; production
    # provider actions use admitted progress inactivity, while homogeneous
    # total-deadline requests remain a compatibility mode.
    timeout_modes = {
        resolution.wire.logical_action_timeout_modes[unit["capability"]]
        for unit in document["work_units"]
    }
    if len(timeout_modes) > 1:
        return RuntimeResult(
            RuntimeStatus.INVALID_REQUEST,
            error="mixed timeout modes are unsupported; use one lifecycle contract",
            manifest_digest=resolution.manifest_digest,
            artifact_digest=resolution.artifact_digest,
        )
    admitted_progress = (
        document["dispatch_requested"]
        and "admitted_progress_inactivity" in timeout_modes
    )
    deadline = time.monotonic() + timeout_ms / 1000.0
    reserve_ms = min(
        int(PROCESS_CLEANUP_RESERVE_SECONDS * 1000),
        max(1, timeout_ms // 2),
    )
    runtime_deadline = deadline - reserve_ms / 1000.0
    remaining_runtime_ms = int(max(
        0.0,
        runtime_deadline - time.monotonic(),
    ) * 1000)
    if remaining_runtime_ms < 1:
        return RuntimeResult(
            RuntimeStatus.TIMEOUT,
            error="deadline expired before runtime launch",
            manifest_digest=resolution.manifest_digest,
            artifact_digest=resolution.artifact_digest,
        )
    document = dict(document)
    document["deadline_ms"] = remaining_runtime_ms
    try:
        request = _canonical_json(document) + b"\n"
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        return RuntimeResult(RuntimeStatus.INVALID_REQUEST, error=str(exc), manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
    if len(request) > MAX_REQUEST_BYTES:
        return RuntimeResult(RuntimeStatus.INVALID_REQUEST, error="runtime request exceeds input bound", manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
    if _identity(resolution.path, executable=True) != resolution.identity:
        return RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="runtime identity changed before launch", manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
    teardown_note = ""
    stdout = b""
    terminal = ""
    returncode = None
    progress_reader = progress_writer = None
    try:
        with _isolated_tmpdir() as tmpdir:
            environment = _scrubbed_env(tmpdir)
            try:
                if admitted_progress:
                    progress_reader, progress_writer = _progress_pipe()
                    environment[_PROGRESS_FD_ENV] = str(progress_writer)
                process = subprocess.Popen(
                    [str(resolution.path), "invoke", "--protocol", str(PROTOCOL_VERSION)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=tmpdir,
                    env=environment,
                    start_new_session=True,
                    pass_fds=(progress_writer,) if progress_writer is not None else (),
                )
            except OSError:
                return RuntimeResult(RuntimeStatus.CLIENT_ERROR, error="local runtime launch failed; provider state is unknown", manifest_digest=resolution.manifest_digest, artifact_digest=resolution.artifact_digest)
            finally:
                _close_fd(progress_writer)
                progress_writer = None
            try:
                stdout, _stderr, terminal = _collect_bounded(
                    process, request, runtime_deadline,
                    progress_reader=progress_reader,
                    stall_interval=(remaining_runtime_ms / 1000.0 if admitted_progress else None),
                )
            except OSError:
                terminal = "runtime_io_error"
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
            if terminal:
                reaped = _terminate_and_reap(
                    process,
                    deadline=time.monotonic() + TEARDOWN_REAP_SECONDS,
                )
                if not reaped:
                    teardown_note = "process group teardown unproven"
            else:
                try:
                    returncode = process.wait(timeout=max(0.0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    terminal = "timeout"
                try:
                    if not _terminate_and_reap(
                        process,
                        deadline=time.monotonic() + TEARDOWN_REAP_SECONDS,
                    ):
                        teardown_note = "process group teardown unproven"
                except Exception:
                    teardown_note = "process group teardown unproven"
    except _PrivateTmpCleanupError as exc:
        teardown_note = teardown_note or str(exc)
    finally:
        _close_fd(progress_reader)
        _close_fd(progress_writer)
    records, parse_note = _parse_routing_records(stdout)
    notes = [
        note for note in (
            parse_note,
            terminal.replace("_", " ") if terminal else "",
            f"runtime exited with status {returncode}" if returncode not in {None, 0} else "",
            teardown_note,
        ) if note
    ]
    if records:
        return RuntimeResult(
            RuntimeStatus.OK,
            result=records,
            provenance={"wire_contract_sha256": resolution.wire.sha256},
            error="; ".join(notes),
            manifest_digest=resolution.manifest_digest,
            artifact_digest=resolution.artifact_digest,
        )
    status = {
        "timeout": RuntimeStatus.TIMEOUT,
        "output_limit": RuntimeStatus.OUTPUT_LIMIT,
        "runtime_io_error": RuntimeStatus.CLIENT_ERROR,
        "progress_pipe_lost": RuntimeStatus.CLIENT_ERROR,
    }.get(terminal, RuntimeStatus.CLIENT_ERROR if returncode else RuntimeStatus.PROTOCOL_ERROR)
    return RuntimeResult(
        status,
        result=[],
        provenance={"wire_contract_sha256": resolution.wire.sha256},
        error="; ".join(notes) or "direct runtime returned no records",
        manifest_digest=resolution.manifest_digest,
        artifact_digest=resolution.artifact_digest,
    )


def invoke(*, envelope: object) -> RuntimeResult:
    return _call_runtime(envelope=envelope)


if __name__ == "__main__":
    raise SystemExit("runtime_client.py is a library; import invoke")
