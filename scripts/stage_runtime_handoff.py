#!/usr/bin/env python3
"""Validate and atomically stage one sealed production runtime handoff.

The workspace builder owns production signing, notarization, and manifest
authorship.  This importer performs no build or provider invocation: it binds
the sealed handoff to the public package's existing manifest, bundle, signature,
and online notarization validators, then publishes the runtime tree followed by
the manifest as the activation marker.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile


sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_plugin_archive as archive_builder  # noqa: E402
import verify_runtime_release as release_verifier  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_REL = Path("plugins/agent-collab")
MANIFEST_NAME = "runtime-manifest.json"
SOURCE_DIRECTORY_MODE = 0o755
SOURCE_FILE_MODE = 0o755
SOURCE_MANIFEST_MODE = 0o644
SEALED_MANIFEST_MODE = 0o400


class StageRuntimeHandoffError(ValueError):
    """The handoff cannot be published without weakening its contract."""


def _raise(message: str) -> None:
    raise StageRuntimeHandoffError(message)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise StageRuntimeHandoffError("runtime handoff directory sync failed") from exc


def _write_file(path: Path, data: bytes, *, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            view = memoryview(data)
            written = 0
            while written < len(view):
                count = os.write(descriptor, view[written:])
                if count <= 0:
                    raise OSError("short runtime handoff write")
                written += count
            os.fchmod(descriptor, mode)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise StageRuntimeHandoffError("runtime handoff staging write failed") from exc


def _directory_identity(path: Path, *, label: str) -> Path:
    try:
        info = path.lstat()
    except OSError as exc:
        raise StageRuntimeHandoffError(f"{label} is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        _raise(f"{label} is unsafe")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise StageRuntimeHandoffError(f"{label} is unavailable") from exc


def _expected_handoff_tree(
    records: tuple[dict[str, object], ...],
) -> tuple[dict[str, int], dict[str, int]]:
    """Derive sealed membership from the existing artifact and file descriptors."""

    bundle = archive_builder.RUNTIME_BUNDLE_REL
    directories: dict[str, int] = {}
    current = Path()
    for part in bundle.parts:
        current /= part
        directories[current.as_posix()] = (
            archive_builder.runtime_bundle.INSTALL_MODE
            if current == bundle
            else SOURCE_DIRECTORY_MODE
        )
    files = {MANIFEST_NAME: SEALED_MANIFEST_MODE}
    files.update(
        {
            (bundle / str(record["path"])).as_posix(): int(record["install_mode"])
            for record in records
        }
    )
    return directories, files


def _validate_handoff_tree(
    root: Path, records: tuple[dict[str, object], ...]
) -> None:
    expected_directories, expected_files = _expected_handoff_tree(records)
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise StageRuntimeHandoffError("runtime handoff is unavailable") from exc
    if (
        stat.S_ISLNK(root_info.st_mode)
        or not stat.S_ISDIR(root_info.st_mode)
        or root_info.st_uid != os.geteuid()
        or stat.S_IMODE(root_info.st_mode) != SOURCE_DIRECTORY_MODE
    ):
        _raise("runtime handoff root identity is invalid")

    observed_directories: dict[str, int] = {}
    observed_files: dict[str, int] = {}
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = tuple(os.scandir(directory))
        except OSError as exc:
            raise StageRuntimeHandoffError("runtime handoff cannot be enumerated") from exc
        for entry in entries:
            try:
                info = entry.stat(follow_symlinks=False)
                relative = Path(entry.path).relative_to(root).as_posix()
            except (OSError, ValueError) as exc:
                raise StageRuntimeHandoffError("runtime handoff entry is unavailable") from exc
            if info.st_uid != os.geteuid() or stat.S_ISLNK(info.st_mode):
                _raise("runtime handoff contains an unsafe entry")
            if stat.S_ISDIR(info.st_mode):
                observed_directories[relative] = stat.S_IMODE(info.st_mode)
                stack.append(Path(entry.path))
            elif stat.S_ISREG(info.st_mode):
                if info.st_nlink != 1:
                    _raise("runtime handoff contains a hard link")
                observed_files[relative] = stat.S_IMODE(info.st_mode)
            else:
                _raise("runtime handoff contains a special entry")
    if observed_directories != expected_directories or observed_files != expected_files:
        _raise("runtime handoff membership or modes are invalid")


def _load_handoff(
    root: Path,
) -> tuple[bytes, tuple[dict[str, object], ...], dict[str, bytes]]:
    manifest_bytes = archive_builder._read_manifest_bytes(root)
    manifest = archive_builder._parse_manifest(manifest_bytes)
    artifacts = manifest.get("artifacts")
    if manifest.get("channel") != "production" or not isinstance(artifacts, list):
        _raise("runtime handoff manifest is not production activation")
    if len(artifacts) != 1:
        _raise("runtime handoff requires exactly one production artifact")
    records = archive_builder._validate_activation_manifest(artifacts[0])
    _validate_handoff_tree(root, records)
    bundle = root / archive_builder.RUNTIME_BUNDLE_REL
    archive_builder._validate_activation_bundle_tree(
        bundle, records, require_install_mode=True
    )
    payloads = archive_builder._read_runtime_payloads(
        bundle, records, require_install_mode=True
    )
    _validate_handoff_tree(root, records)
    return manifest_bytes, records, payloads


def _read_existing_manifest(plugin: Path) -> tuple[bytes, int]:
    path = plugin / MANIFEST_NAME
    try:
        info = path.lstat()
    except OSError as exc:
        raise StageRuntimeHandoffError("destination runtime manifest is unavailable") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
    ):
        _raise("destination runtime manifest is unsafe")
    data = archive_builder._read_manifest_bytes(plugin)
    return data, stat.S_IMODE(info.st_mode)


def _stage_transaction(
    transaction: Path,
    plugin: Path,
    manifest_bytes: bytes,
    records: tuple[dict[str, object], ...],
    payloads: dict[str, bytes],
    *,
    old_manifest: bytes,
    old_manifest_mode: int,
) -> tuple[Path, Path, Path]:
    verification_root = transaction / "verification-root"
    verification_plugin = verification_root / PLUGIN_REL
    verification_plugin.mkdir(parents=True, mode=SOURCE_DIRECTORY_MODE)
    signing_policy = plugin / "signing_policy.py"
    try:
        signing_policy_info = signing_policy.lstat()
        signing_policy_bytes = signing_policy.read_bytes()
    except OSError as exc:
        raise StageRuntimeHandoffError("public signing policy is unavailable") from exc
    if (
        stat.S_ISLNK(signing_policy_info.st_mode)
        or not stat.S_ISREG(signing_policy_info.st_mode)
        or signing_policy_info.st_uid != os.geteuid()
        or signing_policy_info.st_nlink != 1
        or signing_policy_info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        _raise("public signing policy is unsafe")
    _write_file(
        verification_plugin / "signing_policy.py",
        signing_policy_bytes,
        mode=SOURCE_MANIFEST_MODE,
    )

    staged_runtime = verification_plugin / "runtime"
    staged_runtime.mkdir(mode=SOURCE_DIRECTORY_MODE)
    staged_runtime.chmod(SOURCE_DIRECTORY_MODE)
    staged_bundle = staged_runtime
    for part in archive_builder.RUNTIME_BUNDLE_REL.relative_to("runtime").parts:
        staged_bundle /= part
        staged_bundle.mkdir(mode=SOURCE_DIRECTORY_MODE)
        staged_bundle.chmod(SOURCE_DIRECTORY_MODE)
    for record in records:
        relative = archive_builder.RUNTIME_BUNDLE_REL / str(record["path"])
        _write_file(
            staged_runtime / relative.relative_to("runtime"),
            payloads[relative.as_posix()],
            mode=SOURCE_FILE_MODE,
        )
    staged_manifest = verification_plugin / MANIFEST_NAME
    _write_file(staged_manifest, manifest_bytes, mode=SOURCE_MANIFEST_MODE)
    backup_manifest = transaction / "old-manifest"
    _write_file(backup_manifest, old_manifest, mode=old_manifest_mode)
    archive_builder._validate_activation_bundle_tree(
        staged_bundle, records, require_install_mode=False
    )
    rebound = archive_builder._read_runtime_payloads(
        staged_bundle, records, require_install_mode=False
    )
    if rebound != payloads or staged_manifest.read_bytes() != manifest_bytes:
        _raise("staged runtime handoff changed before publication")
    _fsync_directory(staged_bundle)
    _fsync_directory(staged_bundle.parent)
    _fsync_directory(staged_runtime)
    _fsync_directory(verification_plugin)
    _fsync_directory(verification_root)
    ok, _evidence, _errors = release_verifier.verify_release(
        verification_root, git_sha="runtime-handoff-import"
    )
    if not ok:
        _raise("runtime handoff signature or notarization verification failed")
    return staged_runtime, staged_manifest, backup_manifest


def _remove_runtime_tree(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or not path.is_dir():
        path.unlink()
        return
    shutil.rmtree(path)


def stage_runtime_handoff(handoff_dir: Path, *, repo_root: Path = REPO_ROOT) -> None:
    """Stage one canonical handoff without rewriting its manifest metadata."""

    raw_handoff = Path(handoff_dir)
    handoff = _directory_identity(raw_handoff, label="runtime handoff")
    raw_repo = Path(repo_root)
    repo = _directory_identity(raw_repo, label="destination repository")
    plugin = _directory_identity(repo / PLUGIN_REL, label="destination plugin")
    if handoff == plugin or handoff.is_relative_to(plugin) or plugin.is_relative_to(handoff):
        _raise("runtime handoff and destination plugin must be separate trees")
    manifest_bytes, records, payloads = _load_handoff(handoff)
    old_manifest, old_manifest_mode = _read_existing_manifest(plugin)
    destination_runtime = plugin / "runtime"
    had_runtime = destination_runtime.exists() or destination_runtime.is_symlink()
    if had_runtime:
        try:
            runtime_info = destination_runtime.lstat()
        except OSError as exc:
            raise StageRuntimeHandoffError("destination runtime is unavailable") from exc
        if stat.S_ISLNK(runtime_info.st_mode) or not stat.S_ISDIR(runtime_info.st_mode):
            _raise("destination runtime is unsafe")

    transaction = Path(
        tempfile.mkdtemp(prefix=".runtime-handoff-stage-", dir=str(plugin))
    )
    publish_started = False
    retain_transaction = False
    backup_manifest: Path | None = None
    backup_runtime = transaction / "old-runtime"
    try:
        staged_runtime, staged_manifest, backup_manifest = _stage_transaction(
            transaction,
            plugin,
            manifest_bytes,
            records,
            payloads,
            old_manifest=old_manifest,
            old_manifest_mode=old_manifest_mode,
        )
        publish_started = True
        if had_runtime:
            os.replace(destination_runtime, backup_runtime)
            _fsync_directory(plugin)
            _fsync_directory(transaction)
        os.replace(staged_runtime, destination_runtime)
        _fsync_directory(plugin)
        _fsync_directory(transaction)
        os.replace(staged_manifest, plugin / MANIFEST_NAME)
        _fsync_directory(plugin)
        archive_builder._validate_activation_bundle_tree(
            plugin / archive_builder.RUNTIME_BUNDLE_REL,
            records,
            require_install_mode=False,
        )
        if (plugin / MANIFEST_NAME).read_bytes() != manifest_bytes:
            _raise("published runtime manifest changed")
    except BaseException as exc:
        rollback_error: BaseException | None = None
        try:
            if publish_started:
                if had_runtime and backup_runtime.exists():
                    _remove_runtime_tree(destination_runtime)
                    os.replace(backup_runtime, destination_runtime)
                    _fsync_directory(transaction)
                elif not had_runtime:
                    _remove_runtime_tree(destination_runtime)
                if backup_manifest is None:
                    _raise("runtime handoff rollback state is incomplete")
                os.replace(backup_manifest, plugin / MANIFEST_NAME)
                _fsync_directory(plugin)
        except BaseException as rollback_exc:  # pragma: no cover - catastrophic fs fault
            rollback_error = rollback_exc
        if rollback_error is not None:
            retain_transaction = True
            raise StageRuntimeHandoffError(
                "runtime handoff publish and rollback failed; "
                f"recovery retained at {transaction}"
            ) from rollback_error
        if not isinstance(exc, Exception):
            raise
        if isinstance(exc, StageRuntimeHandoffError):
            raise
        raise StageRuntimeHandoffError("runtime handoff publication failed") from exc
    finally:
        if not retain_transaction:
            _remove_runtime_tree(transaction)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--handoff",
        type=Path,
        required=True,
        help="sealed workspace production handoff directory",
    )
    args = parser.parse_args(argv)
    try:
        stage_runtime_handoff(args.handoff)
    except (StageRuntimeHandoffError, ValueError, OSError) as exc:
        print(f"stage-runtime-handoff: {exc}", file=sys.stderr)
        return 1
    print("stage-runtime-handoff: production runtime staged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
