#!/usr/bin/env python3
"""Verify and invoke the co-packaged signed native agent-collab runtime.

Only the fixed plugin-relative Darwin/arm64 artifact is eligible.  There is no
PATH lookup, runtime override, downloader, provider recipe, or policy inference.
The same-UID operator account is trusted: macOS has no descriptor-only Mach-O
execution primitive, so a malicious same-UID process can still race the final
path-based exec or replace this public client.  Identity is nevertheless
rechecked immediately before the fixed-path spawn to narrow accidental and
lower-privilege substitution windows.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import ctypes
import hashlib
import hmac
import importlib.util
import json
import math
import os
import platform
import plistlib
import re
import selectors
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Mapping

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - exercised by a simulated non-POSIX import
    _fcntl = None

try:
    import pwd as _pwd
except ImportError:  # pragma: no cover - exercised by a simulated non-POSIX import
    _pwd = None


PLUGIN_ROOT = Path(__file__).resolve().parent
MANIFEST_NAME = "runtime-manifest.json"
PROTOCOL_VERSION = 2
LEGACY_BLUE_PROTOCOL_VERSION = 1
CONTRACT_VERSION = 3
MANIFEST_SCHEMA_VERSION = 3
LEGACY_MANIFEST_SCHEMA_VERSION = 2
MAX_REQUEST_BYTES = 48 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_TIMEOUT_MS = 600_000
BROKER_PROTOCOL_VERSION = 2
BROKER_LABEL = "com.agent-collab.provider-broker"
BROKER_SOCKET_NAME = "ProviderBroker"
BROKER_SOCKET_FILENAME = "provider-broker.sock"
BROKER_SELECTOR_FILENAME = "selector.json"
BROKER_SELECTOR_V2_FILENAME = "selector-v2.json"
BROKER_SELECTOR_MAX_BYTES = 16 * 1024
DISPATCHER_PROTOCOL_VERSION = 2
LEGACY_DISPATCHER_PROTOCOL_VERSION = 1
DISPATCHER_MAX_HANDSHAKE_SECONDS = 30.0
DISPATCHER_MAX_REQUEST_SECONDS = MAX_TIMEOUT_MS / 1000.0
DISPATCHER_LAUNCHD_LISTENER_UID = 0
DISPATCHER_LAUNCHD_SENTINEL_PID = 1
DISPATCHER_LAUNCHD_INITIAL_DELAY_SECONDS = 0.01
DISPATCHER_LAUNCHD_MAX_DELAY_SECONDS = 0.1
BROKER_SELECTOR_KEYS = frozenset(
    {"schema_version", "generation", "selected_lane", "blue", "green"}
)
BROKER_SELECTOR_V2_KEYS = frozenset(
    {
        "schema_version",
        "generation",
        "selector_v1_sha256",
        "selected",
        "retained",
        "candidate",
        "lifecycle",
    }
)
BROKER_SELECTOR_V2_LANE_KEYS = frozenset(
    {
        "artifact_sha256",
        "manifest_sha256",
        "transport",
        "protocol_version",
        "lane_generation",
    }
)
NORMALIZED_DISTRIBUTION_SIGNING_KEYS = frozenset(
    {
        "mode",
        "identity",
        "team_id",
        "require_notarization",
        "hardened_runtime",
        "secure_timestamp",
    }
)
BROKER_LANE_REFERENCE_KEYS = frozenset(
    {"artifact_sha256", "manifest_sha256"}
)
BROKER_DISPATCHER_STATE_KEYS = frozenset(
    {
        "schema_version",
        "contract_version",
        "dispatcher_protocol_version",
        "runtime_protocol_version",
        "artifact_sha256",
        "manifest_sha256",
        "plist_sha256",
    }
)
BROKER_FRAME_KEYS = frozenset(
    {
        "broker_protocol_version",
        "runtime_protocol_version",
        "artifact_sha256",
        "manifest_sha256",
        "client_pid",
        "nonce",
        "deadline_monotonic_ms",
        "request",
    }
)
DISPATCHER_HELLO_KEYS = frozenset(
    {
        "frame_type",
        "dispatcher_protocol_version",
        "client_pid",
        "nonce",
        "deadline_monotonic_ms",
        "lane_generation",
        "lane_token",
        "artifact_sha256",
        "manifest_sha256",
        "execution_key",
        "request_size",
        "request_sha256",
    }
)
LEGACY_DISPATCHER_HELLO_KEYS = frozenset(
    DISPATCHER_HELLO_KEYS - {"execution_key", "request_size", "request_sha256"}
)
DISPATCHER_READY_KEYS = frozenset(
    set(DISPATCHER_HELLO_KEYS) | {"dispatcher_pid", "hello_sha256"}
)
LEGACY_DISPATCHER_READY_KEYS = frozenset(
    set(LEGACY_DISPATCHER_HELLO_KEYS) | {"dispatcher_pid", "hello_sha256"}
)
DISPATCHER_REQUEST_KEYS = frozenset(
    set(DISPATCHER_HELLO_KEYS) | {"hello_sha256", "ready_sha256", "request"}
)
LEGACY_DISPATCHER_REQUEST_KEYS = frozenset(
    set(LEGACY_DISPATCHER_HELLO_KEYS)
    | {"hello_sha256", "ready_sha256", "request"}
)
DISPATCHER_BRIDGE_KEYS = frozenset(
    {
        "bridge_protocol_version",
        "lane_generation",
        "artifact_sha256",
        "manifest_sha256",
        "deadline_monotonic_ms",
        "handshake_deadline_monotonic_ms",
        "request",
        "execution_key",
        "request_size",
        "request_sha256",
    }
)
LEGACY_DISPATCHER_BRIDGE_KEYS = frozenset(
    DISPATCHER_BRIDGE_KEYS - {"execution_key", "request_size", "request_sha256"}
)
ADOPTION_CANARY_KEYS = frozenset(
    {
        "protocol_version",
        "request_id",
        "operation",
        "provider",
        "registry_generation",
        "source_generation",
        "binary_sha256",
        "worker_sha256",
        "adapter_contract_generation",
        "routes",
        "attempt_generation",
        "authority_token",
        "timeout_ms",
    }
)
BROKERED_ROUTES = frozenset({"codex", "opencode", "gemini", "grok", "composer"})
BROKER_MAX_REQUEST_BYTES = MAX_REQUEST_BYTES
BROKER_MAX_RESPONSE_BYTES = MAX_RESPONSE_BYTES
BROKER_STATE_MAX_BYTES = 64 * 1024
BROKER_SUN_PATH_MAX_BYTES = 103
BROKER_FALLBACK_CONNECT_TIMEOUT_SECONDS = 2.0
BROKER_FALLBACK_RESERVE_SECONDS = 1.0
# Version 3.5 supports an authenticated request-free green handshake.  The
# shipped selector remains blue; this flag only permits a separately committed
# selector transition to use the verified dispatcher protocol.
BROKER_GREEN_PROMOTION_SUPPORTED = True
BROKER_SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
LIFECYCLE_BLUE_PROTOCOL_VERSIONS = frozenset(
    {LEGACY_BLUE_PROTOCOL_VERSION, PROTOCOL_VERSION}
)
BROKER_STATE_KEYS = frozenset(
    {
        "schema_version",
        "contract_version",
        "broker_protocol_version",
        "runtime_protocol_version",
        "artifact_sha256",
        "manifest_sha256",
        "bundle_path",
        "entrypoint_path",
        "manifest_path",
        "plist_sha256",
        "socket_path",
        "label",
        "previous",
    }
)
_BROKER_HEADER = struct.Struct(">Q")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_JOB_LABEL_RE = re.compile(
    r"com\.agent-collab\.provider-(?:broker|dispatcher\.[0-9a-f]{32})"
)
_TEAM_ID_RE = re.compile(r"^[A-Z0-9]{10}$")
_DEVELOPER_ID_RE = re.compile(
    r"^Developer ID Application: [^\r\n]{1,160} \(([A-Z0-9]{10})\)$"
)
_CODESIGN_FLAGS_RE = re.compile(r"\bflags=(0x[0-9a-f]+)(?:\([^)]*\))?", re.IGNORECASE)
_CODESIGN_TIMESTAMP_RE = re.compile(r"(?m)^Timestamp=(.+)$")
_CODESIGN_TEAM_RE = re.compile(r"(?m)^TeamIdentifier=([A-Z0-9]{10})(?=\s|$)")
_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){1,2}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
EXPECTED_MINIMUM_MACOS = "14.0"
ISOLATED_TEMP_ROOT = Path("/tmp")
CODEX_DESKTOP_TUPLE = {
    "CODEX_SANDBOX": "seatbelt",
    "__CFBundleIdentifier": "com.openai.codex",
    "CODEX_INTERNAL_ORIGINATOR_OVERRIDE": "Codex Desktop",
    "CODEX_CI": "1",
}
MANAGEMENT_ACTIONS = frozenset({"status", "prepare", "grok_login"})


def _load_runtime_bundle():
    name = "agent_collab_runtime_bundle"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = PLUGIN_ROOT / "runtime_bundle.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("runtime bundle verifier cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_signing_policy():
    name = "agent_collab_signing_policy"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = PLUGIN_ROOT / "signing_policy.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("signing policy cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


try:
    EXPECTED_DEVELOPER_ID_TEAM = _load_signing_policy().EXPECTED_DEVELOPER_ID_TEAM
except (AttributeError, OSError, RuntimeError, ValueError):
    EXPECTED_DEVELOPER_ID_TEAM = ""
runtime_bundle = _load_runtime_bundle()
SUPPORTED_CONTRACTS = frozenset(
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
ADOPTION_PROVIDER_ROUTES = {
    "gemini": frozenset(
        f"{route}/{action}"
        for route, action in SUPPORTED_CONTRACTS
        if route == "gemini"
    ),
    "grok": frozenset(
        f"{route}/{action}"
        for route, action in SUPPORTED_CONTRACTS
        if route in {"grok", "composer"}
    ),
    "opencode": frozenset(
        f"{route}/{action}"
        for route, action in SUPPORTED_CONTRACTS
        if route == "opencode"
    ),
}
FIXED_AUTHOR_MODELS = {
    "grok": "xai/grok-4.5",
    "composer": "xai/grok-4.5",
}
GEMINI_GOVERNANCE_MODEL = "google/gemini-3.1-pro"
GEMINI_GOVERNANCE_DISPLAY = "Gemini 3.1 Pro (High)"
GEMINI_GOVERNANCE_CONTAINMENT = "write_contained_shared_home"
GEMINI_GOVERNANCE_PROOF_KEYS = frozenset(
    {
        "version",
        "request_id",
        "action",
        "authority",
        "transport",
        "backend",
        "runtime_version",
        "contract_version",
        "artifact_sha256",
        "artifact_author_model",
        "artifact_author_family",
        "reviewer_model",
        "reviewer_family",
        "selected_display",
        "effective_effort",
        "containment_level",
        "tools_disabled",
        "pty_used",
        "lock_acquired",
        "cleanup_confirmed",
        "provider_process_started",
        "returncode",
        "model_source",
        "failed_over",
        "response_sha256",
        "proof_sha256",
    }
)
TEMPORARILY_UNAVAILABLE_CONTRACTS = {
    ("codex", "build"): "Codex build is unavailable until a hardened mutation backend exists"
}
KNOWN_NATIVE_FAILURES = frozenset(
    {
        "unavailable",
        "auth_error",
        "quota_error",
        "containment_error",
        "cancelled",
        "input_limit",
        "timeout",
        "output_limit",
        "teardown_error",
        "provider_error",
    }
)


class RuntimeStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    MANIFEST_INVALID = "manifest_invalid"
    PLATFORM_UNSUPPORTED = "platform_unsupported"
    PATH_INVALID = "path_invalid"
    INTEGRITY_ERROR = "integrity_error"
    SIGNATURE_ERROR = "signature_error"
    HOST_BLOCKED = "host_blocked"
    CONFIG_ERROR = "config_error"
    SPAWN_ERROR = "spawn_error"
    TIMEOUT = "timeout"
    OUTPUT_LIMIT = "output_limit"
    PROTOCOL_ERROR = "protocol_error"
    AUTH_ERROR = "auth_error"
    QUOTA_ERROR = "quota_error"
    CONTAINMENT_ERROR = "containment_error"
    CANCELLED = "cancelled"
    INPUT_LIMIT = "input_limit"
    TEARDOWN_ERROR = "teardown_error"
    PROVIDER_ERROR = "provider_error"
    CANARY_BLOCKED = "canary_blocked"


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    mtime_ns: int
    mode: int
    uid: int
    links: int


@dataclass(frozen=True)
class RuntimeContractAnchor:
    provider_runtime_version: str
    route_contract_version: int

    def __post_init__(self) -> None:
        if (
            type(self.provider_runtime_version) is not str
            or _VERSION_RE.fullmatch(self.provider_runtime_version) is None
            or not _exact_int(self.route_contract_version)
            or self.route_contract_version < 1
        ):
            raise ValueError("provider runtime contract anchor is invalid")


@dataclass(frozen=True)
class RuntimeResolution:
    status: RuntimeStatus
    path: Path | None = None
    bundle_path: Path | None = None
    files: tuple[Mapping[str, Any], ...] = ()
    contracts: frozenset[tuple[str, str]] = frozenset()
    manifest_digest: str = ""
    artifact_digest: str = ""
    identity: FileIdentity | None = None
    anchor: RuntimeContractAnchor | None = None
    error: str = ""


@dataclass(frozen=True)
class BrokerLaneSnapshot:
    name: str
    generation: int
    artifact_digest: str
    manifest_digest: str
    label: str
    socket_path: Path
    transport: str = ""
    protocol_version: int = 0
    anchor: RuntimeContractAnchor | None = None

    def __post_init__(self) -> None:
        transport = self.transport or (
            "broker" if self.label == BROKER_LABEL else "dispatcher"
        )
        protocol_version = self.protocol_version or (
            BROKER_PROTOCOL_VERSION
            if transport == "broker"
            else DISPATCHER_PROTOCOL_VERSION
        )
        if transport not in {"broker", "dispatcher"} or not _exact_int(
            protocol_version
        ):
            raise ValueError("provider lane transport is invalid")
        object.__setattr__(self, "transport", transport)
        object.__setattr__(self, "protocol_version", protocol_version)


@dataclass
class DispatcherSession:
    lane: BrokerLaneSnapshot
    client_pid: int
    dispatcher_pid: int
    nonce: str
    deadline_monotonic_ms: int
    hello_sha256: str
    ready_sha256: str
    execution_key: str = ""
    request_size: int = 0
    request_sha256: str = ""
    consumed: bool = False


@dataclass(frozen=True)
class RuntimeResult:
    status: RuntimeStatus
    result: Mapping[str, Any] | None = None
    provenance: Mapping[str, Any] | None = None
    error: str = ""


class _DispatcherPreRequestError(RuntimeError):
    """Green failed before any request-bearing frame could be accepted."""


class _DispatcherPostRequestError(RuntimeError):
    """Green failed at or after request send, so another lane is prohibited."""

    def __init__(
        self,
        message: str,
        *,
        result: RuntimeResult | None = None,
    ) -> None:
        if result is not None and (
            not isinstance(result, RuntimeResult)
            or result.status
            not in {
                RuntimeStatus.SPAWN_ERROR,
                RuntimeStatus.TIMEOUT,
                RuntimeStatus.OUTPUT_LIMIT,
                RuntimeStatus.TEARDOWN_ERROR,
            }
            or result.result is not None
            or result.provenance is not None
            or not result.error
        ):
            raise TypeError("dispatcher post-request result is invalid")
        super().__init__(message)
        self.result = result


class _DarwinProcBSDInfo(ctypes.Structure):
    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16),
        ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


def normalized_platform() -> str:
    return {"macos": "darwin"}.get(platform.system().lower(), platform.system().lower())


def normalized_arch() -> str:
    value = platform.machine().lower()
    return {"aarch64": "arm64", "amd64": "x86_64", "x64": "x86_64"}.get(value, value)


def _load_host_policy():
    name = "agent_collab_host_policy"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = PLUGIN_ROOT / "host_policy.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("host policy cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _exact_int(value: object, expected: int | None = None) -> bool:
    return type(value) is int and (expected is None or value == expected)


def _operator_uid() -> int | None:
    getuid = getattr(os, "getuid", None)
    if not callable(getuid):
        return None
    try:
        value = getuid()
    except (OSError, TypeError, ValueError):
        return None
    return value if _exact_int(value) and value >= 0 else None


def _safe_file_identity(path: Path, *, executable: bool) -> FileIdentity | None:
    operator_uid = _operator_uid()
    if operator_uid is None:
        return None
    try:
        info = path.lstat()
    except OSError:
        return None
    mode = info.st_mode
    if (
        not stat.S_ISREG(mode)
        or stat.S_ISLNK(mode)
        or info.st_uid != operator_uid
        or info.st_nlink != 1
        or mode & (stat.S_IWGRP | stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID)
        or (executable and not (mode & stat.S_IXUSR))
    ):
        return None
    return FileIdentity(
        device=info.st_dev,
        inode=info.st_ino,
        size=info.st_size,
        mtime_ns=info.st_mtime_ns,
        mode=mode,
        uid=info.st_uid,
        links=info.st_nlink,
    )


def _read_regular_nofollow(path: Path, *, limit: int) -> tuple[bytes | None, FileIdentity | None]:
    identity = _safe_file_identity(path, executable=False)
    if identity is None or identity.size > limit:
        return None, None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (identity.device, identity.inode):
                return None, None
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > limit:
                    return None, None
            return b"".join(chunks), identity
        finally:
            os.close(descriptor)
    except OSError:
        return None, None


def _contracts(value: object) -> frozenset[tuple[str, str]] | None:
    if not isinstance(value, list) or not value:
        return None
    result: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"route", "action"}:
            return None
        contract = (item.get("route"), item.get("action"))
        if contract not in SUPPORTED_CONTRACTS:
            return None
        result.append((str(contract[0]), str(contract[1])))
    if len(result) != len(set(result)):
        return None
    return frozenset(result)


def _normalized_distribution_signing_valid(document: object) -> bool:
    return bool(
        isinstance(document, dict)
        and set(document) == NORMALIZED_DISTRIBUTION_SIGNING_KEYS
        and document.get("mode") in {"developer_id", "adhoc"}
        and type(document.get("identity")) is str
        and type(document.get("team_id")) is str
        and type(document.get("require_notarization")) is bool
        and type(document.get("hardened_runtime")) is bool
        and type(document.get("secure_timestamp")) is bool
    )


def _distribution_signing_policy(
    *,
    channel: object,
    signing: object,
    file_signing_profiles: tuple[object, ...],
) -> dict[str, Any] | None:
    """Authorize only the production distribution and signing policy.

    Private adapters may replace this hook to authorize their development
    channel and ad-hoc signing profile.  Manifest grammar, lane role,
    protocol, anchor, contract, and artifact identity remain outside the hook.
    """

    if (
        channel != "production"
        or not isinstance(signing, dict)
        or set(signing) != NORMALIZED_DISTRIBUTION_SIGNING_KEYS
        or type(file_signing_profiles) is not tuple
        or any(
            type(profile) is not str or profile != "production_developer_id"
            for profile in file_signing_profiles
        )
    ):
        return None
    identity = signing.get("identity")
    identity_match = (
        _DEVELOPER_ID_RE.fullmatch(identity) if isinstance(identity, str) else None
    )
    if (
        not file_signing_profiles
        or signing.get("mode") != "developer_id"
        or identity_match is None
        or not isinstance(signing.get("team_id"), str)
        or not _TEAM_ID_RE.fullmatch(signing["team_id"])
        or identity_match.group(1) != signing["team_id"]
        or not _TEAM_ID_RE.fullmatch(EXPECTED_DEVELOPER_ID_TEAM)
        or signing["team_id"] != EXPECTED_DEVELOPER_ID_TEAM
        or signing.get("require_notarization") is not True
        or signing.get("hardened_runtime") is not True
        or signing.get("secure_timestamp") is not True
    ):
        return None
    return dict(signing)


def _manifest_entry(
    data: object,
    *,
    runtime_protocol_version: int | None = None,
    role: str = "candidate",
    transport: str = "dispatcher",
    dispatcher_protocol_version: int | None = DISPATCHER_PROTOCOL_VERSION,
) -> tuple[dict[str, Any] | None, str]:
    if runtime_protocol_version is not None:
        if not _exact_int(runtime_protocol_version):
            return None, "manifest or protocol version is unsupported"
        if runtime_protocol_version == LEGACY_BLUE_PROTOCOL_VERSION:
            role = "lifecycle"
            transport = "broker"
            dispatcher_protocol_version = None
    if role == "lifecycle" and dispatcher_protocol_version is None:
        transport = "broker"
    allowed_roles = {"candidate", "selected", "retained", "lifecycle"}
    if role not in allowed_roles:
        return None, "manifest role is unsupported"
    if not isinstance(data, dict) or set(data) != {
        "schema_version",
        "protocol_version",
        "contract_version",
        "broker_protocol_version",
        "channel",
        "artifacts",
    }:
        return None, "manifest root shape is invalid"
    schema_version = data.get("schema_version")
    runtime_version = data.get("protocol_version")
    if (
        runtime_protocol_version is not None
        and not _exact_int(runtime_version, runtime_protocol_version)
    ):
        return None, "manifest or protocol version is unsupported"
    schema3 = _exact_int(schema_version, MANIFEST_SCHEMA_VERSION)
    legacy_runtime2 = (
        _exact_int(schema_version, LEGACY_MANIFEST_SCHEMA_VERSION)
        and _exact_int(runtime_version, PROTOCOL_VERSION)
        and role in {"selected", "retained"}
        and (
            (
                transport == "dispatcher"
                and _exact_int(
                    dispatcher_protocol_version,
                    LEGACY_DISPATCHER_PROTOCOL_VERSION,
                )
            )
            or (
                transport == "broker"
                and dispatcher_protocol_version is None
            )
        )
    )
    lifecycle_runtime1 = (
        _exact_int(schema_version, LEGACY_MANIFEST_SCHEMA_VERSION)
        and _exact_int(runtime_version, LEGACY_BLUE_PROTOCOL_VERSION)
        and role == "lifecycle"
        and transport == "broker"
        and dispatcher_protocol_version is None
    )
    if (
        not (
            (
                schema3
                and _exact_int(runtime_version, PROTOCOL_VERSION)
                and role in {"candidate", "selected", "retained"}
                and transport == "dispatcher"
                and _exact_int(
                    dispatcher_protocol_version, DISPATCHER_PROTOCOL_VERSION
                )
            )
            or legacy_runtime2
            or lifecycle_runtime1
        )
        or not _exact_int(data["contract_version"], CONTRACT_VERSION)
        or not _exact_int(data["broker_protocol_version"], BROKER_PROTOCOL_VERSION)
    ):
        return None, "manifest or protocol version is unsupported"
    artifacts = data["artifacts"]
    if not isinstance(artifacts, list):
        return None, "artifacts must be an array"
    selected: list[dict[str, Any]] = []
    seen_hosts: set[tuple[str, str]] = set()
    for item in artifacts:
        expected_item_keys = {
            "platform",
            "arch",
            "kind",
            "minimum_macos",
            "path",
            "entrypoint",
            "size",
            "sha256",
            "signing",
            "files",
            "contracts",
        }
        if schema3:
            expected_item_keys |= {
                "provider_runtime_version",
                "route_contract_version",
            }
        if not isinstance(item, dict) or set(item) != expected_item_keys:
            return None, "artifact shape is invalid"
        signing = item.get("signing")
        contracts = _contracts(item.get("contracts"))
        expected_path = "runtime/darwin-arm64/agent-collab-runtime.bundle"
        try:
            records = runtime_bundle.validate_file_records(item.get("files"))
            bundle_digest = runtime_bundle.compute_bundle_identity(records)
        except runtime_bundle.BundleContractError:
            return None, "artifact file records are invalid"
        try:
            normalized_signing = _distribution_signing_policy(
                channel=data["channel"],
                signing=signing,
                file_signing_profiles=tuple(
                    record.get("signing_profile") for record in records
                ),
            )
        except Exception:
            normalized_signing = None
        anchor: RuntimeContractAnchor | None
        if schema3:
            try:
                anchor = RuntimeContractAnchor(
                    item.get("provider_runtime_version"),
                    item.get("route_contract_version"),
                )
            except (TypeError, ValueError):
                return None, "artifact contract anchor is invalid"
        elif legacy_runtime2:
            anchor = RuntimeContractAnchor("2.0.0", 2)
        else:
            anchor = None
        if (
            item.get("platform") != "darwin"
            or item.get("arch") != "arm64"
            or item.get("kind") != "standalone_bundle"
            or item.get("minimum_macos") != EXPECTED_MINIMUM_MACOS
            or item.get("path") != expected_path
            or item.get("entrypoint") != runtime_bundle.ENTRYPOINT_NAME
            or type(item.get("size")) is not int
            or not 1 <= item["size"] <= MAX_ARTIFACT_BYTES
            or item["size"] != sum(record["size"] for record in records)
            or not isinstance(item.get("sha256"), str)
            or not _SHA256_RE.fullmatch(item["sha256"])
            or bundle_digest != item["sha256"]
            or not _normalized_distribution_signing_valid(normalized_signing)
            or contracts is None
        ):
            return None, "artifact fields are invalid"
        host_key = (item["platform"], item["arch"])
        if host_key in seen_hosts:
            return None, "manifest contains duplicate host artifacts"
        seen_hosts.add(host_key)
        if host_key == ("darwin", "arm64"):
            selected.append(
                {
                    **item,
                    "signing": normalized_signing,
                    "_contracts": contracts,
                    "_files": records,
                    "_anchor": anchor,
                    "_manifest_schema_version": schema_version,
                    "_runtime_protocol_version": runtime_version,
                    "_dispatcher_protocol_version": dispatcher_protocol_version,
                    "_role": role,
                }
            )
    if not selected:
        return {}, "runtime artifact is not packaged for this host"
    if len(selected) != 1:
        return None, "manifest contains duplicate host artifacts"
    return selected[0], ""


def _path_beneath_root(root: Path, rel: str) -> Path | None:
    pure = PurePosixPath(rel)
    expected = PurePosixPath(
        "runtime", "darwin-arm64", "agent-collab-runtime.bundle"
    )
    if pure != expected or pure.is_absolute() or ".." in pure.parts:
        return None
    try:
        resolved_root = root.resolve(strict=True)
    except OSError:
        return None
    current = resolved_root
    for part in pure.parts:
        current = current / part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                return None
        except OSError:
            return current
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError):
        return current
    return resolved


def _verify_macos_signature(
    path: Path,
    *,
    team_id: str,
    require_notarization: bool,
    identity: str = "",
    secure_timestamp: bool = True,
) -> tuple[bool, str]:
    if (
        not _TEAM_ID_RE.fullmatch(EXPECTED_DEVELOPER_ID_TEAM)
        or team_id != EXPECTED_DEVELOPER_ID_TEAM
    ):
        return False, "runtime signing team does not match the pinned operator identity"
    macho_valid, macho_error = _verify_macho_identity(
        path, minimum_macos=EXPECTED_MINIMUM_MACOS
    )
    if not macho_valid:
        return False, macho_error
    detail_output = ""
    for command in (
        ["/usr/bin/codesign", "--verify", "--strict", "--verbose=4", str(path)],
        ["/usr/bin/codesign", "-dv", "--verbose=4", str(path)],
    ):
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        output = result.stdout + result.stderr
        if "-dv" in command:
            detail_output = output
        if result.returncode != 0:
            return False, "macOS code signature verification failed"
    team_ids = _CODESIGN_TEAM_RE.findall(detail_output)
    if team_ids != [team_id]:
        return False, "macOS signing identity does not match"
    authorities = re.findall(r"(?m)^Authority=(.+)$", detail_output)
    if identity and (not authorities or authorities[0] != identity):
        return False, "macOS Developer ID identity does not match"
    hardened = any(
        int(match.group(1), 16) & 0x10000
        for match in _CODESIGN_FLAGS_RE.finditer(detail_output)
    )
    if not hardened:
        return False, "macOS hardened runtime flag is missing"
    timestamp_match = _CODESIGN_TIMESTAMP_RE.search(detail_output)
    if secure_timestamp and (
        timestamp_match is None
        or timestamp_match.group(1).strip().casefold()
        in {"", "none", "not set", "unsigned"}
    ):
        return False, "macOS code signature is missing a secure Timestamp"
    if require_notarization:
        # The runtime entrypoint is a bare command-line Mach-O, not a .app
        # bundle, so `spctl --assess --type execute` always rejects it ("the
        # code is valid but does not seem to be an app"). Verify notarization
        # the same way the release gate (verify_runtime_release.py) does: the
        # codesign requirement `notarized` is the documented, code-object-native
        # proof and binds to this binary's CDHash. A tool failure or a failed
        # requirement is a fail-closed reject, never a pass. Offline note: a
        # bare Mach-O cannot have a notarization ticket stapled (stapling targets
        # bundles, disk images, and installer packages, not standalone binaries).
        # Without `--check-notarization` this requirement does not run the online
        # Gatekeeper lookup itself; it is satisfied by a stapled ticket or the
        # host's local notarization trust state. A bare binary therefore relies
        # on that local state (e.g. the host that notarized it, or a prior
        # Gatekeeper assessment); a host without it fails closed, never a bypass.
        # This activation-time dependency is a known operational constraint
        # (pipeline follow-up).
        try:
            result = subprocess.run(
                [
                    "/usr/bin/codesign",
                    "--verify",
                    "--strict",
                    "--verbose=4",
                    "--test-requirement",
                    "=notarized",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            return False, "macOS notarization verification tool failed"
        if result.returncode != 0:
            return False, "runtime is not notarized: codesign '=notarized' requirement failed"
    return True, ""


class _RuntimeSignatureError(runtime_bundle.BundleContractError):
    """Preserve signature failures through the closed bundle verifier."""


def _encoded_macos_version(value: int) -> str:
    if not _exact_int(value) or value < 0:
        raise ValueError("runtime Mach-O minimum version is invalid")
    major = (value >> 16) & 0xFFFF
    minor = (value >> 8) & 0xFF
    patch = value & 0xFF
    return f"{major}.{minor}" if patch == 0 else f"{major}.{minor}.{patch}"


def _inspect_runtime_member(
    path: Path,
    record: Mapping[str, Any],
    *,
    signing: Mapping[str, Any],
) -> dict[str, str]:
    """Inspect one exact thin-arm64 Mach-O member and its production signature."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        header_raw = os.read(descriptor, 32)
        if len(header_raw) != 32:
            raise ValueError("runtime Mach-O header is truncated")
        (
            magic,
            cpu_type,
            _subtype,
            file_type,
            command_count,
            command_bytes,
            _flags,
            _reserved,
        ) = struct.unpack("<IiiIIIII", header_raw)
        if (
            magic != 0xFEEDFACF
            or cpu_type != 0x0100000C
            or not 0 < command_count <= 4096
            or not 0 < command_bytes <= min(4 * 1024 * 1024, info.st_size - 32)
        ):
            raise ValueError("runtime Mach-O header is unsupported")
        commands = bytearray()
        while len(commands) < command_bytes:
            block = os.read(descriptor, min(1024 * 1024, command_bytes - len(commands)))
            if not block:
                raise ValueError("runtime Mach-O commands are truncated")
            commands.extend(block)
    finally:
        os.close(descriptor)

    offset = 0
    minimum_versions: list[str] = []
    for _index in range(command_count):
        if offset + 8 > len(commands):
            raise ValueError("runtime Mach-O command is truncated")
        command, size = struct.unpack_from("<II", commands, offset)
        if size < 8 or offset + size > len(commands):
            raise ValueError("runtime Mach-O command is invalid")
        if command == 0x32:
            if size < 24:
                raise ValueError("runtime build-version command is truncated")
            _cmd, _size, platform_id, minimum, _sdk, tool_count = struct.unpack_from(
                "<IIIIII", commands, offset
            )
            if platform_id != 1 or size != 24 + tool_count * 8:
                raise ValueError("runtime build-version command is invalid")
            minimum_versions.append(_encoded_macos_version(minimum))
        offset += size
    if offset != len(commands) or len(minimum_versions) != 1:
        raise ValueError("runtime Mach-O command table is ambiguous")
    macho_type = {2: "executable", 6: "dylib", 8: "bundle"}.get(file_type)
    observed = {
        "macho_type": macho_type,
        "architecture": "arm64",
        "minimum_macos": minimum_versions[0],
        "signing_profile": record.get("signing_profile"),
    }
    if any(type(record.get(key)) is not str or record[key] != value for key, value in observed.items()):
        raise ValueError("runtime Mach-O identity does not match the manifest")
    valid, error = _verify_macos_signature(
        path,
        team_id=signing["team_id"],
        identity=signing["identity"],
        secure_timestamp=signing["secure_timestamp"],
        require_notarization=(
            record["role"] == "entrypoint" and signing["require_notarization"]
        ),
    )
    if not valid:
        raise _RuntimeSignatureError(error)
    return observed


