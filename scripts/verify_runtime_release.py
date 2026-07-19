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
RUNTIME_BUNDLE_REL = Path("runtime/darwin-arm64/agent-collab-runtime.bundle")
RUNTIME_REL = RUNTIME_BUNDLE_REL / "agent-collab-runtime"
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
REQUIRED_CONTRACTS = frozenset(
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
_TEAM_ID_RE = re.compile(r"^[A-Z0-9]{10}$")
_CODESIGN_FLAGS_RE = re.compile(r"\bflags=(0x[0-9a-f]+)(?:\([^)]*\))?", re.IGNORECASE)
_CODESIGN_TIMESTAMP_RE = re.compile(r"(?m)^Timestamp=(.+)$")
_CODESIGN_TEAM_RE = re.compile(r"(?m)^TeamIdentifier=([A-Z0-9]{10})(?=\s|$)")
_CODESIGN_AUTHORITY_RE = re.compile(r"(?m)^Authority=(.+)$")
_VERSION_RE = re.compile(r"^\d+(?:\.\d+){1,2}$")
EXPECTED_MINIMUM_MACOS = "14.0"


def _load_runtime_bundle_contract():
    path = REPO_ROOT / PLUGIN_REL / "runtime_bundle.py"
    spec = importlib.util.spec_from_file_location(
        "agent_collab_release_runtime_bundle", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("runtime bundle contract cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime_bundle = _load_runtime_bundle_contract()


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
        or set(data)
        != {
            "schema_version",
            "protocol_version",
            "contract_version",
            "broker_protocol_version",
            "channel",
            "artifacts",
        }
        or not _exact_int(data.get("schema_version"), 3)
        or not _exact_int(data.get("protocol_version"), 2)
        or not _exact_int(data.get("contract_version"), 3)
        or not _exact_int(data.get("broker_protocol_version"), 2)
        or data.get("channel") != "production"
        or not isinstance(data.get("artifacts"), list)
    ):
        errors.append("runtime manifest root or version is invalid")
        return data if isinstance(data, dict) else None, manifest_path, errors
    if len(data["artifacts"]) != 1:
        errors.append("activation release requires exactly one Darwin-arm64 artifact")
    return data, manifest_path, errors


def _verify_macho_record(
    path: Path, record: dict[str, Any]
) -> tuple[bool, bool, bool, str]:
    arch_ok, minimum_ok, error = _verify_macho_identity(
        path, minimum_macos=record["minimum_macos"]
    )
    if error:
        return arch_ok, minimum_ok, False, error
    try:
        header = subprocess.run(
            ["/usr/bin/otool", "-hv", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return arch_ok, minimum_ok, False, "Mach-O type inspection tool failed"
    expected = {
        "executable": "EXECUTE",
        "dylib": "DYLIB",
        "bundle": "BUNDLE",
    }[record["macho_type"]]
    tokens = header.stdout.split()
    type_ok = header.returncode == 0 and tokens.count(expected) == 1
    return (
        arch_ok,
        minimum_ok,
        type_ok,
        "" if type_ok else "Mach-O file type does not match the manifest",
    )


def _verify_member_signature(
    path: Path,
    *,
    signing: dict[str, Any],
    assess_notarization: bool,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    try:
        verify = subprocess.run(
            ["/usr/bin/codesign", "--verify", "--strict", "--verbose=4", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        detail = subprocess.run(
            ["/usr/bin/codesign", "-dv", "--verbose=4", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return {}, ["macOS code-signing verification tool failed"]
    detail_output = detail.stdout + detail.stderr
    if verify.returncode != 0 or detail.returncode != 0:
        errors.append("macOS code-signing verification failed")
    if _CODESIGN_TEAM_RE.findall(detail_output) != [signing["team_id"]]:
        errors.append("runtime signing team does not match the pinned operator identity")
    authorities = _CODESIGN_AUTHORITY_RE.findall(detail_output)
    if not authorities or authorities[0] != signing["identity"]:
        errors.append("runtime Developer ID signing identity does not match")
    hardened = any(
        int(match.group(1), 16) & 0x10000
        for match in _CODESIGN_FLAGS_RE.finditer(detail_output)
    )
    if not hardened:
        errors.append("runtime hardened-signing flags are missing")
    timestamp = _secure_codesign_timestamp(detail_output)
    if not timestamp:
        errors.append("runtime code signature is missing a secure Timestamp")
    # The runtime entrypoint is a bare command-line Mach-O, not a .app bundle or
    # an installer package, so `spctl --assess` cannot assess it: `--type execute`
    # only assesses .app bundles (always "the code is valid but does not seem to
    # be an app"), and `--type install` is an installer-package policy whose
    # acceptance of a bare binary is empirical, not a documented contract. The
    # documented, code-object-native notarization proof is the codesign
    # requirement `notarized`, which binds to the CDHash. Empirically (exit codes):
    # a notarized Developer-ID binary passes (0); unsigned (1), ad-hoc (3), and
    # Developer-ID-signed-but-NOT-notarized (3) all fail. `--check-notarization`
    # is deliberately NOT combined — with `--test-requirement` it makes ad-hoc and
    # un-notarized binaries pass (rc 0). `spctl_source` keeps its name and its
    # "Notarized Developer ID" value (a stable cross-job evidence-schema field);
    # it is now populated from the codesign requirement result rather than spctl.
    # Offline note: a bare command-line Mach-O cannot have a notarization ticket
    # stapled (stapling targets bundles, disk images, and installer packages, not
    # standalone binaries). Without `--check-notarization` this requirement does
    # not run the online Gatekeeper lookup itself; it is satisfied by a stapled
    # ticket or the host's local notarization trust state. A bare binary relies
    # on that local state (the build host populates it at notarize time), so a
    # clean host without it fails closed, never a bypass. A `macOS notarization
    # verification tool failed` / requirement failure here is a fail-closed
    # reject, never a pass.
    spctl_source = ""
    if assess_notarization:
        try:
            assessment = subprocess.run(
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
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            errors.append("macOS notarization verification tool failed")
        else:
            if assessment.returncode == 0:
                spctl_source = "Notarized Developer ID"
            else:
                errors.append(
                    "runtime is not notarized: codesign '=notarized' requirement failed"
                )
    return {
        "codesign_timestamp": timestamp,
        "spctl_source": spctl_source,
        "codesign_verified": not errors,
        "hardened_runtime_verified": hardened,
    }, errors


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
        "kind",
        "minimum_macos",
        "path",
        "entrypoint",
        "size",
        "sha256",
        "provider_runtime_version",
        "route_contract_version",
        "signing",
        "files",
        "contracts",
    }
    if not isinstance(item, dict) or set(item) != expected_fields:
        return False, {}, ["runtime artifact manifest shape is invalid"]
    if (
        item.get("provider_runtime_version") != "2.0.0"
        or item.get("route_contract_version") != 2
    ):
        errors.append("runtime artifact contract anchor is invalid")

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
        errors.append(
            "runtime artifact does not advertise the exact required route/action contract"
        )
    try:
        records = runtime_bundle.validate_file_records(item.get("files"))
        artifact_digest = runtime_bundle.compute_bundle_identity(records)
    except runtime_bundle.BundleContractError:
        records = ()
        artifact_digest = ""
        errors.append("runtime bundle file records are invalid")

    identity_value = signing.get("identity") if isinstance(signing, dict) else None
    identity_match = (
        re.fullmatch(
            r"Developer ID Application: [^\r\n]{1,160} \(([A-Z0-9]{10})\)",
            identity_value,
        )
        if isinstance(identity_value, str)
        else None
    )
    if (
        item.get("platform") != "darwin"
        or item.get("arch") != "arm64"
        or item.get("kind") != "standalone_bundle"
        or item.get("minimum_macos") != EXPECTED_MINIMUM_MACOS
        or item.get("path") != RUNTIME_BUNDLE_REL.as_posix()
        or item.get("entrypoint") != runtime_bundle.ENTRYPOINT_NAME
        or type(item.get("size")) is not int
        or not 1 <= item["size"] <= MAX_ARTIFACT_BYTES
        or item["size"] != sum(record["size"] for record in records)
        or not isinstance(item.get("sha256"), str)
        or item["sha256"] != artifact_digest
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
        or _TEAM_ID_RE.fullmatch(signing["team_id"]) is None
        or identity_match.group(1) != signing["team_id"]
        or signing["team_id"] != EXPECTED_DEVELOPER_ID_TEAM
        or signing.get("require_notarization") is not True
        or signing.get("hardened_runtime") is not True
        or signing.get("secure_timestamp") is not True
        or any(
            record["signing_profile"] != "production_developer_id"
            for record in records
        )
    ):
        errors.append("runtime artifact platform/signing fields are invalid")

    bundle = root / PLUGIN_REL / RUNTIME_BUNDLE_REL
    try:
        bundle_info = bundle.lstat()
        names = sorted(path.name for path in bundle.iterdir())
        expected_names = [record["path"] for record in records]
        if (
            not stat.S_ISDIR(bundle_info.st_mode)
            or stat.S_ISLNK(bundle_info.st_mode)
            or bundle_info.st_uid != os.getuid()
            or stat.S_IMODE(bundle_info.st_mode) != runtime_bundle.INSTALL_MODE
            or names != expected_names
        ):
            errors.append("runtime bundle root identity or membership is unsafe")
    except OSError:
        errors.append("runtime bundle is missing or unreadable")

    file_evidence: list[dict[str, Any]] = []
    metadata_valid = not errors
    for record in records:
        member = bundle / record["path"]
        member_errors: list[str] = []
        try:
            info = member.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_ISLNK(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != record["install_mode"]
                or info.st_size != record["size"]
                or _sha256(member) != record["sha256"]
            ):
                member_errors.append("runtime bundle member identity is unsafe")
        except OSError:
            member_errors.append("runtime bundle member is missing or unreadable")
        evidence_row = {
            "path": record["path"],
            "sha256": record["sha256"],
            "codesign_timestamp": "",
            "spctl_source": "",
            "codesign_verified": False,
            "hardened_runtime_verified": False,
            "macho_arch_verified": False,
            "macho_type_verified": False,
            "minimum_macos_verified": False,
        }
        if metadata_valid and not member_errors:
            arch_ok, minimum_ok, type_ok, macho_error = _verify_macho_record(
                member, record
            )
            evidence_row["macho_arch_verified"] = arch_ok
            evidence_row["minimum_macos_verified"] = minimum_ok
            evidence_row["macho_type_verified"] = type_ok
            if macho_error:
                member_errors.append(macho_error)
            if not member_errors:
                signature_evidence, signature_errors = _verify_member_signature(
                    member,
                    signing=signing,
                    assess_notarization=record["role"] == "entrypoint",
                )
                evidence_row.update(signature_evidence)
                member_errors.extend(signature_errors)
        errors.extend(
            f"{record['path']}: {message}" for message in member_errors
        )
        file_evidence.append(evidence_row)

    if platform.system().lower() != "darwin" or platform.machine().lower() not in {
        "arm64",
        "aarch64",
    }:
        errors.append("signing verification must run on Darwin arm64")

    entrypoint_evidence = next(
        (
            row
            for row, record in zip(file_evidence, records, strict=True)
            if record["role"] == "entrypoint"
        ),
        {},
    )
    evidence = {
        "schema_version": 2,
        "git_sha": git_sha,
        "manifest_sha256": _sha256(manifest_path) if manifest_path.is_file() else "",
        "artifact_path": (PLUGIN_REL / RUNTIME_BUNDLE_REL).as_posix(),
        "artifact_sha256": artifact_digest,
        "artifact_size": item.get("size", 0),
        "files": file_evidence,
        "signing_policy_sha256": signing_policy_sha256,
        "team_id": signing.get("team_id", "") if isinstance(signing, dict) else "",
        "codesign_timestamp": entrypoint_evidence.get("codesign_timestamp", ""),
        "spctl_source": entrypoint_evidence.get("spctl_source", ""),
        "codesign_verified": bool(file_evidence)
        and all(row["codesign_verified"] for row in file_evidence),
        "notarization_verified": entrypoint_evidence.get("spctl_source")
        == "Notarized Developer ID",
        "hardened_runtime_verified": bool(file_evidence)
        and all(row["hardened_runtime_verified"] for row in file_evidence),
        "macho_arch_verified": bool(file_evidence)
        and all(row["macho_arch_verified"] for row in file_evidence),
        "macho_type_verified": bool(file_evidence)
        and all(row["macho_type_verified"] for row in file_evidence),
        "minimum_macos_verified": bool(file_evidence)
        and all(row["minimum_macos_verified"] for row in file_evidence),
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
        "artifact_size",
        "files",
        "signing_policy_sha256",
        "team_id",
        "codesign_timestamp",
        "spctl_source",
        "codesign_verified",
        "notarization_verified",
        "hardened_runtime_verified",
        "macho_arch_verified",
        "macho_type_verified",
        "minimum_macos_verified",
    }
    errors: list[str] = []
    if not isinstance(evidence, dict) or set(evidence) != expected_keys:
        return ["runtime verification evidence shape is invalid"]
    if (
        not _exact_int(evidence.get("schema_version"), 2)
        or evidence.get("git_sha") != git_sha
        or evidence.get("artifact_path")
        != (PLUGIN_REL / RUNTIME_BUNDLE_REL).as_posix()
        or type(evidence.get("artifact_size")) is not int
        or not isinstance(evidence.get("codesign_timestamp"), str)
        or not _secure_codesign_timestamp(
            f"Timestamp={evidence.get('codesign_timestamp', '')}"
        )
        or evidence.get("spctl_source") != "Notarized Developer ID"
        or evidence.get("codesign_verified") is not True
        or evidence.get("notarization_verified") is not True
        or evidence.get("hardened_runtime_verified") is not True
        or evidence.get("macho_arch_verified") is not True
        or evidence.get("macho_type_verified") is not True
        or evidence.get("minimum_macos_verified") is not True
    ):
        errors.append("runtime verification evidence is not valid for this release commit")

    manifest_path = root / MANIFEST_REL
    signing_policy_sha256, signing_policy_error = _signing_policy_digest(root)
    if signing_policy_error:
        errors.append(signing_policy_error)
    elif evidence.get("signing_policy_sha256") != signing_policy_sha256:
        errors.append("runtime evidence signing policy digest mismatch")
    try:
        if evidence.get("manifest_sha256") != _sha256(manifest_path):
            errors.append("runtime evidence manifest digest mismatch")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        item = manifest["artifacts"][0]
        records = runtime_bundle.validate_file_records(item["files"])
        artifact_digest = runtime_bundle.compute_bundle_identity(records)
        if evidence.get("artifact_sha256") != artifact_digest:
            errors.append("runtime evidence artifact digest mismatch")
        if evidence.get("artifact_size") != sum(record["size"] for record in records):
            errors.append("runtime evidence artifact size mismatch")
        signing = item["signing"]
        if evidence.get("team_id") != signing.get("team_id"):
            errors.append("runtime evidence signing team mismatch")
        if evidence.get("team_id") != EXPECTED_DEVELOPER_ID_TEAM:
            errors.append("runtime evidence does not match the pinned operator identity")

        rows = evidence.get("files")
        row_keys = {
            "path",
            "sha256",
            "codesign_timestamp",
            "spctl_source",
            "codesign_verified",
            "hardened_runtime_verified",
            "macho_arch_verified",
            "macho_type_verified",
            "minimum_macos_verified",
        }
        if (
            type(rows) is not list
            or len(rows) != len(records)
            or any(type(row) is not dict or set(row) != row_keys for row in rows)
        ):
            errors.append("runtime evidence bundle-member shape mismatch")
        else:
            for row, record in zip(rows, records, strict=True):
                member = root / PLUGIN_REL / RUNTIME_BUNDLE_REL / record["path"]
                if (
                    row["path"] != record["path"]
                    or row["sha256"] != record["sha256"]
                    or _sha256(member) != record["sha256"]
                    or not _secure_codesign_timestamp(
                        f"Timestamp={row['codesign_timestamp']}"
                    )
                    or row["codesign_verified"] is not True
                    or row["hardened_runtime_verified"] is not True
                    or row["macho_arch_verified"] is not True
                    or row["macho_type_verified"] is not True
                    or row["minimum_macos_verified"] is not True
                    or (
                        record["role"] == "entrypoint"
                        and row["spctl_source"] != "Notarized Developer ID"
                    )
                    or (
                        record["role"] != "entrypoint"
                        and row["spctl_source"] not in {"", "Notarized Developer ID"}
                    )
                ):
                    errors.append("runtime evidence bundle-member identity mismatch")
                    break
    except (
        OSError,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
        runtime_bundle.BundleContractError,
    ):
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
