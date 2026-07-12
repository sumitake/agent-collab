#!/usr/bin/env python3
"""Verify the signed/notarized Darwin-arm64 runtime before activation release."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import re
import stat
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_REL = Path("plugins/agent-collab")
MANIFEST_REL = PLUGIN_REL / "runtime-manifest.json"
SIGNING_POLICY_REL = PLUGIN_REL / "signing_policy.py"
RUNTIME_REL = Path("runtime/darwin-arm64/agent-collab-runtime")
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
REQUIRED_CONTRACTS = frozenset(
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
_TEAM_ID_RE = re.compile(r"^[A-Z0-9]{10}$")
_CODESIGN_FLAGS_RE = re.compile(r"\bflags=(0x[0-9a-f]+)(?:\([^)]*\))?", re.IGNORECASE)
_CODESIGN_TIMESTAMP_RE = re.compile(r"(?m)^Timestamp=(.+)$")
_CODESIGN_TEAM_RE = re.compile(r"(?m)^TeamIdentifier=([A-Z0-9]{10})(?=\s|$)")
_VERSION_RE = re.compile(r"^\d+(?:\.\d+){1,2}$")
EXPECTED_MINIMUM_MACOS = "14.0"


def _load_expected_team_id() -> str:
    path = REPO_ROOT / PLUGIN_REL / "signing_policy.py"
    spec = importlib.util.spec_from_file_location(
        "agent_collab_release_signing_policy", path
    )
    if spec is None or spec.loader is None:
        return ""
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (AttributeError, OSError, RuntimeError, ValueError):
        return ""
    value = getattr(module, "EXPECTED_DEVELOPER_ID_TEAM", "")
    return value if isinstance(value, str) else ""


EXPECTED_DEVELOPER_ID_TEAM = _load_expected_team_id()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _signing_policy_digest(root: Path) -> tuple[str, str]:
    path = root / SIGNING_POLICY_REL
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID)
        ):
            return "", "signing policy ownership, mode, or link count is unsafe"
        return _sha256(path), ""
    except OSError:
        return "", "signing policy is missing or unreadable"


def _secure_codesign_timestamp(output: str) -> str:
    match = _CODESIGN_TIMESTAMP_RE.search(output)
    if match is None:
        return ""
    value = match.group(1).strip()
    if value.casefold() in {"", "none", "not set", "unsigned"}:
        return ""
    return value


def _spctl_source(output: str) -> str:
    expected = "source=Notarized Developer ID"
    return "Notarized Developer ID" if expected in {
        line.strip() for line in output.splitlines()
    } else ""


def _exact_int(value: object, expected: int) -> bool:
    return type(value) is int and value == expected


def _normalized_version(value: str) -> tuple[int, ...] | None:
    if not _VERSION_RE.fullmatch(value):
        return None
    parts = [int(part) for part in value.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _verify_macho_identity(
    path: Path, *, minimum_macos: str
) -> tuple[bool, bool, str]:
    try:
        architecture = subprocess.run(
            ["/usr/bin/lipo", "-archs", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        load_commands = subprocess.run(
            ["/usr/bin/otool", "-l", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False, False, "Mach-O inspection tool failed"
    arch_ok = (
        architecture.returncode == 0
        and architecture.stdout.strip().split() == ["arm64"]
    )
    if not arch_ok:
        return False, False, "Mach-O artifact is not a thin arm64 binary"
    if load_commands.returncode != 0:
        return True, False, "Mach-O load commands cannot be inspected"
    build_versions: list[tuple[str, str]] = []
    for block in re.split(r"(?m)^Load command \d+\s*$", load_commands.stdout):
        if not re.search(r"(?m)^\s*cmd\s+LC_BUILD_VERSION\s*$", block):
            continue
        platform_match = re.search(r"(?m)^\s*platform\s+(\S+)\s*$", block)
        minos_match = re.search(r"(?m)^\s*minos\s+(\S+)\s*$", block)
        if platform_match is None or minos_match is None:
            return True, False, "Mach-O LC_BUILD_VERSION is malformed"
        build_versions.append((platform_match.group(1), minos_match.group(1)))
    if len(build_versions) != 1:
        return True, False, "Mach-O must contain exactly one LC_BUILD_VERSION command"
    build_platform, observed_minimum = build_versions[0]
    min_ok = (
        build_platform.lower() in {"1", "macos"}
        and _normalized_version(observed_minimum) is not None
        and _normalized_version(observed_minimum)
        == _normalized_version(minimum_macos)
    )
    if not min_ok:
        return True, False, "Mach-O LC_BUILD_VERSION macOS minimum is invalid"
    return True, True, ""


def _manifest(root: Path) -> tuple[dict[str, Any] | None, Path, list[str]]:
    manifest_path = root / MANIFEST_REL
    errors: list[str] = []
    try:
        if stat.S_ISLNK(manifest_path.lstat().st_mode):
            return None, manifest_path, ["runtime manifest is a symlink"]
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None, manifest_path, ["runtime manifest is unreadable"]
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "protocol_version", "contract_version", "artifacts"}
        or not _exact_int(data.get("schema_version"), 1)
        or not _exact_int(data.get("protocol_version"), 1)
        or not _exact_int(data.get("contract_version"), 1)
        or not isinstance(data.get("artifacts"), list)
    ):
        errors.append("runtime manifest root or version is invalid")
        return data if isinstance(data, dict) else None, manifest_path, errors
    if len(data["artifacts"]) != 1:
        errors.append("activation release requires exactly one Darwin-arm64 artifact")
    return data, manifest_path, errors


def verify_release(
    root: Path, *, git_sha: str
) -> tuple[bool, dict[str, Any], list[str]]:
    root = root.resolve()
    signing_policy_sha256, signing_policy_error = _signing_policy_digest(root)
    if signing_policy_error:
        return False, {}, [signing_policy_error]
    data, manifest_path, errors = _manifest(root)
    if data is None or errors:
        return False, {}, errors
    item = data["artifacts"][0]
    expected_fields = {
        "platform",
        "arch",
        "minimum_macos",
        "path",
        "size",
        "sha256",
        "signing",
        "contracts",
    }
    if not isinstance(item, dict) or set(item) != expected_fields:
        return False, {}, ["runtime artifact manifest shape is invalid"]
    signing = item.get("signing")
    if not _TEAM_ID_RE.fullmatch(EXPECTED_DEVELOPER_ID_TEAM):
        errors.append("operator Developer ID Team ID is not configured")
    try:
        contracts = frozenset(
            (entry["route"], entry["action"])
            for entry in item["contracts"]
            if isinstance(entry, dict) and set(entry) == {"route", "action"}
        )
    except (KeyError, TypeError):
        contracts = frozenset()
    if contracts != REQUIRED_CONTRACTS or len(item.get("contracts", [])) != len(contracts):
        errors.append("runtime artifact does not advertise the exact required route/action contract")
    if (
        item.get("platform") != "darwin"
        or item.get("arch") != "arm64"
        or item.get("minimum_macos") != "14.0"
        or item.get("path") != RUNTIME_REL.as_posix()
        or type(item.get("size")) is not int
        or not 1 <= item["size"] <= MAX_ARTIFACT_BYTES
        or not isinstance(item.get("sha256"), str)
        or not isinstance(signing, dict)
        or set(signing) != {"team_id", "require_notarization", "hardened_runtime"}
        or not isinstance(signing.get("team_id"), str)
        or not _TEAM_ID_RE.fullmatch(signing["team_id"])
        or signing["team_id"] != EXPECTED_DEVELOPER_ID_TEAM
        or signing.get("require_notarization") is not True
        or signing.get("hardened_runtime") is not True
    ):
        errors.append("runtime artifact platform/signing fields are invalid")
    binary = root / PLUGIN_REL / RUNTIME_REL
    try:
        info = binary.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID)
            or not info.st_mode & stat.S_IXUSR
        ):
            errors.append("runtime artifact ownership, mode, or link count is unsafe")
        if info.st_size != item.get("size"):
            errors.append("runtime artifact size does not match the manifest")
        digest = _sha256(binary)
        if digest != item.get("sha256"):
            errors.append("runtime artifact digest does not match the manifest")
    except OSError:
        digest = ""
        errors.append("runtime artifact is missing or unreadable")
    if platform.system().lower() != "darwin" or platform.machine().lower() not in {"arm64", "aarch64"}:
        errors.append("signing verification must run on Darwin arm64")
    codesign_detail_output = ""
    codesign_timestamp = ""
    spctl_source = ""
    macho_arch_verified = False
    minimum_macos_verified = False
    if not errors:
        (
            macho_arch_verified,
            minimum_macos_verified,
            macho_error,
        ) = _verify_macho_identity(binary, minimum_macos=EXPECTED_MINIMUM_MACOS)
        if macho_error:
            errors.append(macho_error)
    if not errors:
        commands = (
            ("codesign-verify", ["/usr/bin/codesign", "--verify", "--strict", "--verbose=4", str(binary)]),
            ("codesign-detail", ["/usr/bin/codesign", "-dv", "--verbose=4", str(binary)]),
            ("spctl", ["/usr/sbin/spctl", "--assess", "--type", "execute", "--verbose=4", str(binary)]),
        )
        spctl_output = ""
        for tool, command in commands:
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                errors.append("macOS signing/notarization verification tool failed")
                break
            output = result.stdout + result.stderr
            if tool == "codesign-detail":
                codesign_detail_output = output
            elif tool == "spctl":
                spctl_output = output
            if result.returncode != 0:
                errors.append("macOS signing or notarization verification failed")
                break
        team_ids = _CODESIGN_TEAM_RE.findall(codesign_detail_output)
        if signing and team_ids != [EXPECTED_DEVELOPER_ID_TEAM]:
            errors.append("runtime signing team does not match the pinned operator identity")
        hardened = any(
            int(match.group(1), 16) & 0x10000
            for match in _CODESIGN_FLAGS_RE.finditer(codesign_detail_output)
        )
        if not hardened:
            errors.append("runtime hardened-signing flags are missing")
        codesign_timestamp = _secure_codesign_timestamp(codesign_detail_output)
        if not codesign_timestamp:
            errors.append("runtime code signature is missing a secure Timestamp")
        spctl_source = _spctl_source(spctl_output)
        if not spctl_source:
            errors.append("runtime notarization source is not exactly Notarized Developer ID")
    evidence = {
        "schema_version": 1,
        "git_sha": git_sha,
        "manifest_sha256": _sha256(manifest_path) if manifest_path.is_file() else "",
        "artifact_path": (PLUGIN_REL / RUNTIME_REL).as_posix(),
        "artifact_sha256": digest,
        "signing_policy_sha256": signing_policy_sha256,
        "team_id": signing.get("team_id", "") if isinstance(signing, dict) else "",
        "codesign_timestamp": codesign_timestamp,
        "spctl_source": spctl_source,
        "codesign_verified": not errors,
        "notarization_verified": not errors,
        "hardened_runtime_verified": not errors,
        "macho_arch_verified": macho_arch_verified,
        "minimum_macos_verified": minimum_macos_verified,
    }
    return not errors, evidence, errors


def verify_evidence(root: Path, evidence_path: Path, *, git_sha: str) -> list[str]:
    root = root.resolve()
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return ["runtime verification evidence is unreadable"]
    expected_keys = {
        "schema_version",
        "git_sha",
        "manifest_sha256",
        "artifact_path",
        "artifact_sha256",
        "signing_policy_sha256",
        "team_id",
        "codesign_timestamp",
        "spctl_source",
        "codesign_verified",
        "notarization_verified",
        "hardened_runtime_verified",
        "macho_arch_verified",
        "minimum_macos_verified",
    }
    errors: list[str] = []
    if not isinstance(evidence, dict) or set(evidence) != expected_keys:
        return ["runtime verification evidence shape is invalid"]
    if (
        not _exact_int(evidence.get("schema_version"), 1)
        or evidence.get("git_sha") != git_sha
        or evidence.get("artifact_path") != (PLUGIN_REL / RUNTIME_REL).as_posix()
        or not isinstance(evidence.get("codesign_timestamp"), str)
        or not _secure_codesign_timestamp(
            f"Timestamp={evidence.get('codesign_timestamp', '')}"
        )
        or evidence.get("spctl_source") != "Notarized Developer ID"
        or evidence.get("codesign_verified") is not True
        or evidence.get("notarization_verified") is not True
        or evidence.get("hardened_runtime_verified") is not True
        or evidence.get("macho_arch_verified") is not True
        or evidence.get("minimum_macos_verified") is not True
    ):
        errors.append("runtime verification evidence is not valid for this release commit")
    manifest_path = root / MANIFEST_REL
    binary = root / PLUGIN_REL / RUNTIME_REL
    signing_policy_sha256, signing_policy_error = _signing_policy_digest(root)
    if signing_policy_error:
        errors.append(signing_policy_error)
    elif evidence.get("signing_policy_sha256") != signing_policy_sha256:
        errors.append("runtime evidence signing policy digest mismatch")
    try:
        if evidence.get("manifest_sha256") != _sha256(manifest_path):
            errors.append("runtime evidence manifest digest mismatch")
        if evidence.get("artifact_sha256") != _sha256(binary):
            errors.append("runtime evidence artifact digest mismatch")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        signing = manifest["artifacts"][0]["signing"]
        if evidence.get("team_id") != signing.get("team_id"):
            errors.append("runtime evidence signing team mismatch")
        if evidence.get("team_id") != EXPECTED_DEVELOPER_ID_TEAM:
            errors.append("runtime evidence does not match the pinned operator identity")
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        errors.append("runtime evidence cannot be bound to the packaged artifact")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--git-sha", default=os.environ.get("GITHUB_SHA", "local"))
    parser.add_argument("--write-evidence", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args(argv)
    if args.evidence:
        errors = verify_evidence(args.repo_root, args.evidence, git_sha=args.git_sha)
        evidence: dict[str, Any] = {}
        ok = not errors
    else:
        ok, evidence, errors = verify_release(args.repo_root, git_sha=args.git_sha)
    for error in errors:
        print(f"FAIL: {error}")
    if not ok:
        return 1
    if args.write_evidence:
        args.write_evidence.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print("PASS: signed/notarized runtime release evidence verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