def _normalized_version(value: str) -> tuple[int, ...] | None:
    if not _VERSION_RE.fullmatch(value):
        return None
    parts = [int(part) for part in value.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _verify_macho_identity(
    path: Path, *, minimum_macos: str
) -> tuple[bool, str]:
    architecture = subprocess.run(
        ["/usr/bin/lipo", "-archs", str(path)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if architecture.returncode != 0 or architecture.stdout.strip().split() != ["arm64"]:
        return False, "Mach-O artifact is not a thin arm64 binary"
    load_commands = subprocess.run(
        ["/usr/bin/otool", "-l", str(path)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if load_commands.returncode != 0:
        return False, "Mach-O load commands cannot be inspected"
    build_versions: list[tuple[str, str]] = []
    for block in re.split(r"(?m)^Load command \d+\s*$", load_commands.stdout):
        if not re.search(r"(?m)^\s*cmd\s+LC_BUILD_VERSION\s*$", block):
            continue
        platform_match = re.search(r"(?m)^\s*platform\s+(\S+)\s*$", block)
        minos_match = re.search(r"(?m)^\s*minos\s+(\S+)\s*$", block)
        if platform_match is None or minos_match is None:
            return False, "Mach-O LC_BUILD_VERSION is malformed"
        build_versions.append((platform_match.group(1), minos_match.group(1)))
    if len(build_versions) != 1:
        return False, "Mach-O must contain exactly one LC_BUILD_VERSION command"
    build_platform, observed_minimum = build_versions[0]
    if build_platform.lower() not in {"1", "macos"}:
        return False, "Mach-O LC_BUILD_VERSION platform is not macOS"
    if (
        _normalized_version(observed_minimum) is None
        or _normalized_version(observed_minimum)
        != _normalized_version(minimum_macos)
    ):
        return False, "Mach-O minimum macOS version does not match the manifest"
    return True, ""


def _sha256_regular(path: Path, expected: FileIdentity) -> str | None:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                expected.device,
                expected.inode,
                expected.size,
            ):
                return None
            digest = hashlib.sha256()
            total = 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARTIFACT_BYTES:
                    return None
                digest.update(chunk)
            return digest.hexdigest()
        finally:
            os.close(descriptor)
    except OSError:
        return None


def _committed_legacy_package_role(
    data: object, manifest_digest: str
) -> tuple[str, str, int | None] | None:
    if (
        not isinstance(data, dict)
        or not _exact_int(data.get("schema_version"), LEGACY_MANIFEST_SCHEMA_VERSION)
        or not _exact_int(data.get("protocol_version"), PROTOCOL_VERSION)
        or not isinstance(data.get("artifacts"), list)
        or len(data["artifacts"]) != 1
        or not isinstance(data["artifacts"][0], dict)
    ):
        return None
    artifact_digest = data["artifacts"][0].get("sha256")
    if not isinstance(artifact_digest, str) or _SHA256_RE.fullmatch(artifact_digest) is None:
        return None
    try:
        selector = _read_broker_selector_view(_broker_root())
    except (OSError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError):
        return None
    if selector is None:
        return None
    for role in ("selected", "retained"):
        lane = selector.get(role)
        if (
            isinstance(lane, dict)
            and lane.get("artifact_sha256") == artifact_digest
            and lane.get("manifest_sha256") == manifest_digest
        ):
            return (
                role,
                lane["transport"],
                lane["protocol_version"] if lane["transport"] == "dispatcher" else None,
            )
    return None


def resolve_runtime() -> RuntimeResolution:
    if _operator_uid() is None:
        return RuntimeResolution(
            RuntimeStatus.PLATFORM_UNSUPPORTED,
            error="this release requires a POSIX user identity",
        )
    try:
        root = PLUGIN_ROOT.resolve(strict=True)
    except OSError:
        return RuntimeResolution(RuntimeStatus.PATH_INVALID, error="plugin root is unsafe")
    manifest_path = root / MANIFEST_NAME
    raw, _manifest_identity = _read_regular_nofollow(manifest_path, limit=1024 * 1024)
    if raw is None:
        if not manifest_path.exists():
            return RuntimeResolution(RuntimeStatus.UNAVAILABLE, error="runtime manifest absent")
        return RuntimeResolution(RuntimeStatus.PATH_INVALID, error="runtime manifest is unsafe")
    manifest_digest = hashlib.sha256(raw).hexdigest()
    try:
        data = runtime_bundle.load_closed_json_object(raw)
    except runtime_bundle.BundleContractError:
        return RuntimeResolution(RuntimeStatus.MANIFEST_INVALID, error="runtime manifest unreadable")
    commitment = _committed_legacy_package_role(data, manifest_digest)
    entry, error = _manifest_entry(
        data,
        role="candidate" if commitment is None else commitment[0],
        transport="dispatcher" if commitment is None else commitment[1],
        dispatcher_protocol_version=(
            DISPATCHER_PROTOCOL_VERSION if commitment is None else commitment[2]
        ),
    )
    if entry is None:
        return RuntimeResolution(RuntimeStatus.MANIFEST_INVALID, manifest_digest=manifest_digest, error=error)
    if entry == {}:
        return RuntimeResolution(RuntimeStatus.UNAVAILABLE, manifest_digest=manifest_digest, error=error)
    if normalized_platform() != "darwin" or normalized_arch() != "arm64":
        return RuntimeResolution(
            RuntimeStatus.PLATFORM_UNSUPPORTED,
            manifest_digest=manifest_digest,
            error="this release supports Darwin arm64 only",
        )
    bundle_path = _path_beneath_root(root, entry["path"])
    if bundle_path is None:
        return RuntimeResolution(RuntimeStatus.PATH_INVALID, manifest_digest=manifest_digest, error="runtime path is unsafe")
    entrypoint = bundle_path / entry["entrypoint"]
    identity = _safe_file_identity(entrypoint, executable=True)
    if identity is None:
        if not entrypoint.exists() or not bundle_path.exists():
            return RuntimeResolution(RuntimeStatus.UNAVAILABLE, manifest_digest=manifest_digest, error="runtime artifact absent")
        return RuntimeResolution(RuntimeStatus.PATH_INVALID, manifest_digest=manifest_digest, error="runtime ownership, mode, or link count is unsafe")
    try:
        by_name = {record["path"]: record for record in entry["_files"]}
        digest = runtime_bundle.verify_bundle_tree(
            bundle_path,
            entry["_files"],
            inspector=lambda member: _inspect_runtime_member(
                member,
                by_name[member.name],
                signing=entry["signing"],
            ),
        )
    except _RuntimeSignatureError as exc:
        return RuntimeResolution(RuntimeStatus.SIGNATURE_ERROR, manifest_digest=manifest_digest, error=str(exc))
    except runtime_bundle.BundleContractError as exc:
        return RuntimeResolution(RuntimeStatus.INTEGRITY_ERROR, manifest_digest=manifest_digest, error=str(exc))
    if digest != entry["sha256"]:
        return RuntimeResolution(RuntimeStatus.INTEGRITY_ERROR, manifest_digest=manifest_digest, error="runtime bundle identity mismatch")
    # Close the verification-to-exec window as far as path-based macOS exec
    # permits by recording the exact identity that invoke() must recheck.
    if _safe_file_identity(entrypoint, executable=True) != identity:
        return RuntimeResolution(RuntimeStatus.INTEGRITY_ERROR, manifest_digest=manifest_digest, error="runtime identity changed during verification")
    return RuntimeResolution(
        RuntimeStatus.OK,
        path=entrypoint,
        bundle_path=bundle_path,
        files=entry["_files"],
        contracts=entry["_contracts"],
        manifest_digest=manifest_digest,
        artifact_digest=digest,
        identity=identity,
        anchor=entry["_anchor"],
    )


def runtime_contract_snapshot() -> tuple[frozenset[tuple[str, str]], str]:
    resolution = resolve_runtime()
    if resolution.status != RuntimeStatus.OK:
        return frozenset(), resolution.manifest_digest
    return resolution.contracts, resolution.manifest_digest


def classify_host_context() -> str:
    if all(os.environ.get(key) == value for key, value in CODEX_DESKTOP_TUPLE.items()):
        return "codex_desktop"
    return "generic"


class _OperatorHomeUnavailable(ValueError):
    """Operator-home could not be resolved at a launchctl call site.

    A ValueError subclass (backward-compatible with existing `except ValueError`
    callers) that lets the idle-probe loop distinguish this ENVIRONMENTAL
    failure — including a transient `getpwuid` failure on `_launchctl`'s
    per-call re-resolution — from a genuine code-bug ValueError, without a racy
    re-check of `_operator_home()`.
    """


def _operator_home() -> str | None:
    if _pwd is None:
        return None
    operator_uid = _operator_uid()
    if operator_uid is None:
        return None
    try:
        value = _pwd.getpwuid(operator_uid).pw_dir
    except (KeyError, OSError):
        return None
    if (
        type(value) is not str
        or not value
        or "\0" in value
        or len(value) > 4096
        or not Path(value).is_absolute()
    ):
        return None
    return value


def _scrubbed_env(*, tmpdir: Path) -> dict[str, str]:
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    value = _operator_home()
    if value is not None:
        env["HOME"] = value
    env["TMPDIR"] = str(tmpdir)
    return env


def _broker_root() -> Path:
    value = _operator_home()
    if value is None:
        raise ValueError("operator home is unavailable")
    return Path(value) / ".agent-collab" / "provider-broker"


def _broker_lane_reference_valid(document: object) -> bool:
    return bool(
        isinstance(document, dict)
        and set(document) == BROKER_LANE_REFERENCE_KEYS
        and isinstance(document.get("artifact_sha256"), str)
        and _SHA256_RE.fullmatch(document["artifact_sha256"])
        and isinstance(document.get("manifest_sha256"), str)
        and _SHA256_RE.fullmatch(document["manifest_sha256"])
    )


def _broker_selector_valid(document: object) -> bool:
    if not isinstance(document, dict) or set(document) != BROKER_SELECTOR_KEYS:
        return False
    if (
        not _exact_int(document.get("schema_version"), 1)
        or not _exact_int(document.get("generation"))
        or document["generation"] < 1
        or document.get("selected_lane") not in {"blue", "green"}
        or not _broker_lane_reference_valid(document.get("blue"))
    ):
        return False
    green = document.get("green")
    if green is not None and not _broker_lane_reference_valid(green):
        return False
    return document["selected_lane"] != "green" or green is not None


def _broker_selector_transition_valid(current: object, candidate: object) -> bool:
    if not _broker_selector_valid(current) or not _broker_selector_valid(candidate):
        return False
    assert isinstance(current, dict) and isinstance(candidate, dict)
    if (
        candidate["generation"] != current["generation"] + 1
        or candidate["blue"] != current["blue"]
    ):
        return False
    if candidate["selected_lane"] == "green":
        return current["green"] is not None and candidate["green"] == current["green"]
    return True


def _broker_selector_v2_lane_valid(
    document: object, *, role: str
) -> bool:
    if not isinstance(document, dict) or set(document) != BROKER_SELECTOR_V2_LANE_KEYS:
        return False
    if (
        not _broker_lane_reference_valid(
            {
                "artifact_sha256": document.get("artifact_sha256"),
                "manifest_sha256": document.get("manifest_sha256"),
            }
        )
        or document.get("transport") not in {"broker", "dispatcher"}
        or not _exact_int(document.get("protocol_version"))
        or not _exact_int(document.get("lane_generation"))
    ):
        return False
    transport = document["transport"]
    protocol = document["protocol_version"]
    lane_generation = document["lane_generation"]
    if role == "lifecycle":
        return (
            transport == "broker"
            and protocol == LEGACY_BLUE_PROTOCOL_VERSION
            and lane_generation == 0
        )
    if role in {"selected", "retained"} and transport == "broker":
        return protocol == BROKER_PROTOCOL_VERSION and lane_generation == 0
    if transport != "dispatcher" or lane_generation < 1:
        return False
    if role == "candidate":
        return protocol == DISPATCHER_PROTOCOL_VERSION
    return protocol in {
        LEGACY_DISPATCHER_PROTOCOL_VERSION,
        DISPATCHER_PROTOCOL_VERSION,
    }


def _broker_selector_v2_valid(document: object) -> bool:
    if not isinstance(document, dict) or set(document) != BROKER_SELECTOR_V2_KEYS:
        return False
    if (
        not _exact_int(document.get("schema_version"), 2)
        or not _exact_int(document.get("generation"))
        or document["generation"] < 1
        or (
            document.get("selector_v1_sha256") is not None
            and (
                not isinstance(document["selector_v1_sha256"], str)
                or _SHA256_RE.fullmatch(document["selector_v1_sha256"]) is None
            )
        )
        or not _broker_selector_v2_lane_valid(
            document.get("selected"), role="selected"
        )
    ):
        return False
    for role in ("retained", "candidate", "lifecycle"):
        lane = document.get(role)
        if lane is not None and not _broker_selector_v2_lane_valid(lane, role=role):
            return False
    identities = [
        (
            lane["artifact_sha256"],
            lane["manifest_sha256"],
            lane["transport"],
            lane["protocol_version"],
        )
        for role in ("selected", "retained", "candidate", "lifecycle")
        if isinstance((lane := document.get(role)), dict)
    ]
    return len(identities) == len(set(identities))


def _broker_selector_v2_transition_valid(
    current: object, candidate: object, *, action: str
) -> bool:
    if (
        not _broker_selector_v2_valid(current)
        or not _broker_selector_v2_valid(candidate)
        or not isinstance(current, dict)
        or not isinstance(candidate, dict)
        or candidate["generation"] != current["generation"] + 1
        or candidate["selector_v1_sha256"] != current["selector_v1_sha256"]
        or candidate["lifecycle"] != current["lifecycle"]
    ):
        return False
    if action == "commit":
        return bool(
            current["candidate"] is not None
            and candidate["selected"] == current["candidate"]
            and candidate["retained"] == current["selected"]
            and candidate["candidate"] is None
        )
    if action == "abort":
        return bool(
            current["candidate"] is not None
            and candidate["selected"] == current["selected"]
            and candidate["retained"] == current["retained"]
            and candidate["candidate"] is None
        )
    return False


def _read_broker_selector(root: Path) -> dict[str, Any] | None:
    if _exact_mode(root, expected_type=stat.S_IFDIR, mode=0o700) is None:
        raise ValueError("provider broker root identity is unsafe")
    path = root / BROKER_SELECTOR_FILENAME
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    identity = _exact_mode(path, expected_type=stat.S_IFREG, mode=0o600)
    if identity is None or identity.st_size > BROKER_SELECTOR_MAX_BYTES:
        raise ValueError("provider broker selector identity is unsafe")
    raw, opened = _read_regular_nofollow(path, limit=BROKER_SELECTOR_MAX_BYTES)
    if raw is None or opened is None:
        raise ValueError("provider broker selector cannot be read safely")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_broker_json_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("provider broker selector is malformed") from exc
    if not _broker_selector_valid(document):
        raise ValueError("provider broker selector contract mismatch")
    return dict(document)


def _read_broker_selector_v2(root: Path) -> dict[str, Any] | None:
    if _exact_mode(root, expected_type=stat.S_IFDIR, mode=0o700) is None:
        raise ValueError("provider broker root identity is unsafe")
    path = root / BROKER_SELECTOR_V2_FILENAME
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    identity = _exact_mode(path, expected_type=stat.S_IFREG, mode=0o600)
    if identity is None or identity.st_size > BROKER_SELECTOR_MAX_BYTES:
        raise ValueError("provider broker selector-v2 identity is unsafe")
    raw, opened = _read_regular_nofollow(path, limit=BROKER_SELECTOR_MAX_BYTES)
    if raw is None or opened is None:
        raise ValueError("provider broker selector-v2 cannot be read safely")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_broker_json_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("provider broker selector-v2 is malformed") from exc
    if not _broker_selector_v2_valid(document):
        raise ValueError("provider broker selector-v2 contract mismatch")
    return dict(document)


def _read_broker_selector_view(root: Path) -> dict[str, Any] | None:
    selector_v1, selector_v1_raw = _read_selector_snapshot(root)
    selector_v2 = _read_broker_selector_v2(root)
    if selector_v2 is not None:
        projection = selector_v2["selector_v1_sha256"]
        if (
            (projection is None and selector_v1_raw is not None)
            or (
                projection is not None
                and (
                    selector_v1_raw is None
                    or hashlib.sha256(selector_v1_raw).hexdigest() != projection
                )
            )
        ):
            raise ValueError("provider broker selector-v1 projection changed")
        return selector_v2
    if selector_v1 is None:
        return None
    if selector_v1_raw is None:
        raise ValueError("provider broker selector-v1 topology is not migratable")
    if selector_v1.get("selected_lane") == "green" and selector_v1.get("green") is not None:
        selected = _load_dispatcher_broker_lane(
            root,
            selector_v1["green"],
            selector_v1["generation"],
            name="selected",
            protocol_version=LEGACY_DISPATCHER_PROTOCOL_VERSION,
        )
        lifecycle = _load_lifecycle_blue_lane(root)
    elif selector_v1.get("selected_lane") == "blue":
        selected = _load_legacy_broker_lane(root, role="selected")
        if selected is None or {
            "artifact_sha256": selected.artifact_digest,
            "manifest_sha256": selected.manifest_digest,
        } != selector_v1["blue"]:
            raise ValueError("committed legacy broker lane changed")
        lifecycle = None
    else:
        raise ValueError("provider broker selector-v1 topology is not migratable")
    return {
        "schema_version": 2,
        "generation": 1,
        "selector_v1_sha256": hashlib.sha256(selector_v1_raw).hexdigest(),
        "selected": _selector_v2_lane_document(selected),
        "retained": None,
        "candidate": None,
        "lifecycle": (
            None if lifecycle is None else _selector_v2_lane_document(lifecycle)
        ),
    }


def _selector_v1_projection_matches_selected(
    root: Path, selector_v2: Mapping[str, Any]
) -> bool:
    selector_v1, selector_v1_raw = _read_selector_snapshot(root)
    if (
        selector_v1 is None
        or selector_v1_raw is None
        or selector_v2.get("selector_v1_sha256")
        != hashlib.sha256(selector_v1_raw).hexdigest()
        or not isinstance(selector_v2.get("selected"), dict)
    ):
        return False
    selected = selector_v2["selected"]
    reference = {
        "artifact_sha256": selected.get("artifact_sha256"),
        "manifest_sha256": selected.get("manifest_sha256"),
    }
    if selector_v1["selected_lane"] == "blue":
        return bool(
            selected.get("transport") == "broker"
            and selected.get("protocol_version") == BROKER_PROTOCOL_VERSION
            and selected.get("lane_generation") == 0
            and selector_v1["blue"] == reference
        )
    return bool(
        selector_v1["selected_lane"] == "green"
        and selected.get("transport") == "dispatcher"
        and selected.get("protocol_version")
        == LEGACY_DISPATCHER_PROTOCOL_VERSION
        and selected.get("lane_generation") == selector_v1["generation"]
        and selector_v1["green"] == reference
    )


def _selector_v2_lane_document(lane: BrokerLaneSnapshot) -> dict[str, Any]:
    role = lane.name if lane.name in {"selected", "retained", "candidate"} else "lifecycle"
    document = {
        "artifact_sha256": lane.artifact_digest,
        "manifest_sha256": lane.manifest_digest,
        "transport": lane.transport,
        "protocol_version": lane.protocol_version,
        "lane_generation": lane.generation,
    }
    if not _broker_selector_v2_lane_valid(document, role=role):
        raise ValueError("provider broker selector-v2 lane is invalid")
    return document


def _load_selector_v2_lane(
    root: Path, document: Mapping[str, Any], *, role: str
) -> BrokerLaneSnapshot:
    if not _broker_selector_v2_lane_valid(document, role=role):
        raise ValueError("provider broker selector-v2 lane is invalid")
    reference = {
        "artifact_sha256": document["artifact_sha256"],
        "manifest_sha256": document["manifest_sha256"],
    }
    if role == "lifecycle":
        lane = _load_lifecycle_blue_lane(root)
        if lane is None or _selector_v2_lane_document(lane) != dict(document):
            raise ValueError("provider broker lifecycle lane changed")
        return lane
    if document["transport"] == "broker":
        lane = _load_legacy_broker_lane(root, role=role)
        if lane is None or _selector_v2_lane_document(lane) != dict(document):
            raise ValueError("committed legacy broker lane changed")
        return lane
    return _load_dispatcher_broker_lane(
        root,
        reference,
        document["lane_generation"],
        name=role,
        protocol_version=document["protocol_version"],
    )


def _dispatcher_lane_token(artifact_digest: str, manifest_digest: str) -> str:
    if (
        not isinstance(artifact_digest, str)
        or _SHA256_RE.fullmatch(artifact_digest) is None
        or not isinstance(manifest_digest, str)
        or _SHA256_RE.fullmatch(manifest_digest) is None
    ):
        raise ValueError("provider dispatcher identity is invalid")
    digest = hashlib.sha256()
    digest.update(b"agent-collab-provider-dispatcher-v1\0")
    digest.update(bytes.fromhex(artifact_digest))
    digest.update(bytes.fromhex(manifest_digest))
    return digest.hexdigest()[:32]


def _dispatcher_canonical_json(document: Mapping[str, Any]) -> bytes:
    if type(document) is not dict:
        raise ValueError("provider dispatcher frame must be an object")
    try:
        return json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("provider dispatcher frame is not canonical") from exc


def _dispatcher_frame_sha256(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(_dispatcher_canonical_json(document)).hexdigest()


def _dispatcher_nonce(value: object) -> str:
    if type(value) is not str or not value or len(value) > 64:
        raise ValueError("provider dispatcher nonce is invalid")
    try:
        padded = value + "=" * ((4 - len(value) % 4) % 4)
        raw = base64.b64decode(
            padded.encode("ascii"), altchars=b"-_", validate=True
        )
    except (UnicodeError, ValueError) as exc:
        raise ValueError("provider dispatcher nonce is invalid") from exc
    if (
        len(raw) != 32
        or base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value
    ):
        raise ValueError("provider dispatcher nonce is invalid")
    return value


def _dispatcher_lane_fields(lane: BrokerLaneSnapshot) -> dict[str, Any]:
    if (
        not isinstance(lane, BrokerLaneSnapshot)
        or lane.transport != "dispatcher"
        or lane.protocol_version
        not in {LEGACY_DISPATCHER_PROTOCOL_VERSION, DISPATCHER_PROTOCOL_VERSION}
        or not _exact_int(lane.generation)
        or lane.generation < 1
        or _SHA256_RE.fullmatch(lane.artifact_digest) is None
        or _SHA256_RE.fullmatch(lane.manifest_digest) is None
        or lane.label
        != "com.agent-collab.provider-dispatcher."
        + _dispatcher_lane_token(lane.artifact_digest, lane.manifest_digest)
    ):
        raise ValueError("provider dispatcher lane identity is invalid")
    return {
        "lane_generation": lane.generation,
        "lane_token": _dispatcher_lane_token(
            lane.artifact_digest, lane.manifest_digest
        ),
        "artifact_sha256": lane.artifact_digest,
        "manifest_sha256": lane.manifest_digest,
    }


def _dispatcher_execution_key(request: Mapping[str, Any]) -> str:
    if type(request) is not dict:
        raise ValueError("provider dispatcher execution key is invalid")
    operation = request.get("operation")
    if operation == "dispatcher_ping":
        key = "dispatcher_ping"
    elif operation in {"dispatcher_lock_probe", "adoption_canary"}:
        provider = request.get("provider")
        key = provider if provider in {"gemini", "grok", "opencode"} else None
    elif operation in {"readiness", "execute"}:
        route = request.get("route")
        key = "grok" if route in {"grok", "composer"} else route
    else:
        key = None
    if key not in {"gemini", "grok", "opencode", "codex", "dispatcher_ping"}:
        raise ValueError("provider dispatcher execution key is invalid")
    assert isinstance(key, str)
    return key


def _dispatcher_request_reservation(
    request: Mapping[str, Any], *, canonical: bytes | None = None
) -> tuple[int, str, str]:
    encoded = _dispatcher_canonical_json(request) if canonical is None else canonical
    if not encoded or len(encoded) > MAX_REQUEST_BYTES - 4096:
        raise ValueError("provider dispatcher request reservation is invalid")
    return (
        len(encoded),
        hashlib.sha256(encoded).hexdigest(),
        _dispatcher_execution_key(request),
    )


def _dispatcher_build_hello(
    *,
    lane: BrokerLaneSnapshot,
    client_pid: int,
    nonce: str,
    deadline_monotonic_ms: int,
    request: Mapping[str, Any] | None = None,
    reservation: tuple[int, str, str] | None = None,
) -> dict[str, Any]:
    if (
        type(client_pid) is not int
        or client_pid <= 1
        or type(deadline_monotonic_ms) is not int
        or deadline_monotonic_ms < 1
    ):
        raise ValueError("provider dispatcher hello identity is invalid")
    document: dict[str, Any] = {
        "frame_type": "hello",
        "dispatcher_protocol_version": lane.protocol_version,
        "client_pid": client_pid,
        "nonce": _dispatcher_nonce(nonce),
        "deadline_monotonic_ms": deadline_monotonic_ms,
        **_dispatcher_lane_fields(lane),
    }
    expected_keys = LEGACY_DISPATCHER_HELLO_KEYS
    if lane.protocol_version == DISPATCHER_PROTOCOL_VERSION:
        selected = reservation
        if selected is None:
            if request is None:
                raise ValueError("provider dispatcher reservation is unavailable")
            selected = _dispatcher_request_reservation(request)
        if (
            not isinstance(selected, tuple)
            or len(selected) != 3
            or not _exact_int(selected[0])
            or selected[0] < 1
            or not isinstance(selected[1], str)
            or _SHA256_RE.fullmatch(selected[1]) is None
            or selected[2]
            not in {"gemini", "grok", "opencode", "codex", "dispatcher_ping"}
        ):
            raise ValueError("provider dispatcher reservation is invalid")
        document.update(
            {
                "request_size": selected[0],
                "request_sha256": selected[1],
                "execution_key": selected[2],
            }
        )
        expected_keys = DISPATCHER_HELLO_KEYS
    if set(document) != expected_keys:
        raise ValueError("provider dispatcher hello schema is invalid")
    _dispatcher_canonical_json(document)
    return document


def _dispatcher_accept_ready(
    hello: object,
    ready: object,
    *,
    lane: BrokerLaneSnapshot,
    expected_dispatcher_pid: int,
    now_monotonic: float,
) -> DispatcherSession:
    hello_keys = (
        DISPATCHER_HELLO_KEYS
        if lane.protocol_version == DISPATCHER_PROTOCOL_VERSION
        else LEGACY_DISPATCHER_HELLO_KEYS
    )
    ready_keys = (
        DISPATCHER_READY_KEYS
        if lane.protocol_version == DISPATCHER_PROTOCOL_VERSION
        else LEGACY_DISPATCHER_READY_KEYS
    )
    if (
        type(hello) is not dict
        or set(hello) != hello_keys
        or type(ready) is not dict
        or set(ready) != ready_keys
        or type(expected_dispatcher_pid) is not int
        or expected_dispatcher_pid <= 1
        or isinstance(now_monotonic, bool)
        or not isinstance(now_monotonic, (int, float))
        or not math.isfinite(float(now_monotonic))
        or float(now_monotonic) < 0
    ):
        raise ValueError("provider dispatcher ready schema is invalid")
    expected_hello = {
        "frame_type": "hello",
        "dispatcher_protocol_version": lane.protocol_version,
        "client_pid": hello.get("client_pid"),
        "nonce": _dispatcher_nonce(hello.get("nonce")),
        "deadline_monotonic_ms": hello.get("deadline_monotonic_ms"),
        **_dispatcher_lane_fields(lane),
    }
    if lane.protocol_version == DISPATCHER_PROTOCOL_VERSION:
        expected_hello.update(
            {
                "execution_key": hello.get("execution_key"),
                "request_size": hello.get("request_size"),
                "request_sha256": hello.get("request_sha256"),
            }
        )
    now_ms = int(float(now_monotonic) * 1000)
    if (
        hello != expected_hello
        or hello["deadline_monotonic_ms"] <= now_ms
        or hello["deadline_monotonic_ms"]
        > now_ms + int(DISPATCHER_MAX_REQUEST_SECONDS * 1000)
    ):
        raise ValueError("provider dispatcher hello is invalid")
    hello_sha256 = _dispatcher_frame_sha256(hello)
    expected_ready = {
        **hello,
        "frame_type": "ready",
        "dispatcher_pid": expected_dispatcher_pid,
        "hello_sha256": hello_sha256,
    }
    if ready != expected_ready:
        raise ValueError("provider dispatcher ready identity is unbound")
    return DispatcherSession(
        lane=lane,
        client_pid=hello["client_pid"],
        dispatcher_pid=expected_dispatcher_pid,
        nonce=hello["nonce"],
        deadline_monotonic_ms=hello["deadline_monotonic_ms"],
        hello_sha256=hello_sha256,
        ready_sha256=_dispatcher_frame_sha256(expected_ready),
        execution_key=str(hello.get("execution_key", "")),
        request_size=int(hello.get("request_size", 0)),
        request_sha256=str(hello.get("request_sha256", "")),
    )


def _dispatcher_build_request_frame(
    *, session: DispatcherSession, request: Mapping[str, Any]
) -> dict[str, Any]:
    if (
        not isinstance(session, DispatcherSession)
        or session.consumed
        or type(request) is not dict
    ):
        raise ValueError("provider dispatcher handshake was already consumed")
    document: dict[str, Any] = {
        "frame_type": "request",
        "dispatcher_protocol_version": session.lane.protocol_version,
        "client_pid": session.client_pid,
        "nonce": session.nonce,
        "deadline_monotonic_ms": session.deadline_monotonic_ms,
        **_dispatcher_lane_fields(session.lane),
        "hello_sha256": session.hello_sha256,
        "ready_sha256": session.ready_sha256,
        "request": dict(request),
    }
    expected_keys = LEGACY_DISPATCHER_REQUEST_KEYS
    if session.lane.protocol_version == DISPATCHER_PROTOCOL_VERSION:
        reservation = _dispatcher_request_reservation(request)
        if reservation != (
            session.request_size,
            session.request_sha256,
            session.execution_key,
        ):
            raise ValueError("provider dispatcher request reservation is unbound")
        document.update(
            {
                "execution_key": session.execution_key,
                "request_size": session.request_size,
                "request_sha256": session.request_sha256,
            }
        )
        expected_keys = DISPATCHER_REQUEST_KEYS
    if set(document) != expected_keys:
        raise ValueError("provider dispatcher request schema is invalid")
    _dispatcher_canonical_json(document)
    return document


def _dispatcher_bridge_document(
    *,
    lane: BrokerLaneSnapshot,
    request: Mapping[str, Any],
    deadline_monotonic_ms: int,
    handshake_deadline_monotonic_ms: int,
) -> bytes:
    if (
        not isinstance(lane, BrokerLaneSnapshot)
        or lane.transport != "dispatcher"
        or lane.protocol_version
        not in {LEGACY_DISPATCHER_PROTOCOL_VERSION, DISPATCHER_PROTOCOL_VERSION}
        or lane.label
        != "com.agent-collab.provider-dispatcher."
        + _dispatcher_lane_token(lane.artifact_digest, lane.manifest_digest)
        or type(request) is not dict
        or not _exact_int(deadline_monotonic_ms)
        or not _exact_int(handshake_deadline_monotonic_ms)
        or handshake_deadline_monotonic_ms <= 0
        or handshake_deadline_monotonic_ms > deadline_monotonic_ms
    ):
        raise ValueError("provider dispatcher bridge input is invalid")
    document: dict[str, Any] = {
        "bridge_protocol_version": lane.protocol_version,
        "lane_generation": lane.generation,
        "artifact_sha256": lane.artifact_digest,
        "manifest_sha256": lane.manifest_digest,
        "deadline_monotonic_ms": deadline_monotonic_ms,
        "handshake_deadline_monotonic_ms": handshake_deadline_monotonic_ms,
        "request": dict(request),
    }
    expected_keys = LEGACY_DISPATCHER_BRIDGE_KEYS
    if lane.protocol_version == DISPATCHER_PROTOCOL_VERSION:
        request_size, request_sha256, execution_key = _dispatcher_request_reservation(
            request
        )
        document.update(
            {
                "execution_key": execution_key,
                "request_size": request_size,
                "request_sha256": request_sha256,
            }
        )
        expected_keys = DISPATCHER_BRIDGE_KEYS
    if set(document) != expected_keys:
        raise ValueError("provider dispatcher bridge schema is invalid")
    encoded = _dispatcher_canonical_json(document) + b"\n"
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("provider dispatcher bridge exceeded its bound")
    return encoded


def _adoption_canary_document(request: object) -> bytes:
    if type(request) is not dict or set(request) != ADOPTION_CANARY_KEYS:
        raise ValueError("adoption canary schema is invalid")
    provider = request.get("provider")
    routes = request.get("routes")
    if (
        request.get("operation") != "adoption_canary"
        or not _exact_int(request.get("protocol_version"), PROTOCOL_VERSION)
        or type(request.get("request_id")) is not str
        or _REQUEST_ID_RE.fullmatch(request["request_id"]) is None
        or type(provider) is not str
        or provider not in ADOPTION_PROVIDER_ROUTES
        or type(routes) is not list
        or not routes
        or any(type(route) is not str for route in routes)
        or routes != sorted(routes, key=lambda item: item.encode("utf-8"))
        or len(routes) != len(set(routes))
        or not set(routes).issubset(ADOPTION_PROVIDER_ROUTES[provider])
        or any(
            type(request.get(key)) is not int or request[key] < 1
            for key in (
                "registry_generation",
                "source_generation",
                "adapter_contract_generation",
                "attempt_generation",
            )
        )
        or type(request.get("timeout_ms")) is not int
        or not 1 <= request["timeout_ms"] <= MAX_TIMEOUT_MS
        or any(
            type(request.get(key)) is not str
            or _SHA256_RE.fullmatch(request[key]) is None
            for key in ("binary_sha256", "worker_sha256")
        )
    ):
        raise ValueError("adoption canary fields are invalid")
    _dispatcher_nonce(request.get("authority_token"))
    # The request remains on the public runtime protocol sealed into the
    # one-time authority record.  Only the surrounding dispatcher bridge and
    # handshake frames use the private dispatcher protocol.
    document = {
        **request,
        "host_context": classify_host_context(),
    }
    encoded = _dispatcher_canonical_json(document) + b"\n"
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("adoption canary exceeds the fixed protocol limit")
    return encoded


def _observe_dispatcher_credentials(
    peer: socket.socket,
    *,
    allow_launchd_sentinel: bool = False,
) -> tuple[int, int]:
    if type(allow_launchd_sentinel) is not bool:
        raise ValueError("provider dispatcher peer credential policy is invalid")
    try:
        raw = peer.getsockopt(0, 1, 256)
        pid_raw = peer.getsockopt(0, 2, struct.calcsize("i"))
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise ValueError("provider dispatcher peer credentials are unavailable") from exc
    if not isinstance(raw, bytes) or len(raw) < 12:
        raise ValueError("provider dispatcher peer credentials are malformed")
    version = int.from_bytes(raw[0:4], sys.byteorder, signed=False)
    uid = int.from_bytes(raw[4:8], sys.byteorder, signed=False)
    group_count = int.from_bytes(raw[8:10], sys.byteorder, signed=True)
    if (
        version != 0
        or not 0 <= group_count <= 16
        or len(raw) < 12 + group_count * 4
        or not isinstance(pid_raw, bytes)
        or len(pid_raw) != struct.calcsize("i")
    ):
        raise ValueError("provider dispatcher peer credentials are malformed")
    pid = int.from_bytes(pid_raw, sys.byteorder, signed=True)
    if pid <= 1 and not (
        allow_launchd_sentinel and pid == DISPATCHER_LAUNCHD_SENTINEL_PID
    ):
        raise ValueError("provider dispatcher peer PID is invalid")
    return uid, pid


def _await_dispatcher_launchd_credentials(
    peer: socket.socket,
    *,
    deadline: float,
    credential_observer=None,
    now_monotonic=time.monotonic,
    sleeper=time.sleep,
) -> tuple[int, int]:
    if (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(float(deadline))
        or not callable(now_monotonic)
        or not callable(sleeper)
        or (credential_observer is not None and not callable(credential_observer))
    ):
        raise ValueError("provider dispatcher launchd peer deadline is invalid")
    if credential_observer is None:
        def observe_launchd_peer(selected: socket.socket) -> tuple[int, int]:
            return _observe_dispatcher_credentials(
                selected,
                allow_launchd_sentinel=True,
            )

        observer = observe_launchd_peer
    else:
        observer = credential_observer
    delay = DISPATCHER_LAUNCHD_INITIAL_DELAY_SECONDS
    while True:
        try:
            now = float(now_monotonic())
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("provider dispatcher launchd peer clock is invalid") from exc
        if not math.isfinite(now) or now >= float(deadline):
            raise ValueError("provider dispatcher launchd peer deadline expired")
        try:
            credentials = observer(peer)
        except (AttributeError, OSError, TypeError, ValueError) as exc:
            raise ValueError(
                "provider dispatcher launchd peer credentials are unavailable"
            ) from exc
        if (
            not isinstance(credentials, tuple)
            or len(credentials) != 2
            or type(credentials[0]) is not int
            or type(credentials[1]) is not int
        ):
            raise ValueError("provider dispatcher launchd peer credentials are invalid")
        uid, pid = credentials
        if uid != DISPATCHER_LAUNCHD_LISTENER_UID:
            raise ValueError("provider dispatcher launchd listener was rejected")
        if pid > DISPATCHER_LAUNCHD_SENTINEL_PID:
            return uid, pid
        if pid != DISPATCHER_LAUNCHD_SENTINEL_PID:
            raise ValueError("provider dispatcher launchd peer PID was rejected")
        try:
            current = float(now_monotonic())
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("provider dispatcher launchd peer clock is invalid") from exc
        remaining = float(deadline) - current
        if not math.isfinite(current) or remaining <= 0:
            raise ValueError("provider dispatcher launchd peer deadline expired")
        sleep_for = min(delay, remaining)
        try:
            sleeper(sleep_for)
        except (OSError, OverflowError, TypeError, ValueError) as exc:
            raise ValueError("provider dispatcher launchd peer wait failed") from exc
        delay = min(delay * 2, DISPATCHER_LAUNCHD_MAX_DELAY_SECONDS)


def _observe_dispatcher_process(pid: int) -> tuple[str, Path]:
    if normalized_platform() != "darwin" or type(pid) is not int or pid <= 1:
        raise ValueError("provider dispatcher process proof is unavailable")
    try:
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        path_function = library.proc_pidpath
        path_function.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        path_function.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(4096)
        length = int(path_function(pid, buffer, len(buffer)))
        if length <= 0 or length >= len(buffer):
            raise OSError("dispatcher path query failed")
        raw = bytes(buffer.raw[:length])
        if b"\0" in raw:
            raise OSError("dispatcher path contains NUL")
        path = Path(os.fsdecode(raw))
        if not path.is_absolute() or os.fsencode(path) != raw:
            raise OSError("dispatcher path is invalid")

        info_function = library.proc_pidinfo
        info_function.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        info_function.restype = ctypes.c_int
        info = _DarwinProcBSDInfo()
        observed = int(
            info_function(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
        )
        if (
            observed != ctypes.sizeof(info)
            or info.pbi_pid != pid
            or info.pbi_uid != os.getuid()
            or info.pbi_start_tvsec <= 0
        ):
            raise OSError("dispatcher process identity is invalid")
        return f"{info.pbi_start_tvsec}:{info.pbi_start_tvusec}", path
    except (OSError, TypeError, ValueError, UnicodeError, ctypes.ArgumentError) as exc:
        raise ValueError("provider dispatcher process proof failed") from exc


def _observe_dispatcher_socket(lane: BrokerLaneSnapshot) -> FileIdentity:
    info = _exact_mode(lane.socket_path, expected_type=stat.S_IFSOCK, mode=0o600)
    if info is None:
        raise ValueError("provider dispatcher socket identity is unavailable")
    return FileIdentity(
        device=info.st_dev,
        inode=info.st_ino,
        size=info.st_size,
        mtime_ns=info.st_mtime_ns,
        mode=info.st_mode,
        uid=info.st_uid,
        links=info.st_nlink,
    )


def _prove_dispatcher_peer(
    peer: socket.socket,
    lane: BrokerLaneSnapshot,
    *,
    credentials: tuple[int, int] | None = None,
    expected_credential_uid: int | None = None,
    expected_pid: int | None = None,
    final_credential_observer=None,
    credential_observer=_observe_dispatcher_credentials,
    process_observer=_observe_dispatcher_process,
    socket_observer=_observe_dispatcher_socket,
    published_verifier=None,
    root: Path | None = None,
) -> int:
    if (
        not isinstance(lane, BrokerLaneSnapshot)
        or lane.transport != "dispatcher"
        or lane.anchor is None
    ):
        raise ValueError("provider dispatcher lane proof is invalid")
    selected_root = _broker_root() if root is None else root
    verifier = _verify_published_version if published_verifier is None else published_verifier
    if not isinstance(selected_root, Path) or not selected_root.is_absolute():
        raise ValueError("provider dispatcher root is invalid")
    selected_credential_uid = (
        os.getuid()
        if expected_credential_uid is None
        else expected_credential_uid
    )
    if (
        type(selected_credential_uid) is not int
        or selected_credential_uid < 0
        or (
            expected_pid is not None
            and (type(expected_pid) is not int or expected_pid <= 1)
        )
        or (
            final_credential_observer is not None
            and not callable(final_credential_observer)
        )
        or (
            expected_credential_uid is not None
            and final_credential_observer is None
        )
    ):
        raise ValueError("provider dispatcher peer policy is invalid")
    try:
        socket_before = socket_observer(lane)
        _bundle, runtime, _manifest, anchor = verifier(
            selected_root,
            artifact_digest=lane.artifact_digest,
            manifest_digest=lane.manifest_digest,
            role=lane.name,
            dispatcher_protocol_version=lane.protocol_version,
        )
        if anchor != lane.anchor:
            raise ValueError("provider dispatcher contract anchor changed")
        observed_credentials = (
            credential_observer(peer)
            if credentials is None
            else credentials
        )
        if (
            not isinstance(observed_credentials, tuple)
            or len(observed_credentials) != 2
            or type(observed_credentials[0]) is not int
            or type(observed_credentials[1]) is not int
        ):
            raise ValueError("provider dispatcher peer credentials are invalid")
        uid, pid = observed_credentials
        start_before, path_before = process_observer(pid)
        start_after, path_after = process_observer(pid)
        _bundle2, runtime_after, _manifest2, anchor_after = verifier(
            selected_root,
            artifact_digest=lane.artifact_digest,
            manifest_digest=lane.manifest_digest,
            role=lane.name,
            dispatcher_protocol_version=lane.protocol_version,
        )
        socket_after = socket_observer(lane)
        final_credentials = (
            None
            if final_credential_observer is None
            else final_credential_observer()
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("provider dispatcher peer identity is unproven") from exc
    try:
        same_before = os.path.samefile(path_before, runtime)
        same_after = os.path.samefile(path_after, runtime_after)
    except OSError as exc:
        raise ValueError("provider dispatcher executable identity is unproven") from exc
    if (
        uid != selected_credential_uid
        or pid <= 1
        or (expected_pid is not None and pid != expected_pid)
        or type(start_before) is not str
        or not start_before
        or start_after != start_before
        or path_after != path_before
        or runtime_after != runtime
        or anchor_after != anchor
        or not same_before
        or not same_after
        or socket_after != socket_before
        or (
            final_credentials is not None
            and (
                not isinstance(final_credentials, tuple)
                or len(final_credentials) != 2
                or type(final_credentials[0]) is not int
                or type(final_credentials[1]) is not int
                or final_credentials != (uid, pid)
            )
        )
    ):
        raise ValueError("provider dispatcher peer identity changed")
    return pid


def _prove_dispatcher_launchd_peer(
    peer: socket.socket,
    lane: BrokerLaneSnapshot,
    *,
    deadline: float,
    credential_waiter=_await_dispatcher_launchd_credentials,
    credential_observer=_observe_dispatcher_credentials,
    peer_prover=_prove_dispatcher_peer,
) -> int:
    if credential_observer is _observe_dispatcher_credentials:
        credentials = credential_waiter(peer, deadline=deadline)
    else:
        credentials = credential_waiter(
            peer,
            deadline=deadline,
            credential_observer=credential_observer,
        )
    return peer_prover(
        peer,
        lane,
        credentials=credentials,
        expected_credential_uid=DISPATCHER_LAUNCHD_LISTENER_UID,
        expected_pid=credentials[1],
        final_credential_observer=lambda: credential_observer(peer),
    )


def _dispatcher_exchange(
    *,
    peer: socket.socket,
    lane: BrokerLaneSnapshot,
    request: Mapping[str, Any],
    deadline: float,
    handshake_deadline: float | None = None,
) -> dict[str, Any]:
    request_started = False
    ready_accepted = False
    try:
        now = time.monotonic()
        selected_handshake_deadline = (
            min(deadline, now + DISPATCHER_MAX_HANDSHAKE_SECONDS)
            if handshake_deadline is None
            else handshake_deadline
        )
        if (
            isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or not math.isfinite(float(deadline))
            or isinstance(selected_handshake_deadline, bool)
            or not isinstance(selected_handshake_deadline, (int, float))
            or not math.isfinite(float(selected_handshake_deadline))
            or selected_handshake_deadline <= now
            or selected_handshake_deadline > deadline
            or selected_handshake_deadline
            > now + DISPATCHER_MAX_HANDSHAKE_SECONDS
        ):
            raise ValueError("provider dispatcher handshake deadline is invalid")
        dispatcher_pid = _prove_dispatcher_launchd_peer(
            peer,
            lane,
            deadline=selected_handshake_deadline,
        )
        nonce = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
        canonical_request = _dispatcher_canonical_json(request)
        reservation = _dispatcher_request_reservation(
            request, canonical=canonical_request
        )
        hello = _dispatcher_build_hello(
            lane=lane,
            client_pid=os.getpid(),
            nonce=nonce,
            deadline_monotonic_ms=int(deadline * 1000),
            request=request,
            reservation=reservation,
        )
        peer.settimeout(max(0.001, selected_handshake_deadline - time.monotonic()))
        peer.sendall(
            _encode_broker_frame(hello, max_bytes=BROKER_MAX_REQUEST_BYTES)
        )
        ready = _read_broker_frame(
            peer,
            max_bytes=BROKER_MAX_REQUEST_BYTES,
            deadline=selected_handshake_deadline,
        )
        session = _dispatcher_accept_ready(
            hello,
            ready,
            lane=lane,
            expected_dispatcher_pid=dispatcher_pid,
            now_monotonic=time.monotonic(),
        )
        ready_accepted = True
        frame = _dispatcher_build_request_frame(session=session, request=request)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("provider dispatcher request deadline expired")
        peer.settimeout(remaining)
        request_started = True
        session.consumed = True
        peer.sendall(
            _encode_broker_frame(frame, max_bytes=BROKER_MAX_REQUEST_BYTES)
        )
        return _read_broker_frame(
            peer,
            max_bytes=BROKER_MAX_RESPONSE_BYTES,
            deadline=deadline,
        )
    except _DispatcherPostRequestError:
        raise
    except (OSError, OverflowError, TimeoutError, TypeError, ValueError) as exc:
        error = (
            _DispatcherPostRequestError
            if request_started
            or (
                ready_accepted
                and lane.protocol_version == DISPATCHER_PROTOCOL_VERSION
            )
            else _DispatcherPreRequestError
        )
        raise error("provider dispatcher exchange failed") from exc


def _dispatcher_lane_snapshot(
    root: Path,
    *,
    artifact_digest: str,
    manifest_digest: str,
    generation: int,
    name: str = "candidate",
    protocol_version: int = DISPATCHER_PROTOCOL_VERSION,
    anchor: RuntimeContractAnchor | None = None,
) -> BrokerLaneSnapshot:
    if (
        not root.is_absolute()
        or name not in {"selected", "retained", "candidate", "green"}
        or not _exact_int(generation)
        or generation < 1
        or protocol_version
        not in {LEGACY_DISPATCHER_PROTOCOL_VERSION, DISPATCHER_PROTOCOL_VERSION}
    ):
        raise ValueError("provider dispatcher lane input is invalid")
    token = _dispatcher_lane_token(artifact_digest, manifest_digest)
    socket_path = root / f"provider-dispatcher-{token}.sock"
    if len(os.fsencode(socket_path)) > BROKER_SUN_PATH_MAX_BYTES:
        raise ValueError("provider dispatcher socket path is too long")
    return BrokerLaneSnapshot(
        name=name,
        generation=generation,
        artifact_digest=artifact_digest,
        manifest_digest=manifest_digest,
        label=f"com.agent-collab.provider-dispatcher.{token}",
        socket_path=socket_path,
        transport="dispatcher",
        protocol_version=protocol_version,
        anchor=anchor,
    )


def _dispatcher_mutable_path(root: Path, lane: BrokerLaneSnapshot, suffix: str) -> Path:
    if lane.transport != "dispatcher" or suffix not in {"json", "plist"}:
        raise ValueError("provider dispatcher mutable path is invalid")
    token = _dispatcher_lane_token(lane.artifact_digest, lane.manifest_digest)
    return root / f"provider-dispatcher-{token}.{suffix}"


def _exact_mode(path: Path, *, expected_type: int, mode: int) -> os.stat_result | None:
    try:
        info = path.lstat()
    except OSError:
        return None
    if (
        stat.S_IFMT(info.st_mode) != expected_type
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or (expected_type != stat.S_IFDIR and info.st_nlink != 1)
        or stat.S_IMODE(info.st_mode) != mode
    ):
        return None
    return info


def _broker_record_valid(
    document: object,
    root: Path,
    *,
    allow_previous: bool,
    runtime_protocol_version: int | None = None,
) -> bool:
    expected_protocol = (
        PROTOCOL_VERSION
        if runtime_protocol_version is None
        else runtime_protocol_version
    )
    if not isinstance(document, dict) or set(document) != BROKER_STATE_KEYS:
        return False
    if (
        not _exact_int(expected_protocol)
        or expected_protocol not in LIFECYCLE_BLUE_PROTOCOL_VERSIONS
        or not _exact_int(document.get("schema_version"), 2)
        or not _exact_int(document.get("contract_version"), CONTRACT_VERSION)
        or not _exact_int(
            document.get("broker_protocol_version"), BROKER_PROTOCOL_VERSION
        )
        or not _exact_int(
            document.get("runtime_protocol_version"), expected_protocol
        )
        or not isinstance(document.get("artifact_sha256"), str)
        or not _SHA256_RE.fullmatch(document["artifact_sha256"])
        or not isinstance(document.get("manifest_sha256"), str)
        or not _SHA256_RE.fullmatch(document["manifest_sha256"])
        or not isinstance(document.get("plist_sha256"), str)
        or not _SHA256_RE.fullmatch(document["plist_sha256"])
        or document.get("label") != BROKER_LABEL
    ):
        return False
    expected_version = _broker_version_path(
        root,
        artifact_digest=document["artifact_sha256"],
        manifest_digest=document["manifest_sha256"],
    )
    expected_paths = {
        "bundle_path": expected_version / "agent-collab-runtime.bundle",
        "entrypoint_path": expected_version
        / "agent-collab-runtime.bundle"
        / runtime_bundle.ENTRYPOINT_NAME,
        "manifest_path": expected_version / MANIFEST_NAME,
        "socket_path": root / BROKER_SOCKET_FILENAME,
    }
    for key, expected in expected_paths.items():
        if not isinstance(document.get(key), str) or document[key] != str(expected):
            return False
    previous = document.get("previous")
    if previous is not None:
        if not allow_previous or not isinstance(previous, dict):
            return False
        if not _broker_record_valid(
            previous,
            root,
            allow_previous=False,
            runtime_protocol_version=previous.get("runtime_protocol_version"),
        ):
            return False
    return True


def _load_broker_state(
    *,
    artifact_digest: str,
    manifest_digest: str,
    require_socket: bool,
) -> tuple[dict[str, Any] | None, RuntimeResult | None]:
    try:
        root = _broker_root()
    except ValueError:
        return None, RuntimeResult(RuntimeStatus.CONFIG_ERROR, error="provider broker configuration is unavailable")
    state_path = root / "state.json"
    try:
        root.lstat()
    except FileNotFoundError:
        return None, RuntimeResult(RuntimeStatus.UNAVAILABLE, error="provider broker is not installed")
    if _exact_mode(root, expected_type=stat.S_IFDIR, mode=0o700) is None:
        return None, RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="provider broker root identity is unsafe")
    try:
        state_path.lstat()
    except FileNotFoundError:
        return None, RuntimeResult(RuntimeStatus.UNAVAILABLE, error="provider broker is not installed")
    state_identity = _exact_mode(state_path, expected_type=stat.S_IFREG, mode=0o600)
    if state_identity is None or state_identity.st_size > BROKER_STATE_MAX_BYTES:
        return None, RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="provider broker state identity is unsafe")
    raw, opened_identity = _read_regular_nofollow(state_path, limit=BROKER_STATE_MAX_BYTES)
    if raw is None or opened_identity is None:
        return None, RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="provider broker state cannot be read safely")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_broker_json_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, RecursionError):
        return None, RuntimeResult(RuntimeStatus.CONFIG_ERROR, error="provider broker state is malformed")
    if not _broker_record_valid(document, root, allow_previous=True):
        return None, RuntimeResult(RuntimeStatus.CONFIG_ERROR, error="provider broker state contract mismatch")
    if (
        document["artifact_sha256"] != artifact_digest
        or document["manifest_sha256"] != manifest_digest
    ):
        return None, RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="provider broker digest does not match the verified runtime")
    try:
        _verify_published_version(
            root,
            artifact_digest=artifact_digest,
            manifest_digest=manifest_digest,
            role="selected",
            transport="broker",
            dispatcher_protocol_version=None,
        )
        _verify_plist_against_state(root, document)
    except (OSError, ValueError):
        return None, RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="provider broker installed identity could not be proven")
    if require_socket:
        socket_path = Path(document["socket_path"])
        if len(os.fsencode(socket_path)) > BROKER_SUN_PATH_MAX_BYTES:
            return None, RuntimeResult(RuntimeStatus.CONFIG_ERROR, error="provider broker socket path is too long")
        if _exact_mode(socket_path, expected_type=stat.S_IFSOCK, mode=0o600) is None:
            return None, RuntimeResult(RuntimeStatus.UNAVAILABLE, error="provider broker socket is unavailable")
    return dict(document), None


def _load_legacy_broker_lane(
    root: Path, *, role: str = "selected"
) -> BrokerLaneSnapshot | None:
    state = _read_current_broker_state(root)
    if state is None:
        return None
    _bundle, _runtime, _manifest, anchor = _verify_published_version(
        root,
        artifact_digest=state["artifact_sha256"],
        manifest_digest=state["manifest_sha256"],
        role=role,
        transport="broker",
        dispatcher_protocol_version=None,
    )
    if anchor is None:
        raise ValueError("committed legacy broker anchor is unavailable")
    _verify_plist_against_state(root, state)
    socket_path = root / BROKER_SOCKET_FILENAME
    if _exact_mode(socket_path, expected_type=stat.S_IFSOCK, mode=0o600) is None:
        raise ValueError("provider broker socket identity is unavailable")
    return BrokerLaneSnapshot(
        name=role,
        generation=0,
        artifact_digest=state["artifact_sha256"],
        manifest_digest=state["manifest_sha256"],
        label=BROKER_LABEL,
        socket_path=socket_path,
        transport="broker",
        protocol_version=BROKER_PROTOCOL_VERSION,
        anchor=anchor,
    )


def _load_lifecycle_blue_lane(root: Path) -> BrokerLaneSnapshot | None:
    """Verify an exact runtime-v1 blue solely for lifecycle control."""

    state = _read_lifecycle_blue_state(root)
    if state is None:
        return None
    _bundle, _runtime, _manifest, anchor = _verify_published_version(
        root,
        artifact_digest=state["artifact_sha256"],
        manifest_digest=state["manifest_sha256"],
        runtime_protocol_version=state["runtime_protocol_version"],
        role="lifecycle",
        transport="broker",
        dispatcher_protocol_version=None,
    )
    if anchor is not None:
        raise ValueError("legacy lifecycle runtime must not carry a normal anchor")
    _verify_plist_against_state(root, state)
    socket_path = root / BROKER_SOCKET_FILENAME
    if (
        not _job_loaded(BROKER_LABEL)
        or _exact_mode(socket_path, expected_type=stat.S_IFSOCK, mode=0o600)
        is None
    ):
        raise ValueError("legacy provider broker lifecycle identity is unavailable")
    return BrokerLaneSnapshot(
        name="blue",
        generation=0,
        artifact_digest=state["artifact_sha256"],
        manifest_digest=state["manifest_sha256"],
        label=BROKER_LABEL,
        socket_path=socket_path,
        transport="broker",
        protocol_version=LEGACY_BLUE_PROTOCOL_VERSION,
        anchor=None,
    )


def _load_dispatcher_broker_lane(
    root: Path,
    reference: Mapping[str, Any],
    generation: int,
    *,
    name: str = "candidate",
    protocol_version: int = DISPATCHER_PROTOCOL_VERSION,
    expected_anchor: RuntimeContractAnchor | None = None,
) -> BrokerLaneSnapshot:
    if not _broker_lane_reference_valid(reference):
        raise ValueError("provider dispatcher reference is invalid")
    lane = _dispatcher_lane_snapshot(
        root,
        artifact_digest=reference["artifact_sha256"],
        manifest_digest=reference["manifest_sha256"],
        generation=generation,
        name=name,
        protocol_version=protocol_version,
        anchor=expected_anchor,
    )
    state_path = _dispatcher_mutable_path(root, lane, "json")
    identity = _exact_mode(state_path, expected_type=stat.S_IFREG, mode=0o600)
    if identity is None or identity.st_size > BROKER_STATE_MAX_BYTES:
        raise ValueError("provider dispatcher state identity is unsafe")
    raw, opened = _read_regular_nofollow(state_path, limit=BROKER_STATE_MAX_BYTES)
    if raw is None or opened is None:
        raise ValueError("provider dispatcher state cannot be read safely")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_broker_json_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("provider dispatcher state is malformed") from exc
    if (
        not isinstance(document, dict)
        or set(document) != BROKER_DISPATCHER_STATE_KEYS
        or not _exact_int(document.get("schema_version"), 1)
        or not _exact_int(document.get("contract_version"), CONTRACT_VERSION)
        or not _exact_int(
            document.get("dispatcher_protocol_version"),
            protocol_version,
        )
        or not _exact_int(document.get("runtime_protocol_version"), PROTOCOL_VERSION)
        or document.get("artifact_sha256") != lane.artifact_digest
        or document.get("manifest_sha256") != lane.manifest_digest
        or not isinstance(document.get("plist_sha256"), str)
        or _SHA256_RE.fullmatch(document["plist_sha256"]) is None
    ):
        raise ValueError("provider dispatcher state contract mismatch")
    _bundle, runtime, _manifest, observed_anchor = _verify_published_version(
        root,
        artifact_digest=lane.artifact_digest,
        manifest_digest=lane.manifest_digest,
        role=name,
        dispatcher_protocol_version=protocol_version,
    )
    if expected_anchor is not None and observed_anchor != expected_anchor:
        raise ValueError("provider dispatcher contract anchor mismatch")
    if observed_anchor is None:
        raise ValueError("provider dispatcher contract anchor is unavailable")
    lane = replace(lane, anchor=observed_anchor)
    plist_path = _dispatcher_mutable_path(root, lane, "plist")
    plist_identity = _exact_mode(plist_path, expected_type=stat.S_IFREG, mode=0o600)
    plist_raw, _plist_opened = _read_regular_nofollow(
        plist_path, limit=1024 * 1024
    )
    if (
        plist_identity is None
        or plist_raw is None
        or hashlib.sha256(plist_raw).hexdigest() != document["plist_sha256"]
    ):
        raise ValueError("provider dispatcher plist identity mismatch")
    try:
        plist_document = plistlib.loads(plist_raw)
    except (plistlib.InvalidFileException, ValueError) as exc:
        raise ValueError("provider dispatcher plist is malformed") from exc
    home = _operator_home()
    if home is None:
        raise ValueError("operator home is unavailable")
    expected_plist = _broker_plist_document(
        runtime_path=runtime,
        socket_path=lane.socket_path,
        tmpdir=root / "tmp",
        home=Path(home),
        uid=os.getuid(),
        label=lane.label,
        dispatcher_protocol_version=lane.protocol_version,
    )
    if plist_document != expected_plist:
        raise ValueError("provider dispatcher plist contract mismatch")
    if _exact_mode(lane.socket_path, expected_type=stat.S_IFSOCK, mode=0o600) is None:
        raise ValueError("provider dispatcher socket identity is unavailable")
    return lane


def _capture_broker_lanes(
    resolution: RuntimeResolution,
    *,
    deadline: float | None = None,
) -> tuple[tuple[BrokerLaneSnapshot, ...], RuntimeResult | None]:
    if (
        not isinstance(resolution, RuntimeResolution)
        or not resolution.artifact_digest
        or not resolution.manifest_digest
    ):
        return (), RuntimeResult(
            RuntimeStatus.INTEGRITY_ERROR,
            error="verified runtime digests are unavailable",
        )
    try:
        root = _broker_root()
    except ValueError:
        return (), RuntimeResult(
            RuntimeStatus.CONFIG_ERROR,
            error="provider broker configuration is unavailable",
        )
    try:
        selector = _read_broker_selector_view(root)
        if selector is None:
            return (), RuntimeResult(
                RuntimeStatus.UNAVAILABLE, error="provider dispatcher is not installed"
            )
        lanes: list[BrokerLaneSnapshot] = []
        for role in ("selected", "retained"):
            document = selector.get(role)
            if document is not None:
                lane = _load_selector_v2_lane(root, document, role=role)
                if role == "retained" and not _job_loaded(
                    lane.label, deadline=deadline
                ):
                    continue
                lanes.append(lane)
        if not lanes:
            raise ValueError("provider dispatcher has no committed normal lane")
        return tuple(lanes), None
    except (OSError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError):
        return (), RuntimeResult(
            RuntimeStatus.INTEGRITY_ERROR,
            error="provider dispatcher committed lane identity could not be proven",
        )


def _broker_request_frame(
    *,
    request: Mapping[str, Any],
    artifact_digest: str,
    manifest_digest: str,
    timeout_ms: int,
    deadline_monotonic_ms: int | None = None,
) -> dict[str, Any]:
    if (
        not isinstance(request, dict)
        or not _SHA256_RE.fullmatch(artifact_digest)
        or not _SHA256_RE.fullmatch(manifest_digest)
        or not _exact_int(timeout_ms)
        or not 1 <= timeout_ms <= MAX_TIMEOUT_MS
        or (
            deadline_monotonic_ms is not None
            and (
                not _exact_int(deadline_monotonic_ms)
                or deadline_monotonic_ms <= 0
            )
        )
        or os.getpid() <= 1
    ):
        raise ValueError("invalid provider broker request")
    nonce = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
    return {
        "broker_protocol_version": BROKER_PROTOCOL_VERSION,
        "runtime_protocol_version": PROTOCOL_VERSION,
        "artifact_sha256": artifact_digest,
        "manifest_sha256": manifest_digest,
        "client_pid": os.getpid(),
        "nonce": nonce,
        "deadline_monotonic_ms": (
            int(time.monotonic() * 1000) + timeout_ms
            if deadline_monotonic_ms is None
            else deadline_monotonic_ms
        ),
        "request": dict(request),
    }


def _encode_broker_frame(document: object, *, max_bytes: int) -> bytes:
    if not isinstance(document, dict) or not _exact_int(max_bytes) or max_bytes <= 0:
        raise ValueError("invalid broker frame")
    try:
        payload = json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("invalid broker frame") from exc
    if len(payload) > max_bytes:
        raise OverflowError("broker frame exceeds limit")
    return _BROKER_HEADER.pack(len(payload)) + payload


def _recv_broker_exact(peer: socket.socket, count: int, deadline: float) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining:
        budget = deadline - time.monotonic()
        if budget <= 0:
            raise TimeoutError("provider broker deadline expired")
        peer.settimeout(budget)
        try:
            chunk = peer.recv(remaining)
        except socket.timeout as exc:
            raise TimeoutError("provider broker deadline expired") from exc
        if not chunk:
            raise ValueError("truncated broker frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _unique_broker_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("duplicate provider broker JSON key")
        document[key] = value
    return document


def _finite_broker_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite provider broker JSON number")
    return parsed


def _read_broker_frame(
    peer: socket.socket, *, max_bytes: int, deadline: float
) -> dict[str, Any]:
    if not _exact_int(max_bytes) or max_bytes <= 0 or not isinstance(deadline, (int, float)):
        raise ValueError("invalid broker frame reader")
    header = _recv_broker_exact(peer, _BROKER_HEADER.size, deadline)
    size = _BROKER_HEADER.unpack(header)[0]
    if size == 0:
        raise ValueError("empty broker frame")
    if size > max_bytes:
        raise OverflowError("broker frame exceeds limit")
    raw = _recv_broker_exact(peer, size, deadline)
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_broker_json_object,
            parse_float=_finite_broker_json_float,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("invalid broker response") from exc
    if not isinstance(document, dict):
        raise ValueError("invalid broker response")
    return document


def _parse_broker_response(
    document: dict[str, Any],
    envelope: object,
    anchor: RuntimeContractAnchor | None,
) -> RuntimeResult:
    status = document.get("status")
    local_mapping = {
        "config_error": RuntimeStatus.CONFIG_ERROR,
        "integrity_error": RuntimeStatus.INTEGRITY_ERROR,
        "peer_error": RuntimeStatus.INTEGRITY_ERROR,
        "replay_error": RuntimeStatus.INTEGRITY_ERROR,
        "protocol_error": RuntimeStatus.PROTOCOL_ERROR,
    }
    if status in local_mapping:
        if (
            set(document) != {"protocol_version", "request_id", "status", "error"}
            or not _exact_int(document.get("protocol_version"), PROTOCOL_VERSION)
            or document.get("request_id") != envelope.request_id
            or not isinstance(document.get("error"), str)
            or len(document["error"].encode("utf-8")) > 4096
        ):
            return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="provider broker failure contract mismatch")
        return RuntimeResult(local_mapping[status], error=document["error"])
    encoded = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return _parse_response(encoded, envelope, 0, anchor=anchor)


def _closed_dispatcher_bridge_response(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("provider dispatcher bridge response is invalid")
    body = raw[:-1] if raw.endswith(b"\n") else raw
    try:
        document = json.loads(
            body.decode("ascii"),
            object_pairs_hook=_unique_broker_json_object,
            parse_float=_finite_broker_json_float,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
        canonical = _dispatcher_canonical_json(document)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ValueError("provider dispatcher bridge response is malformed") from exc
    if type(document) is not dict or canonical != body:
        raise ValueError("provider dispatcher bridge response is noncanonical")
    return document


def _invoke_dispatcher_bridge(
    *,
    lane: BrokerLaneSnapshot,
    request: Mapping[str, Any],
    deadline: float,
    handshake_deadline: float,
) -> dict[str, Any]:
    try:
        now = time.monotonic()
        if (
            not isinstance(lane, BrokerLaneSnapshot)
            or lane.transport != "dispatcher"
            or lane.anchor is None
            or type(request) is not dict
            or isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or not math.isfinite(float(deadline))
            or isinstance(handshake_deadline, bool)
            or not isinstance(handshake_deadline, (int, float))
            or not math.isfinite(float(handshake_deadline))
            or handshake_deadline <= now
            or handshake_deadline > deadline
        ):
            raise ValueError("provider dispatcher bridge input is invalid")
        root = _broker_root()
        bundle, runtime, _manifest, observed_anchor = _verify_published_version(
            root,
            artifact_digest=lane.artifact_digest,
            manifest_digest=lane.manifest_digest,
            role=lane.name,
            dispatcher_protocol_version=lane.protocol_version,
        )
        if observed_anchor != lane.anchor:
            raise ValueError("provider dispatcher contract anchor mismatch")
        identity = _safe_file_identity(runtime, executable=True)
        if identity is None:
            raise ValueError("provider dispatcher bridge executable is unsafe")
        payload = _dispatcher_bridge_document(
            lane=lane,
            request=request,
            deadline_monotonic_ms=int(deadline * 1000),
            handshake_deadline_monotonic_ms=int(handshake_deadline * 1000),
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError) as exc:
        raise _DispatcherPreRequestError(
            "provider dispatcher bridge preflight failed"
        ) from exc

    command = [
        str(runtime),
        "dispatcher-client",
        "--protocol",
        str(lane.protocol_version),
    ]
    request_launched = False
    try:
        with _isolated_runtime_tmpdir() as runtime_tmpdir:
            with tempfile.TemporaryFile(dir=runtime_tmpdir) as stdin:
                stdin.write(payload)
                stdin.seek(0)
                if _safe_file_identity(runtime, executable=True) != identity:
                    raise _DispatcherPreRequestError(
                        "provider dispatcher bridge identity changed before launch"
                    )
                process = subprocess.Popen(
                    command,
                    stdin=stdin,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(bundle),
                    env=_scrubbed_env(tmpdir=runtime_tmpdir),
                    start_new_session=True,
                    close_fds=True,
                )
                request_launched = True
                remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
                out, err, collection_error = _collect_bounded_output(
                    process,
                    timeout_ms=remaining_ms,
                )
                if collection_error is not None:
                    raise _DispatcherPostRequestError(
                        "provider dispatcher bridge completion was unproven",
                        result=collection_error,
                    )
                returncode = process.returncode if process.returncode is not None else -1
                if err:
                    raise _DispatcherPostRequestError(
                        "provider dispatcher bridge emitted stderr"
                    )
                if returncode == 3 and not out:
                    raise _DispatcherPreRequestError(
                        "provider dispatcher bridge failed before request"
                    )
                if returncode != 0:
                    raise _DispatcherPostRequestError(
                        "provider dispatcher bridge failed after preflight"
                    )
                response = _closed_dispatcher_bridge_response(out)
                if _safe_file_identity(runtime, executable=True) != identity:
                    raise _DispatcherPostRequestError(
                        "provider dispatcher bridge identity changed after launch"
                    )
                _verify_published_version(
                    root,
                    artifact_digest=lane.artifact_digest,
                    manifest_digest=lane.manifest_digest,
                    role=lane.name,
                    dispatcher_protocol_version=lane.protocol_version,
                )
                return response
    except _DispatcherPreRequestError:
        raise
    except _DispatcherPostRequestError:
        raise
    except _RuntimeTempCleanupError as exc:
        raise _DispatcherPostRequestError(
            "provider dispatcher bridge cleanup was unproven"
        ) from exc
    except (OSError, PermissionError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        error = (
            _DispatcherPostRequestError
            if request_launched
            else _DispatcherPreRequestError
        )
        raise error(
            "provider dispatcher bridge failed after request launch"
            if request_launched
            else "provider dispatcher bridge could not start"
        ) from exc


def _launch_broker(
    *,
    resolution: RuntimeResolution,
    payload: bytes,
    timeout_ms: int,
    envelope: object,
) -> RuntimeResult:
    if not resolution.artifact_digest or not resolution.manifest_digest:
        return RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="verified runtime digests are unavailable")
    try:
        request = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="sealed broker request is invalid")
    # Start the request deadline BEFORE capturing lanes: the retained-lane
    # availability probe inside _capture_broker_lanes runs launchctl, and must
    # be bounded by this request's timeout rather than launchctl's independent
    # ~20s default (otherwise a small-timeout request could block ~20s before
    # dispatch even begins).
    started = time.monotonic()
    deadline = started + timeout_ms / 1000
    deadline_monotonic_ms = int(started * 1000) + timeout_ms
    lanes, error = _capture_broker_lanes(resolution, deadline=deadline)
    if error is not None or not lanes:
        return error or RuntimeResult(
            RuntimeStatus.UNAVAILABLE, error="provider broker is unavailable"
        )
    try:
        for index, lane in enumerate(lanes):
            if lane.transport == "dispatcher":
                now = time.monotonic()
                remaining = deadline - now
                if remaining <= 0:
                    raise TimeoutError("provider broker deadline expired")
                handshake_deadline = min(
                    deadline,
                    now + DISPATCHER_MAX_HANDSHAKE_SECONDS,
                )
                if index + 1 < len(lanes):
                    reserve = min(BROKER_FALLBACK_RESERVE_SECONDS, remaining / 2)
                    handshake_deadline = min(handshake_deadline, deadline - reserve)
                try:
                    response = _invoke_dispatcher_bridge(
                        lane=lane,
                        request=request,
                        deadline=deadline,
                        handshake_deadline=handshake_deadline,
                    )
                except _DispatcherPreRequestError:
                    if index + 1 < len(lanes):
                        continue
                    raise ValueError("provider dispatcher bridge preflight failed")
                except _DispatcherPostRequestError as exc:
                    if (
                        lane.protocol_version
                        == LEGACY_DISPATCHER_PROTOCOL_VERSION
                        and not _wait_for_job_idle(lane.label, deadline=deadline)
                    ):
                        return RuntimeResult(
                            RuntimeStatus.TEARDOWN_ERROR,
                            error="legacy provider dispatcher did not return idle",
                        )
                    if exc.result is not None:
                        return exc.result
                    raise ValueError(
                        "provider dispatcher failed after request acceptance"
                    ) from exc
                if (
                    lane.protocol_version == LEGACY_DISPATCHER_PROTOCOL_VERSION
                    and not _wait_for_job_idle(lane.label, deadline=deadline)
                ):
                    return RuntimeResult(
                        RuntimeStatus.TEARDOWN_ERROR,
                        error="legacy provider dispatcher did not return idle",
                    )
                return _parse_broker_response(response, envelope, lane.anchor)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("provider broker deadline expired")
                if index + 1 < len(lanes):
                    reserve = min(BROKER_FALLBACK_RESERVE_SECONDS, remaining / 2)
                    connect_budget = min(
                        BROKER_FALLBACK_CONNECT_TIMEOUT_SECONDS,
                        remaining - reserve,
                    )
                    if connect_budget <= 0:
                        continue
                else:
                    connect_budget = remaining
                peer.settimeout(connect_budget)
                try:
                    peer.connect(str(lane.socket_path))
                except OSError:
                    if index + 1 < len(lanes):
                        continue
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("provider broker deadline expired")
                peer.settimeout(remaining)
                frame = _broker_request_frame(
                    request=request,
                    artifact_digest=lane.artifact_digest,
                    manifest_digest=lane.manifest_digest,
                    timeout_ms=timeout_ms,
                    deadline_monotonic_ms=deadline_monotonic_ms,
                )
                encoded = _encode_broker_frame(
                    frame, max_bytes=BROKER_MAX_REQUEST_BYTES
                )
                peer.sendall(encoded)
                response = _read_broker_frame(
                    peer,
                    max_bytes=BROKER_MAX_RESPONSE_BYTES,
                    deadline=deadline,
                )
            return _parse_broker_response(response, envelope, lane.anchor)
        return RuntimeResult(
            RuntimeStatus.UNAVAILABLE, error="provider broker is unavailable"
        )
    except TimeoutError:
        return RuntimeResult(RuntimeStatus.TIMEOUT, error="provider broker deadline expired")
    except OverflowError:
        return RuntimeResult(RuntimeStatus.OUTPUT_LIMIT, error="provider broker frame exceeded the fixed limit")
    except PermissionError:
        return RuntimeResult(RuntimeStatus.HOST_BLOCKED, error="host blocked provider broker connection")
    except (ConnectionRefusedError, FileNotFoundError):
        return RuntimeResult(RuntimeStatus.UNAVAILABLE, error="provider broker is unavailable")
    except (OSError, TypeError, ValueError):
        return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="provider broker exchange failed")


def _broker_plist_document(
    *,
    runtime_path: Path,
    socket_path: Path,
    tmpdir: Path,
    home: Path,
    uid: int,
    label: str = BROKER_LABEL,
    dispatcher_protocol_version: int = DISPATCHER_PROTOCOL_VERSION,
) -> dict[str, Any]:
    if (
        not all(path.is_absolute() for path in (runtime_path, socket_path, tmpdir, home))
        or not _exact_int(uid)
        or uid < 0
        or not isinstance(label, str)
        or re.fullmatch(r"com\.agent-collab\.provider-(?:broker|dispatcher\.[0-9a-f]{32})", label)
        is None
        or len(os.fsencode(socket_path)) > BROKER_SUN_PATH_MAX_BYTES
        or dispatcher_protocol_version
        not in {LEGACY_DISPATCHER_PROTOCOL_VERSION, DISPATCHER_PROTOCOL_VERSION}
    ):
        raise ValueError("invalid provider broker plist input")
    runtime = str(runtime_path)
    dispatcher = label.startswith("com.agent-collab.provider-dispatcher.")
    subcommand = "dispatcher" if dispatcher else "broker"
    protocol = (
        dispatcher_protocol_version if dispatcher else BROKER_PROTOCOL_VERSION
    )
    return {
        "Label": label,
        "Program": runtime,
        "ProgramArguments": [runtime, subcommand, "--protocol", str(protocol)],
        "EnvironmentVariables": {
            "HOME": str(home),
            "TMPDIR": str(tmpdir),
            "PATH": BROKER_SYSTEM_PATH,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        },
        "ProcessType": "Background",
        "ThrottleInterval": 0,
        "Sockets": {
            BROKER_SOCKET_NAME: {
                "SockFamily": "Unix",
                "SockType": "stream",
                "SockPathName": str(socket_path),
                "SockPathOwner": uid,
                "SockPathMode": 0o600,
            }
        },
    }


def _ensure_private_directory(path: Path, *, mode: int) -> None:
    try:
        path.mkdir(mode=mode)
    except FileExistsError:
        pass
    if _exact_mode(path, expected_type=stat.S_IFDIR, mode=mode) is None:
        raise ValueError("unsafe provider broker directory")


def _ensure_broker_layout() -> Path:
    root = _broker_root()
    if len(os.fsencode(root / BROKER_SOCKET_FILENAME)) > BROKER_SUN_PATH_MAX_BYTES:
        raise ValueError("provider broker socket path is too long")
    parent = root.parent
    if not parent.exists():
        parent.mkdir(mode=0o700)
    parent_info = parent.lstat()
    if (
        not stat.S_ISDIR(parent_info.st_mode)
        or stat.S_ISLNK(parent_info.st_mode)
        or parent_info.st_uid != os.getuid()
        or stat.S_IMODE(parent_info.st_mode) & 0o022
    ):
        raise ValueError("unsafe provider broker parent")
    _ensure_private_directory(root, mode=0o700)
    for name in ("versions", "tmp", "replay"):
        _ensure_private_directory(root / name, mode=0o700)
    return root


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_private_atomic(path: Path, content: bytes, *, mode: int) -> None:
    derived_dispatcher = re.fullmatch(
        r"provider-dispatcher-[0-9a-f]{32}\.(?:json|plist)", path.name
    )
    if path.parent != _broker_root() or (
        path.name
        not in {
            "broker.plist",
            "state.json",
            BROKER_SELECTOR_FILENAME,
            BROKER_SELECTOR_V2_FILENAME,
        }
        and derived_dispatcher is None
    ):
        raise ValueError("unsafe provider broker write target")
    temporary = path.parent / "tmp" / f".{path.name}.{os.urandom(16).hex()}"
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        try:
            view = memoryview(content)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("provider broker write made no progress")
                view = view[written:]
            os.fsync(descriptor)
            os.fchmod(descriptor, mode)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        os.chmod(path, mode, follow_symlinks=False)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _unlink_private_durable(path: Path) -> None:
    derived_dispatcher = re.fullmatch(
        r"provider-dispatcher-[0-9a-f]{32}\.(?:json|plist|sock)", path.name
    )
    if path.parent != _broker_root() or (
        path.name
        not in {
            "broker.plist",
            "state.json",
            BROKER_SELECTOR_FILENAME,
            BROKER_SELECTOR_V2_FILENAME,
            BROKER_SOCKET_FILENAME,
        }
        and derived_dispatcher is None
    ):
        raise ValueError("unsafe provider broker unlink target")
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if info.st_uid != os.getuid() or stat.S_ISLNK(info.st_mode):
        raise ValueError("unsafe provider broker unlink identity")
    path.unlink()
    _fsync_directory(path.parent)


@contextmanager
def _broker_control_lock(root: Path) -> Iterator[None]:
    if _fcntl is None:
        raise ValueError("provider broker control locking is unavailable")
    if root != _broker_root() or _exact_mode(
        root, expected_type=stat.S_IFDIR, mode=0o700
    ) is None:
        raise ValueError("provider broker control root is unsafe")
    path = root / "control.lock"
    descriptor = os.open(
        path,
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ValueError("provider broker control lock is unsafe")
        _fcntl.flock(descriptor, _fcntl.LOCK_EX)
        yield
    finally:
        try:
            _fcntl.flock(descriptor, _fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


class _BrokerMutationFailure(RuntimeError):
    def __init__(self, *, restored_previous: bool) -> None:
        super().__init__("provider control mutation failed")
        self.restored_previous = restored_previous


@contextmanager
def _broker_control_transaction(
    root: Path, *, rollback: Callable[[], bool]
) -> Iterator[None]:
    """Run rollback before releasing the shared lifecycle-writer lock."""

    with _broker_control_lock(root):
        try:
            yield
        except (
            OSError,
            RuntimeError,
            subprocess.SubprocessError,
            TypeError,
            ValueError,
        ) as exc:
            try:
                restored = rollback()
            except (
                OSError,
                RuntimeError,
                subprocess.SubprocessError,
                TypeError,
                ValueError,
            ):
                restored = False
            raise _BrokerMutationFailure(restored_previous=restored) from exc


def _copy_regular_nofollow(source: Path, target: Path, *, limit: int, mode: int) -> None:
    raw, identity = _read_regular_nofollow(source, limit=limit)
    if raw is None or identity is None:
        raise ValueError("verified provider runtime source became unsafe")
    descriptor = os.open(
        target,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("provider broker copy made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, mode)
    finally:
        os.close(descriptor)


def _broker_version_path(
    root: Path, *, artifact_digest: str, manifest_digest: str
) -> Path:
    if (
        not isinstance(artifact_digest, str)
        or not _SHA256_RE.fullmatch(artifact_digest)
        or not isinstance(manifest_digest, str)
        or not _SHA256_RE.fullmatch(manifest_digest)
    ):
        raise ValueError("provider broker version identity is invalid")
    return root / "versions" / f"{artifact_digest}-{manifest_digest}"


def _verify_published_version(
    root: Path,
    *,
    artifact_digest: str,
    manifest_digest: str,
    runtime_protocol_version: int | None = None,
    role: str = "candidate",
    transport: str = "dispatcher",
    dispatcher_protocol_version: int | None = DISPATCHER_PROTOCOL_VERSION,
) -> tuple[Path, Path, Path, RuntimeContractAnchor | None]:
    version = _broker_version_path(
        root,
        artifact_digest=artifact_digest,
        manifest_digest=manifest_digest,
    )
    bundle = version / "agent-collab-runtime.bundle"
    entrypoint = bundle / runtime_bundle.ENTRYPOINT_NAME
    manifest = version / MANIFEST_NAME
    if _exact_mode(version, expected_type=stat.S_IFDIR, mode=0o500) is None:
        raise ValueError("provider broker version directory is unsafe")
    manifest_identity = _exact_mode(manifest, expected_type=stat.S_IFREG, mode=0o400)
    if manifest_identity is None:
        raise ValueError("provider broker version files are unsafe")
    raw_manifest, _identity = _read_regular_nofollow(manifest, limit=1024 * 1024)
    if raw_manifest is None or hashlib.sha256(raw_manifest).hexdigest() != manifest_digest:
        raise ValueError("provider broker version digest mismatch")
    try:
        document = runtime_bundle.load_closed_json_object(raw_manifest)
        entry, error = _manifest_entry(
            document,
            runtime_protocol_version=runtime_protocol_version,
            role=role,
            transport=transport,
            dispatcher_protocol_version=dispatcher_protocol_version,
        )
    except runtime_bundle.BundleContractError as exc:
        raise ValueError("provider broker manifest is invalid") from exc
    if entry is None or entry == {} or entry["sha256"] != artifact_digest:
        raise ValueError(error or "provider broker manifest identity mismatch")
    try:
        members = sorted(item.name for item in version.iterdir())
    except OSError as exc:
        raise ValueError("provider broker version cannot be enumerated") from exc
    if members != ["agent-collab-runtime.bundle", MANIFEST_NAME]:
        raise ValueError("provider broker version membership changed")
    by_name = {record["path"]: record for record in entry["_files"]}
    try:
        observed = runtime_bundle.verify_bundle_tree(
            bundle,
            entry["_files"],
            inspector=lambda member: _inspect_runtime_member(
                member,
                by_name[member.name],
                signing=entry["signing"],
            ),
        )
    except runtime_bundle.BundleContractError as exc:
        raise ValueError("provider broker bundle identity mismatch") from exc
    if observed != artifact_digest or _safe_file_identity(entrypoint, executable=True) is None:
        raise ValueError("provider broker bundle identity mismatch")
    return bundle, entrypoint, manifest, entry["_anchor"]


def _publish_broker_version(
    root: Path,
    *,
    resolution: RuntimeResolution,
    role: str = "candidate",
    transport: str = "dispatcher",
    dispatcher_protocol_version: int | None = DISPATCHER_PROTOCOL_VERSION,
) -> tuple[Path, Path, Path, RuntimeContractAnchor | None]:
    if (
        resolution.path is None
        or resolution.bundle_path is None
        or resolution.identity is None
        or not resolution.files
    ):
        raise ValueError("verified provider runtime is unavailable")
    if _safe_file_identity(resolution.path, executable=True) != resolution.identity:
        raise ValueError("verified provider runtime identity changed")
    version = _broker_version_path(
        root,
        artifact_digest=resolution.artifact_digest,
        manifest_digest=resolution.manifest_digest,
    )
    if version.exists():
        return _verify_published_version(
            root,
            artifact_digest=resolution.artifact_digest,
            manifest_digest=resolution.manifest_digest,
            role=role,
            transport=transport,
            dispatcher_protocol_version=dispatcher_protocol_version,
        )
    staging = root / "tmp" / f"version-{resolution.artifact_digest}-{os.urandom(8).hex()}"
    staging.mkdir(mode=0o700)
    try:
        staged_bundle = staging / "agent-collab-runtime.bundle"
        staged_bundle.mkdir(mode=0o700)
        for record in resolution.files:
            _copy_regular_nofollow(
                resolution.bundle_path / record["path"],
                staged_bundle / record["path"],
                limit=MAX_ARTIFACT_BYTES,
                mode=runtime_bundle.INSTALL_MODE,
            )
        _fsync_directory(staged_bundle)
        os.chmod(staged_bundle, runtime_bundle.INSTALL_MODE)
        _copy_regular_nofollow(
            PLUGIN_ROOT / MANIFEST_NAME,
            staging / MANIFEST_NAME,
            limit=1024 * 1024,
            mode=0o400,
        )
        _fsync_directory(staging)
        os.rename(staging, version)
        os.chmod(version, 0o500)
        _fsync_directory(root / "versions")
    except BaseException:
        if staging.exists():
            os.chmod(staging, 0o700)
            for child in staging.iterdir():
                if child.is_dir() and not child.is_symlink():
                    child.chmod(0o700)
                    for member in child.iterdir():
                        member.unlink()
                    child.rmdir()
                else:
                    child.unlink()
            staging.rmdir()
        raise
    return _verify_published_version(
        root,
        artifact_digest=resolution.artifact_digest,
        manifest_digest=resolution.manifest_digest,
        role=role,
        transport=transport,
        dispatcher_protocol_version=dispatcher_protocol_version,
    )


def _plist_bytes(document: Mapping[str, Any]) -> bytes:
    raw = plistlib.dumps(dict(document), fmt=plistlib.FMT_XML, sort_keys=True)
    if plistlib.loads(raw) != dict(document):
        raise ValueError("provider broker plist roundtrip failed")
    return raw


def _state_bytes(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(document),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _selector_bytes(document: Mapping[str, Any]) -> bytes:
    value = dict(document)
    if not _broker_selector_valid(value):
        raise ValueError("provider broker selector contract mismatch")
    raw = _state_bytes(value)
    try:
        roundtrip = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_unique_broker_json_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("provider broker selector roundtrip failed") from exc
    if roundtrip != value:
        raise ValueError("provider broker selector roundtrip failed")
    return raw


def _selector_v2_bytes(document: Mapping[str, Any]) -> bytes:
    value = dict(document)
    if not _broker_selector_v2_valid(value):
        raise ValueError("provider broker selector-v2 contract mismatch")
    return _state_bytes(value)


def _read_selector_snapshot(root: Path) -> tuple[dict[str, Any] | None, bytes | None]:
    selector = _read_broker_selector(root)
    if selector is None:
        return None, None
    path = root / BROKER_SELECTOR_FILENAME
    raw, identity = _read_regular_nofollow(path, limit=BROKER_SELECTOR_MAX_BYTES)
    if raw is None or identity is None or json.loads(raw) != selector:
        raise ValueError("provider broker selector snapshot is unproven")
    return selector, raw


def _read_selector_v2_snapshot(
    root: Path,
) -> tuple[dict[str, Any] | None, bytes | None]:
    selector = _read_broker_selector_v2(root)
    if selector is None:
        return None, None
    path = root / BROKER_SELECTOR_V2_FILENAME
    raw, identity = _read_regular_nofollow(path, limit=BROKER_SELECTOR_MAX_BYTES)
    if raw is None or identity is None or json.loads(raw) != selector:
        raise ValueError("provider broker selector-v2 snapshot is unproven")
    return selector, raw


def _restore_selector_snapshot(root: Path, raw: bytes | None) -> bool:
    try:
        if raw is None:
            _unlink_private_durable(root / BROKER_SELECTOR_FILENAME)
        else:
            document = json.loads(
                raw.decode("ascii"),
                object_pairs_hook=_unique_broker_json_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            )
            if not _broker_selector_valid(document):
                raise ValueError("provider broker selector restore is invalid")
            _write_private_atomic(
                root / BROKER_SELECTOR_FILENAME, raw, mode=0o600
            )
        _observed, observed_raw = _read_selector_snapshot(root)
        return observed_raw == raw
    except (OSError, TypeError, ValueError, RecursionError):
        return False


def _restore_selector_v2_snapshot(root: Path, raw: bytes | None) -> bool:
    try:
        path = root / BROKER_SELECTOR_V2_FILENAME
        if raw is None:
            _unlink_private_durable(path)
        else:
            document = json.loads(
                raw.decode("ascii"),
                object_pairs_hook=_unique_broker_json_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
            )
            if not _broker_selector_v2_valid(document):
                raise ValueError("provider broker selector-v2 restore is invalid")
            _write_private_atomic(path, raw, mode=0o600)
        _observed, observed_raw = _read_selector_v2_snapshot(root)
        return observed_raw == raw
    except (OSError, TypeError, ValueError, RecursionError):
        return False


def _snapshot_private_mutable(path: Path, *, limit: int) -> bytes | None:
    """Capture an absent or exact private regular file before a locked rewrite."""

    try:
        path.lstat()
    except FileNotFoundError:
        return None
    if _exact_mode(path, expected_type=stat.S_IFREG, mode=0o600) is None:
        raise ValueError("provider mutable control identity is unsafe")
    raw, opened = _read_regular_nofollow(path, limit=limit)
    if raw is None or opened is None:
        raise ValueError("provider mutable control snapshot is unavailable")
    return raw


def _restore_private_mutable(path: Path, raw: bytes | None, *, limit: int) -> bool:
    """Restore a locked mutable-file snapshot and prove the exact result."""

    try:
        if raw is None:
            _unlink_private_durable(path)
        else:
            _write_private_atomic(path, raw, mode=0o600)
        return _snapshot_private_mutable(path, limit=limit) == raw
    except (OSError, TypeError, ValueError):
        return False


def _preserved_broker_previous(
    raw: bytes | None,
    root: Path,
    reference: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Retain rollback metadata only from the selected valid broker record."""

    if raw is None:
        return None
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_broker_json_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, RecursionError):
        return None
    if (
        not _broker_record_valid(
            document,
            root,
            allow_previous=True,
            runtime_protocol_version=PROTOCOL_VERSION,
        )
        or document.get("artifact_sha256") != reference.get("artifact_sha256")
        or document.get("manifest_sha256") != reference.get("manifest_sha256")
    ):
        return None
    previous = document.get("previous")
    return None if previous is None else dict(previous)


def _dispatcher_state_document(
    *,
    artifact_digest: str,
    manifest_digest: str,
    plist_digest: str,
    dispatcher_protocol_version: int = DISPATCHER_PROTOCOL_VERSION,
) -> dict[str, Any]:
    document = {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "dispatcher_protocol_version": dispatcher_protocol_version,
        "runtime_protocol_version": PROTOCOL_VERSION,
        "artifact_sha256": artifact_digest,
        "manifest_sha256": manifest_digest,
        "plist_sha256": plist_digest,
    }
    if (
        not _broker_lane_reference_valid(
            {
                "artifact_sha256": artifact_digest,
                "manifest_sha256": manifest_digest,
            }
        )
        or not isinstance(plist_digest, str)
        or _SHA256_RE.fullmatch(plist_digest) is None
        or dispatcher_protocol_version
        not in {LEGACY_DISPATCHER_PROTOCOL_VERSION, DISPATCHER_PROTOCOL_VERSION}
    ):
        raise ValueError("provider dispatcher state identity is invalid")
    return document


def _blue_reference(state: Mapping[str, Any]) -> dict[str, str]:
    reference = {
        "artifact_sha256": state.get("artifact_sha256"),
        "manifest_sha256": state.get("manifest_sha256"),
    }
    if not _broker_lane_reference_valid(reference):
        raise ValueError("legacy provider broker reference is invalid")
    return dict(reference)


def _read_current_broker_state(
    root: Path, *, runtime_protocol_version: int | None = None
) -> dict[str, Any] | None:
    try:
        root.lstat()
    except FileNotFoundError:
        return None
    if _exact_mode(root, expected_type=stat.S_IFDIR, mode=0o700) is None:
        raise ValueError("provider broker root identity is unsafe")
    state_path = root / "state.json"
    if not state_path.exists():
        return None
    if _exact_mode(state_path, expected_type=stat.S_IFREG, mode=0o600) is None:
        raise ValueError("provider broker state identity is unsafe")
    raw, _identity = _read_regular_nofollow(state_path, limit=BROKER_STATE_MAX_BYTES)
    if raw is None:
        raise ValueError("provider broker state cannot be read safely")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_broker_json_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("provider broker state is malformed") from exc
    if not _broker_record_valid(
        document,
        root,
        allow_previous=True,
        runtime_protocol_version=runtime_protocol_version,
    ):
        raise ValueError("provider broker state contract mismatch")
    return dict(document)


def _read_lifecycle_blue_state(root: Path) -> dict[str, Any] | None:
    """Read only the closed runtime-v1 lifecycle broker."""

    return _read_current_broker_state(
        root, runtime_protocol_version=LEGACY_BLUE_PROTOCOL_VERSION
    )


def _without_previous(document: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(document)
    result["previous"] = None
    return result


def _launchctl(
    arguments: list[str],
    *,
    timeout: int | float = 20,
    deadline: float | None = None,
) -> subprocess.CompletedProcess[str]:
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or timeout <= 0
    ):
        raise ValueError("launchctl timeout is invalid")
    timeout_ms: int | float = timeout * 1000
    if deadline is not None:
        if (
            isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or not math.isfinite(float(deadline))
        ):
            raise ValueError("launchctl deadline is invalid")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("launchctl deadline expired")
        timeout_ms = min(timeout_ms, remaining * 1000)
    home = _operator_home()
    if home is None:
        raise _OperatorHomeUnavailable("operator home is unavailable")
    command = ["/bin/launchctl", *arguments]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/",
        env={
            "HOME": home,
            "PATH": BROKER_SYSTEM_PATH,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        },
        start_new_session=True,
        close_fds=True,
    )
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _terminate_and_reap(process, deadline=deadline)
            raise RuntimeError("launchctl deadline expired")
        timeout_ms = min(timeout_ms, remaining * 1000)
    out, err, collection_error = _collect_bounded_output(
        process, timeout_ms=timeout_ms
    )
    if collection_error is not None:
        raise RuntimeError(collection_error.error)
    return subprocess.CompletedProcess(
        command,
        process.returncode if process.returncode is not None else -1,
        out.decode("utf-8", errors="replace"),
        err.decode("utf-8", errors="replace"),
    )


def _bootout_broker(plist_path: Path) -> bool:
    result = _launchctl(["bootout", f"gui/{os.getuid()}", str(plist_path)])
    if result.returncode == 0:
        return True
    detail = (result.stdout + result.stderr).casefold()
    return any(
        marker in detail
        for marker in ("could not find service", "no such process", "not found")
    )


def _bootstrap_broker(plist_path: Path) -> bool:
    return _launchctl(
        ["bootstrap", f"gui/{os.getuid()}", str(plist_path)]
    ).returncode == 0


def _job_loaded(label: str, *, deadline: float | None = None) -> bool:
    if not isinstance(label, str) or _JOB_LABEL_RE.fullmatch(label) is None:
        raise ValueError("provider job label is invalid")
    # deadline bounds the probe on the request-dispatch path so a small-timeout
    # request cannot block launchctl's independent default before dispatch;
    # lifecycle/status callers pass None and keep the default bound.
    return _launchctl(
        ["print", f"gui/{os.getuid()}/{label}"], deadline=deadline
    ).returncode == 0


def _broker_job_loaded() -> bool:
    return _job_loaded(BROKER_LABEL)


# The activation liveness knock must outlast the signed runtime's cold start.
# A freshly published bundle (new digest directory, non-page-cached files)
# cold-starts in 6-12s on first exec -- Gatekeeper/codesign validation plus
# interpreter init for a ~20MB standalone bundle (unified-log evidence:
# first-activation broker runs of 6302ms-12111ms; warm runs ~1.4s). A 5s
# budget made the first activation after every fresh publish spuriously fail
# ("activation ping failed") and fall through to the restore path, which
# skips the ping and so silently masked the miscalibration.
BROKER_COLD_START_TIMEOUT_SECONDS = 30.0
# Upper bound on how long teardown may poll to reap a SIGKILLed leader when no
# caller deadline is supplied (preserves the pre-existing wait bound). When a
# deadline is supplied, teardown polls at most REAP_GRACE_SECONDS past it.
REAP_BOUND_SECONDS = 5.0
# Minimal grace for a just-posted SIGKILL to be delivered and the leader
# reaped, even when the caller deadline is already expired. Small enough that
# the worst-case deadline overrun is a fraction of a second (not the old ~10s),
# large enough that an ordinary killable process is not mistyped as a teardown
# failure.
REAP_GRACE_SECONDS = 0.25


def _broker_ping(socket_path: Path) -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(BROKER_COLD_START_TIMEOUT_SECONDS)
            peer.connect(str(socket_path))
            # Hold the connection open through the broker's peer-identity
            # observation, then half-close the write side so the broker's
            # frame read returns end-of-stream promptly and it exits. A bare
            # connect-and-close races socket activation: the peer can be gone
            # before the broker reads LOCAL_PEERPID (ENOTCONN -> peer_error),
            # and the broker would otherwise block in accept() for its full
            # timeout instead of servicing this liveness knock.
            peer.shutdown(socket.SHUT_WR)
            try:
                peer.recv(1)
            except OSError:
                pass
        return _wait_for_broker_exit()
    except OSError:
        return False


def _job_process_idle(label: str, *, deadline: float | None = None) -> bool:
    if not isinstance(label, str) or _JOB_LABEL_RE.fullmatch(label) is None:
        raise ValueError("provider job label is invalid")
    arguments = ["print", f"gui/{os.getuid()}/{label}"]
    result = (
        _launchctl(arguments)
        if deadline is None
        else _launchctl(arguments, deadline=deadline)
    )
    if result.returncode != 0:
        return False
    # launchctl prints a `state = active` line for each listening socket
    # endpoint (always active while the job is bootstrapped). Those are not
    # the job's lifecycle state; including them made the terminal-state check
    # below never hold, so the activation ping never observed the broker exit.
    states = [
        line.split("=", 1)[1].strip().casefold()
        for line in result.stdout.splitlines()
        if line.strip().startswith("state =")
        and line.split("=", 1)[1].strip().casefold() != "active"
    ]
    has_live_pid = any(
        line.strip().startswith("pid =")
        and line.split("=", 1)[1].strip().isdigit()
        and int(line.split("=", 1)[1].strip()) > 0
        for line in result.stdout.splitlines()
    )
    return bool(states) and not has_live_pid and all(
        state in {"not running", "exited"} for state in states
    )


def _broker_process_idle() -> bool:
    return _job_process_idle(BROKER_LABEL)


def _wait_for_job_idle(label: str, *, deadline: float | None = None) -> bool:
    if deadline is None:
        deadline = time.monotonic() + BROKER_COLD_START_TIMEOUT_SECONDS
    elif (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(float(deadline))
    ):
        raise ValueError("provider job idle deadline is invalid")
    # Validate the label at entry (hoisted out of the probe loop): an invalid
    # label is a caller bug and must raise, not be swallowed by the fail-closed
    # loop below. _JOB_LABEL_RE mirrors the check inside _job_process_idle.
    if not isinstance(label, str) or _JOB_LABEL_RE.fullmatch(label) is None:
        raise ValueError("provider job label is invalid")
    # Pre-check operator-home once as an early-out for the common
    # not-yet-configured case.
    if _operator_home() is None:
        return False
    while True:
        if time.monotonic() >= deadline:
            return False
        try:
            idle = _job_process_idle(label, deadline=deadline)
        except (
            OSError,
            RuntimeError,
            subprocess.SubprocessError,
            _OperatorHomeUnavailable,
        ):
            # An accepted-request idle probe that cannot be completed is a
            # failed idle proof -> not idle. The accepted-request boundary then
            # types this as TEARDOWN_ERROR, not PROTOCOL_ERROR. This covers a
            # launchctl spawn failure, deadline expiry, subprocess error, and
            # (via the typed _OperatorHomeUnavailable) _launchctl's per-call
            # operator-home re-resolution failing after the entry pre-check —
            # without a racy re-check. A plain ValueError (a genuine code bug;
            # label is pre-validated and timeout/deadline are fixed/pre-checked)
            # is deliberately NOT caught and still surfaces.
            return False
        if idle:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(max(0.0, min(0.05, remaining)))


def _wait_for_broker_exit() -> bool:
    # Success returns as soon as the job reaches a terminal state; the
    # cold-start budget only bounds the failure case (see the constant above).
    deadline = time.monotonic() + BROKER_COLD_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _broker_process_idle():
            return True
        time.sleep(0.05)
    return False


def _record_for(
    *,
    root: Path,
    artifact_digest: str,
    manifest_digest: str,
    plist_digest: str,
    previous: Mapping[str, Any] | None,
    runtime_protocol_version: int | None = None,
) -> dict[str, Any]:
    recorded_protocol = (
        PROTOCOL_VERSION
        if runtime_protocol_version is None
        else runtime_protocol_version
    )
    if (
        not _exact_int(recorded_protocol)
        or recorded_protocol not in LIFECYCLE_BLUE_PROTOCOL_VERSIONS
    ):
        raise ValueError("provider broker runtime protocol is invalid")
    version = _broker_version_path(
        root,
        artifact_digest=artifact_digest,
        manifest_digest=manifest_digest,
    )
    return {
        "schema_version": 2,
        "contract_version": CONTRACT_VERSION,
        "broker_protocol_version": BROKER_PROTOCOL_VERSION,
        "runtime_protocol_version": recorded_protocol,
        "artifact_sha256": artifact_digest,
        "manifest_sha256": manifest_digest,
        "bundle_path": str(version / "agent-collab-runtime.bundle"),
        "entrypoint_path": str(
            version / "agent-collab-runtime.bundle" / runtime_bundle.ENTRYPOINT_NAME
        ),
        "manifest_path": str(version / MANIFEST_NAME),
        "plist_sha256": plist_digest,
        "socket_path": str(root / BROKER_SOCKET_FILENAME),
        "label": BROKER_LABEL,
        "previous": None if previous is None else _without_previous(previous),
    }


def _verify_plist_against_state(root: Path, state: Mapping[str, Any]) -> None:
    plist_path = root / "broker.plist"
    identity = _exact_mode(plist_path, expected_type=stat.S_IFREG, mode=0o600)
    raw, _opened = _read_regular_nofollow(plist_path, limit=1024 * 1024)
    if identity is None or raw is None or hashlib.sha256(raw).hexdigest() != state["plist_sha256"]:
        raise ValueError("provider broker plist identity mismatch")
    try:
        document = plistlib.loads(raw)
    except (plistlib.InvalidFileException, ValueError) as exc:
        raise ValueError("provider broker plist is malformed") from exc
    expected = _broker_plist_document(
        runtime_path=Path(state["entrypoint_path"]),
        socket_path=root / BROKER_SOCKET_FILENAME,
        tmpdir=root / "tmp",
        home=Path(_operator_home() or ""),
        uid=os.getuid(),
    )
    if document != expected:
        raise ValueError("provider broker plist contract mismatch")


def _sandbox_denies_broker_lifecycle() -> bool:
    """Ask the Darwin kernel policy whether this process can reach launchd.

    The environment marker remains a fast, explicit signal, but it is not an
    authority boundary: descendants can delete environment variables while
    retaining the parent's Seatbelt profile.  The kernel query survives that
    deletion.  Fail closed on Darwin when the policy cannot be queried.
    """

    if platform.system().lower() != "darwin":
        return False
    try:
        sandbox = ctypes.CDLL("/usr/lib/libsandbox.1.dylib", use_errno=True)
        check = sandbox.sandbox_check
        check.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        check.restype = ctypes.c_int
        no_report = ctypes.c_int.in_dll(
            sandbox, "SANDBOX_CHECK_NO_REPORT"
        ).value
        # SANDBOX_FILTER_GLOBAL_NAME is 2 in Darwin's sandbox interface.
        result = check(
            os.getpid(),
            b"mach-lookup",
            2 | no_report,
            ctypes.c_char_p(b"com.apple.xpc.launchd"),
        )
    except (AttributeError, OSError, TypeError, ValueError, ctypes.ArgumentError):
        return True
    return result != 0


def _broker_lifecycle_seatbelt_block() -> RuntimeResult | None:
    if (
        os.environ.get("CODEX_SANDBOX") != "seatbelt"
        and not _sandbox_denies_broker_lifecycle()
    ):
        return None
    return RuntimeResult(
        RuntimeStatus.HOST_BLOCKED,
        error="broker lifecycle is unavailable from the Codex seatbelt",
    )


def _prove_legacy_blue(root: Path) -> dict[str, Any]:
    state = _read_lifecycle_blue_state(root)
    if state is None:
        raise ValueError("legacy provider broker is unavailable")
    _verify_published_version(
        root,
        artifact_digest=state["artifact_sha256"],
        manifest_digest=state["manifest_sha256"],
        runtime_protocol_version=state["runtime_protocol_version"],
        role="lifecycle",
        transport="broker",
        dispatcher_protocol_version=None,
    )
    _verify_plist_against_state(root, state)
    if not _job_loaded(BROKER_LABEL):
        raise ValueError("legacy provider broker job is unavailable")
    if _exact_mode(
        root / BROKER_SOCKET_FILENAME, expected_type=stat.S_IFSOCK, mode=0o600
    ) is None:
        raise ValueError("legacy provider broker socket is unavailable")
    return state


def _dispatcher_ping_response(
    response: object,
    *,
    request_id: str,
    dispatcher_protocol_version: int = DISPATCHER_PROTOCOL_VERSION,
) -> RuntimeResult:
    if (
        dispatcher_protocol_version
        not in {
            LEGACY_DISPATCHER_PROTOCOL_VERSION,
            DISPATCHER_PROTOCOL_VERSION,
        }
        or not isinstance(response, dict)
        or response.get("request_id") != request_id
    ):
        return RuntimeResult(
            RuntimeStatus.PROTOCOL_ERROR,
            error="provider dispatcher ping response was rejected",
        )
    if response.get("status") != "ok":
        status_value = response.get("status")
        error = response.get("error")
        try:
            status = RuntimeStatus(status_value)
        except (TypeError, ValueError):
            status = RuntimeStatus.PROTOCOL_ERROR
        if (
            set(response) != {"protocol_version", "request_id", "status", "error"}
            or response.get("protocol_version") != PROTOCOL_VERSION
            or type(error) is not str
            or not error
        ):
            return RuntimeResult(
                RuntimeStatus.PROTOCOL_ERROR,
                error="provider dispatcher ping failure was rejected",
            )
        return RuntimeResult(status, error=error)
    if (
        set(response)
        != {"protocol_version", "request_id", "status", "result", "provenance"}
        or response.get("protocol_version") != dispatcher_protocol_version
        or response.get("result") != {"ready": True}
        or response.get("provenance") != {"operation": "dispatcher_ping"}
    ):
        return RuntimeResult(
            RuntimeStatus.PROTOCOL_ERROR,
            error="provider dispatcher ping success was rejected",
        )
    return RuntimeResult(
        RuntimeStatus.OK,
        result={"ready": True},
        provenance={"operation": "dispatcher_ping"},
    )


def invoke_dispatcher_ping(
    *,
    timeout_ms: int = 30_000,
    lane: BrokerLaneSnapshot | None = None,
) -> RuntimeResult:
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= MAX_TIMEOUT_MS:
        return RuntimeResult(
            RuntimeStatus.CONFIG_ERROR,
            error="provider dispatcher ping timeout is invalid",
        )
    try:
        root = _broker_root()
        if lane is None:
            selector = _read_broker_selector_view(root)
            if selector is None:
                return RuntimeResult(
                    RuntimeStatus.UNAVAILABLE,
                    error="provider dispatcher is unavailable",
                )
            role = "candidate" if selector.get("candidate") is not None else "selected"
            selected = selector.get(role)
            if selected is None:
                return RuntimeResult(
                    RuntimeStatus.UNAVAILABLE,
                    error="provider dispatcher is unavailable",
                )
            lane = _load_selector_v2_lane(root, selected, role=role)
        request_id = "dispatcher-ping-" + os.urandom(16).hex()
        request = {
            "protocol_version": lane.protocol_version,
            "request_id": request_id,
            "operation": "dispatcher_ping",
            "timeout_ms": timeout_ms,
            "host_context": classify_host_context(),
        }
        deadline = time.monotonic() + timeout_ms / 1000.0
        response = _invoke_dispatcher_bridge(
            lane=lane,
            request=request,
            deadline=deadline,
            handshake_deadline=min(
                deadline, time.monotonic() + DISPATCHER_MAX_HANDSHAKE_SECONDS
            ),
        )
        return _dispatcher_ping_response(
            response,
            request_id=request_id,
            dispatcher_protocol_version=lane.protocol_version,
        )
    except _DispatcherPreRequestError:
        return RuntimeResult(
            RuntimeStatus.INTEGRITY_ERROR,
            error="staged provider dispatcher ping bridge is unproven",
        )
    except _DispatcherPostRequestError as exc:
        if exc.result is not None:
            return exc.result
        return RuntimeResult(
            RuntimeStatus.PROTOCOL_ERROR,
            error="staged provider dispatcher ping completion is unproven",
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError):
        return RuntimeResult(
            RuntimeStatus.INTEGRITY_ERROR,
            error="staged provider dispatcher ping identity is unproven",
        )


def _dispatcher_lock_probe_response(
    response: object, *, request_id: str, provider: str
) -> RuntimeResult:
    if not isinstance(response, dict) or response.get("request_id") != request_id:
        return RuntimeResult(
            RuntimeStatus.PROTOCOL_ERROR,
            error="provider dispatcher lock probe response was rejected",
        )
    if response.get("status") != "ok":
        status_value = response.get("status")
        error = response.get("error")
        try:
            status = RuntimeStatus(status_value)
        except (TypeError, ValueError):
            status = RuntimeStatus.PROTOCOL_ERROR
        if (
            set(response) != {"protocol_version", "request_id", "status", "error"}
            or response.get("protocol_version") != PROTOCOL_VERSION
            or type(error) is not str
            or not error
        ):
            return RuntimeResult(
                RuntimeStatus.PROTOCOL_ERROR,
                error="provider dispatcher lock probe failure was rejected",
            )
        return RuntimeResult(status, error=error)
    result = response.get("result")
    provenance = response.get("provenance")
    if (
        set(response)
        != {"protocol_version", "request_id", "status", "result", "provenance"}
        or response.get("protocol_version") != DISPATCHER_PROTOCOL_VERSION
        or result
        != {
            "provider": provider,
            "lock_acquired": True,
            "namespace": "legacy-compatible-v1",
        }
        or provenance != {"operation": "dispatcher_lock_probe"}
    ):
        return RuntimeResult(
            RuntimeStatus.PROTOCOL_ERROR,
            error="provider dispatcher lock probe success was rejected",
        )
    return RuntimeResult(
        RuntimeStatus.OK,
        result=dict(result),
        provenance=dict(provenance),
    )


def invoke_dispatcher_lock_probe(
    *, provider: str, timeout_ms: int = 5_000
) -> RuntimeResult:
    if (
        provider not in {"gemini", "grok", "opencode"}
        or type(timeout_ms) is not int
        or not 1 <= timeout_ms <= MAX_TIMEOUT_MS
    ):
        return RuntimeResult(
            RuntimeStatus.CONFIG_ERROR,
            error="provider dispatcher lock probe input is invalid",
        )
    try:
        root = _broker_root()
        selector = _read_broker_selector_v2(root)
        if selector is None or selector.get("candidate") is None:
            return RuntimeResult(
                RuntimeStatus.UNAVAILABLE,
                error="staged provider dispatcher is unavailable",
            )
        lane = _load_selector_v2_lane(
            root, selector["candidate"], role="candidate"
        )
        request_id = "dispatcher-lock-probe-" + os.urandom(16).hex()
        request = {
            "protocol_version": DISPATCHER_PROTOCOL_VERSION,
            "request_id": request_id,
            "operation": "dispatcher_lock_probe",
            "provider": provider,
            "timeout_ms": timeout_ms,
            "host_context": classify_host_context(),
        }
        deadline = time.monotonic() + timeout_ms / 1000.0
        response = _invoke_dispatcher_bridge(
            lane=lane,
            request=request,
            deadline=deadline,
            handshake_deadline=min(
                deadline, time.monotonic() + DISPATCHER_MAX_HANDSHAKE_SECONDS
            ),
        )
        return _dispatcher_lock_probe_response(
            response, request_id=request_id, provider=provider
        )
    except _DispatcherPreRequestError:
        return RuntimeResult(
            RuntimeStatus.INTEGRITY_ERROR,
            error="staged provider dispatcher lock probe bridge is unproven",
        )
    except _DispatcherPostRequestError as exc:
        if exc.result is not None:
            return exc.result
        return RuntimeResult(
            RuntimeStatus.PROTOCOL_ERROR,
            error="staged provider dispatcher lock probe completion is unproven",
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError):
        return RuntimeResult(
            RuntimeStatus.INTEGRITY_ERROR,
            error="staged provider dispatcher lock probe identity is unproven",
        )


def _cleanup_dispatcher_candidate(root: Path, lane: BrokerLaneSnapshot) -> bool:
    cleaned = True
    plist_path = _dispatcher_mutable_path(root, lane, "plist")
    try:
        if not _bootout_broker(plist_path):
            cleaned = False
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
        cleaned = False
    for path in (
        lane.socket_path,
        _dispatcher_mutable_path(root, lane, "json"),
        plist_path,
    ):
        try:
            _unlink_private_durable(path)
        except (OSError, ValueError):
            cleaned = False
    return cleaned


def _provision_dispatcher_lane(
    root: Path, lane: BrokerLaneSnapshot
) -> BrokerLaneSnapshot:
    if lane.transport != "dispatcher" or lane.anchor is None:
        raise ValueError("provider dispatcher provisioning lane is invalid")
    for path in (
        lane.socket_path,
        _dispatcher_mutable_path(root, lane, "json"),
        _dispatcher_mutable_path(root, lane, "plist"),
    ):
        if path.exists() or path.is_symlink():
            raise ValueError("untracked provider dispatcher state exists")
    _bundle, runtime, _manifest, anchor = _verify_published_version(
        root,
        artifact_digest=lane.artifact_digest,
        manifest_digest=lane.manifest_digest,
        role=lane.name,
        dispatcher_protocol_version=lane.protocol_version,
    )
    if anchor != lane.anchor:
        raise ValueError("provider dispatcher contract anchor changed")
    home = _operator_home()
    if home is None:
        raise ValueError("operator home is unavailable")
    plist_raw = _plist_bytes(
        _broker_plist_document(
            runtime_path=runtime,
            socket_path=lane.socket_path,
            tmpdir=root / "tmp",
            home=Path(home),
            uid=os.getuid(),
            label=lane.label,
            dispatcher_protocol_version=lane.protocol_version,
        )
    )
    state = _dispatcher_state_document(
        artifact_digest=lane.artifact_digest,
        manifest_digest=lane.manifest_digest,
        plist_digest=hashlib.sha256(plist_raw).hexdigest(),
        dispatcher_protocol_version=lane.protocol_version,
    )
    _write_private_atomic(
        _dispatcher_mutable_path(root, lane, "plist"), plist_raw, mode=0o600
    )
    _write_private_atomic(
        _dispatcher_mutable_path(root, lane, "json"),
        _state_bytes(state),
        mode=0o600,
    )
    if not _bootstrap_broker(_dispatcher_mutable_path(root, lane, "plist")):
        raise RuntimeError("provider dispatcher could not be bootstrapped")
    if not _job_loaded(lane.label) or _exact_mode(
        lane.socket_path, expected_type=stat.S_IFSOCK, mode=0o600
    ) is None:
        raise RuntimeError("provider dispatcher launchd identity is unavailable")
    return _load_dispatcher_broker_lane(
        root,
        {
            "artifact_sha256": lane.artifact_digest,
            "manifest_sha256": lane.manifest_digest,
        },
        lane.generation,
        name=lane.name,
        protocol_version=lane.protocol_version,
        expected_anchor=lane.anchor,
    )


def _staged_dispatcher_result(
    *, selector: Mapping[str, Any], lane: BrokerLaneSnapshot
) -> RuntimeResult:
    return RuntimeResult(
        RuntimeStatus.OK,
        result={
            "staged": True,
            "generation": selector["generation"],
            "selected": dict(selector["selected"]),
            "retained": (
                None if selector["retained"] is None else dict(selector["retained"])
            ),
            "candidate": dict(selector["candidate"]),
            "lifecycle": (
                None if selector["lifecycle"] is None else dict(selector["lifecycle"])
            ),
            "label": lane.label,
            "socket_activated": True,
            "persistent_process": False,
        },
    )


def dispatcher_status() -> RuntimeResult:
    """Report independently proven selector-v2 logical roles."""

    try:
        root = _broker_root()
        try:
            root.lstat()
        except FileNotFoundError:
            return RuntimeResult(
                RuntimeStatus.UNAVAILABLE,
                result={"installed": False},
                error="provider dispatcher is not installed",
            )
        if _exact_mode(root, expected_type=stat.S_IFDIR, mode=0o700) is None:
            raise ValueError("provider broker root identity is unsafe")
        selector = _read_broker_selector_view(root)
        if selector is None:
            return RuntimeResult(
                RuntimeStatus.UNAVAILABLE,
                result={"installed": False},
                error="provider dispatcher is not installed",
            )
        roles: dict[str, Any] = {}
        for role in ("selected", "retained", "candidate", "lifecycle"):
            document = selector.get(role)
            if document is None:
                roles[role] = None
                continue
            _load_selector_v2_lane(root, document, role=role)
            roles[role] = {**dict(document), "available": True}
        return RuntimeResult(
            RuntimeStatus.OK,
            result={
                "installed": True,
                "generation": selector["generation"],
                **roles,
                "persistent_process": False,
            },
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError):
        return RuntimeResult(
            RuntimeStatus.INTEGRITY_ERROR,
            error="provider dispatcher status could not be proven",
        )


def stage_dispatcher() -> RuntimeResult:
    """Publish and prove a dispatcher-v2 candidate without rewriting selector-v1."""

    blocked = _broker_lifecycle_seatbelt_block()
    if blocked is not None:
        return blocked
    resolution = resolve_runtime()
    if resolution.status is not RuntimeStatus.OK:
        return RuntimeResult(resolution.status, error=resolution.error)
    selector_before_raw: bytes | None = None
    selector_snapshot_captured = False
    lane: BrokerLaneSnapshot | None = None
    lane_owned = False
    root: Path | None = None

    def rollback_stage() -> bool:
        if root is None:
            return False
        restored = (
            _restore_selector_v2_snapshot(root, selector_before_raw)
            if selector_snapshot_captured
            else True
        )
        if lane is not None and lane_owned:
            restored = _cleanup_dispatcher_candidate(root, lane) and restored
        return restored

    try:
        root = _ensure_broker_layout()
        with _broker_control_transaction(root, rollback=rollback_stage):
            selector_before, selector_before_raw = _read_selector_v2_snapshot(root)
            selector_snapshot_captured = True
            baseline = (
                _read_broker_selector_view(root)
                if selector_before is None
                else selector_before
            )
            if baseline is None:
                raise ValueError("provider dispatcher committed baseline is unavailable")
            existing = baseline.get("candidate")
            expected_digests = (
                resolution.artifact_digest,
                resolution.manifest_digest,
            )
            if existing is not None:
                if (
                    existing["artifact_sha256"],
                    existing["manifest_sha256"],
                ) != expected_digests:
                    raise ValueError("another provider dispatcher candidate is staged")
                lane = _load_selector_v2_lane(root, existing, role="candidate")
                ping = invoke_dispatcher_ping(lane=lane)
                if ping.status is not RuntimeStatus.OK or not _wait_for_job_idle(lane.label):
                    raise RuntimeError("staged provider dispatcher is not ready")
                return _staged_dispatcher_result(selector=baseline, lane=lane)

            projection_restage = bool(
                selector_before is not None
                and baseline.get("retained") is None
                and baseline.get("selector_v1_sha256") is not None
                and _selector_v1_projection_matches_selected(root, baseline)
            )
            if selector_before is not None and (
                baseline.get("retained") is not None
                or (
                    baseline.get("selector_v1_sha256") is not None
                    and not projection_restage
                )
            ):
                return RuntimeResult(
                    RuntimeStatus.UNAVAILABLE,
                    result={"selected": dict(baseline["selected"])},
                    error="retained provider lane must be drained before staging",
                )

            _publish_broker_version(root, resolution=resolution)
            lane_generation = max(
                document["lane_generation"]
                for role in ("selected", "retained", "lifecycle")
                if isinstance((document := baseline.get(role)), dict)
            ) + 1
            lane = _dispatcher_lane_snapshot(
                root,
                artifact_digest=resolution.artifact_digest,
                manifest_digest=resolution.manifest_digest,
                generation=lane_generation,
                name="candidate",
                protocol_version=DISPATCHER_PROTOCOL_VERSION,
                anchor=resolution.anchor,
            )
            for path in (
                lane.socket_path,
                _dispatcher_mutable_path(root, lane, "json"),
                _dispatcher_mutable_path(root, lane, "plist"),
            ):
                if path.exists() or path.is_symlink():
                    raise ValueError("untracked provider dispatcher candidate exists")
            _bundle, runtime, _manifest, anchor = _verify_published_version(
                root,
                artifact_digest=resolution.artifact_digest,
                manifest_digest=resolution.manifest_digest,
                role="candidate",
                dispatcher_protocol_version=DISPATCHER_PROTOCOL_VERSION,
            )
            if anchor is None or anchor != resolution.anchor:
                raise ValueError("provider dispatcher candidate anchor changed")
            home = _operator_home()
            if home is None:
                raise ValueError("operator home is unavailable")
            plist_document = _broker_plist_document(
                runtime_path=runtime,
                socket_path=lane.socket_path,
                tmpdir=root / "tmp",
                home=Path(home),
                uid=os.getuid(),
                label=lane.label,
                dispatcher_protocol_version=DISPATCHER_PROTOCOL_VERSION,
            )
            plist_raw = _plist_bytes(plist_document)
            state = _dispatcher_state_document(
                artifact_digest=resolution.artifact_digest,
                manifest_digest=resolution.manifest_digest,
                plist_digest=hashlib.sha256(plist_raw).hexdigest(),
                dispatcher_protocol_version=DISPATCHER_PROTOCOL_VERSION,
            )
            lane_owned = True
            _write_private_atomic(
                _dispatcher_mutable_path(root, lane, "plist"),
                plist_raw,
                mode=0o600,
            )
            _write_private_atomic(
                _dispatcher_mutable_path(root, lane, "json"),
                _state_bytes(state),
                mode=0o600,
            )
            if not _bootstrap_broker(
                _dispatcher_mutable_path(root, lane, "plist")
            ):
                raise RuntimeError("provider dispatcher could not be bootstrapped")
            if not _job_loaded(lane.label) or _exact_mode(
                lane.socket_path, expected_type=stat.S_IFSOCK, mode=0o600
            ) is None:
                raise RuntimeError("provider dispatcher launchd identity is unavailable")
            selector = {
                **baseline,
                "generation": baseline["generation"] + 1,
                "candidate": _selector_v2_lane_document(lane),
            }
            if not _broker_selector_v2_valid(selector):
                raise ValueError("provider dispatcher stage transition is invalid")
            _write_private_atomic(
                root / BROKER_SELECTOR_V2_FILENAME,
                _selector_v2_bytes(selector),
                mode=0o600,
            )
            ping = invoke_dispatcher_ping(lane=lane)
            if ping.status is not RuntimeStatus.OK:
                raise RuntimeError("provider dispatcher activation ping failed")
            if not _wait_for_job_idle(lane.label):
                raise RuntimeError("provider dispatcher process exit was not observed")
            observed = _read_broker_selector_v2(root)
            if observed != selector:
                raise RuntimeError("provider dispatcher selector readback failed")
            _load_selector_v2_lane(
                root, selector["candidate"], role="candidate"
            )
            return _staged_dispatcher_result(selector=selector, lane=lane)
    except _BrokerMutationFailure as failure:
        restored = failure.restored_previous
        return RuntimeResult(
            RuntimeStatus.PROVIDER_ERROR,
            result={"restored_previous": restored},
            error=(
                "provider dispatcher staging failed; committed lanes were preserved"
                if restored
                else "provider dispatcher staging failed; candidate cleanup is unproven"
            ),
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError):
        restored = False
        return RuntimeResult(
            RuntimeStatus.PROVIDER_ERROR,
            result={"restored_previous": restored},
            error=(
                "provider dispatcher staging failed; committed lanes were preserved"
                if restored
                else "provider dispatcher staging failed; candidate cleanup is unproven"
            ),
        )


def commit_dispatcher_selector() -> RuntimeResult:
    """Commit candidate to selected and move prior selected to retained."""

    blocked = _broker_lifecycle_seatbelt_block()
    if blocked is not None:
        return blocked
    selector_raw: bytes | None = None
    selector_snapshot_captured = False
    root: Path | None = None

    def rollback_commit() -> bool:
        if root is None:
            return False
        return (
            _restore_selector_v2_snapshot(root, selector_raw)
            if selector_snapshot_captured
            else True
        )

    try:
        root = _broker_root()
        with _broker_control_transaction(root, rollback=rollback_commit):
            selector, selector_raw = _read_selector_v2_snapshot(root)
            selector_snapshot_captured = True
            if selector is None or selector.get("candidate") is None:
                return RuntimeResult(
                    RuntimeStatus.UNAVAILABLE,
                    error="provider dispatcher candidate is unavailable",
                )
            if selector.get("retained") is not None:
                return RuntimeResult(
                    RuntimeStatus.UNAVAILABLE,
                    result={"selected": dict(selector["selected"])},
                    error="retained provider lane must be drained before commitment",
                )
            lane = _load_selector_v2_lane(
                root, selector["candidate"], role="candidate"
            )
            if not _job_loaded(lane.label):
                raise RuntimeError("provider dispatcher job is unavailable")
            ping = invoke_dispatcher_ping(lane=lane)
            if ping.status is not RuntimeStatus.OK or not _wait_for_job_idle(lane.label):
                raise RuntimeError("provider dispatcher commitment preflight failed")
            candidate = {
                **selector,
                "generation": selector["generation"] + 1,
                "selected": selector["candidate"],
                "retained": selector["selected"],
                "candidate": None,
            }
            if not _broker_selector_v2_transition_valid(
                selector, candidate, action="commit"
            ):
                raise ValueError("provider dispatcher selector transition is invalid")
            _write_private_atomic(
                root / BROKER_SELECTOR_V2_FILENAME,
                _selector_v2_bytes(candidate),
                mode=0o600,
            )
            if _read_broker_selector_v2(root) != candidate:
                raise RuntimeError("provider dispatcher selector commit was not observed")
            return RuntimeResult(
                RuntimeStatus.OK,
                result={
                    "committed": True,
                    "generation": candidate["generation"],
                    "selected": dict(candidate["selected"]),
                    "retained": dict(candidate["retained"]),
                },
            )
    except _BrokerMutationFailure as failure:
        restored = failure.restored_previous
        return RuntimeResult(
            RuntimeStatus.PROVIDER_ERROR,
            result={"restored_previous": restored},
            error=(
                "provider dispatcher selector commit failed; prior generation restored"
                if restored
                else "provider dispatcher selector commit failed; control metadata is unproven"
            ),
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError):
        restored = False
        return RuntimeResult(
            RuntimeStatus.PROVIDER_ERROR,
            result={"restored_previous": restored},
            error=(
                "provider dispatcher selector commit failed; prior generation restored"
                if restored
                else "provider dispatcher selector commit failed; control metadata is unproven"
            ),
        )


def abort_dispatcher_candidate() -> RuntimeResult:
    """Discard only an uncommitted candidate; preserve every committed role."""

    blocked = _broker_lifecycle_seatbelt_block()
    if blocked is not None:
        return blocked
    selector_raw: bytes | None = None
    selector_snapshot_captured = False
    root: Path | None = None

    def rollback_abort() -> bool:
        if root is None:
            return False
        return (
            _restore_selector_v2_snapshot(root, selector_raw)
            if selector_snapshot_captured
            else True
        )

    try:
        root = _broker_root()
        with _broker_control_transaction(root, rollback=rollback_abort):
            selector, selector_raw = _read_selector_v2_snapshot(root)
            selector_snapshot_captured = True
            if selector is None or selector.get("candidate") is None:
                return RuntimeResult(
                    RuntimeStatus.OK,
                    result={"aborted": False},
                )
            lane = _load_selector_v2_lane(
                root, selector["candidate"], role="candidate"
            )
            candidate = {
                **selector,
                "generation": selector["generation"] + 1,
                "candidate": None,
            }
            if not _broker_selector_v2_transition_valid(
                selector, candidate, action="abort"
            ):
                raise ValueError("provider dispatcher abort transition is invalid")
            _write_private_atomic(
                root / BROKER_SELECTOR_V2_FILENAME,
                _selector_v2_bytes(candidate),
                mode=0o600,
            )
            if _read_broker_selector_v2(root) != candidate:
                raise RuntimeError("provider dispatcher abort was not observed")
            if not _cleanup_dispatcher_candidate(root, lane):
                return RuntimeResult(
                    RuntimeStatus.PROVIDER_ERROR,
                    result={
                        "aborted": True,
                        "candidate_cleanup": False,
                    },
                    error="provider dispatcher candidate was unselected but cleanup is unproven",
                )
            return RuntimeResult(
                RuntimeStatus.OK,
                result={
                    "aborted": True,
                    "generation": candidate["generation"],
                    "candidate_cleanup": True,
                },
            )
    except _BrokerMutationFailure as failure:
        restored = failure.restored_previous
        return RuntimeResult(
            RuntimeStatus.PROVIDER_ERROR,
            result={"restored_previous": restored},
            error=(
                "provider dispatcher abort failed; prior selector restored"
                if restored
                else "provider dispatcher abort failed; selector is unproven"
            ),
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError):
        restored = False
        return RuntimeResult(
            RuntimeStatus.PROVIDER_ERROR,
            result={"restored_previous": restored},
            error=(
                "provider dispatcher abort failed; prior selector restored"
                if restored
                else "provider dispatcher abort failed; selector is unproven"
            ),
        )


def _verify_lifecycle_blue_version(
    root: Path, reference: Mapping[str, Any]
) -> tuple[int, Path, Path, Path, RuntimeContractAnchor | None]:
    if not _broker_lane_reference_valid(reference):
        raise ValueError("legacy provider broker reference is invalid")
    bundle, runtime, manifest, anchor = _verify_published_version(
        root,
        artifact_digest=reference["artifact_sha256"],
        manifest_digest=reference["manifest_sha256"],
        runtime_protocol_version=LEGACY_BLUE_PROTOCOL_VERSION,
        role="lifecycle",
        transport="broker",
        dispatcher_protocol_version=None,
    )
    return LEGACY_BLUE_PROTOCOL_VERSION, bundle, runtime, manifest, anchor


def _rebuild_legacy_blue_files(
    root: Path, reference: Mapping[str, Any]
) -> tuple[dict[str, Any], bytes]:
    (
        runtime_protocol_version,
        _bundle,
        runtime,
        _manifest,
        anchor,
    ) = _verify_lifecycle_blue_version(root, reference)
    if anchor is not None:
        raise ValueError("lifecycle broker unexpectedly carries a normal anchor")
    home = _operator_home()
    if home is None:
        raise ValueError("operator home is unavailable")
    plist_raw = _plist_bytes(
        _broker_plist_document(
            runtime_path=runtime,
            socket_path=root / BROKER_SOCKET_FILENAME,
            tmpdir=root / "tmp",
            home=Path(home),
            uid=os.getuid(),
        )
    )
    state = _record_for(
        root=root,
        artifact_digest=reference["artifact_sha256"],
        manifest_digest=reference["manifest_sha256"],
        plist_digest=hashlib.sha256(plist_raw).hexdigest(),
        previous=None,
        runtime_protocol_version=runtime_protocol_version,
    )
    return state, plist_raw


def _rollback_recovery_mutation(
    *,
    bootstrap_attempted: bool,
    job_label: str,
    job_was_loaded: bool,
    plist_path: Path,
    plist_before: bytes | None,
    state_path: Path,
    state_before: bytes | None,
) -> bool:
    """Undo only recovery-owned job state and restore both mutable files."""

    job_restored = True
    if bootstrap_attempted and not job_was_loaded:
        try:
            if _job_loaded(job_label):
                booted_out = _bootout_broker(plist_path)
                job_restored = booted_out and not _job_loaded(job_label)
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
            job_restored = False
    state_restored = _restore_private_mutable(
        state_path, state_before, limit=BROKER_STATE_MAX_BYTES
    )
    plist_restored = _restore_private_mutable(
        plist_path, plist_before, limit=1024 * 1024
    )
    return job_restored and state_restored and plist_restored


def recover_last_committed_control_plane() -> RuntimeResult:
    """Repair mutable control files from the committed selector reference."""

    blocked = _broker_lifecycle_seatbelt_block()
    if blocked is not None:
        return blocked
    try:
        root = _broker_root()
        with _broker_control_lock(root):
            selector = _read_broker_selector_view(root)
            if selector is None:
                return RuntimeResult(
                    RuntimeStatus.UNAVAILABLE,
                    error="committed provider dispatcher selector is unavailable",
                )
            selected = selector["selected"]
            reference = {
                "artifact_sha256": selected["artifact_sha256"],
                "manifest_sha256": selected["manifest_sha256"],
            }
            if selected["transport"] == "broker":
                state_path = root / "state.json"
                plist_path = root / "broker.plist"
                state_before = _snapshot_private_mutable(
                    state_path, limit=BROKER_STATE_MAX_BYTES
                )
                plist_before = _snapshot_private_mutable(
                    plist_path, limit=1024 * 1024
                )
                job_was_loaded = _job_loaded(BROKER_LABEL)
                bootstrap_attempted = False
                _bundle, runtime, _manifest, anchor = _verify_published_version(
                    root,
                    artifact_digest=reference["artifact_sha256"],
                    manifest_digest=reference["manifest_sha256"],
                    role="selected",
                    transport="broker",
                    dispatcher_protocol_version=None,
                )
                if anchor is None:
                    raise ValueError("committed legacy broker anchor is unavailable")
                home = _operator_home()
                if home is None:
                    raise ValueError("operator home is unavailable")
                plist_raw = _plist_bytes(
                    _broker_plist_document(
                        runtime_path=runtime,
                        socket_path=root / BROKER_SOCKET_FILENAME,
                        tmpdir=root / "tmp",
                        home=Path(home),
                        uid=os.getuid(),
                    )
                )
                state = _record_for(
                    root=root,
                    artifact_digest=reference["artifact_sha256"],
                    manifest_digest=reference["manifest_sha256"],
                    plist_digest=hashlib.sha256(plist_raw).hexdigest(),
                    previous=_preserved_broker_previous(
                        state_before, root, reference
                    ),
                    runtime_protocol_version=PROTOCOL_VERSION,
                )
                try:
                    _write_private_atomic(
                        state_path, _state_bytes(state), mode=0o600
                    )
                    _write_private_atomic(plist_path, plist_raw, mode=0o600)
                    if not job_was_loaded:
                        bootstrap_attempted = True
                        if not _bootstrap_broker(plist_path):
                            raise RuntimeError(
                                "committed blue job could not be restored"
                            )
                    observed = _read_current_broker_state(root)
                    if observed != state:
                        raise RuntimeError("committed blue state was not restored")
                    _verify_plist_against_state(root, state)
                except (
                    OSError,
                    RuntimeError,
                    subprocess.SubprocessError,
                    TypeError,
                    ValueError,
                ) as exc:
                    if not _rollback_recovery_mutation(
                        bootstrap_attempted=bootstrap_attempted,
                        job_label=BROKER_LABEL,
                        job_was_loaded=job_was_loaded,
                        plist_path=plist_path,
                        plist_before=plist_before,
                        state_path=state_path,
                        state_before=state_before,
                    ):
                        raise RuntimeError(
                            "committed blue recovery rollback failed"
                        ) from exc
                    raise
            else:
                lane = _dispatcher_lane_snapshot(
                    root,
                    artifact_digest=reference["artifact_sha256"],
                    manifest_digest=reference["manifest_sha256"],
                    generation=selected["lane_generation"],
                    name="selected",
                    protocol_version=selected["protocol_version"],
                )
                state_path = _dispatcher_mutable_path(root, lane, "json")
                plist_path = _dispatcher_mutable_path(root, lane, "plist")
                state_before = _snapshot_private_mutable(
                    state_path, limit=BROKER_STATE_MAX_BYTES
                )
                plist_before = _snapshot_private_mutable(
                    plist_path, limit=1024 * 1024
                )
                job_was_loaded = _job_loaded(lane.label)
                bootstrap_attempted = False
                _bundle, runtime, _manifest, anchor = _verify_published_version(
                    root,
                    artifact_digest=lane.artifact_digest,
                    manifest_digest=lane.manifest_digest,
                    role="selected",
                    dispatcher_protocol_version=lane.protocol_version,
                )
                if anchor is None:
                    raise ValueError("committed dispatcher anchor is unavailable")
                home = _operator_home()
                if home is None:
                    raise ValueError("operator home is unavailable")
                plist_raw = _plist_bytes(
                    _broker_plist_document(
                        runtime_path=runtime,
                        socket_path=lane.socket_path,
                        tmpdir=root / "tmp",
                        home=Path(home),
                        uid=os.getuid(),
                        label=lane.label,
                        dispatcher_protocol_version=lane.protocol_version,
                    )
                )
                state = _dispatcher_state_document(
                    artifact_digest=lane.artifact_digest,
                    manifest_digest=lane.manifest_digest,
                    plist_digest=hashlib.sha256(plist_raw).hexdigest(),
                    dispatcher_protocol_version=lane.protocol_version,
                )
                try:
                    _write_private_atomic(
                        state_path, _state_bytes(state), mode=0o600
                    )
                    _write_private_atomic(plist_path, plist_raw, mode=0o600)
                    if not job_was_loaded:
                        bootstrap_attempted = True
                        if not _bootstrap_broker(plist_path):
                            raise RuntimeError(
                                "committed green job could not be restored"
                            )
                    _load_dispatcher_broker_lane(
                        root,
                        reference,
                        lane.generation,
                        name="selected",
                        protocol_version=lane.protocol_version,
                    )
                except (
                    OSError,
                    RuntimeError,
                    subprocess.SubprocessError,
                    TypeError,
                    ValueError,
                ) as exc:
                    if not _rollback_recovery_mutation(
                        bootstrap_attempted=bootstrap_attempted,
                        job_label=lane.label,
                        job_was_loaded=job_was_loaded,
                        plist_path=plist_path,
                        plist_before=plist_before,
                        state_path=state_path,
                        state_before=state_before,
                    ):
                        raise RuntimeError(
                            "committed dispatcher recovery rollback failed"
                        ) from exc
                    raise
            return RuntimeResult(
                RuntimeStatus.OK,
                result={
                    "recovered": True,
                    "generation": selector["generation"],
                    "selected": dict(selected),
                    "desired_provider_binaries_changed": False,
                },
            )
    except (OSError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError):
        return RuntimeResult(
            RuntimeStatus.PROVIDER_ERROR,
            result={"recovered": False},
            error="last committed provider control plane could not be recovered",
        )


BROKER_RETIRE_QUIESCENCE_SECONDS = 1.0


def _observe_job_quiescent(label: str) -> bool:
    if not _job_process_idle(label):
        return False
    time.sleep(BROKER_RETIRE_QUIESCENCE_SECONDS)
    return _job_process_idle(label)


def drain_retiring_dispatcher() -> RuntimeResult:
    """Retire selector-v2 fallback and lifecycle planes after quiescence."""

    blocked = _broker_lifecycle_seatbelt_block()
    if blocked is not None:
        return blocked
    try:
        root = _broker_root()
        with _broker_control_lock(root):
            selector, selector_raw = _read_selector_v2_snapshot(root)
            if selector is None or selector.get("candidate") is not None:
                return RuntimeResult(
                    RuntimeStatus.CONFIG_ERROR,
                    error="provider dispatcher selector-v2 is not drainable",
                )
            _selector_v1, selector_v1_raw = _read_selector_snapshot(root)
            if _read_broker_selector_view(root) != selector:
                raise ValueError("provider dispatcher selector projection is unproven")
            selected = _load_selector_v2_lane(
                root, selector["selected"], role="selected"
            )
            if not _job_loaded(selected.label):
                raise RuntimeError("committed provider job is unavailable")
            if selected.transport == "dispatcher":
                ping = invoke_dispatcher_ping(lane=selected)
                if ping.status is not RuntimeStatus.OK:
                    raise RuntimeError("committed provider dispatcher is unavailable")
            elif not _broker_ping(selected.socket_path):
                raise RuntimeError("committed provider broker is unavailable")

            retiring: list[BrokerLaneSnapshot] = []
            for role in ("retained", "lifecycle"):
                reference = selector.get(role)
                if reference is not None:
                    retiring.append(
                        _load_selector_v2_lane(root, reference, role=role)
                    )
            projection_present = selector["selector_v1_sha256"] is not None
            if not retiring and not projection_present:
                return RuntimeResult(
                    RuntimeStatus.OK,
                    result={
                        "selected": dict(selector["selected"]),
                        "retained_drained": True,
                        "projection_retired": True,
                        "versions_retained": True,
                    },
                )

            for lane in retiring:
                if not _observe_job_quiescent(lane.label):
                    return RuntimeResult(
                        RuntimeStatus.UNAVAILABLE,
                        error="retained provider lane is not quiescent",
                    )

            candidate = {
                **selector,
                "generation": selector["generation"] + 1,
                "selector_v1_sha256": None,
                "retained": None,
                "lifecycle": None,
            }
            if not _broker_selector_v2_valid(candidate):
                raise ValueError("provider dispatcher drain transition is invalid")
            _write_private_atomic(
                root / BROKER_SELECTOR_V2_FILENAME,
                _selector_v2_bytes(candidate),
                mode=0o600,
            )
            try:
                if projection_present:
                    _unlink_private_durable(root / BROKER_SELECTOR_FILENAME)
                if _read_broker_selector_view(root) != candidate:
                    raise RuntimeError("provider dispatcher drain was not observed")
            except (OSError, RuntimeError, TypeError, ValueError):
                restored_v1 = _restore_selector_snapshot(root, selector_v1_raw)
                restored_v2 = _restore_selector_v2_snapshot(root, selector_raw)
                if not restored_v1 or not restored_v2:
                    raise RuntimeError(
                        "provider dispatcher selector projection restoration failed"
                    )
                raise

            for lane in retiring:
                if lane.transport == "dispatcher":
                    cleaned = _cleanup_dispatcher_candidate(root, lane)
                else:
                    plist_path = root / "broker.plist"
                    cleaned = _bootout_broker(plist_path)
                    for path in (
                        root / "state.json",
                        plist_path,
                        root / BROKER_SOCKET_FILENAME,
                    ):
                        try:
                            _unlink_private_durable(path)
                        except (OSError, ValueError):
                            cleaned = False
                if not cleaned or _job_loaded(lane.label):
                    raise RuntimeError("retained provider lane could not be retired")
            return RuntimeResult(
                RuntimeStatus.OK,
                result={
                    "selected": dict(candidate["selected"]),
                    "retained_drained": True,
                    "projection_retired": True,
                    "versions_retained": True,
                },
            )
    except (OSError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError):
        return RuntimeResult(
            RuntimeStatus.PROVIDER_ERROR,
            result={"retained_drained": False},
            error="retained provider lane retirement could not be proven",
        )


def _activate_broker_record(
    root: Path,
    *,
    target_artifact: str,
    target_manifest: str,
    current_state: Mapping[str, Any] | None,
    next_previous: Mapping[str, Any] | None,
    restore_state: Mapping[str, Any] | None,
) -> RuntimeResult:
    _bundle, runtime, _manifest, _anchor = _verify_published_version(
        root,
        artifact_digest=target_artifact,
        manifest_digest=target_manifest,
        role="selected",
        transport="broker",
        dispatcher_protocol_version=None,
    )
    home = _operator_home()
    if home is None:
        return RuntimeResult(RuntimeStatus.CONFIG_ERROR, error="operator home is unavailable")
    plist_document = _broker_plist_document(
        runtime_path=runtime,
        socket_path=root / BROKER_SOCKET_FILENAME,
        tmpdir=root / "tmp",
        home=Path(home),
        uid=os.getuid(),
    )
    plist_raw = _plist_bytes(plist_document)
    record = _record_for(
        root=root,
        artifact_digest=target_artifact,
        manifest_digest=target_manifest,
        plist_digest=hashlib.sha256(plist_raw).hexdigest(),
        previous=next_previous,
    )
    plist_path = root / "broker.plist"
    old_record = None if current_state is None else dict(current_state)
    restore_record = None if restore_state is None else dict(restore_state)
    try:
        if old_record is not None and not _bootout_broker(plist_path):
            raise RuntimeError("existing provider broker could not be stopped")
        if old_record is None and plist_path.exists():
            raise RuntimeError("untracked provider broker plist exists")
        _write_private_atomic(plist_path, plist_raw, mode=0o600)
        _write_private_atomic(root / "state.json", _state_bytes(record), mode=0o600)
        if not _bootstrap_broker(plist_path):
            raise RuntimeError("provider broker could not be bootstrapped")
        if not _broker_job_loaded():
            raise RuntimeError("provider broker launchd identity was not observed")
        socket_path = root / BROKER_SOCKET_FILENAME
        if _exact_mode(socket_path, expected_type=stat.S_IFSOCK, mode=0o600) is None:
            raise RuntimeError("provider broker socket identity was not observed")
        if not _broker_ping(socket_path):
            raise RuntimeError("provider broker activation ping failed")
        observed_state, observed_error = _load_broker_state(
            artifact_digest=target_artifact,
            manifest_digest=target_manifest,
            require_socket=True,
        )
        if observed_error is not None or observed_state != record:
            raise RuntimeError("provider broker activation state could not be read back")
        return RuntimeResult(
            RuntimeStatus.OK,
            result={
                "installed": True,
                "artifact_sha256": target_artifact,
                "manifest_sha256": target_manifest,
                "socket_activated": True,
                "persistent_process": False,
            },
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
        restored = False
        try:
            _bootout_broker(plist_path)
            if restore_record is not None:
                _prior_bundle, prior_runtime, _prior_manifest, _prior_anchor = _verify_published_version(
                    root,
                    artifact_digest=restore_record["artifact_sha256"],
                    manifest_digest=restore_record["manifest_sha256"],
                    role="selected",
                    transport="broker",
                    dispatcher_protocol_version=None,
                )
                prior_document = _broker_plist_document(
                    runtime_path=prior_runtime,
                    socket_path=root / BROKER_SOCKET_FILENAME,
                    tmpdir=root / "tmp",
                    home=Path(home),
                    uid=os.getuid(),
                )
                prior_raw = _plist_bytes(prior_document)
                if hashlib.sha256(prior_raw).hexdigest() != restore_record["plist_sha256"]:
                    raise ValueError("prior provider broker plist digest mismatch")
                # Publish the committed record before its derived plist.  The
                # previous order bootstrapped the prior plist while target
                # state.json was still visible, producing the observed split
                # after a failed update.  A mid-write interruption is now
                # recoverable from the committed record (and, once seeded, the
                # blue selector reference) without mistaking candidate state
                # for the restored control plane.
                _write_private_atomic(
                    root / "state.json", _state_bytes(restore_record), mode=0o600
                )
                _write_private_atomic(plist_path, prior_raw, mode=0o600)
                if not _bootstrap_broker(plist_path) or not _broker_job_loaded():
                    raise RuntimeError("prior provider broker could not be restored")
                restored = True
            else:
                for candidate in (
                    root / "state.json",
                    plist_path,
                    root / BROKER_SOCKET_FILENAME,
                ):
                    try:
                        candidate.unlink()
                    except FileNotFoundError:
                        pass
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
            restored = False
        return RuntimeResult(
            RuntimeStatus.PROVIDER_ERROR,
            result={"restored_previous": restored},
            error=(
                "provider broker update failed; previous version restored"
                if restored
                else "provider broker update failed; no active version is proven"
            ),
        )


def install_broker() -> RuntimeResult:
    blocked = _broker_lifecycle_seatbelt_block()
    if blocked is not None:
        return blocked
    resolution = resolve_runtime()
    if resolution.status is not RuntimeStatus.OK:
        return RuntimeResult(resolution.status, error=resolution.error)
    try:
        root = _ensure_broker_layout()
        raw_manifest, _identity = _read_regular_nofollow(
            PLUGIN_ROOT / MANIFEST_NAME, limit=1024 * 1024
        )
        source_manifest = (
            runtime_bundle.load_closed_json_object(raw_manifest)
            if raw_manifest is not None
            else None
        )
        if (
            isinstance(source_manifest, dict)
            and _exact_int(source_manifest.get("schema_version"), MANIFEST_SCHEMA_VERSION)
        ):
            with _broker_control_lock(root):
                existing, selector_before_raw = _read_selector_v2_snapshot(root)
                if existing is not None:
                    selected = _load_selector_v2_lane(
                        root, existing["selected"], role="selected"
                    )
                    if (
                        selected.artifact_digest != resolution.artifact_digest
                        or selected.manifest_digest != resolution.manifest_digest
                    ):
                        return RuntimeResult(
                            RuntimeStatus.CONFIG_ERROR,
                            error="a different provider dispatcher is already selected",
                        )
                    return RuntimeResult(
                        RuntimeStatus.OK,
                        result={
                            "installed": True,
                            "selected": dict(existing["selected"]),
                            "fresh_bootstrap": False,
                            "socket_activated": True,
                            "persistent_process": False,
                        },
                    )
                if (
                    _read_broker_selector(root) is not None
                    or (root / "state.json").exists()
                ):
                    return RuntimeResult(
                        RuntimeStatus.CONFIG_ERROR,
                        error="legacy provider topology requires selector-v2 migration",
                    )
                lane: BrokerLaneSnapshot | None = None
                try:
                    _publish_broker_version(root, resolution=resolution)
                    lane = _dispatcher_lane_snapshot(
                        root,
                        artifact_digest=resolution.artifact_digest,
                        manifest_digest=resolution.manifest_digest,
                        generation=1,
                        name="selected",
                        protocol_version=DISPATCHER_PROTOCOL_VERSION,
                        anchor=resolution.anchor,
                    )
                    _provision_dispatcher_lane(root, lane)
                    selector = {
                        "schema_version": 2,
                        "generation": 1,
                        "selector_v1_sha256": None,
                        "selected": _selector_v2_lane_document(lane),
                        "retained": None,
                        "candidate": None,
                        "lifecycle": None,
                    }
                    _write_private_atomic(
                        root / BROKER_SELECTOR_V2_FILENAME,
                        _selector_v2_bytes(selector),
                        mode=0o600,
                    )
                    ping = invoke_dispatcher_ping(lane=lane)
                    if ping.status is not RuntimeStatus.OK or not _wait_for_job_idle(
                        lane.label
                    ):
                        raise RuntimeError("fresh provider dispatcher is not ready")
                    if _read_broker_selector_view(root) != selector:
                        raise RuntimeError("fresh provider selector readback failed")
                    return RuntimeResult(
                        RuntimeStatus.OK,
                        result={
                            "installed": True,
                            "selected": dict(selector["selected"]),
                            "fresh_bootstrap": True,
                            "socket_activated": True,
                            "persistent_process": False,
                        },
                    )
                except (
                    OSError,
                    RuntimeError,
                    subprocess.SubprocessError,
                    TypeError,
                    ValueError,
                ):
                    restored = _restore_selector_v2_snapshot(
                        root, selector_before_raw
                    )
                    if lane is not None:
                        restored = _cleanup_dispatcher_candidate(root, lane) and restored
                    return RuntimeResult(
                        RuntimeStatus.PROVIDER_ERROR,
                        result={"restored_previous": restored},
                        error=(
                            "fresh provider dispatcher bootstrap failed and was cleaned up"
                            if restored
                            else "fresh provider dispatcher bootstrap cleanup is unproven"
                        ),
                    )
        current = _read_current_broker_state(root)
        proven_current = None
        if current is not None:
            _verify_plist_against_state(root, current)
            try:
                _verify_published_version(
                    root,
                    artifact_digest=current["artifact_sha256"],
                    manifest_digest=current["manifest_sha256"],
                    role="selected",
                    transport="broker",
                    dispatcher_protocol_version=None,
                )
            except ValueError:
                proven_current = None
            else:
                proven_current = current
        _publish_broker_version(
            root,
            resolution=resolution,
            role="selected",
            transport="broker",
            dispatcher_protocol_version=None,
        )
        same_version = bool(
            current is not None
            and current["artifact_sha256"] == resolution.artifact_digest
            and current["manifest_sha256"] == resolution.manifest_digest
        )
        return _activate_broker_record(
            root,
            target_artifact=resolution.artifact_digest,
            target_manifest=resolution.manifest_digest,
            current_state=current,
            next_previous=(
                current.get("previous")
                if same_version and proven_current is not None
                else proven_current
            ),
            restore_state=proven_current,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
        return RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="provider broker installation preflight failed")


def broker_status() -> RuntimeResult:
    try:
        root = _broker_root()
        if not root.exists():
            return RuntimeResult(
                RuntimeStatus.UNAVAILABLE,
                result={"installed": False},
                error="provider broker is not installed",
            )
        if _exact_mode(root, expected_type=stat.S_IFDIR, mode=0o700) is None:
            raise ValueError("unsafe provider broker root")
        selector = _read_broker_selector_view(root)
        if selector is not None:
            lane = _load_selector_v2_lane(
                root, selector["selected"], role="selected"
            )
            loaded = _job_loaded(lane.label)
            socket_valid = _exact_mode(
                lane.socket_path, expected_type=stat.S_IFSOCK, mode=0o600
            ) is not None
            ready = False
            persistent_process = False
            if loaded and socket_valid:
                if lane.transport == "dispatcher":
                    ping = invoke_dispatcher_ping(lane=lane)
                    live = ping.status is RuntimeStatus.OK
                else:
                    live = _broker_ping(lane.socket_path)
                idle = _wait_for_job_idle(lane.label)
                ready = live and idle
                persistent_process = not idle

            rollback_available = False
            retained = selector.get("retained")
            if retained is not None:
                retained_lane = _load_selector_v2_lane(
                    root, retained, role="retained"
                )
                rollback_available = _job_loaded(retained_lane.label)

            if _read_broker_selector_view(root) != selector:
                raise ValueError("provider broker selector changed during status proof")
            status = RuntimeStatus.OK if ready else RuntimeStatus.UNAVAILABLE
            return RuntimeResult(
                status,
                result={
                    "installed": True,
                    "active": ready,
                    "launchd_job": loaded,
                    "socket": socket_valid,
                    "selected": dict(selector["selected"]),
                    "rollback_available": rollback_available,
                    "dispatcher_ready": ready and lane.transport == "dispatcher",
                    "persistent_process": persistent_process,
                },
                error=(
                    ""
                    if status is RuntimeStatus.OK
                    else "provider selected lane is installed but not executable"
                ),
            )
        state = _read_current_broker_state(root)
        if state is None:
            return RuntimeResult(
                RuntimeStatus.UNAVAILABLE,
                result={"installed": False},
                error="provider broker is not installed",
            )
        _verify_published_version(
            root,
            artifact_digest=state["artifact_sha256"],
            manifest_digest=state["manifest_sha256"],
            role="selected",
            transport="broker",
            dispatcher_protocol_version=None,
        )
        _verify_plist_against_state(root, state)
        socket_valid = _exact_mode(
            root / BROKER_SOCKET_FILENAME,
            expected_type=stat.S_IFSOCK,
            mode=0o600,
        ) is not None
        loaded = _broker_job_loaded()
        if _read_current_broker_state(root) != state:
            raise ValueError("provider broker state changed during status proof")
        rollback_available = False
        previous = state.get("previous")
        if isinstance(previous, Mapping):
            try:
                _verify_published_version(
                    root,
                    artifact_digest=previous["artifact_sha256"],
                    manifest_digest=previous["manifest_sha256"],
                    runtime_protocol_version=previous["runtime_protocol_version"],
                    role="retained",
                    transport="broker",
                    dispatcher_protocol_version=None,
                )
            except (
                OSError,
                RuntimeError,
                subprocess.SubprocessError,
                TypeError,
                ValueError,
            ):
                rollback_available = False
            else:
                rollback_available = True
        return RuntimeResult(
            RuntimeStatus.UNAVAILABLE,
            result={
                "installed": True,
                "active": False,
                "launchd_job": loaded,
                "socket": socket_valid,
                "artifact_sha256": state["artifact_sha256"],
                "manifest_sha256": state["manifest_sha256"],
                "rollback_available": rollback_available,
                "dispatcher_ready": False,
                "persistent_process": False,
            },
            error="provider broker selector is unavailable",
        )
    except (
        KeyError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ):
        return RuntimeResult(
            RuntimeStatus.INTEGRITY_ERROR,
            error="provider broker status could not be proven",
        )


def rollback_broker() -> RuntimeResult:
    blocked = _broker_lifecycle_seatbelt_block()
    if blocked is not None:
        return blocked
    try:
        root = _broker_root()
        if not root.exists():
            return RuntimeResult(
                RuntimeStatus.UNAVAILABLE,
                error="provider broker rollback is unavailable",
            )
        with _broker_control_lock(root):
            selector, selector_raw = _read_selector_v2_snapshot(root)
            if selector is not None:
                if selector.get("candidate") is not None or selector.get("retained") is None:
                    return RuntimeResult(
                        RuntimeStatus.UNAVAILABLE,
                        error="provider dispatcher rollback is unavailable",
                    )
                _load_selector_v2_lane(
                    root, selector["selected"], role="selected"
                )
                retained_lane = _load_selector_v2_lane(
                    root, selector["retained"], role="retained"
                )
                if not _job_loaded(retained_lane.label):
                    raise RuntimeError("retained provider lane is unavailable")
                if retained_lane.transport == "dispatcher":
                    ping = invoke_dispatcher_ping(lane=retained_lane)
                    if ping.status is not RuntimeStatus.OK or not _wait_for_job_idle(
                        retained_lane.label
                    ):
                        raise RuntimeError("retained provider dispatcher is unavailable")
                elif not _broker_ping(retained_lane.socket_path):
                    raise RuntimeError("retained provider broker is unavailable")
                candidate = {
                    **selector,
                    "generation": selector["generation"] + 1,
                    "selected": selector["retained"],
                    "retained": selector["selected"],
                }
                if not _broker_selector_v2_valid(candidate):
                    raise ValueError("provider dispatcher rollback transition is invalid")
                try:
                    _write_private_atomic(
                        root / BROKER_SELECTOR_V2_FILENAME,
                        _selector_v2_bytes(candidate),
                        mode=0o600,
                    )
                    if _read_broker_selector_v2(root) != candidate:
                        raise RuntimeError(
                            "provider dispatcher rollback was not observed"
                        )
                except (OSError, RuntimeError, TypeError, ValueError):
                    restored = _restore_selector_v2_snapshot(root, selector_raw)
                    return RuntimeResult(
                        RuntimeStatus.PROVIDER_ERROR,
                        result={"rolled_back": False, "restored_previous": restored},
                        error=(
                            "provider dispatcher rollback failed; prior selector restored"
                            if restored
                            else "provider dispatcher rollback failed; selector restoration is unproven"
                        ),
                    )
                return RuntimeResult(
                    RuntimeStatus.OK,
                    result={
                        "rolled_back": True,
                        "generation": candidate["generation"],
                        "selected": dict(candidate["selected"]),
                        "retained": dict(candidate["retained"]),
                        "persistent_process": False,
                    },
                )
        state = _read_current_broker_state(root)
        if state is None or state["previous"] is None:
            return RuntimeResult(RuntimeStatus.UNAVAILABLE, error="provider broker rollback is unavailable")
        _verify_plist_against_state(root, state)
        try:
            _verify_published_version(
                root,
                artifact_digest=state["artifact_sha256"],
                manifest_digest=state["manifest_sha256"],
                role="selected",
                transport="broker",
                dispatcher_protocol_version=None,
            )
        except ValueError:
            proven_current = None
        else:
            proven_current = state
        previous = dict(state["previous"])
        return _activate_broker_record(
            root,
            target_artifact=previous["artifact_sha256"],
            target_manifest=previous["manifest_sha256"],
            current_state=state,
            next_previous=proven_current,
            restore_state=proven_current,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
        return RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="provider broker rollback preflight failed")


def uninstall_broker() -> RuntimeResult:
    blocked = _broker_lifecycle_seatbelt_block()
    if blocked is not None:
        return blocked
    try:
        root = _broker_root()
        if not root.exists():
            return RuntimeResult(
                RuntimeStatus.OK,
                result={"installed": False, "versions_retained": True},
            )
        with _broker_control_lock(root):
            selector = _read_broker_selector_v2(root)
            if selector is not None:
                lanes = [
                    _load_selector_v2_lane(root, reference, role=role)
                    for role in ("selected", "retained", "candidate", "lifecycle")
                    if (reference := selector.get(role)) is not None
                ]
                for lane in lanes:
                    if not _observe_job_quiescent(lane.label):
                        return RuntimeResult(
                            RuntimeStatus.UNAVAILABLE,
                            error="provider lane is not quiescent",
                        )
                if selector["selector_v1_sha256"] is not None:
                    _unlink_private_durable(root / BROKER_SELECTOR_FILENAME)
                _unlink_private_durable(root / BROKER_SELECTOR_V2_FILENAME)
                for lane in lanes:
                    if lane.transport == "dispatcher":
                        cleaned = _cleanup_dispatcher_candidate(root, lane)
                    else:
                        plist_path = root / "broker.plist"
                        cleaned = _bootout_broker(plist_path)
                        for path in (
                            root / "state.json",
                            plist_path,
                            root / BROKER_SOCKET_FILENAME,
                        ):
                            try:
                                _unlink_private_durable(path)
                            except (OSError, ValueError):
                                cleaned = False
                    if not cleaned or _job_loaded(lane.label):
                        raise RuntimeError("provider lane could not be uninstalled")
                return RuntimeResult(
                    RuntimeStatus.OK,
                    result={"installed": False, "versions_retained": True},
                )
        state = _read_current_broker_state(root)
        if state is None:
            return RuntimeResult(RuntimeStatus.OK, result={"installed": False, "versions_retained": True})
        _verify_plist_against_state(root, state)
        plist_path = root / "broker.plist"
        if not _bootout_broker(plist_path):
            return RuntimeResult(RuntimeStatus.PROVIDER_ERROR, error="provider broker could not be stopped")
        socket_path = root / BROKER_SOCKET_FILENAME
        try:
            socket_path.lstat()
        except FileNotFoundError:
            pass
        else:
            if _exact_mode(
                socket_path, expected_type=stat.S_IFSOCK, mode=0o600
            ) is None:
                raise ValueError("unsafe provider broker socket")
        for candidate, expected_type, mode in (
            (socket_path, stat.S_IFSOCK, 0o600),
            (root / "state.json", stat.S_IFREG, 0o600),
            (plist_path, stat.S_IFREG, 0o600),
        ):
            try:
                candidate.lstat()
            except FileNotFoundError:
                continue
            else:
                if _exact_mode(candidate, expected_type=expected_type, mode=mode) is None:
                    raise ValueError("unsafe provider broker mutable state")
                candidate.unlink()
        return RuntimeResult(
            RuntimeStatus.OK,
            result={"installed": False, "versions_retained": True},
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
        return RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="provider broker uninstall preflight failed")


class _RuntimeTempCleanupError(RuntimeError):
    """Raised when an invocation's isolated temporary directory cannot be removed."""


@contextmanager
def _isolated_runtime_tmpdir() -> Iterator[Path]:
    """Create a fresh 0700 temp root without consulting caller-controlled TMPDIR."""

    operator_uid = _operator_uid()
    if operator_uid is None:
        raise OSError("operator identity is unavailable")
    path = Path(
        tempfile.mkdtemp(
            prefix="agent-collab-runtime-",
            dir=str(ISOLATED_TEMP_ROOT),
        )
    )
    try:
        os.chmod(path, 0o700)
        info = path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != operator_uid
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise OSError("isolated runtime temp directory is unsafe")
        yield path
    finally:
        try:
            shutil.rmtree(path)
        except OSError as exc:
            raise _RuntimeTempCleanupError(
                "isolated runtime temp directory could not be removed"
            ) from exc


def _native_document(envelope: object) -> bytes:
    policy = _load_host_policy()
    if not policy.verify_policy_envelope(envelope):
        raise ValueError("policy envelope seal is invalid")
    if (
        type(envelope.timeout_ms) is not int
        or not 1 <= envelope.timeout_ms <= MAX_TIMEOUT_MS
        or not _REQUEST_ID_RE.fullmatch(envelope.request_id)
        or (envelope.route, envelope.action) not in SUPPORTED_CONTRACTS
    ):
        raise ValueError("policy envelope fields are invalid")
    try:
        row = json.loads(envelope.row_json)
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("policy row is invalid") from None
    validated, family, error = policy._validate_row(
        envelope.route,
        envelope.action,
        row,
        policy.HostProfile(
            envelope.primary_id,
            envelope.primary_family,
            envelope.primary_model,
            envelope.primary_host_runtime,
            envelope.primary_session_identifier,
            True,
        ),
        {"opencode_model": row.get("model", "")},
        sealed=True,
    )
    if validated is None or family != envelope.target_author_family:
        raise ValueError(error or "policy row family changed")
    document: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": envelope.request_id,
        "operation": envelope.operation,
        "route": envelope.route,
        "action": envelope.action,
        "authority": envelope.authority,
        "timeout_ms": envelope.timeout_ms,
        "host_context": classify_host_context(),
        **validated,
    }
    if envelope.artifact_present:
        try:
            artifact_bytes = base64.b64decode(
                envelope.artifact_content_base64.encode("ascii"), validate=True
            )
        except (UnicodeError, ValueError):
            raise ValueError("artifact encoding is invalid") from None
        if (
            type(envelope.artifact_size) is not int
            or not 0 <= envelope.artifact_size <= policy.MAX_ARTIFACT_BYTES
            or len(artifact_bytes) != envelope.artifact_size
            or hashlib.sha256(artifact_bytes).hexdigest() != envelope.artifact_sha256
        ):
            raise ValueError("artifact hash or size verification failed")
        derived_artifact_family = policy.resolve_model_family(
            envelope.artifact_author_model
        )
        if derived_artifact_family != envelope.artifact_author_family:
            raise ValueError("artifact author provenance is invalid")
        document["artifact"] = {
            "encoding": "base64",
            "content": envelope.artifact_content_base64,
            "sha256": envelope.artifact_sha256,
            "size": envelope.artifact_size,
            "author_model": envelope.artifact_author_model,
            "author_family": envelope.artifact_author_family,
        }
    elif (
        envelope.artifact_content_base64
        or envelope.artifact_size != 0
        or envelope.artifact_sha256 != hashlib.sha256(b"").hexdigest()
        or envelope.artifact_author_model
        or envelope.artifact_author_family != "unknown"
    ):
        raise ValueError("absent artifact snapshot is inconsistent")
    if envelope.operation == "execute":
        document["prompt"] = envelope.prompt
    encoded = (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("runtime request exceeds the fixed protocol limit")
    return encoded


def _management_document(
    *, action: str, request_id: str, timeout_ms: int
) -> bytes:
    if action not in MANAGEMENT_ACTIONS:
        raise ValueError("runtime management action is invalid")
    if type(request_id) is not str or not _REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("runtime management request identifier is invalid")
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= MAX_TIMEOUT_MS:
        raise ValueError("runtime management timeout is invalid")
    document = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "operation": "manage",
        "management_action": action,
        "host_context": classify_host_context(),
        "timeout_ms": timeout_ms,
    }
    encoded = (
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("runtime management request exceeds the fixed protocol limit")
    return encoded


def _failure_response_result(response: Mapping[str, Any]) -> RuntimeResult | None:
    status = response.get("status")
    if status not in KNOWN_NATIVE_FAILURES:
        return None
    mapping = {
        "unavailable": RuntimeStatus.UNAVAILABLE,
        "auth_error": RuntimeStatus.AUTH_ERROR,
        "quota_error": RuntimeStatus.QUOTA_ERROR,
        "containment_error": RuntimeStatus.CONTAINMENT_ERROR,
        "cancelled": RuntimeStatus.CANCELLED,
        "input_limit": RuntimeStatus.INPUT_LIMIT,
        "timeout": RuntimeStatus.TIMEOUT,
        "output_limit": RuntimeStatus.OUTPUT_LIMIT,
        "teardown_error": RuntimeStatus.TEARDOWN_ERROR,
        "provider_error": RuntimeStatus.PROVIDER_ERROR,
    }
    return RuntimeResult(mapping[status], error=str(response["error"]))


def _parse_management_response(
    out: bytes, *, request_id: str, returncode: int
) -> RuntimeResult:
    try:
        response = json.loads(out.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="invalid runtime management response")
    if not isinstance(response, dict):
        return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="runtime management response contract mismatch")
    if response.get("status") in KNOWN_NATIVE_FAILURES:
        if (
            set(response) != {"protocol_version", "request_id", "status", "error"}
            or not _exact_int(response.get("protocol_version"), PROTOCOL_VERSION)
            or response.get("request_id") != request_id
            or not isinstance(response.get("error"), str)
            or len(response["error"].encode("utf-8")) > 4096
        ):
            return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="runtime management failure contract mismatch")
        result = _failure_response_result(response)
        return result or RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="runtime management failure contract mismatch")
    if returncode != 0:
        return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="native runtime failed without a typed management result")
    if (
        set(response) != {"protocol_version", "request_id", "status", "result"}
        or not _exact_int(response.get("protocol_version"), PROTOCOL_VERSION)
        or response.get("request_id") != request_id
        or response.get("status") != "ok"
        or not isinstance(response.get("result"), dict)
    ):
        return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="runtime management response contract mismatch")
    return RuntimeResult(RuntimeStatus.OK, result=response["result"])


def _gemini_governance_readiness_result_valid(
    result: Mapping[str, Any], envelope: object
) -> bool:
    expected_keys = {
        "ready",
        "containment_level",
        "tools_disabled",
        "pty_used",
        "lock_acquired",
        "cleanup_confirmed",
        "selected_display",
        "governance_ready",
        "artifact_sha256",
        "artifact_author_model",
        "artifact_author_family",
    }
    return (
        set(result) == expected_keys
        and result.get("ready") is True
        and result.get("containment_level") == GEMINI_GOVERNANCE_CONTAINMENT
        and result.get("tools_disabled") is False
        and result.get("pty_used") is True
        and result.get("lock_acquired") is True
        and result.get("cleanup_confirmed") is True
        and result.get("selected_display") == GEMINI_GOVERNANCE_DISPLAY
        and result.get("governance_ready") is True
        and result.get("artifact_sha256") == envelope.artifact_sha256
        and result.get("artifact_author_model") == envelope.artifact_author_model
        and result.get("artifact_author_family") == envelope.artifact_author_family
    )


def _gemini_governance_execute_result_valid(
    result: Mapping[str, Any],
    envelope: object,
    provenance: Mapping[str, Any],
    anchor: RuntimeContractAnchor,
) -> bool:
    expected_result_keys = {
        "text",
        "containment_level",
        "tools_disabled",
        "pty_used",
        "lock_acquired",
        "cleanup_confirmed",
        "selected_display",
        "governance_evidence",
        "artifact_sha256",
        "artifact_author_model",
        "artifact_author_family",
        "governance_proof",
    }
    text = result.get("text")
    proof = result.get("governance_proof")
    if (
        set(result) != expected_result_keys
        or type(text) is not str
        or len(text.encode("utf-8")) > MAX_RESPONSE_BYTES
        or result.get("containment_level") != GEMINI_GOVERNANCE_CONTAINMENT
        or result.get("tools_disabled") is not False
        or result.get("pty_used") is not True
        or result.get("lock_acquired") is not True
        or result.get("cleanup_confirmed") is not True
        or result.get("selected_display") != GEMINI_GOVERNANCE_DISPLAY
        or result.get("governance_evidence") is not True
        or result.get("artifact_sha256") != envelope.artifact_sha256
        or result.get("artifact_author_model") != envelope.artifact_author_model
        or result.get("artifact_author_family") != envelope.artifact_author_family
        or type(proof) is not dict
        or set(proof) != GEMINI_GOVERNANCE_PROOF_KEYS
    ):
        return False

    expected_scalars = {
        "version": 1,
        "request_id": envelope.request_id,
        "action": "governance",
        "authority": "read_only",
        "transport": "broker",
        "backend": "agy",
        "runtime_version": anchor.provider_runtime_version,
        "contract_version": anchor.route_contract_version,
        "artifact_sha256": envelope.artifact_sha256,
        "artifact_author_model": envelope.artifact_author_model,
        "artifact_author_family": envelope.artifact_author_family,
        "reviewer_model": GEMINI_GOVERNANCE_MODEL,
        "reviewer_family": "google",
        "selected_display": GEMINI_GOVERNANCE_DISPLAY,
        "effective_effort": "high",
        "containment_level": GEMINI_GOVERNANCE_CONTAINMENT,
        "tools_disabled": False,
        "pty_used": True,
        "lock_acquired": True,
        "cleanup_confirmed": True,
        "provider_process_started": True,
        "returncode": 0,
        "model_source": "agy-selected",
        "failed_over": False,
        "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    if any(
        type(proof.get(key)) is not type(expected) or proof.get(key) != expected
        for key, expected in expected_scalars.items()
    ):
        return False
    if (
        provenance.get("author_model") != proof.get("reviewer_model")
        or provenance.get("author_family") != proof.get("reviewer_family")
        or type(proof.get("proof_sha256")) is not str
        or _SHA256_RE.fullmatch(proof["proof_sha256"]) is None
    ):
        return False
    unsigned = dict(proof)
    supplied_digest = unsigned.pop("proof_sha256")
    try:
        encoded = json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError):
        return False
    return hmac.compare_digest(hashlib.sha256(encoded).hexdigest(), supplied_digest)


def _gemini_result_valid(
    result: Mapping[str, Any],
    envelope: object,
    provenance: Mapping[str, Any],
    anchor: RuntimeContractAnchor | None,
) -> bool:
    if envelope.route != "gemini":
        return True
    if envelope.action == "governance":
        if (
            anchor is None
            or envelope.governance is not True
            or envelope.authority != "read_only"
            or envelope.target_author_family != "google"
            or envelope.primary_family == "google"
            or envelope.artifact_present is not True
            or envelope.artifact_author_family in {"google", "unknown"}
            or provenance.get("host_runtime")
            != f"agent-collab-provider-runtime/{anchor.provider_runtime_version}"
        ):
            return False
        policy = _load_host_policy()
        if (
            policy.resolve_model_family(envelope.artifact_author_model)
            != envelope.artifact_author_family
        ):
            return False
        if envelope.operation == "readiness":
            return _gemini_governance_readiness_result_valid(result, envelope)
        if envelope.operation == "execute":
            return _gemini_governance_execute_result_valid(
                result, envelope, provenance, anchor
            )
        return False

    forbidden = {
        "governance_proof",
        "artifact_sha256",
        "artifact_author_model",
        "artifact_author_family",
    }
    if forbidden.intersection(result):
        return False
    if envelope.operation == "readiness":
        return result.get("governance_ready") is False
    if envelope.operation == "execute":
        return result.get("governance_evidence") is False
    return False


def _parse_response(
    out: bytes,
    envelope: object,
    returncode: int,
    *,
    anchor: RuntimeContractAnchor | None = None,
) -> RuntimeResult:
    try:
        response = json.loads(out.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="invalid runtime response")
    if not isinstance(response, dict):
        return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="runtime response contract mismatch")
    status = response.get("status")
    if status in KNOWN_NATIVE_FAILURES:
        if set(response) != {"protocol_version", "request_id", "status", "error"}:
            return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="runtime failure response contract mismatch")
        if (
            not _exact_int(response.get("protocol_version"), PROTOCOL_VERSION)
            or response.get("request_id") != envelope.request_id
            or not isinstance(response.get("error"), str)
            or len(response["error"].encode("utf-8")) > 4096
        ):
            return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="runtime failure response contract mismatch")
        mapping = {
            "unavailable": RuntimeStatus.UNAVAILABLE,
            "auth_error": RuntimeStatus.AUTH_ERROR,
            "quota_error": RuntimeStatus.QUOTA_ERROR,
            "containment_error": RuntimeStatus.CONTAINMENT_ERROR,
            "cancelled": RuntimeStatus.CANCELLED,
            "input_limit": RuntimeStatus.INPUT_LIMIT,
            "timeout": RuntimeStatus.TIMEOUT,
            "output_limit": RuntimeStatus.OUTPUT_LIMIT,
            "teardown_error": RuntimeStatus.TEARDOWN_ERROR,
            "provider_error": RuntimeStatus.PROVIDER_ERROR,
        }
        return RuntimeResult(mapping[status], error=response["error"])
    if returncode != 0:
        return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="native runtime failed without a typed result")
    if (
        set(response) != {"protocol_version", "request_id", "status", "result", "provenance"}
        or not _exact_int(response.get("protocol_version"), PROTOCOL_VERSION)
        or response.get("request_id") != envelope.request_id
        or status != "ok"
        or not isinstance(response.get("result"), dict)
    ):
        return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="runtime response contract mismatch")
    provenance = response.get("provenance")
    expected_keys = {
        "route",
        "action",
        "authority",
        "author_model",
        "author_family",
        "host_runtime",
        "session_identifier",
        "observation_sequence",
    }
    author_model = provenance.get("author_model") if isinstance(provenance, dict) else None
    try:
        sealed_row = json.loads(envelope.row_json)
    except (AttributeError, UnicodeError, ValueError, RecursionError):
        sealed_row = None
    expected_author_model = (
        FIXED_AUTHOR_MODELS.get(envelope.route)
        if hasattr(envelope, "route")
        else None
    )
    if expected_author_model is None and isinstance(sealed_row, dict):
        candidate = sealed_row.get("model")
        if isinstance(candidate, str) and candidate.strip():
            expected_author_model = candidate
    policy = _load_host_policy()
    derived_family = (
        policy.resolve_model_family(author_model) if isinstance(author_model, str) else "unknown"
    )
    if (
        not isinstance(provenance, dict)
        or set(provenance) != expected_keys
        or provenance.get("route") != envelope.route
        or provenance.get("action") != envelope.action
        or provenance.get("authority") != envelope.authority
        or provenance.get("author_family") != envelope.target_author_family
        or not isinstance(author_model, str)
        or not author_model.strip()
        or not isinstance(expected_author_model, str)
        or author_model != expected_author_model
        or derived_family not in policy.KNOWN_FAMILIES
        or provenance.get("author_family") != derived_family
        or not isinstance(provenance.get("host_runtime"), str)
        or not provenance["host_runtime"].strip()
        or not isinstance(provenance.get("session_identifier"), str)
        or not provenance["session_identifier"].strip()
        or type(provenance.get("observation_sequence")) is not int
        or provenance["observation_sequence"] < 0
    ):
        return RuntimeResult(RuntimeStatus.PROTOCOL_ERROR, error="runtime provenance contract mismatch")
    if not _gemini_result_valid(response["result"], envelope, provenance, anchor):
        return RuntimeResult(
            RuntimeStatus.PROTOCOL_ERROR,
            error="runtime Gemini result contract mismatch",
        )
    return RuntimeResult(RuntimeStatus.OK, result=response["result"], provenance=provenance)


