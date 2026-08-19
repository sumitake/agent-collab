#!/usr/bin/env python3
"""Tests for the atomic production-runtime handoff importer."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "stage_runtime_handoff.py"
PLUGIN_REL = Path("plugins/agent-collab")
BUNDLE_REL = Path("runtime/darwin-arm64/agent-collab-runtime.bundle")
X86_BUNDLE_REL = Path("runtime/darwin-x86_64/agent-collab-runtime.bundle")

sys.path.insert(0, str(ROOT / "scripts"))
import build_plugin_archive as archive_builder  # noqa: E402


def _load_importer():
    spec = importlib.util.spec_from_file_location("stage_runtime_handoff_tested", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest_bytes(payload: bytes) -> bytes:
    base = json.loads(
        (ROOT / PLUGIN_REL / "runtime-manifest.json").read_text(encoding="utf-8")
    )
    record = {
        "architecture": "arm64",
        "install_mode": 0o500,
        "macho_type": "executable",
        "minimum_macos": "14.0",
        "path": "agent-collab-runtime",
        "role": "entrypoint",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "signing_profile": "production_developer_id",
        "size": len(payload),
    }
    base["artifacts"] = [
        {
            "platform": "darwin",
            "arch": "arm64",
            "kind": "standalone_bundle",
            "minimum_macos": "14.0",
            "path": BUNDLE_REL.as_posix(),
            "entrypoint": "agent-collab-runtime",
            "size": len(payload),
            "sha256": archive_builder.runtime_bundle.compute_bundle_identity([record]),
            "provider_runtime_version": "4.0.6",
            "wire_contract_sha256": base["wire_contract_sha256"],
            "signing": {
                "mode": "developer_id",
                "identity": "Developer ID Application: Test Runtime (ABCDEFGHIJ)",
                "team_id": "ABCDEFGHIJ",
                "require_notarization": True,
                "hardened_runtime": True,
                "secure_timestamp": True,
            },
            "files": [record],
        }
    ]
    return (
        json.dumps(base, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _make_handoff(parent: Path, name: str, payload: bytes) -> tuple[Path, bytes]:
    root = parent / name
    bundle = root / BUNDLE_REL
    bundle.mkdir(parents=True)
    member = bundle / "agent-collab-runtime"
    member.write_bytes(payload)
    member.chmod(0o500)
    bundle.chmod(0o500)
    manifest = _manifest_bytes(payload)
    manifest_path = root / "runtime-manifest.json"
    manifest_path.write_bytes(manifest)
    manifest_path.chmod(0o400)
    root.chmod(0o755)
    return root, manifest


def _make_matrix_handoff(parent: Path, name: str) -> tuple[Path, dict[Path, bytes]]:
    root = parent / name
    payloads = {BUNDLE_REL: b"arm runtime", X86_BUNDLE_REL: b"x86 runtime"}
    base = json.loads(
        (ROOT / PLUGIN_REL / "runtime-manifest.json").read_text(encoding="utf-8")
    )
    artifacts = []
    for bundle, payload in payloads.items():
        architecture = "x86_64" if bundle == X86_BUNDLE_REL else "arm64"
        record = {
            "architecture": architecture,
            "install_mode": 0o500,
            "macho_type": "executable",
            "minimum_macos": "14.0",
            "path": "agent-collab-runtime",
            "role": "entrypoint",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "signing_profile": "production_developer_id",
            "size": len(payload),
        }
        artifacts.append(
            {
                "platform": "darwin",
                "arch": architecture,
                "kind": "standalone_bundle",
                "minimum_macos": "14.0",
                "path": bundle.as_posix(),
                "entrypoint": "agent-collab-runtime",
                "size": len(payload),
                "sha256": archive_builder.runtime_bundle.compute_bundle_identity(
                    [record]
                ),
                "provider_runtime_version": "4.0.6",
                "wire_contract_sha256": base["wire_contract_sha256"],
                "signing": {
                    "mode": "developer_id",
                    "identity": "Developer ID Application: Test Runtime (ABCDEFGHIJ)",
                    "team_id": "ABCDEFGHIJ",
                    "require_notarization": True,
                    "hardened_runtime": True,
                    "secure_timestamp": True,
                },
                "files": [record],
            }
        )
        leaf = root / bundle
        leaf.mkdir(parents=True)
        (leaf / "agent-collab-runtime").write_bytes(payload)
        (leaf / "agent-collab-runtime").chmod(0o500)
        leaf.chmod(0o500)
    base["artifacts"] = artifacts
    manifest = (
        json.dumps(base, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")
    (root / "runtime-manifest.json").write_bytes(manifest)
    (root / "runtime-manifest.json").chmod(0o400)
    root.chmod(0o755)
    return root, payloads


def _make_repo(parent: Path) -> tuple[Path, Path, bytes]:
    repo = parent / "public-repo"
    plugin = repo / PLUGIN_REL
    plugin.mkdir(parents=True)
    old_manifest = (ROOT / PLUGIN_REL / "runtime-manifest.json").read_bytes()
    (plugin / "runtime-manifest.json").write_bytes(old_manifest)
    (plugin / "runtime-manifest.json").chmod(0o644)
    (plugin / "signing_policy.py").write_bytes(
        (ROOT / PLUGIN_REL / "signing_policy.py").read_bytes()
    )
    (plugin / "signing_policy.py").chmod(0o644)
    (plugin / "keep.txt").write_bytes(b"unrelated\n")
    return repo, plugin, old_manifest


def _snapshot_tree(root: Path) -> tuple[tuple[str, str, int, bytes], ...]:
    items: list[tuple[str, str, int, bytes]] = []
    for path in sorted((root, *root.rglob("*")), key=lambda item: item.as_posix()):
        info = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        if stat.S_ISDIR(info.st_mode):
            items.append((relative, "dir", stat.S_IMODE(info.st_mode), b""))
        elif stat.S_ISREG(info.st_mode):
            items.append((relative, "file", stat.S_IMODE(info.st_mode), path.read_bytes()))
        elif stat.S_ISLNK(info.st_mode):
            items.append(
                (relative, "link", stat.S_IMODE(info.st_mode), os.readlink(path).encode())
            )
        else:
            items.append((relative, "special", stat.S_IMODE(info.st_mode), b""))
    return tuple(items)


def _verified_stage(importer, handoff: Path, *, repo_root: Path) -> None:
    with mock.patch.object(
        importer.release_verifier,
        "verify_release",
        return_value=(True, {"notarization_verified": True}, []),
    ):
        importer.stage_runtime_handoff(handoff, repo_root=repo_root)


class StageRuntimeHandoffTests(unittest.TestCase):
    def test_matrix_handoff_stages_both_architectures_as_one_unit(self):
        importer = _load_importer()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo, plugin, _old_manifest = _make_repo(root)
            handoff, payloads = _make_matrix_handoff(root, "matrix")
            _verified_stage(importer, handoff, repo_root=repo)
            for bundle, payload in payloads.items():
                self.assertEqual(
                    (plugin / bundle / "agent-collab-runtime").read_bytes(), payload
                )

    def test_valid_first_import_stages_only_manifest_and_runtime(self) -> None:
        self.assertTrue(SCRIPT.is_file(), "production handoff importer is missing")
        importer = _load_importer()
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            repo, plugin, _old_manifest = _make_repo(parent)
            handoff, manifest = _make_handoff(parent, "handoff", b"signed-runtime")
            source_before = _snapshot_tree(handoff)

            _verified_stage(importer, handoff, repo_root=repo)

            self.assertEqual(_snapshot_tree(handoff), source_before)
            self.assertEqual((plugin / "runtime-manifest.json").read_bytes(), manifest)
            member = plugin / BUNDLE_REL / "agent-collab-runtime"
            self.assertEqual(member.read_bytes(), b"signed-runtime")
            self.assertEqual(stat.S_IMODE(member.stat().st_mode), 0o755)
            self.assertEqual(
                stat.S_IMODE((plugin / "runtime-manifest.json").stat().st_mode),
                0o644,
            )
            self.assertEqual((plugin / "keep.txt").read_bytes(), b"unrelated\n")
            self.assertEqual(
                {path.name for path in plugin.iterdir()},
                {
                    "keep.txt",
                    "runtime",
                    "runtime-manifest.json",
                    "signing_policy.py",
                },
            )

    def test_valid_replacement_publishes_the_new_sealed_unit(self) -> None:
        importer = _load_importer()
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            repo, plugin, _old_manifest = _make_repo(parent)
            first, _first_manifest = _make_handoff(parent, "first", b"runtime-one")
            second, second_manifest = _make_handoff(parent, "second", b"runtime-two")
            first_before = _snapshot_tree(first)
            second_before = _snapshot_tree(second)

            _verified_stage(importer, first, repo_root=repo)
            _verified_stage(importer, second, repo_root=repo)

            self.assertEqual(_snapshot_tree(first), first_before)
            self.assertEqual(_snapshot_tree(second), second_before)
            self.assertEqual((plugin / "runtime-manifest.json").read_bytes(), second_manifest)
            self.assertEqual(
                (plugin / BUNDLE_REL / "agent-collab-runtime").read_bytes(),
                b"runtime-two",
            )
            self.assertFalse(
                any(path.name.startswith(".runtime-handoff-stage-") for path in plugin.iterdir())
            )

    def test_invalid_handoff_never_changes_the_destination_or_source(self) -> None:
        importer = _load_importer()

        def malformed_manifest(root: Path) -> None:
            path = root / "runtime-manifest.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["channel"] = "development"
            path.chmod(0o600)
            path.write_text(
                json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="ascii",
            )
            path.chmod(0o400)

        def extra_tree_member(root: Path) -> None:
            path = root / "unexpected-build-input.tar"
            path.write_bytes(b"must-not-stage")
            path.chmod(0o400)

        def wrong_member_mode(root: Path) -> None:
            (root / BUNDLE_REL / "agent-collab-runtime").chmod(0o700)

        def wrong_member_digest(root: Path) -> None:
            member = root / BUNDLE_REL / "agent-collab-runtime"
            member.chmod(0o700)
            member.write_bytes(b"forged-runtime")
            member.chmod(0o500)

        def linked_member(root: Path) -> None:
            bundle = root / BUNDLE_REL
            member = bundle / "agent-collab-runtime"
            outside = root.parent / "outside-runtime"
            outside.write_bytes(b"outside")
            bundle.chmod(0o700)
            member.unlink()
            member.symlink_to(outside)
            bundle.chmod(0o500)

        cases = {
            "manifest": malformed_manifest,
            "tree": extra_tree_member,
            "mode": wrong_member_mode,
            "digest": wrong_member_digest,
            "link": linked_member,
        }
        for label, mutate in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                parent = Path(raw)
                repo, plugin, _old_manifest = _make_repo(parent)
                handoff, _manifest = _make_handoff(
                    parent, "handoff", b"signed-runtime"
                )
                mutate(handoff)
                source_before = _snapshot_tree(handoff)
                destination_before = _snapshot_tree(plugin)

                with self.assertRaises(ValueError):
                    _verified_stage(importer, handoff, repo_root=repo)

                self.assertEqual(_snapshot_tree(handoff), source_before)
                self.assertEqual(_snapshot_tree(plugin), destination_before)

    def test_existing_release_verifier_gates_exact_staged_bytes(self) -> None:
        importer = _load_importer()
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            repo, plugin, _old_manifest = _make_repo(parent)
            handoff, manifest = _make_handoff(parent, "handoff", b"signed-runtime")
            destination_before = _snapshot_tree(plugin)

            def reject_staged(root: Path, *, git_sha: str):
                staged_plugin = root / PLUGIN_REL
                self.assertEqual(git_sha, "runtime-handoff-import")
                self.assertEqual(
                    (staged_plugin / "runtime-manifest.json").read_bytes(), manifest
                )
                self.assertEqual(
                    (staged_plugin / BUNDLE_REL / "agent-collab-runtime").read_bytes(),
                    b"signed-runtime",
                )
                self.assertEqual(
                    (staged_plugin / "signing_policy.py").read_bytes(),
                    (ROOT / PLUGIN_REL / "signing_policy.py").read_bytes(),
                )
                return False, {}, ["runtime is not notarized"]

            with (
                mock.patch.object(
                    importer.release_verifier,
                    "verify_release",
                    side_effect=reject_staged,
                ) as verifier,
                self.assertRaisesRegex(ValueError, "signature or notarization"),
            ):
                importer.stage_runtime_handoff(handoff, repo_root=repo)

            verifier.assert_called_once()
            self.assertEqual(_snapshot_tree(plugin), destination_before)

    def test_interrupted_manifest_publish_restores_prior_unit_byte_for_byte(self) -> None:
        importer = _load_importer()
        for replacement_happened in (False, True):
            with (
                self.subTest(replacement_happened=replacement_happened),
                tempfile.TemporaryDirectory() as raw,
            ):
                parent = Path(raw)
                repo, plugin, _old_manifest = _make_repo(parent)
                first, _first_manifest = _make_handoff(
                    parent, "first", b"runtime-before"
                )
                second, _second_manifest = _make_handoff(
                    parent, "second", b"runtime-after"
                )
                _verified_stage(importer, first, repo_root=repo)
                destination_before = _snapshot_tree(plugin)
                source_before = _snapshot_tree(second)
                real_replace = os.replace
                calls = 0

                def interrupted_replace(source, destination):
                    nonlocal calls
                    calls += 1
                    if calls == 3:
                        if replacement_happened:
                            real_replace(source, destination)
                        raise OSError("simulated publish interruption")
                    return real_replace(source, destination)

                with (
                    mock.patch.object(
                        importer.os, "replace", side_effect=interrupted_replace
                    ),
                    self.assertRaises(ValueError),
                ):
                    _verified_stage(importer, second, repo_root=repo)

                self.assertEqual(_snapshot_tree(plugin), destination_before)
                self.assertEqual(_snapshot_tree(second), source_before)
                self.assertFalse(
                    any(
                        path.name.startswith(".runtime-handoff-stage-")
                        for path in plugin.iterdir()
                    )
                )

    def test_interrupted_first_import_restores_policy_only_tree(self) -> None:
        importer = _load_importer()
        for replacement_happened in (False, True):
            with (
                self.subTest(replacement_happened=replacement_happened),
                tempfile.TemporaryDirectory() as raw,
            ):
                parent = Path(raw)
                repo, plugin, _old_manifest = _make_repo(parent)
                handoff, _manifest = _make_handoff(
                    parent, "handoff", b"runtime-after"
                )
                destination_before = _snapshot_tree(plugin)
                source_before = _snapshot_tree(handoff)
                real_replace = os.replace
                calls = 0

                def interrupted_replace(source, destination):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        if replacement_happened:
                            real_replace(source, destination)
                        raise OSError("simulated first-import interruption")
                    return real_replace(source, destination)

                with (
                    mock.patch.object(
                        importer.os, "replace", side_effect=interrupted_replace
                    ),
                    self.assertRaises(ValueError),
                ):
                    _verified_stage(importer, handoff, repo_root=repo)

                self.assertEqual(_snapshot_tree(plugin), destination_before)
                self.assertEqual(_snapshot_tree(handoff), source_before)

    def test_keyboard_interrupt_during_publish_also_rolls_back(self) -> None:
        importer = _load_importer()
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            repo, plugin, _old_manifest = _make_repo(parent)
            first, _first_manifest = _make_handoff(
                parent, "first", b"runtime-before"
            )
            second, _second_manifest = _make_handoff(
                parent, "second", b"runtime-after"
            )
            _verified_stage(importer, first, repo_root=repo)
            destination_before = _snapshot_tree(plugin)
            real_replace = os.replace
            calls = 0

            def interrupt(source, destination):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise KeyboardInterrupt
                return real_replace(source, destination)

            with (
                mock.patch.object(importer.os, "replace", side_effect=interrupt),
                self.assertRaises(KeyboardInterrupt),
            ):
                _verified_stage(importer, second, repo_root=repo)

            self.assertEqual(_snapshot_tree(plugin), destination_before)

    def test_rollback_failure_preserves_byte_exact_recovery_transaction(self) -> None:
        importer = _load_importer()
        for rollback_failure in (
            OSError("simulated rollback failure"),
            KeyboardInterrupt(),
        ):
            with (
                self.subTest(rollback_failure=type(rollback_failure).__name__),
                tempfile.TemporaryDirectory() as raw,
            ):
                parent = Path(raw)
                repo, plugin, _old_manifest = _make_repo(parent)
                first, first_manifest = _make_handoff(
                    parent, "first", b"runtime-before"
                )
                second, _second_manifest = _make_handoff(
                    parent, "second", b"runtime-after"
                )
                _verified_stage(importer, first, repo_root=repo)
                real_replace = os.replace
                real_validate = (
                    importer.archive_builder._validate_activation_bundle_tree
                )
                validation_calls = 0

                def fail_after_publish(*args, **kwargs):
                    nonlocal validation_calls
                    validation_calls += 1
                    if validation_calls == 3:
                        raise ValueError("simulated post-publish validation failure")
                    return real_validate(*args, **kwargs)

                def fail_old_runtime_restore(source, destination):
                    if Path(source).name == "old-runtime":
                        raise rollback_failure
                    return real_replace(source, destination)

                with (
                    mock.patch.object(
                        importer.archive_builder,
                        "_validate_activation_bundle_tree",
                        side_effect=fail_after_publish,
                    ),
                    mock.patch.object(
                        importer.os,
                        "replace",
                        side_effect=fail_old_runtime_restore,
                    ),
                    self.assertRaisesRegex(
                        importer.StageRuntimeHandoffError,
                        "rollback failed.*recovery retained",
                    ),
                ):
                    _verified_stage(importer, second, repo_root=repo)

                recoveries = [
                    path
                    for path in plugin.iterdir()
                    if path.name.startswith(".runtime-handoff-stage-")
                ]
                self.assertEqual(len(recoveries), 1)
                recovery = recoveries[0]
                self.assertEqual(
                    (
                        recovery
                        / "old-runtime"
                        / "darwin-arm64"
                        / "agent-collab-runtime.bundle"
                        / "agent-collab-runtime"
                    ).read_bytes(),
                    b"runtime-before",
                )
                self.assertEqual(
                    (recovery / "old-manifest").read_bytes(), first_manifest
                )


if __name__ == "__main__":
    unittest.main()
