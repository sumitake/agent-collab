#!/usr/bin/env python3
"""Build deterministic SHA-256 and SPDX 2.3 evidence for a plugin archive."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
import tarfile
from pathlib import Path, PurePosixPath

try:
    from scripts import build_plugin_archive as archive_builder
except ImportError:  # direct `python3 scripts/build_release_evidence.py`
    import build_plugin_archive as archive_builder


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "agent-collab"
MANIFEST_LICENSE = "PolyForm-Strict-1.0.0"
SPDX_LICENSE = "LicenseRef-PolyForm-Strict-1.0.0"
LICENSE_SHA256 = "9eb48619fbc193ab7bb327b090cfcc703000265b83e670f81f231d0b1c43c56e"
COPYRIGHT_TEXT = (
    "Copyright (c) 2026 John Osumi. All rights reserved except as expressly granted."
)
LEGAL_FILES = ("COMMERCIAL-LICENSING.md", "LICENSE", "NOTICE")
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOTAL_FILE_BYTES = 128 * 1024 * 1024
MAX_MEMBERS = 4096
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_created(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("created timestamp is required")
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("created timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("created timestamp must include a timezone")
    normalized = parsed.astimezone(dt.timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def _safe_regular_file(path: Path, *, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is missing or unreadable") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(f"{label} must be one regular file with one hard link")
    return info


def _validate_output_path(path: Path, *, archive: Path) -> None:
    if path == archive or path.exists() or path.is_symlink():
        raise ValueError(f"output path already exists or aliases the archive: {path}")
    try:
        parent = path.parent.resolve(strict=True)
        info = parent.lstat()
    except OSError as exc:
        raise ValueError(f"output parent is unavailable: {path.parent}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"output parent is not a directory: {path.parent}")


def _write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor != -1:
            os.close(descriptor)


def _archive_files(archive: Path) -> dict[str, bytes]:
    info = _safe_regular_file(archive, label="release archive")
    if not 1 <= info.st_size <= MAX_ARCHIVE_BYTES:
        raise ValueError("release archive size is outside the allowed bound")
    try:
        bundle = tarfile.open(archive, "r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise ValueError("release archive is unreadable") from exc
    files: dict[str, bytes] = {}
    total = 0
    with bundle:
        members = bundle.getmembers()
        if not 1 <= len(members) <= MAX_MEMBERS:
            raise ValueError("release archive member count is outside the allowed bound")
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise ValueError("release archive contains duplicate members")
        for member in members:
            pure = PurePosixPath(member.name)
            if (
                not member.name
                or pure.is_absolute()
                or ".." in pure.parts
                or "\\" in member.name
            ):
                raise ValueError("release archive contains an unsafe member path")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("release archive contains a link or special member")
            if not 0 <= member.size <= MAX_MEMBER_BYTES:
                raise ValueError("release archive member exceeds the size bound")
            total += member.size
            if total > MAX_TOTAL_FILE_BYTES:
                raise ValueError("release archive exceeds the decompressed-size bound")
            stream = bundle.extractfile(member)
            if stream is None:
                raise ValueError("release archive member cannot be read")
            data = stream.read(MAX_MEMBER_BYTES + 1)
            if len(data) != member.size:
                raise ValueError("release archive member size is inconsistent")
            files[member.name] = data
    return files


def _manifest(files: dict[str, bytes], path: str) -> dict[str, object]:
    try:
        parsed = json.loads(files[path].decode("utf-8"))
    except (KeyError, UnicodeError, ValueError) as exc:
        raise ValueError(f"archive manifest is missing or invalid: {path}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"archive manifest root is invalid: {path}")
    return parsed


def build_evidence(
    archive: Path,
    *,
    version: str,
    created: str,
    sbom_output: Path,
    checksum_output: Path,
    repo_root: Path = REPO_ROOT,
) -> None:
    """Validate a canonical archive and write deterministic SPDX/checksum evidence."""
    archive = Path(archive)
    repo_root = Path(repo_root).resolve(strict=True)
    sbom_output = Path(sbom_output)
    checksum_output = Path(checksum_output)
    if not isinstance(version, str) or SEMVER_RE.fullmatch(version) is None:
        raise ValueError("version must be an exact X.Y.Z semantic version")
    normalized_created = _normalize_created(created)
    if sbom_output == checksum_output:
        raise ValueError("SBOM and checksum outputs must be different paths")
    _validate_output_path(sbom_output, archive=archive)
    _validate_output_path(checksum_output, archive=archive)

    plugin_root = repo_root / "plugins" / PLUGIN_NAME
    mode = archive_builder.classify_package(plugin_root)
    archive_builder.verify_archive(plugin_root, archive, mode=mode)
    files = _archive_files(archive)

    for name in LEGAL_FILES:
        root_bytes = (repo_root / name).read_bytes()
        plugin_bytes = (plugin_root / name).read_bytes()
        archive_bytes = files.get(name)
        if archive_bytes is None or not (root_bytes == plugin_bytes == archive_bytes):
            raise ValueError(f"legal-file byte parity failed: {name}")
    license_bytes = files["LICENSE"]
    if _sha256_bytes(license_bytes) != LICENSE_SHA256:
        raise ValueError("LICENSE does not match the pinned official PolyForm text")

    claude_manifest = _manifest(files, ".claude-plugin/plugin.json")
    codex_manifest = _manifest(files, ".codex-plugin/plugin.json")
    for label, manifest in (
        ("Claude", claude_manifest),
        ("Codex", codex_manifest),
    ):
        if (
            manifest.get("name") != PLUGIN_NAME
            or manifest.get("version") != version
            or manifest.get("license") != MANIFEST_LICENSE
        ):
            raise ValueError(f"{label} manifest version or license is inconsistent")

    archive_digest = _sha256_file(archive)
    spdx_files = []
    relationships = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Package-agent-collab",
        }
    ]
    for index, (name, data) in enumerate(sorted(files.items()), 1):
        spdx_id = f"SPDXRef-File-{index:04d}"
        spdx_files.append(
            {
                "SPDXID": spdx_id,
                "fileName": name,
                "checksums": [
                    {"algorithm": "SHA256", "checksumValue": _sha256_bytes(data)}
                ],
                "licenseConcluded": SPDX_LICENSE,
                "licenseInfoInFiles": [SPDX_LICENSE],
                "copyrightText": COPYRIGHT_TEXT,
            }
        )
        relationships.append(
            {
                "spdxElementId": "SPDXRef-Package-agent-collab",
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": spdx_id,
            }
        )

    sbom = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "name": f"agent-collab-v{version}",
        "documentNamespace": (
            "https://github.com/sumitake/agent-collab/releases/tag/"
            f"v{version}/agent-collab-v{version}.spdx.json"
        ),
        "creationInfo": {
            "created": normalized_created,
            "creators": ["Person: John Osumi"],
        },
        "documentDescribes": ["SPDXRef-Package-agent-collab"],
        "packages": [
            {
                "SPDXID": "SPDXRef-Package-agent-collab",
                "name": PLUGIN_NAME,
                "versionInfo": version,
                "packageFileName": archive.name,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": True,
                "checksums": [
                    {"algorithm": "SHA256", "checksumValue": archive_digest}
                ],
                "licenseConcluded": SPDX_LICENSE,
                "licenseDeclared": SPDX_LICENSE,
                "copyrightText": COPYRIGHT_TEXT,
                "supplier": "Person: John Osumi",
            }
        ],
        "files": spdx_files,
        "relationships": relationships,
        "hasExtractedLicensingInfos": [
            {
                "licenseId": SPDX_LICENSE,
                "name": "PolyForm Strict License 1.0.0",
                "extractedText": license_bytes.decode("utf-8"),
                "seeAlsos": [
                    "https://polyformproject.org/licenses/strict/1.0.0"
                ],
            }
        ],
    }
    sbom_bytes = (json.dumps(sbom, indent=2, sort_keys=True) + "\n").encode("utf-8")
    checksum_bytes = f"{archive_digest}  {archive.name}\n".encode("utf-8")
    _write_exclusive(sbom_output, sbom_bytes)
    try:
        _write_exclusive(checksum_output, checksum_bytes)
    except BaseException:
        sbom_output.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--created", required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--checksum", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        build_evidence(
            args.archive,
            version=args.version,
            created=args.created,
            sbom_output=args.sbom,
            checksum_output=args.checksum,
            repo_root=args.repo_root,
        )
    except (OSError, ValueError, tarfile.TarError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: wrote deterministic release checksum and SPDX evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