def _terminate_and_reap(
    process: subprocess.Popen[bytes], *, deadline: float | None = None
) -> bool:
    # Post SIGKILL to the whole session group (process.pid is the session-group
    # leader: every launch uses start_new_session=True). group_killed records
    # whether the WHOLE-group kill is proven so the return can stay honest.
    group_killed = True
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        # ESRCH: the group already exited. The whole-group teardown is proven.
        group_killed = True
    except OSError:
        # The group kill could not be posted; fall back to killing only the
        # leader. Sibling members may survive, so the whole-group teardown is
        # NOT proven and the return below must reflect that.
        group_killed = False
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
    now = time.monotonic()
    if deadline is None:
        reap_deadline = now + REAP_BOUND_SECONDS
    else:
        # Honor the caller deadline as the primary bound, but always allow a
        # minimal grace for the just-posted SIGKILL to be delivered and the
        # leader reaped: a normal (non-D-state) process reaps in milliseconds,
        # so a strictly-zero budget at an already-expired deadline would
        # mistype an ordinary timeout as TEARDOWN_ERROR. The grace caps the
        # worst-case overrun at REAP_GRACE_SECONDS past the deadline (vs the
        # old ~10s of two fixed 5s waits), and is itself capped by the
        # no-deadline bound.
        reap_deadline = min(
            now + REAP_BOUND_SECONDS, max(deadline, now + REAP_GRACE_SECONDS)
        )
    # Reap the leader by polling, bounded above (never the old two fixed 5s
    # waits). A D-state child that outlives the bound yields reaped=False ->
    # TEARDOWN_ERROR (the documented accepted residual), never a false success.
    reaped = process.poll() is not None
    while not reaped and time.monotonic() < reap_deadline:
        time.sleep(min(0.02, max(0.0, reap_deadline - time.monotonic())))
        reaped = process.poll() is not None
    # "Teardown proven" requires BOTH the leader reaped AND the whole-group kill
    # posted; a leader-only fallback returns False so the caller types
    # TEARDOWN_ERROR rather than a false success.
    return reaped and group_killed


