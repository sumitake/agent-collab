#!/usr/bin/env python3
"""Build and verify the canonical public agent-collab plugin archive."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
import re
import stat
import tarfile
import zlib
from pathlib import Path, PurePosixPath

try:
    from scripts.skill_structure import expected_skill_relpaths, skill_tree_differences
except ModuleNotFoundError:  # direct `python3 scripts/build_plugin_archive.py`
    from skill_structure import expected_skill_relpaths, skill_tree_differences


REPO_ROOT = Path(__file__).resolve().parents[1]
SPECS_DIR = REPO_ROOT / "skill-specs"
PLUGIN_NAME = "agent-collab"
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
RUNTIME_BUNDLE_REL = Path("runtime/darwin-arm64/agent-collab-runtime.bundle")
RUNTIME_REL = RUNTIME_BUNDLE_REL / "agent-collab-runtime"
RUNTIME_FILE_MODE = 0o500
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
    "runtime_bundle.py",
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


def _load_runtime_bundle_contract():
    path = REPO_ROOT / "plugins" / PLUGIN_NAME / "runtime_bundle.py"
    spec = importlib.util.spec_from_file_location(
        "agent_collab_archive_runtime_bundle", path
    )
    if spec is None or spec.loader is None:
        raise ValueError("runtime bundle contract cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime_bundle = _load_runtime_bundle_contract()


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


def _read_manifest_bytes(plugin_path: Path) -> bytes:
    """Read the committed manifest exactly once for a frozen-snapshot check.

    The read goes through a single O_NOFOLLOW descriptor whose fstat is
    checked, so the snapshot is one coherent read of one regular file — a
    concurrent swap yields either the old bytes or the new bytes, never a
    mixture, and everything downstream derives from the returned snapshot.
    """

    manifest_path = plugin_path / "runtime-manifest.json"
    info = _safe_source(manifest_path)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("runtime-manifest.json is not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(manifest_path, flags)
    except OSError as exc:
        raise ValueError("runtime manifest is unreadable") from exc
    try:
        described = os.fstat(descriptor)
        if not stat.S_ISREG(described.st_mode):
            raise ValueError("runtime-manifest.json is not a regular file")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            if sum(len(part) for part in chunks) > MAX_ARTIFACT_BYTES:
                raise ValueError("runtime manifest is unreasonably large")
        return b"".join(chunks)
    except OSError as exc:
        raise ValueError("runtime manifest is unreadable") from exc
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _parse_manifest(data: bytes) -> dict[str, object]:
    try:
        manifest = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("runtime manifest is unreadable") from exc
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {
            "schema_version",
            "protocol_version",
            "contract_version",
            "broker_protocol_version",
            "channel",
            "artifacts",
        }
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 2
        or type(manifest.get("protocol_version")) is not int
        or manifest["protocol_version"] != 1
        or type(manifest.get("contract_version")) is not int
        or manifest["contract_version"] != 3
        or type(manifest.get("broker_protocol_version")) is not int
        or manifest["broker_protocol_version"] != 2
        or manifest.get("channel") != "production"
        or not isinstance(manifest.get("artifacts"), list)
    ):
        raise ValueError("runtime manifest root or version is invalid")
    return manifest


def _load_manifest(plugin_path: Path) -> dict[str, object]:
    return _parse_manifest(_read_manifest_bytes(plugin_path))


def _validate_activation_manifest(item: object) -> tuple[dict[str, object], ...]:
    """Validate the activation artifact SHAPE from the committed manifest only.

    Deliberately touches no filesystem bundle state: with the signed runtime
    shipped as a release asset (never committed), the committed manifest is the
    activation marker (design decision D1) and the physical bundle bytes are
    validated separately against wherever they are sourced from
    (`_validate_activation_bundle_tree`).
    """

    fields = {
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
    try:
        records = runtime_bundle.validate_file_records(item.get("files"))
        bundle_digest = runtime_bundle.compute_bundle_identity(records)
    except runtime_bundle.BundleContractError:
        records = ()
        bundle_digest = ""
    identity = signing.get("identity") if isinstance(signing, dict) else None
    identity_match = (
        re.fullmatch(
            r"Developer ID Application: [^\r\n]{1,160} \(([A-Z0-9]{10})\)",
            identity,
        )
        if isinstance(identity, str)
        else None
    )
    if (
        item.get("platform") != "darwin"
        or item.get("arch") != "arm64"
        or item.get("kind") != "standalone_bundle"
        or item.get("minimum_macos") != "14.0"
        or item.get("path") != RUNTIME_BUNDLE_REL.as_posix()
        or item.get("entrypoint") != runtime_bundle.ENTRYPOINT_NAME
        or type(item.get("size")) is not int
        or not 1 <= item["size"] <= MAX_ARTIFACT_BYTES
        or item["size"] != sum(record["size"] for record in records)
        or not isinstance(item.get("sha256"), str)
        or _SHA256_RE.fullmatch(item["sha256"]) is None
        or item["sha256"] != bundle_digest
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
        or signing.get("require_notarization") is not True
        or signing.get("hardened_runtime") is not True
        or signing.get("secure_timestamp") is not True
        or any(
            record["signing_profile"] != "production_developer_id"
            for record in records
        )
        or not isinstance(contracts_value, list)
        or contracts != REQUIRED_CONTRACTS
        or len(contracts_value) != len(contracts)
    ):
        raise ValueError("activation runtime manifest fields are invalid")
    return records


def _validate_activation_bundle_tree(
    bundle_leaf: Path, records: tuple[dict[str, object], ...]
) -> None:
    """Validate the physical runtime bundle leaf directory against the manifest.

    The leaf is HOSTILE input (an operator-supplied out-of-tree handoff):
    enumerate it bounded and non-following, require member-set EQUALITY with
    the manifest records, and admit only regular files owned by the invoking
    user with nlink 1, the exact install mode, exact size, and exact sha256.
    Devices, FIFOs, sockets, and symlinks all fail the S_ISREG/O_NOFOLLOW
    checks. `validate_file_records` has already rejected traversal, separator
    confusables, and Unicode-normalization/case-fold collisions in the paths.
    """

    try:
        leaf_info = bundle_leaf.lstat()
    except OSError as exc:
        raise ValueError("runtime bundle source is missing") from exc
    if (
        stat.S_ISLNK(leaf_info.st_mode)
        or not stat.S_ISDIR(leaf_info.st_mode)
        or leaf_info.st_uid != os.getuid()
        or stat.S_IMODE(leaf_info.st_mode) != runtime_bundle.INSTALL_MODE
    ):
        raise ValueError("runtime bundle source root identity is invalid")
    expected_names = {record["path"] for record in records}
    observed_names: set[str] = set()
    try:
        with os.scandir(bundle_leaf) as entries:
            for entry in entries:
                observed_names.add(entry.name)
                if len(observed_names) > len(expected_names):
                    raise ValueError(
                        "runtime bundle source membership is not exact"
                    )
    except OSError as exc:
        raise ValueError("runtime bundle source could not be enumerated") from exc
    if observed_names != expected_names:
        raise ValueError("runtime bundle source membership is not exact")
    member_flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)  # a swapped FIFO must not block the open
    )
    for record in records:
        member = bundle_leaf / record["path"]
        try:
            lexical = member.lstat()
            descriptor = os.open(member, member_flags)
        except OSError as exc:
            raise ValueError("runtime bundle source member is unsafe") from exc
        try:
            info = os.fstat(descriptor)
            if (
                stat.S_ISLNK(lexical.st_mode)
                or not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != record["install_mode"]
                or info.st_size != record["size"]
            ):
                raise ValueError(
                    "runtime bundle source member identity is invalid"
                )
            digest = hashlib.sha256()
            read_total = 0
            while read_total <= record["size"]:
                # Cap the read at the fstat'd size: a file that grows after the
                # fstat cannot cause unbounded reading.
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                read_total += len(chunk)
                digest.update(chunk)
            if read_total != record["size"] or digest.hexdigest() != record["sha256"]:
                raise ValueError("runtime bundle source member digest is invalid")
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _classify_from_manifest(
    plugin_path: Path, manifest_bytes: bytes
) -> tuple[str, tuple[dict[str, object], ...]]:
    """Classify + fully validate the package from ONE manifest byte snapshot.

    The mode decision, the full activation-manifest shape validation, and the
    runtime records ALL derive from the same ``manifest_bytes`` — so a caller
    that freezes the manifest once and passes those exact bytes here cannot be
    raced (an A→B→A manifest swap between classification and packing is
    impossible; the frozen bytes are the single source).
    """

    policy = plugin_path / "signing_policy.py"
    policy_info = _safe_source(policy)
    if not stat.S_ISREG(policy_info.st_mode):
        raise ValueError("signing_policy.py must be a regular file")
    manifest = _parse_manifest(manifest_bytes)
    artifacts = manifest["artifacts"]
    runtime_root = plugin_path / "runtime"
    if not artifacts:
        if runtime_root.exists() or runtime_root.is_symlink():
            raise ValueError("policy-only package contains an unadvertised runtime")
        return "policy-only", ()
    if len(artifacts) != 1:
        raise ValueError("activation package requires exactly one runtime artifact")
    # D1: the committed manifest is the activation marker. The physical bundle
    # is NOT read here — it ships as a release asset (never committed) and is
    # validated against its actual source by `_validate_activation_bundle_tree`
    # (build) and against the frozen manifest records (verify_archive).
    records = _validate_activation_manifest(artifacts[0])
    return "activation", records


def classify_package(plugin_path: Path) -> str:
    plugin_path = plugin_path.resolve(strict=True)
    mode, _records = _classify_from_manifest(
        plugin_path, _read_manifest_bytes(plugin_path)
    )
    return mode


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


# Runtime DIRECTORY members are packaging scaffolding, synthesized with fixed
# canonical metadata — never statted from a mutable source tree. The two
# traversal parents are plain 0o755 directories; the bundle leaf itself keeps
# the sealed install mode.
_RUNTIME_DIR_MODES: dict[str, int] = {
    "runtime": 0o755,
    "runtime/darwin-arm64": 0o755,
    RUNTIME_BUNDLE_REL.as_posix(): runtime_bundle.INSTALL_MODE,
}


def _member_plan(
    plugin_path: Path,
    *,
    mode: str,
    records: tuple[dict[str, object], ...] = (),
) -> list[tuple[str, Path | None]]:
    """Return the canonical (archive name, source path) plan, sorted by name.

    Runtime members carry a ``None`` source: their archive metadata derives
    entirely from the frozen manifest ``records`` (and `_RUNTIME_DIR_MODES`),
    never from a stat of a mutable tree. Every other member is sourced from
    the git-tracked plugin tree.
    """

    if mode not in {"policy-only", "activation"}:
        raise ValueError("unknown archive mode")
    if mode == "activation" and not records:
        raise ValueError("activation member plan requires frozen manifest records")
    if mode == "policy-only" and records:
        raise ValueError("policy-only member plan forbids runtime records")
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
    members: dict[str, Path | None] = {}
    if mode == "activation":
        _require_exact_third_party_notice_tree(plugin_path)
        relatives.extend(ACTIVATION_THIRD_PARTY_MEMBERS)
        for name in _RUNTIME_DIR_MODES:
            members[name] = None
        for record in records:
            members[(RUNTIME_BUNDLE_REL / record["path"]).as_posix()] = None
    for relative in relatives:
        source = plugin_path / relative
        _safe_source(source)
        members[relative.as_posix()] = source
    return [(name, members[name]) for name in sorted(members)]


# Hard resource bounds for reading a possibly-hostile archive. The verifier
# NEVER parses hostile tar/PAX bytes: it regenerates the ONE canonical tar from
# trusted inputs and byte-compares, so a candidate archive is only ever sliced
# by offsets WE computed. Only the bounded gzip inflater touches candidate
# bytes, under hard compressed- and decompressed-size caps.
#
# The runtime payload alone may be as large as MAX_ARTIFACT_BYTES (64 MiB); the
# archive additionally holds the manifest, skills, licenses, plugin metadata,
# tar headers/padding, and gzip framing, and a poorly-compressible (already
# compressed/encrypted) runtime near the limit barely shrinks. So BOTH the
# compressed and decompressed caps carry headroom above the payload cap
# (2x = 128 MiB) — otherwise the builder could reject its OWN legitimate output
# — while the decompressed cap still bounds a gzip bomb well below memory
# exhaustion.
_MAX_COMPRESSED_ARCHIVE_BYTES = 2 * MAX_ARTIFACT_BYTES
_MAX_DECOMPRESSED_ARCHIVE_BYTES = 2 * MAX_ARTIFACT_BYTES
_USTAR_BLOCK = 512
# The complete fixed canonical 10-byte gzip header the builder emits: magic
# (1f 8b), DEFLATE method (08), flags 0 (rejects FTEXT/FHCRC/FEXTRA/FNAME/
# FCOMMENT — the malleability/amplification vectors), mtime 0, XFL 02
# (best-compression, GzipFile default level 9), OS ff (unknown). CPython's gzip
# writes XFL and OS deterministically (hardcoded ff for OS; 02 for level 9), so
# binding all ten is byte-reproducible across the operator's build Python and
# CI's 3.10/3.12/3.14 — and the build→verify round-trip tests fail closed on
# any version that diverges rather than silently accepting a variant.
_CANONICAL_GZIP_HEADER = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff"


def _synthesized_tarinfo(
    name: str, *, mode: int, size: int = 0, directory: bool = False
) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.mode = mode
    info.size = size
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def _finalize_tarinfo(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    if info.pax_headers:
        # USTAR_FORMAT would already have raised for an unrepresentable field;
        # this belt-and-suspenders makes it impossible to emit an extension
        # record so build and verify are byte-reproducible across environments.
        raise ValueError(f"archive member is not USTAR-representable: {info.name}")
    return info


def _emit_canonical_tar(
    plan: list[tuple[str, Path | None]],
    *,
    plugin_path: Path,
    frozen_manifest: bytes | None,
    record_by_name: dict[str, dict[str, object]],
    runtime_payloads: dict[str, bytes],
) -> tuple[bytes, dict[str, tuple[int, int]]]:
    """Serialize the ONE canonical uncompressed tar deterministically.

    USTAR_FORMAT (tarfile raises on anything needing a PAX/GNU extension
    record), zeroed ownership/mtime, exact ``_member_plan`` order. Non-runtime
    payloads come from the trusted ``plugin_path`` tree (the manifest member
    from ``frozen_manifest``); runtime FILE payloads come from
    ``runtime_payloads`` (real bytes at build, zero-fill at verify). Both build
    and verify call this, so they produce byte-identical structure. Returns
    ``(tar_bytes, runtime_ranges)`` mapping each runtime file member name to its
    ``(data_offset, length)`` within the tar.
    """

    buffer = io.BytesIO()
    ranges: dict[str, tuple[int, int]] = {}
    with tarfile.open(
        fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT
    ) as tar:
        for name, source in plan:
            if source is None and name in _RUNTIME_DIR_MODES:
                tar.addfile(
                    _finalize_tarinfo(
                        _synthesized_tarinfo(
                            name, mode=_RUNTIME_DIR_MODES[name], directory=True
                        )
                    )
                )
                continue
            if source is None:
                record = record_by_name[name]
                payload = runtime_payloads[name]
                if len(payload) != record["size"]:
                    raise ValueError("runtime payload size mismatch during emit")
                info = _finalize_tarinfo(
                    _synthesized_tarinfo(
                        name, mode=record["install_mode"], size=record["size"]
                    )
                )
                header_offset = buffer.tell()
                tar.addfile(info, io.BytesIO(payload))
                ranges[name] = (header_offset + _USTAR_BLOCK, record["size"])
                continue
            info = tar.gettarinfo(str(source), arcname=name)
            # git tracks ONLY the exec bit, but a working-tree checkout applies
            # the local umask to the rest — so normalize non-runtime modes to
            # 0o755/0o644 by the exec bit alone. Without this the operator's
            # build host and CI (different umask, different checkouts) could
            # emit different mode fields and the verify byte-compare would
            # false-reject a legitimate archive.
            info.mode = 0o755 if (info.isdir() or (info.mode & 0o111)) else 0o644
            info = _finalize_tarinfo(info)
            if name == "runtime-manifest.json" and frozen_manifest is not None:
                info.size = len(frozen_manifest)
                tar.addfile(info, io.BytesIO(frozen_manifest))
            elif info.isfile():
                with source.open("rb") as stream:
                    tar.addfile(info, stream)
            else:
                tar.addfile(info)
    return buffer.getvalue(), ranges


def _read_bounded_compressed(archive_path: Path) -> bytes:
    """Read the compressed archive fd-only under a hard size cap.

    ``O_NOFOLLOW`` refuses a symlinked final component; ``O_NONBLOCK`` keeps a
    substituted FIFO from blocking the open before the ``fstat`` regular-file
    check; the cap is enforced on the bytes ACTUALLY read from the descriptor,
    so a path swap or post-fstat growth cannot smuggle input past it. There is
    no ``lstat``→``open`` window.
    """

    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(archive_path, flags)
    except OSError as exc:
        raise ValueError("plugin archive is unreadable") from exc
    chunks: list[bytes] = []
    total = 0
    try:
        described = os.fstat(descriptor)
        if not stat.S_ISREG(described.st_mode):
            raise ValueError("plugin archive is unreadable")
        if described.st_size > _MAX_COMPRESSED_ARCHIVE_BYTES:
            raise ValueError("plugin archive exceeds the canonical size bound")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_COMPRESSED_ARCHIVE_BYTES:
                raise ValueError("plugin archive exceeds the canonical size bound")
            chunks.append(chunk)
    except OSError as exc:
        raise ValueError("plugin archive is unreadable") from exc
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
    return b"".join(chunks)


def _inflate_bounded(compressed: bytes) -> bytes:
    """Inflate a single gzip stream under a hard output cap.

    Binds the fixed canonical gzip header, caps decompressed OUTPUT per call
    (so a bomb trips before materializing the expansion), validates CRC/ISIZE
    (zlib raises on mismatch at end-of-stream), and requires the stream to be
    complete with NO trailing/concatenated data.
    """

    if compressed[:10] != _CANONICAL_GZIP_HEADER:
        raise ValueError("plugin archive gzip header is not canonical")
    decompressor = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    chunk_size = 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    pending = compressed
    try:
        while not decompressor.eof:
            before = len(pending)
            piece = decompressor.decompress(pending, chunk_size)
            pending = decompressor.unconsumed_tail
            if piece:
                total += len(piece)
                if total > _MAX_DECOMPRESSED_ARCHIVE_BYTES:
                    raise ValueError(
                        "plugin archive decompression exceeds the canonical bound"
                    )
                chunks.append(piece)
            elif len(pending) >= before:
                # No output produced and no input consumed: the stream cannot
                # make progress (truncated/malformed). Stop; the eof check below
                # rejects it.
                break
    except zlib.error as exc:
        raise ValueError("plugin archive is unreadable") from exc
    if not decompressor.eof:
        raise ValueError("plugin archive gzip stream is incomplete")
    if decompressor.unused_data:
        raise ValueError("plugin archive has trailing data after the gzip stream")
    return b"".join(chunks)


def _assert_runtime_range_map(
    ranges: dict[str, tuple[int, int]],
    record_by_name: dict[str, dict[str, object]],
    total_length: int,
) -> None:
    """Assert the regenerated runtime range map is well-formed (design item 6).

    Complete + one-to-one with the manifest runtime entries, each range
    exact-length, in-bounds, and pairwise disjoint. The archived
    ``runtime-manifest.json`` member is non-runtime by construction and thus
    lies OUTSIDE every range (bound by the structural byte-compare).
    """

    if set(ranges) != set(record_by_name):
        raise ValueError("archive runtime range map is not one-to-one with the manifest")
    for name, (offset, length) in ranges.items():
        if length != record_by_name[name]["size"]:
            raise ValueError("archive runtime range length does not match the manifest")
    previous_end = 0
    for offset, length in sorted(ranges.values()):
        if offset < previous_end or offset < 0 or offset + length > total_length:
            raise ValueError("archive runtime range map is out of bounds or overlapping")
        previous_end = offset + length


def _bytes_equal_outside_ranges(
    candidate: bytes, canonical: bytes, ranges: list[tuple[int, int]]
) -> bool:
    """True iff candidate == canonical at every byte NOT inside a runtime range."""

    position = 0
    for offset, length in sorted(ranges):
        if candidate[position:offset] != canonical[position:offset]:
            return False
        position = offset + length
    return candidate[position:] == canonical[position:]


def verify_archive(
    plugin_path: Path,
    archive_path: Path,
    *,
    mode: str,
    frozen_manifest: bytes | None = None,
) -> None:
    """Verify a built archive by REGENERATING the canonical tar and comparing.

    The candidate archive's tar bytes are never handed to ``tarfile``. Instead
    the ONE canonical tar is regenerated from trusted inputs (plugin tree +
    frozen manifest) with runtime payloads zero-filled; the candidate is only
    bounded-inflated and then sliced by offsets WE computed. Every structural
    property (headers, typeflags, ordering, padding, EOF, dialect, no hidden
    records) is bound by the byte-compare OUTSIDE the runtime ranges; each
    runtime payload is bound to the frozen-manifest digest. ``frozen_manifest``
    lets ``build_archive`` share the exact snapshot it packed; CI omits it and
    reads the snapshot once from the signed-tag checkout.
    """

    plugin_path = plugin_path.resolve(strict=True)
    # Freeze ONE manifest snapshot: mode classification, full shape validation,
    # runtime records, and the embedded manifest member all derive from it (a
    # caller-supplied snapshot from build_archive, or a single read here in CI).
    if frozen_manifest is None:
        frozen_manifest = _read_manifest_bytes(plugin_path)
    resolved_mode, records = _classify_from_manifest(plugin_path, frozen_manifest)
    if resolved_mode != mode:
        raise ValueError("archive mode no longer matches the source package")
    plan = _member_plan(plugin_path, mode=mode, records=records)
    record_by_name = {
        (RUNTIME_BUNDLE_REL / record["path"]).as_posix(): record for record in records
    }
    zero_payloads = {
        name: b"\x00" * record["size"] for name, record in record_by_name.items()
    }
    canonical, ranges = _emit_canonical_tar(
        plan,
        plugin_path=plugin_path,
        frozen_manifest=frozen_manifest,
        record_by_name=record_by_name,
        runtime_payloads=zero_payloads,
    )
    candidate = _inflate_bounded(_read_bounded_compressed(archive_path))
    if len(candidate) != len(canonical):
        raise ValueError("archive does not match the canonical layout")
    _assert_runtime_range_map(ranges, record_by_name, len(canonical))
    for name, (offset, length) in ranges.items():
        record = record_by_name[name]
        if (
            length != record["size"]
            or hashlib.sha256(candidate[offset : offset + length]).hexdigest()
            != record["sha256"]
        ):
            raise ValueError(f"archive runtime member digest failed: {name}")
    if not _bytes_equal_outside_ranges(candidate, canonical, list(ranges.values())):
        raise ValueError("archive structure does not match the canonical layout")


def _read_runtime_payloads(
    bundle_leaf: Path, records: tuple[dict[str, object], ...]
) -> dict[str, bytes]:
    """Read + re-validate + re-digest each runtime payload into memory.

    Reading through a fresh ``O_NOFOLLOW``/``O_NONBLOCK`` descriptor and
    re-checking identity here binds the EXACT bytes that will be emitted into
    the archive (closing any window between the earlier tree validation and the
    pack) — and the bytes are additionally re-bound to the manifest digest by
    ``verify_archive`` on the temp before publish.
    """

    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    payloads: dict[str, bytes] = {}
    for record in records:
        name = (RUNTIME_BUNDLE_REL / record["path"]).as_posix()
        try:
            descriptor = os.open(bundle_leaf / record["path"], flags)
        except OSError as exc:
            raise ValueError("runtime bundle source member is unsafe") from exc
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != record["install_mode"]
                or info.st_size != record["size"]
            ):
                raise ValueError("runtime bundle source member changed during packing")
            parts: list[bytes] = []
            read_total = 0
            while read_total <= record["size"]:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                parts.append(chunk)
                read_total += len(chunk)
            data = b"".join(parts)
            if (
                len(data) != record["size"]
                or hashlib.sha256(data).hexdigest() != record["sha256"]
            ):
                raise ValueError("runtime bundle source member changed during packing")
            payloads[name] = data
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass
    return payloads


def build_archive(
    root: Path,
    *,
    plugin: str,
    output: Path,
    bundle_source: Path | None = None,
) -> str:
    if plugin != PLUGIN_NAME:
        raise ValueError("agent-collab is the only releaseable plugin")
    plugin_path = (root / "plugins" / plugin).resolve(strict=True)
    # Freeze the manifest ONCE: mode classification, full shape validation,
    # runtime records, the bundle-tree validation, the embedded manifest member,
    # and verify_archive ALL derive from this single snapshot, so a mid-build
    # A→B→A manifest swap on disk cannot change what gets packaged.
    frozen_manifest: bytes | None = _read_manifest_bytes(plugin_path)
    mode, records = _classify_from_manifest(plugin_path, frozen_manifest)
    bundle_leaf: Path | None = None
    runtime_payloads: dict[str, bytes] = {}
    if mode == "policy-only":
        # The committed manifest — never the flag — decides the mode.
        if bundle_source is not None:
            raise ValueError("policy-only manifest forbids --bundle-source")
    else:
        # Fail closed: an activation manifest without a matching signed bundle
        # source is a hard error, never a silent policy-only downgrade.
        if bundle_source is None:
            raise ValueError("activation manifest requires --bundle-source")
        runtime_root = plugin_path / "runtime"
        if runtime_root.exists() or runtime_root.is_symlink():
            raise ValueError(
                "in-tree runtime conflicts with --bundle-source; remove one source"
            )
        try:
            raw_source = bundle_source.lstat()
        except OSError as exc:
            raise ValueError("runtime bundle source is missing") from exc
        # lstat the raw CLI argument BEFORE resolving — resolve() would erase
        # the evidence that the argument itself was a symlink.
        if stat.S_ISLNK(raw_source.st_mode) or not stat.S_ISDIR(raw_source.st_mode):
            raise ValueError("runtime bundle source is unsafe")
        bundle_leaf = bundle_source.resolve(strict=True)
        _validate_activation_bundle_tree(bundle_leaf, records)
        runtime_payloads = _read_runtime_payloads(bundle_leaf, records)
    plan = _member_plan(plugin_path, mode=mode, records=records)
    record_by_name = {
        (RUNTIME_BUNDLE_REL / record["path"]).as_posix(): record for record in records
    }

    def _reject_source_alias(candidate: Path) -> None:
        for forbidden in (plugin_path, bundle_leaf):
            if forbidden is not None and candidate.is_relative_to(forbidden):
                raise ValueError("archive output must not alias a source tree")

    # Reject a source-tree destination BEFORE creating any directory (mkdir must
    # never mutate a rejected destination), then re-check the strictly resolved
    # path once the parent exists.
    _reject_source_alias(output.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output_resolved = output.parent.resolve(strict=True) / output.name
    _reject_source_alias(output_resolved)
    # Regenerate the ONE canonical tar (shared with verify_archive), then gzip
    # it into an exclusive temp, verify THAT, and only then os.replace() to the
    # destination — a failed build or verification never leaves a publishable
    # artifact. The pid-suffixed temp name is predictable: in a shared/
    # world-writable output dir an adversary could pre-create it as a DoS
    # (O_EXCL fails, their file survives untouched — integrity unaffected).
    # Release builds write to operator-owned directories.
    canonical_tar, _ranges = _emit_canonical_tar(
        plan,
        plugin_path=plugin_path,
        frozen_manifest=frozen_manifest,
        record_by_name=record_by_name,
        runtime_payloads=runtime_payloads,
    )
    temp_path = output_resolved.parent / f".{output_resolved.name}.tmp.{os.getpid()}"
    temp_created = False
    try:
        # Owner-only (0o600): the archive is read + uploaded by the building
        # user; no other local user needs read access to the release artifact.
        descriptor = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        temp_created = True
        with os.fdopen(descriptor, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
                compressed.write(canonical_tar)
        verify_archive(
            plugin_path, temp_path, mode=mode, frozen_manifest=frozen_manifest
        )
        os.replace(temp_path, output_resolved)
    except BaseException:
        if temp_created:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        raise
    return mode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--plugin", default=PLUGIN_NAME)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-mode", action="store_true")
    parser.add_argument(
        "--bundle-source",
        type=Path,
        default=None,
        help=(
            "path to the signed runtime bundle leaf directory "
            "(…/agent-collab-runtime.bundle) from the local release handoff; "
            "required for an activation manifest, forbidden for policy-only"
        ),
    )
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
        mode = build_archive(
            args.repo_root,
            plugin=args.plugin,
            output=args.output,
            bundle_source=args.bundle_source,
        )
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"PASS: built and verified canonical {mode} plugin archive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
