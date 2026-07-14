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
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping

try:
    import pwd as _pwd
except ImportError:  # pragma: no cover - exercised by a simulated non-POSIX import
    _pwd = None


PLUGIN_ROOT = Path(__file__).resolve().parent
MANIFEST_NAME = "runtime-manifest.json"
PROTOCOL_VERSION = 1
CONTRACT_VERSION = 3
MAX_REQUEST_BYTES = 48 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_TIMEOUT_MS = 600_000
BROKER_PROTOCOL_VERSION = 2
BROKER_LABEL = "com.agent-collab.provider-broker"
BROKER_SOCKET_NAME = "ProviderBroker"
BROKER_SOCKET_FILENAME = "provider-broker.sock"
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
BROKERED_ROUTES = frozenset({"codex", "opencode", "gemini", "grok", "composer"})
BROKER_MAX_REQUEST_BYTES = MAX_REQUEST_BYTES
BROKER_MAX_RESPONSE_BYTES = MAX_RESPONSE_BYTES
BROKER_STATE_MAX_BYTES = 64 * 1024
BROKER_SUN_PATH_MAX_BYTES = 103
BROKER_SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
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
_TEAM_ID_RE = re.compile(r"^[A-Z0-9]{10}$")
_DEVELOPER_ID_RE = re.compile(
    r"^Developer ID Application: [^\r\n]{1,160} \(([A-Z0-9]{10})\)$"
)
_CODESIGN_FLAGS_RE = re.compile(r"\bflags=(0x[0-9a-f]+)(?:\([^)]*\))?", re.IGNORECASE)
_CODESIGN_TIMESTAMP_RE = re.compile(r"(?m)^Timestamp=(.+)$")
_CODESIGN_TEAM_RE = re.compile(r"(?m)^TeamIdentifier=([A-Z0-9]{10})(?=\s|$)")
_VERSION_RE = re.compile(r"^\d+(?:\.\d+){1,2}$")
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
FIXED_AUTHOR_MODELS = {
    "grok": "xai/grok-4.5",
    "composer": "xai/grok-composer-2.5-fast",
}
GEMINI_GOVERNANCE_MODEL = "google/gemini-3.1-pro"
GEMINI_GOVERNANCE_DISPLAY = "Gemini 3.1 Pro (High)"
GEMINI_GOVERNANCE_RUNTIME_VERSION = "1.2.0"
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
class RuntimeResolution:
    status: RuntimeStatus
    path: Path | None = None
    bundle_path: Path | None = None
    files: tuple[Mapping[str, Any], ...] = ()
    contracts: frozenset[tuple[str, str]] = frozenset()
    manifest_digest: str = ""
    artifact_digest: str = ""
    identity: FileIdentity | None = None
    error: str = ""


@dataclass(frozen=True)
class RuntimeResult:
    status: RuntimeStatus
    result: Mapping[str, Any] | None = None
    provenance: Mapping[str, Any] | None = None
    error: str = ""


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