def _collect_bounded_output(
    process: subprocess.Popen[bytes], *, timeout_ms: int, relay_stderr: bool = False
) -> tuple[bytes, bytes, RuntimeResult | None]:
    if process.stdout is None or process.stderr is None:
        _terminate_and_reap(process)
        return b"", b"", RuntimeResult(
            RuntimeStatus.SPAWN_ERROR, error="native runtime pipes are unavailable"
        )
    selector = selectors.DefaultSelector()
    streams = {"stdout": process.stdout}
    if process.stderr is not None:
        streams["stderr"] = process.stderr
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout_ms / 1000
    try:
        for name, stream in streams.items():
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, data=name)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                reaped = _terminate_and_reap(process, deadline=deadline)
                status = RuntimeStatus.TIMEOUT if reaped else RuntimeStatus.TEARDOWN_ERROR
                error = (
                    "native runtime timed out"
                    if reaped
                    else "native runtime timed out and could not be reaped"
                )
                return b"", b"", RuntimeResult(status, error=error)
            for key, _ in selector.select(timeout=min(remaining, 0.1)):
                name = key.data
                stream = key.fileobj
                try:
                    chunk = os.read(
                        stream.fileno(),
                        min(64 * 1024, MAX_RESPONSE_BYTES + 1 - len(buffers[name])),
                    )
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                buffers[name].extend(chunk)
                if len(buffers[name]) > MAX_RESPONSE_BYTES:
                    reaped = _terminate_and_reap(process, deadline=deadline)
                    status = (
                        RuntimeStatus.OUTPUT_LIMIT
                        if reaped
                        else RuntimeStatus.TEARDOWN_ERROR
                    )
                    error = (
                        f"native runtime {name} limit exceeded"
                        if reaped
                        else f"native runtime {name} limit exceeded and teardown failed"
                    )
                    return b"", b"", RuntimeResult(status, error=error)
                if name == "stderr" and relay_stderr:
                    pending = memoryview(chunk)
                    while pending:
                        written = os.write(2, pending)
                        if written <= 0:
                            raise OSError("runtime management stderr relay made no progress")
                        pending = pending[written:]
        remaining = deadline - time.monotonic()
        try:
            process.wait(timeout=max(remaining, 0.001))
        except subprocess.TimeoutExpired:
            reaped = _terminate_and_reap(process, deadline=deadline)
            status = RuntimeStatus.TIMEOUT if reaped else RuntimeStatus.TEARDOWN_ERROR
            return b"", b"", RuntimeResult(
                status,
                error=(
                    "native runtime timed out"
                    if reaped
                    else "native runtime timed out and could not be reaped"
                ),
            )
        return bytes(buffers["stdout"]), bytes(buffers["stderr"]), None
    except (OSError, ValueError):
        reaped = _terminate_and_reap(process, deadline=deadline)
        return b"", b"", RuntimeResult(
            RuntimeStatus.TEARDOWN_ERROR,
            error=(
                "native runtime output collection failed"
                if reaped
                else "native runtime output collection failed and could not be reaped"
            ),
        )
    except BaseException:
        _terminate_and_reap(process, deadline=deadline)
        raise
    finally:
        selector.close()
        for stream in streams.values():
            if not stream.closed:
                stream.close()


