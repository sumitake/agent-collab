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
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping


PLUGIN_ROOT = Path(__file__).resolve().parent
MANIFEST_NAME = "runtime-manifest.json"
PROTOCOL_VERSION = 1
CONTRACT_VERSION = 1
MAX_REQUEST_BYTES = 48 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_TIMEOUT_MS = 600_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TEAM_ID_RE = re.compile(r"^[A-Z0-9]{10}$")
_CODESIGN_FLAGS_RE = re.compile(r"\bflags=(0x[0-9a-f]+)(?:\([^)]*\))?", re.IGNORECASE)
_CODESIGN_TIMESTAMP_RE = re.compile(r"(?m)^Timestamp=(.+)$")
_CODESIGN_TEAM_RE = re.compile(r"(?m)^TeamIdentifier=([A-Z0-9]{10})(?=\s|$)")
_VERSION_RE = re.compile(r"^\d+(?:\.\d+){1,2}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
EXPECTED_MINIMUM_MACOS = "14.0"
ISOLATED_TEMP_ROOT = Path("/tmp")


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
SUPPORTED_CONTRACTS = frozenset(
    {
        ("gemini", "advisory"),
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
TEMPORARILY_UNAVAILABLE_CONTRACTS = {
    ("codex", "build"): "Codex build is unavailable until a hardened mutation backend exists"
}
KNOWN_NATIVE_FAILURES = frozenset(
    {
        "unavailable",
        "auth_error",
        "quota_error",
        "containment_error",
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
    contracts: frozenset[tuple[str, str]] = frozenset()
    manifest_digest: str = ""
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


def _safe_file_identity(path: Path, *, executable: bool) -> FileIdentity | None:
    try:
        info = path.lstat()
    except OSError:
        return None
    mode = info.st_mode
    if (
        not stat.S_ISREG(mode)
        or stat.S_ISLNK(mode)
        or info.st_uid != os.getuid()
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
        "artifacts",
    }:
        return None, "manifest root shape is invalid"
    if (
        not _exact_int(data["schema_version"], 1)
        or not _exact_int(data["protocol_version"], PROTOCOL_VERSION)
        or not _exact_int(data["contract_version"], CONTRACT_VERSION)
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
            "minimum_macos",
            "path",
            "size",
            "sha256",
            "signing",
            "contracts",
        }:
            return None, "artifact shape is invalid"
        signing = item.get("signing")
        contracts = _contracts(item.get("contracts"))
        expected_path = "runtime/darwin-arm64/agent-collab-runtime"
        if (
            item.get("platform") != "darwin"
            or item.get("arch") != "arm64"
            or item.get("minimum_macos") != "14.0"
            or item.get("path") != expected_path
            or type(item.get("size")) is not int
            or not 1 <= item["size"] <= MAX_ARTIFACT_BYTES
            or not isinstance(item.get("sha256"), str)
            or not _SHA256_RE.fullmatch(item["sha256"])
            or not isinstance(signing, dict)
            or set(signing) != {"team_id", "require_notarization", "hardened_runtime"}
            or not isinstance(signing.get("team_id"), str)
            or not _TEAM_ID_RE.fullmatch(signing["team_id"])
            or not _TEAM_ID_RE.fullmatch(EXPECTED_DEVELOPER_ID_TEAM)
            or signing["team_id"] != EXPECTED_DEVELOPER_ID_TEAM
            or signing.get("require_notarization") is not True
            or signing.get("hardened_runtime") is not True
            or contracts is None
        ):
            return None, "artifact fields are invalid"
        host_key = (item["platform"], item["arch"])
        if host_key in seen_hosts:
            return None, "manifest contains duplicate host artifacts"
        seen_hosts.add(host_key)
        if host_key == ("darwin", "arm64"):
            selected.append({**item, "_contracts": contracts})
    if not selected:
        return {}, "runtime artifact is not packaged for this host"
    if len(selected) != 1:
        return None, "manifest contains duplicate host artifacts"
    return selected[0], ""


def _path_beneath_root(root: Path, rel: str) -> Path | None:
    pure = PurePosixPath(rel)
    expected = PurePosixPath("runtime", "darwin-arm64", "agent-collab-runtime")
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
    path: Path, *, team_id: str, require_notarization: bool
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
    hardened = any(
        int(match.group(1), 16) & 0x10000
        for match in _CODESIGN_FLAGS_RE.finditer(detail_output)
    )
    if not hardened:
        return False, "macOS hardened runtime flag is missing"
    timestamp_match = _CODESIGN_TIMESTAMP_RE.search(detail_output)
    if timestamp_match is None or timestamp_match.group(1).strip().casefold() in {
        "",
        "none",
        "not set",
        "unsigned",
    }:
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
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
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
    path = _path_beneath_root(root, entry["path"])
    if path is None:
        return RuntimeResolution(RuntimeStatus.PATH_INVALID, manifest_digest=manifest_digest, error="runtime path is unsafe")
    identity = _safe_file_identity(path, executable=True)
    if identity is None:
        if not path.exists():
            return RuntimeResolution(RuntimeStatus.UNAVAILABLE, manifest_digest=manifest_digest, error="runtime artifact absent")
        return RuntimeResolution(RuntimeStatus.PATH_INVALID, manifest_digest=manifest_digest, error="runtime ownership, mode, or link count is unsafe")
    if identity.size != entry["size"]:
        return RuntimeResolution(RuntimeStatus.INTEGRITY_ERROR, manifest_digest=manifest_digest, error="runtime size mismatch")
    digest = _sha256_regular(path, identity)
    if digest is None or digest != entry["sha256"]:
        return RuntimeResolution(RuntimeStatus.INTEGRITY_ERROR, manifest_digest=manifest_digest, error="runtime digest mismatch")
    try:
        valid, detail = _verify_macos_signature(
            path,
            team_id=entry["signing"]["team_id"],
            require_notarization=entry["signing"]["require_notarization"],
        )
    except (OSError, subprocess.SubprocessError):
        return RuntimeResolution(RuntimeStatus.HOST_BLOCKED, manifest_digest=manifest_digest, error="signature tools unavailable")
    if not valid:
        return RuntimeResolution(RuntimeStatus.SIGNATURE_ERROR, manifest_digest=manifest_digest, error=detail)
    # Close the verification-to-exec window as far as path-based macOS exec
    # permits by recording the exact identity that invoke() must recheck.
    if _safe_file_identity(path, executable=True) != identity:
        return RuntimeResolution(RuntimeStatus.INTEGRITY_ERROR, manifest_digest=manifest_digest, error="runtime identity changed during verification")
    return RuntimeResolution(
        RuntimeStatus.OK,
        path=path,
        contracts=entry["_contracts"],
        manifest_digest=manifest_digest,
        identity=identity,
    )


def runtime_contract_snapshot() -> tuple[frozenset[tuple[str, str]], str]:
    resolution = resolve_runtime()
    if resolution.status != RuntimeStatus.OK:
        return frozenset(), resolution.manifest_digest
    return resolution.contracts, resolution.manifest_digest


def _scrubbed_env(*, tmpdir: Path) -> dict[str, str]:
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    value = os.environ.get("HOME")
    if value and "\0" not in value and len(value) <= 4096 and Path(value).is_absolute():
        env["HOME"] = value
    env["TMPDIR"] = str(tmpdir)
    return env


class _RuntimeTempCleanupError(RuntimeError):
    """Raised when an invocation's isolated temporary directory cannot be removed."""


@contextmanager
def _isolated_runtime_tmpdir() -> Iterator[Path]:
    """Create a fresh 0700 temp root without consulting caller-controlled TMPDIR."""

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
            or info.st_uid != os.getuid()
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
    process: subprocess.Popen[bytes], *, timeout_ms: int
) -> tuple[bytes, bytes, RuntimeResult | None]:
    if process.stdout is None or process.stderr is None:
        _terminate_and_reap(process)
        return b"", b"", RuntimeResult(
            RuntimeStatus.SPAWN_ERROR, error="native runtime pipes are unavailable"
        )
    selector = selectors.DefaultSelector()
    streams = {"stdout": process.stdout, "stderr": process.stderr}
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
    if resolution.identity is None or _safe_file_identity(resolution.path, executable=True) != resolution.identity:
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
                out, err, collection_error = _collect_bounded_output(
                    process, timeout_ms=envelope.timeout_ms
                )
                if collection_error is not None:
                    result = collection_error
                else:
                    result = _parse_response(out, envelope, process.returncode)
    except _RuntimeTempCleanupError:
        return RuntimeResult(
            RuntimeStatus.TEARDOWN_ERROR,
            error="isolated runtime temporary state could not be removed",
        )
    except PermissionError:
        return RuntimeResult(RuntimeStatus.HOST_BLOCKED, error="host blocked runtime launch")
    except (OSError, ValueError):
        return RuntimeResult(RuntimeStatus.SPAWN_ERROR, error="native runtime could not start")
    return result
