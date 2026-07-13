#!/usr/bin/env python3
"""Build and verify the canonical public agent-collab plugin archive."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import stat
import tarfile
from pathlib import Path, PurePosixPath
from typing import Iterable

try:
    from scripts.skill_structure import expected_skill_relpaths, skill_tree_differences
except ModuleNotFoundError:  # direct `python3 scripts/build_plugin_archive.py`
    from skill_structure import expected_skill_relpaths, skill_tree_differences


REPO_ROOT = Path(__file__).resolve().parents[1]
SPECS_DIR = REPO_ROOT / "skill-specs"
PLUGIN_NAME = "agent-collab"
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
RUNTIME_REL = Path("runtime/darwin-arm64/agent-collab-runtime")
RUNTIME_FILE_MODE = 0o755
THIRD_PARTY_NOTICE_REL = Path("THIRD-PARTY-NOTICES.txt")
THIRD_PARTY_LICENSE_ROOT_REL = Path("third-party-licenses")
THIRD_PARTY_LICENSE_FILES = (
    "CPython-3.13.14-LICENSE.txt",
    "CPython-3.13.14-NOTICES.txt",
    "Expat-COPYING.txt",
    "HACL-LICENSE.txt",
    "Hedley-CC0-1.0.txt",
    "libb2-CC0-1.0.txt",
    "Nuitka-4.1.3-LICENSE-RUNTIME.txt",
    "Nuitka-4.1.3-LICENSE.txt",
    "Nuitka-4.1.3-NOTICE.txt",
    "mimalloc-LICENSE.txt",
    "mpdecimal-NOTICE.txt",
)
ACTIVATION_THIRD_PARTY_MEMBERS = (
    THIRD_PARTY_NOTICE_REL,
    THIRD_PARTY_LICENSE_ROOT_REL,
    *(
        THIRD_PARTY_LICENSE_ROOT_REL / name
        for name in THIRD_PARTY_LICENSE_FILES
    ),
)
ACTIVATION_THIRD_PARTY_SHA256 = {
    THIRD_PARTY_NOTICE_REL: "a80219a110e7e510724e41c781cc6f40c3b36378ff409ef1dc822e70bf38ed45",
    THIRD_PARTY_LICENSE_ROOT_REL / "CPython-3.13.14-LICENSE.txt": (
        "78b12c3a81360b357002334f0e70ea0e92eebf7a9b358805c03c48484945f3bb"
    ),
    THIRD_PARTY_LICENSE_ROOT_REL / "CPython-3.13.14-NOTICES.txt": (
        "62f2c9c2c75d511170eb464ad5f83b78cc1f37eb2eb49c2846c9aa6c4557ee99"
    ),
    THIRD_PARTY_LICENSE_ROOT_REL / "Expat-COPYING.txt": (
        "31b15de82aa19a845156169a17a5488bf597e561b2c318d159ed583139b25e87"
    ),
    THIRD_PARTY_LICENSE_ROOT_REL / "HACL-LICENSE.txt": (
        "2e04f9bb6a71ee97c24dba3c1cba0931cdfd4f95805f6c3fdf25ea82cad2c21c"
    ),
    THIRD_PARTY_LICENSE_ROOT_REL / "Hedley-CC0-1.0.txt": (
        "a77ea9231d94a8c8764ad6f41822f6b40a9c19f96dd7e36cda0c99070f9bd194"
    ),
    THIRD_PARTY_LICENSE_ROOT_REL / "libb2-CC0-1.0.txt": (
        "8b94ead716c73ba84f9f90cae9a6c8ff0505457a8c5586226947ee4e070df9b4"
    ),
    THIRD_PARTY_LICENSE_ROOT_REL / "Nuitka-4.1.3-LICENSE-RUNTIME.txt": (
        "20ff0ae581adf436a7b06e50e67a6c8913aec1ea4e60dba138d0a0bee7ee520c"
    ),
    THIRD_PARTY_LICENSE_ROOT_REL / "Nuitka-4.1.3-LICENSE.txt": (
        "0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0"
    ),
    THIRD_PARTY_LICENSE_ROOT_REL / "Nuitka-4.1.3-NOTICE.txt": (
        "b6ba5212864ec9f98842220e01b2485a2ebeb8eafa192b016b36032355c8a98d"
    ),
    THIRD_PARTY_LICENSE_ROOT_REL / "mimalloc-LICENSE.txt": (
        "19c99805e7a44a34b297a75d1edea9985e300066dfc024d5c99d4236d4573b5d"
    ),
    THIRD_PARTY_LICENSE_ROOT_REL / "mpdecimal-NOTICE.txt": (
        "e0ec71a76cdfcfc6d74f5ec78915a7f932f5c42d9b3b4f3d292b7eda5107edae"
    ),
}
REQUIRED_ROOTS = (
    ".claude-plugin",
    ".codex-plugin",
    "COMMERCIAL-LICENSING.md",
    "LICENSE",
    "NOTICE",
    "README.md",
    "skills",
    "coordinator.py",
    "runtime_client.py",
    "runtime_setup.py",
    "host_policy.py",
    "migration_doctor.py",
    "signing_policy.py",
    "runtime-manifest.json",
    "runtime-manifest.schema.json",
)
EXACT_MANIFEST_MEMBERS = (
    Path(".claude-plugin"),
    Path(".claude-plugin/plugin.json"),
    Path(".codex-plugin"),
    Path(".codex-plugin/plugin.json"),
)
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
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TEAM_ID_RE = re.compile(r"^[A-Z0-9]{10}$")
_EXCLUDED_PARTS = frozenset({".venv", "__pycache__"})
_EXCLUDED_NAMES = frozenset({".DS_Store"})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _excluded(relative: Path) -> bool:
    return (
        any(part in _EXCLUDED_PARTS for part in relative.parts)
        or relative.name in _EXCLUDED_NAMES
        or relative.suffix == ".pyc"
    )


def _safe_source(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValueError(f"required archive member is missing: {path.name}") from exc
    if stat.S_ISLNK(info.st_mode) or not (
        stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)
    ):
        raise ValueError(f"archive source member is unsafe: {path}")
    return info


def _load_manifest(plugin_path: Path) -> dict[str, object]:
    manifest_path = plugin_path / "runtime-manifest.json"
    info = _safe_source(manifest_path)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("runtime-manifest.json is not a regular file")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("runtime manifest is unreadable") from exc
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {
            "schema_version",
            "protocol_version",
            "contract_version",
            "artifacts",
        }
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
        or type(manifest.get("protocol_version")) is not int
        or manifest["protocol_version"] != 1
        or type(manifest.get("contract_version")) is not int
        or manifest["contract_version"] != 2
        or not isinstance(manifest.get("artifacts"), list)
    ):
        raise ValueError("runtime manifest root or version is invalid")
    return manifest


def _validate_activation(plugin_path: Path, item: object) -> None:
    fields = {
        "platform",
        "arch",
        "minimum_macos",
        "path",
        "size",
        "sha256",
        "signing",
        "contracts",
    }
    if not isinstance(item, dict) or set(item) != fields:
        raise ValueError("activation runtime manifest shape is invalid")
    signing = item.get("signing")
    contracts_value = item.get("contracts")
    try:
        contracts = frozenset(
            (entry["route"], entry["action"])
            for entry in contracts_value
            if isinstance(entry, dict) and set(entry) == {"route", "action"}
        )
    except (KeyError, TypeError):
        contracts = frozenset()
    if (
        item.get("platform") != "darwin"
        or item.get("arch") != "arm64"
        or item.get("minimum_macos") != "14.0"
        or item.get("path") != RUNTIME_REL.as_posix()
        or type(item.get("size")) is not int
        or not 1 <= item["size"] <= MAX_ARTIFACT_BYTES
        or not isinstance(item.get("sha256"), str)
        or _SHA256_RE.fullmatch(item["sha256"]) is None
        or not isinstance(signing, dict)
        or set(signing) != {"team_id", "require_notarization", "hardened_runtime"}
        or not isinstance(signing.get("team_id"), str)
        or _TEAM_ID_RE.fullmatch(signing["team_id"]) is None
        or signing.get("require_notarization") is not True
        or signing.get("hardened_runtime") is not True
        or not isinstance(contracts_value, list)
        or contracts != REQUIRED_CONTRACTS
        or len(contracts_value) != len(contracts)
    ):
        raise ValueError("activation runtime manifest fields are invalid")

    runtime_root = plugin_path / "runtime"
    allowed = {
        Path("runtime"),
        Path("runtime/darwin-arm64"),
        RUNTIME_REL,
    }
    observed = {path.relative_to(plugin_path) for path in runtime_root.rglob("*")}
    observed.add(Path("runtime"))
    if observed != allowed:
        raise ValueError("activation package must contain exactly one runtime executable")
    binary = plugin_path / RUNTIME_REL
    info = _safe_source(binary)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != RUNTIME_FILE_MODE
        or info.st_size != item["size"]
        or _sha256(binary) != item["sha256"]
    ):
        raise ValueError("activation runtime byte, size, ownership, or 0755 mode is invalid")


def classify_package(plugin_path: Path) -> str:
    plugin_path = plugin_path.resolve(strict=True)
    policy = plugin_path / "signing_policy.py"
    policy_info = _safe_source(policy)
    if not stat.S_ISREG(policy_info.st_mode):
        raise ValueError("signing_policy.py must be a regular file")
    manifest = _load_manifest(plugin_path)
    artifacts = manifest["artifacts"]
    runtime_root = plugin_path / "runtime"
    if not artifacts:
        if runtime_root.exists() or runtime_root.is_symlink():
            raise ValueError("policy-only package contains an unadvertised runtime")
        return "policy-only"
    if len(artifacts) != 1:
        raise ValueError("activation package requires exactly one runtime artifact")
    _validate_activation(plugin_path, artifacts[0])
    return "activation"


def _require_exact_manifest_trees(plugin_path: Path) -> None:
    for directory_name in (".claude-plugin", ".codex-plugin"):
        directory = plugin_path / directory_name
        info = _safe_source(directory)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("manifest tree is not canonical")
        observed = {
            path.relative_to(directory)
            for path in directory.rglob("*")
        }
        if observed != {Path("plugin.json")}:
            raise ValueError("manifest tree is not canonical")
        member_info = _safe_source(directory / "plugin.json")
        if not stat.S_ISREG(member_info.st_mode):
            raise ValueError("manifest tree is not canonical")


def _require_exact_third_party_notice_tree(plugin_path: Path) -> None:
    try:
        notice_info = _safe_source(plugin_path / THIRD_PARTY_NOTICE_REL)
        root = plugin_path / THIRD_PARTY_LICENSE_ROOT_REL
        root_info = _safe_source(root)
    except ValueError as exc:
        raise ValueError(
            "activation third-party notice tree is missing or unsafe"
        ) from exc
    if (
        not stat.S_ISREG(notice_info.st_mode)
        or notice_info.st_nlink != 1
        or not stat.S_ISDIR(root_info.st_mode)
    ):
        raise ValueError("activation third-party notice tree is not canonical")
    if _sha256(plugin_path / THIRD_PARTY_NOTICE_REL) != ACTIVATION_THIRD_PARTY_SHA256[
        THIRD_PARTY_NOTICE_REL
    ]:
        raise ValueError("activation third-party notice content digest is invalid")

    expected = {Path(name) for name in THIRD_PARTY_LICENSE_FILES}
    try:
        observed = {path.relative_to(root) for path in root.rglob("*")}
    except OSError as exc:
        raise ValueError("activation third-party notice tree is unreadable") from exc
    if observed != expected:
        raise ValueError("activation third-party notice tree is not canonical")
    for relative in sorted(expected):
        try:
            info = _safe_source(root / relative)
        except ValueError as exc:
            raise ValueError(
                "activation third-party notice tree contains an unsafe member"
            ) from exc
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(
                "activation third-party notice tree contains an unsafe member"
            )
        member = THIRD_PARTY_LICENSE_ROOT_REL / relative
        if _sha256(root / relative) != ACTIVATION_THIRD_PARTY_SHA256.get(member):
            raise ValueError("activation third-party notice content digest is invalid")


def _member_paths(plugin_path: Path, *, mode: str) -> list[Path]:
    if mode not in {"policy-only", "activation"}:
        raise ValueError("unknown archive mode")
    _require_exact_manifest_trees(plugin_path)
    differences = skill_tree_differences(plugin_path / "skills", SPECS_DIR)
    if differences:
        raise ValueError("skill tree is not canonical: " + ", ".join(differences))
    relatives = [
        *EXACT_MANIFEST_MEMBERS,
        *(Path(name) for name in REQUIRED_ROOTS if name not in {".claude-plugin", ".codex-plugin", "skills"}),
        Path("skills"),
        *(Path("skills") / relative for relative in expected_skill_relpaths(SPECS_DIR)),
    ]
    if mode == "activation":
        _require_exact_third_party_notice_tree(plugin_path)
        relatives.extend(
            (
                Path("runtime"),
                Path("runtime/darwin-arm64"),
                RUNTIME_REL,
                *ACTIVATION_THIRD_PARTY_MEMBERS,
            )
        )
    members: dict[str, Path] = {}
    for relative in relatives:
        source = plugin_path / relative
        _safe_source(source)
        members[relative.as_posix()] = source
    return [members[name] for name in sorted(members)]


def _canonical_names(paths: Iterable[Path], plugin_path: Path) -> list[str]:
    return [path.relative_to(plugin_path).as_posix() for path in paths]


def verify_archive(plugin_path: Path, archive_path: Path, *, mode: str) -> None:
    plugin_path = plugin_path.resolve(strict=True)
    if classify_package(plugin_path) != mode:
        raise ValueError("archive mode no longer matches the source package")
    expected_paths = _member_paths(plugin_path, mode=mode)
    expected_names = _canonical_names(expected_paths, plugin_path)
    try:
        bundle = tarfile.open(archive_path, "r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise ValueError("plugin archive is unreadable") from exc
    with bundle:
        members = bundle.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise ValueError("archive contains duplicate members")
        for name in names:
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts or "\\" in name:
                raise ValueError("archive contains an unsafe member path")
        if names != expected_names:
            raise ValueError("archive member list is not canonical")
        for source, member in zip(expected_paths, members, strict=True):
            source_info = _safe_source(source)
            source_is_file = stat.S_ISREG(source_info.st_mode)
            if source_is_file != member.isfile() or (
                not source_is_file and not member.isdir()
            ):
                raise ValueError(f"archive member type parity failed: {member.name}")
            if stat.S_IMODE(member.mode) != stat.S_IMODE(source_info.st_mode):
                raise ValueError(f"archive member mode parity failed: {member.name}")
            if source_is_file:
                archived = bundle.extractfile(member)
                if archived is None or archived.read() != source.read_bytes():
                    raise ValueError(f"archive member byte parity failed: {member.name}")
        runtime_files = [
            member.name
            for member in members
            if member.isfile() and member.name.startswith("runtime/")
        ]
        expected_runtime = [RUNTIME_REL.as_posix()] if mode == "activation" else []
        if runtime_files != expected_runtime:
            raise ValueError("archive runtime membership does not match release mode")


def build_archive(root: Path, *, plugin: str, output: Path) -> str:
    if plugin != PLUGIN_NAME:
        raise ValueError("agent-collab is the only releaseable plugin")
    plugin_path = (root / "plugins" / plugin).resolve(strict=True)
    mode = classify_package(plugin_path)
    members = _member_paths(plugin_path, mode=mode)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as bundle:
                for source in members:
                    name = source.relative_to(plugin_path).as_posix()
                    info = bundle.gettarinfo(str(source), arcname=name)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    if info.isfile():
                        with source.open("rb") as stream:
                            bundle.addfile(info, stream)
                    else:
                        bundle.addfile(info)
    verify_archive(plugin_path, output, mode=mode)
    return mode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--plugin", default=PLUGIN_NAME)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-mode", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.plugin != PLUGIN_NAME:
            raise ValueError("agent-collab is the only releaseable plugin")
        if args.print_mode:
            mode = classify_package(
                (args.repo_root / "plugins" / args.plugin).resolve(strict=True)
            )
            print(mode)
            return 0
        if args.output is None:
            raise ValueError("--output is required when building an archive")
        mode = build_archive(args.repo_root, plugin=args.plugin, output=args.output)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"PASS: built and verified canonical {mode} plugin archive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