def _launch_runtime(
    *,
    resolution: RuntimeResolution,
    payload: bytes,
    timeout_ms: int,
    envelope: object | None = None,
    management_request_id: str = "",
    relay_stderr: bool = False,
) -> RuntimeResult:
    if resolution.path is None or resolution.identity is None:
        return RuntimeResult(RuntimeStatus.UNAVAILABLE, error="native runtime is unavailable")
    if _safe_file_identity(resolution.path, executable=True) != resolution.identity:
        return RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="runtime identity changed before launch")
    command = [str(resolution.path), "invoke", "--protocol", str(PROTOCOL_VERSION)]
    try:
        with _isolated_runtime_tmpdir() as runtime_tmpdir:
            with tempfile.TemporaryFile(dir=runtime_tmpdir) as stdin:
                stdin.write(payload)
                stdin.seek(0)
                process = subprocess.Popen(
                    command,
                    stdin=stdin,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(PLUGIN_ROOT.resolve(strict=True)),
                    env=_scrubbed_env(tmpdir=runtime_tmpdir),
                    start_new_session=True,
                    close_fds=True,
                )
                out, _err, collection_error = _collect_bounded_output(
                    process,
                    timeout_ms=timeout_ms,
                    relay_stderr=relay_stderr,
                )
                if collection_error is not None:
                    return collection_error
                returncode = process.returncode if process.returncode is not None else -1
                if envelope is not None:
                    return _parse_response(
                        out,
                        envelope,
                        returncode,
                        anchor=resolution.anchor,
                    )
                return _parse_management_response(
                    out,
                    request_id=management_request_id,
                    returncode=returncode,
                )
    except _RuntimeTempCleanupError:
        return RuntimeResult(
            RuntimeStatus.TEARDOWN_ERROR,
            error="isolated runtime temporary state could not be removed",
        )
    except PermissionError:
        return RuntimeResult(RuntimeStatus.HOST_BLOCKED, error="host blocked runtime launch")
    except (OSError, ValueError):
        return RuntimeResult(RuntimeStatus.SPAWN_ERROR, error="native runtime could not start")