def _manifest_entry(data: object) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(data, dict) or set(data) != {
        "schema_version",
        "protocol_version",
        "contract_version",
        "broker_protocol_version",
        "channel",
        "artifacts",
    }:
        return None, "manifest root shape is invalid"
    if (
        not _exact_int(data["schema_version"], 2)
        or not _exact_int(data["protocol_version"], PROTOCOL_VERSION)
        or not _exact_int(data["contract_version"], CONTRACT_VERSION)
        or not _exact_int(data["broker_protocol_version"], BROKER_PROTOCOL_VERSION)
        or data["channel"] != "production"
    ):
        return None, "manifest or protocol version is unsupported"
    artifacts = data["artifacts"]
    if not isinstance(artifacts, list):
        return None, "artifacts must be an array"
    selected: list[dict[str, Any]] = []
    seen_hosts: set[tuple[str, str]] = set()
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {
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
        }:
            return None, "artifact shape is invalid"
        signing = item.get("signing")
        contracts = _contracts(item.get("contracts"))
        expected_path = "runtime/darwin-arm64/agent-collab-runtime.bundle"
        try:
            records = runtime_bundle.validate_file_records(item.get("files"))
            bundle_digest = runtime_bundle.compute_bundle_identity(records)
        except runtime_bundle.BundleContractError:
            return None, "artifact file records are invalid"
        identity_value = signing.get("identity") if isinstance(signing, dict) else None
        identity_match = (
            _DEVELOPER_ID_RE.fullmatch(identity_value)
            if isinstance(identity_value, str)
            else None
        )
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
            or not isinstance(signing, dict)
            or set(signing)
            != {
                "mode",
                "identity",
                "team_id",
                "require_notarization",
                "hardened_runtime",
                "secure_timestamp",
            }
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
            or any(
                record["signing_profile"] != "production_developer_id"
                for record in records
            )
            or contracts is None
        ):
            return None, "artifact fields are invalid"
        host_key = (item["platform"], item["arch"])
        if host_key in seen_hosts:
            return None, "manifest contains duplicate host artifacts"
        seen_hosts.add(host_key)
        if host_key == ("darwin", "arm64"):
            selected.append(
                {**item, "_contracts": contracts, "_files": records}
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
        result = subprocess.run(
            ["/usr/sbin/spctl", "--assess", "--type", "execute", "--verbose=4", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return False, "macOS notarization assessment failed"
        assessment = result.stdout + result.stderr
        if "source=Notarized Developer ID" not in {
            line.strip() for line in assessment.splitlines()
        }:
            return False, "macOS notarization source is not Notarized Developer ID"
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
    entry, error = _manifest_entry(data)
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


def _broker_record_valid(document: object, root: Path, *, allow_previous: bool) -> bool:
    if not isinstance(document, dict) or set(document) != BROKER_STATE_KEYS:
        return False
    if (
        not _exact_int(document.get("schema_version"), 2)
        or not _exact_int(document.get("contract_version"), CONTRACT_VERSION)
        or not _exact_int(
            document.get("broker_protocol_version"), BROKER_PROTOCOL_VERSION
        )
        or not _exact_int(
            document.get("runtime_protocol_version"), PROTOCOL_VERSION
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
    if previous is not None and (
        not allow_previous or not _broker_record_valid(previous, root, allow_previous=False)
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


def _broker_request_frame(
    *,
    request: Mapping[str, Any],
    artifact_digest: str,
    manifest_digest: str,
    timeout_ms: int,
) -> dict[str, Any]:
    if (
        not isinstance(request, dict)
        or not _SHA256_RE.fullmatch(artifact_digest)
        or not _SHA256_RE.fullmatch(manifest_digest)
        or not _exact_int(timeout_ms)
        or not 1 <= timeout_ms <= MAX_TIMEOUT_MS
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
        "deadline_monotonic_ms": int(time.monotonic() * 1000) + timeout_ms,
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


def _parse_broker_response(document: dict[str, Any], envelope: object) -> RuntimeResult:
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
    return _parse_response(encoded, envelope, 0)


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
    state, error = _load_broker_state(
        artifact_digest=resolution.artifact_digest,
        manifest_digest=resolution.manifest_digest,
        require_socket=True,
    )
    if error is not None or state is None:
        return error or RuntimeResult(RuntimeStatus.UNAVAILABLE, error="provider broker is unavailable")
    try:
        frame = _broker_request_frame(
            request=request,
            artifact_digest=resolution.artifact_digest,
            manifest_digest=resolution.manifest_digest,
            timeout_ms=timeout_ms,
        )
        encoded = _encode_broker_frame(frame, max_bytes=BROKER_MAX_REQUEST_BYTES)
        deadline = time.monotonic() + timeout_ms / 1000
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(timeout_ms / 1000)
            peer.connect(state["socket_path"])
            peer.sendall(encoded)
            response = _read_broker_frame(
                peer,
                max_bytes=BROKER_MAX_RESPONSE_BYTES,
                deadline=deadline,
            )
        return _parse_broker_response(response, envelope)
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
    *, runtime_path: Path, socket_path: Path, tmpdir: Path, home: Path, uid: int
) -> dict[str, Any]:
    if (
        not all(path.is_absolute() for path in (runtime_path, socket_path, tmpdir, home))
        or not _exact_int(uid)
        or uid < 0
        or len(os.fsencode(socket_path)) > BROKER_SUN_PATH_MAX_BYTES
    ):
        raise ValueError("invalid provider broker plist input")
    runtime = str(runtime_path)
    return {
        "Label": BROKER_LABEL,
        "Program": runtime,
        "ProgramArguments": [runtime, "broker", "--protocol", str(BROKER_PROTOCOL_VERSION)],
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
    if path.parent != _broker_root() or path.name not in {"broker.plist", "state.json"}:
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
    root: Path, *, artifact_digest: str, manifest_digest: str
) -> tuple[Path, Path, Path]:
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
        entry, error = _manifest_entry(document)
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
    return bundle, entrypoint, manifest


def _publish_broker_version(
    root: Path, *, resolution: RuntimeResolution
) -> tuple[Path, Path, Path]:
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


def _read_current_broker_state(root: Path) -> dict[str, Any] | None:
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
    if not _broker_record_valid(document, root, allow_previous=True):
        raise ValueError("provider broker state contract mismatch")
    return dict(document)


def _without_previous(document: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(document)
    result["previous"] = None
    return result


def _launchctl(arguments: list[str], *, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    home = _operator_home()
    if home is None:
        raise ValueError("operator home is unavailable")
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
    out, err, collection_error = _collect_bounded_output(
        process, timeout_ms=timeout * 1000
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


def _broker_job_loaded() -> bool:
    return _launchctl(
        ["print", f"gui/{os.getuid()}/{BROKER_LABEL}"]
    ).returncode == 0


def _broker_ping(socket_path: Path) -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(5.0)
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


def _broker_process_idle() -> bool:
    result = _launchctl(["print", f"gui/{os.getuid()}/{BROKER_LABEL}"])
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


def _wait_for_broker_exit() -> bool:
    deadline = time.monotonic() + 5.0
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
) -> dict[str, Any]:
    version = _broker_version_path(
        root,
        artifact_digest=artifact_digest,
        manifest_digest=manifest_digest,
    )
    return {
        "schema_version": 2,
        "contract_version": CONTRACT_VERSION,
        "broker_protocol_version": BROKER_PROTOCOL_VERSION,
        "runtime_protocol_version": PROTOCOL_VERSION,
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


def _activate_broker_record(
    root: Path,
    *,
    target_artifact: str,
    target_manifest: str,
    current_state: Mapping[str, Any] | None,
    next_previous: Mapping[str, Any] | None,
    restore_state: Mapping[str, Any] | None,
) -> RuntimeResult:
    _bundle, runtime, _manifest = _verify_published_version(
        root,
        artifact_digest=target_artifact,
        manifest_digest=target_manifest,
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
                _prior_bundle, prior_runtime, _prior_manifest = _verify_published_version(
                    root,
                    artifact_digest=restore_record["artifact_sha256"],
                    manifest_digest=restore_record["manifest_sha256"],
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
                _write_private_atomic(plist_path, prior_raw, mode=0o600)
                if not _bootstrap_broker(plist_path) or not _broker_job_loaded():
                    raise RuntimeError("prior provider broker could not be restored")
                _write_private_atomic(
                    root / "state.json", _state_bytes(restore_record), mode=0o600
                )
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
    resolution = resolve_runtime()
    if resolution.status is not RuntimeStatus.OK:
        return RuntimeResult(resolution.status, error=resolution.error)
    try:
        root = _ensure_broker_layout()
        current = _read_current_broker_state(root)
        proven_current = None
        if current is not None:
            _verify_plist_against_state(root, current)
            try:
                _verify_published_version(
                    root,
                    artifact_digest=current["artifact_sha256"],
                    manifest_digest=current["manifest_sha256"],
                )
            except ValueError:
                proven_current = None
            else:
                proven_current = current
        _publish_broker_version(root, resolution=resolution)
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
            return RuntimeResult(RuntimeStatus.UNAVAILABLE, result={"installed": False}, error="provider broker is not installed")
        if _exact_mode(root, expected_type=stat.S_IFDIR, mode=0o700) is None:
            raise ValueError("unsafe provider broker root")
        state = _read_current_broker_state(root)
        if state is None:
            return RuntimeResult(RuntimeStatus.UNAVAILABLE, result={"installed": False}, error="provider broker is not installed")
        _verify_published_version(
            root,
            artifact_digest=state["artifact_sha256"],
            manifest_digest=state["manifest_sha256"],
        )
        _verify_plist_against_state(root, state)
        socket_valid = _exact_mode(
            root / BROKER_SOCKET_FILENAME,
            expected_type=stat.S_IFSOCK,
            mode=0o600,
        ) is not None
        loaded = _broker_job_loaded()
        status = RuntimeStatus.OK if loaded and socket_valid else RuntimeStatus.UNAVAILABLE
        return RuntimeResult(
            status,
            result={
                "installed": True,
                "active": loaded and socket_valid,
                "launchd_job": loaded,
                "socket": socket_valid,
                "artifact_sha256": state["artifact_sha256"],
                "manifest_sha256": state["manifest_sha256"],
                "rollback_available": state["previous"] is not None,
                "persistent_process": False,
            },
            error="" if status is RuntimeStatus.OK else "provider broker is installed but inactive",
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
        return RuntimeResult(RuntimeStatus.INTEGRITY_ERROR, error="provider broker status could not be proven")


def rollback_broker() -> RuntimeResult:
    try:
        root = _broker_root()
        state = _read_current_broker_state(root)
        if state is None or state["previous"] is None:
            return RuntimeResult(RuntimeStatus.UNAVAILABLE, error="provider broker rollback is unavailable")
        _verify_plist_against_state(root, state)
        try:
            _verify_published_version(
                root,
                artifact_digest=state["artifact_sha256"],
                manifest_digest=state["manifest_sha256"],
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
    try:
        root = _broker_root()
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
    result: Mapping[str, Any], envelope: object, provenance: Mapping[str, Any]
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
        "runtime_version": GEMINI_GOVERNANCE_RUNTIME_VERSION,
        "contract_version": CONTRACT_VERSION,
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
    result: Mapping[str, Any], envelope: object, provenance: Mapping[str, Any]
) -> bool:
    if envelope.route != "gemini":
        return True
    if envelope.action == "governance":
        if (
            envelope.governance is not True
            or envelope.authority != "read_only"
            or envelope.target_author_family != "google"
            or envelope.primary_family == "google"
            or envelope.artifact_present is not True
            or envelope.artifact_author_family in {"google", "unknown"}
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
                result, envelope, provenance
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


def _parse_response(out: bytes, envelope: object, returncode: int) -> RuntimeResult:
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
    if not _gemini_result_valid(response["result"], envelope, provenance):
        return RuntimeResult(
            RuntimeStatus.PROTOCOL_ERROR,
            error="runtime Gemini result contract mismatch",
        )
    return RuntimeResult(RuntimeStatus.OK, result=response["result"], provenance=provenance)


def _terminate_and_reap(process: subprocess.Popen[bytes]) -> bool:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
    try:
        process.wait(timeout=5)
        return True
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=5)
            return True
        except (OSError, subprocess.TimeoutExpired):
            return False


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
                reaped = _terminate_and_reap(process)
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
                    reaped = _terminate_and_reap(process)
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
            reaped = _terminate_and_reap(process)
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
        reaped = _terminate_and_reap(process)
        return b"", b"", RuntimeResult(
            RuntimeStatus.TEARDOWN_ERROR,
            error=(
                "native runtime output collection failed"
                if reaped
                else "native runtime output collection failed and could not be reaped"
            ),
        )
    except BaseException:
        _terminate_and_reap(process)
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
                    return _parse_response(out, envelope, returncode)
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