def manage_runtime(*, action: str, request_id: str, timeout_ms: int) -> RuntimeResult:
    try:
        payload = _management_document(
            action=action,
            request_id=request_id,
            timeout_ms=timeout_ms,
        )
    except (TypeError, ValueError, RecursionError):
        return RuntimeResult(RuntimeStatus.CONFIG_ERROR, error="invalid runtime management request")
    resolution = resolve_runtime()
    if resolution.status != RuntimeStatus.OK:
        return RuntimeResult(resolution.status, error=resolution.error)
    return _launch_runtime(
        resolution=resolution,
        payload=payload,
        timeout_ms=timeout_ms,
        management_request_id=request_id,
        relay_stderr=action == "grok_login",
    )


def invoke(*, envelope: object) -> RuntimeResult:
    try:
        payload = _native_document(envelope)
    except (AttributeError, RuntimeError, TypeError, ValueError, RecursionError):
        return RuntimeResult(RuntimeStatus.CONFIG_ERROR, error="invalid or unsealed policy envelope")
    if (envelope.route, envelope.action) in TEMPORARILY_UNAVAILABLE_CONTRACTS:
        return RuntimeResult(
            RuntimeStatus.UNAVAILABLE,
            error=TEMPORARILY_UNAVAILABLE_CONTRACTS[(envelope.route, envelope.action)],
        )
    resolution = resolve_runtime()
    if resolution.status != RuntimeStatus.OK or resolution.path is None:
        return RuntimeResult(resolution.status, error=resolution.error)
    if resolution.manifest_digest != envelope.runtime_manifest_digest:
        return RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="runtime manifest changed after policy selection")
    if (envelope.route, envelope.action) not in resolution.contracts:
        return RuntimeResult(RuntimeStatus.UNAVAILABLE, error="native runtime does not advertise the sealed route/action")
    if envelope.route in BROKERED_ROUTES:
        return _launch_broker(
            resolution=resolution,
            payload=payload,
            timeout_ms=envelope.timeout_ms,
            envelope=envelope,
        )
    return _launch_runtime(
        resolution=resolution,
        payload=payload,
        timeout_ms=envelope.timeout_ms,
        envelope=envelope,
    )


def _parse_adoption_canary_response(
    response: object, *, request: Mapping[str, Any]
) -> RuntimeResult:
    if type(response) is not dict:
        return RuntimeResult(
            RuntimeStatus.PROTOCOL_ERROR,
            error="adoption canary response contract mismatch",
        )
    status = response.get("status")
    if status != "ok":
        mapping = {
            "unavailable": RuntimeStatus.UNAVAILABLE,
            "auth_error": RuntimeStatus.AUTH_ERROR,
            "quota_error": RuntimeStatus.QUOTA_ERROR,
            "containment_error": RuntimeStatus.CONTAINMENT_ERROR,
            "cancelled": RuntimeStatus.CANCELLED,
            "input_limit": RuntimeStatus.INPUT_LIMIT,
            "timeout": RuntimeStatus.TIMEOUT,
            "output_limit": RuntimeStatus.OUTPUT_LIMIT,
            "teardown_error": RuntimeStatus.TEARDOWN_ERROR,
            "provider_error": RuntimeStatus.PROVIDER_ERROR,
            "integrity_error": RuntimeStatus.INTEGRITY_ERROR,
            "protocol_error": RuntimeStatus.PROTOCOL_ERROR,
            "resource_error": RuntimeStatus.UNAVAILABLE,
            "canary_blocked": RuntimeStatus.CANARY_BLOCKED,
        }
        if (
            set(response) != {"protocol_version", "request_id", "status", "error"}
            or not _exact_int(
                response.get("protocol_version"),
                PROTOCOL_VERSION,
            )
            or response.get("request_id") != request.get("request_id")
            or status not in mapping
            or type(response.get("error")) is not str
            or len(response["error"].encode("utf-8")) > 4096
        ):
            return RuntimeResult(
                RuntimeStatus.PROTOCOL_ERROR,
                error="adoption canary failure contract mismatch",
            )
        return RuntimeResult(mapping[status], error=response["error"])
    result = response.get("result")
    provenance = response.get("provenance")
    if (
        set(response)
        != {"protocol_version", "request_id", "status", "result", "provenance"}
        or not _exact_int(
            response.get("protocol_version"),
            PROTOCOL_VERSION,
        )
        or response.get("request_id") != request.get("request_id")
        or type(result) is not dict
        or set(result)
        != {
            "provider",
            "registry_generation",
            "attempt_generation",
            "passed_routes",
        }
        or result.get("provider") != request.get("provider")
        or result.get("registry_generation") != request.get("registry_generation")
        or result.get("attempt_generation") != request.get("attempt_generation")
        or result.get("passed_routes") != request.get("routes")
        or type(provenance) is not dict
        or set(provenance)
        != {
            "operation",
            "binary_sha256",
            "worker_sha256",
            "adapter_contract_generation",
        }
        or provenance.get("operation") != "adoption_canary"
        or provenance.get("binary_sha256") != request.get("binary_sha256")
        or provenance.get("worker_sha256") != request.get("worker_sha256")
        or provenance.get("adapter_contract_generation")
        != request.get("adapter_contract_generation")
    ):
        return RuntimeResult(
            RuntimeStatus.PROTOCOL_ERROR,
            error="adoption canary response contract mismatch",
        )
    return RuntimeResult(
        RuntimeStatus.OK,
        result=dict(result),
        provenance=dict(provenance),
    )


def invoke_adoption_canary(*, request: object) -> RuntimeResult:
    try:
        payload = _adoption_canary_document(request)
        document = json.loads(payload.decode("ascii"))
        root = _broker_root()
        selector = _read_broker_selector_v2(root)
        if selector is None or selector.get("candidate") is None:
            return RuntimeResult(
                RuntimeStatus.UNAVAILABLE,
                error="staged provider dispatcher is unavailable",
            )
        lane = _load_selector_v2_lane(
            root, selector["candidate"], role="candidate"
        )
    except (OSError, TypeError, ValueError, RecursionError):
        return RuntimeResult(
            RuntimeStatus.INTEGRITY_ERROR,
            error="staged provider dispatcher identity is unproven",
        )
    deadline = time.monotonic() + document["timeout_ms"] / 1000.0
    try:
        now = time.monotonic()
        handshake_deadline = min(
            deadline,
            now + DISPATCHER_MAX_HANDSHAKE_SECONDS,
        )
        response = _invoke_dispatcher_bridge(
            lane=lane,
            request=document,
            deadline=deadline,
            handshake_deadline=handshake_deadline,
        )
    except _DispatcherPreRequestError:
        return RuntimeResult(
            RuntimeStatus.INTEGRITY_ERROR,
            error="staged provider dispatcher bridge is unproven",
        )
    except _DispatcherPostRequestError as exc:
        if exc.result is not None:
            return exc.result
        return RuntimeResult(
            RuntimeStatus.PROTOCOL_ERROR,
            error="staged provider dispatcher failed after canary acceptance",
        )
    except (OSError, TypeError, ValueError):
        return RuntimeResult(
            RuntimeStatus.PROTOCOL_ERROR,
            error="adoption canary exchange failed",
        )
    return _parse_adoption_canary_response(response, request=document)
