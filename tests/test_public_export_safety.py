"""Deterministic active-tree and clean-history public export safety tests."""

from __future__ import annotations

import hashlib
import gzip
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-public-export-safety.py"


def _load():
    spec = importlib.util.spec_from_file_location("public_export_safety", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PublicExportSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = _load()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def _git_output(self, *args: str, input_bytes: bytes | None = None) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            input=input_bytes,
            check=True,
            capture_output=True,
        )
        return result.stdout.decode("ascii").strip()

    def _init(self) -> None:
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test")

    @staticmethod
    def _zip_bytes(members: dict[str, bytes]) -> bytes:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, content in members.items():
                bundle.writestr(name, content)
        return stream.getvalue()

    def test_active_tree_rejects_executor_source_and_private_paths(self) -> None:
        (self.root / "plugins" / "agent-collab").mkdir(parents=True)
        (self.root / "plugins" / "agent-collab" / "codex_exec.py").write_text("x")
        backend = self.root / "plugins" / "agent-collab" / "backend" / "client.py"
        backend.parent.mkdir()
        backend.write_text("x")
        (self.root / "note.md").write_text("/Users/private/project")
        violations = self.audit.scan_active_tree(self.root)
        kinds = {item.kind for item in violations}
        self.assertIn("executor_source", kinds)
        self.assertIn("provider_backend_source", kinds)
        self.assertIn("private_path", kinds)

    def test_history_gate_rejects_deleted_legacy_package(self) -> None:
        self._init()
        old = self.root / "plugins" / "codex-tools"
        old.mkdir(parents=True)
        (old / "README.md").write_text("old")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "old")
        subprocess.run(["rm", "-rf", str(old)], check=True)
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "delete")
        violations = self.audit.scan_history(self.root)
        self.assertTrue(any(item.kind == "legacy_history" for item in violations))

    def test_history_gate_rejects_old_release_refs(self) -> None:
        self._init()
        (self.root / "README.md").write_text("safe")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "clean")
        self._git("-c", "tag.gpgSign=false", "tag", "v2.8.1")
        violations = self.audit.scan_history(self.root)
        self.assertTrue(
            any(
                item.kind == "legacy_release_ref" and item.evidence == "v2.8.1"
                for item in violations
            )
        )

    def test_history_inspects_noncommit_refs_release_form_and_tag_messages(self) -> None:
        self._init()
        (self.root / "README.md").write_text("safe", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "clean")
        blob = self._git_output(
            "hash-object",
            "-w",
            "--stdin",
            input_bytes=b"internal_prompt\x00private blob",
        )
        self._git("update-ref", "refs/audit/blob", blob)
        self._git("update-ref", "refs/tags/v3.0.1", blob)
        self._git("-c", "tag.gpgSign=false", "tag", "v3.0.2")
        self._git(
            "-c",
            "tag.gpgSign=false",
            "tag",
            "-a",
            "v3.0.3",
            "-m",
            "/Users/private/tag-message",
        )

        violations = self.audit.scan_history(self.root)
        kinds = {item.kind for item in violations}
        self.assertIn("history_noncommit_ref", kinds)
        self.assertIn("invalid_release_ref", kinds)
        self.assertIn("internal_prompt", kinds)
        self.assertTrue(
            any(
                item.kind == "private_path" and "refs/tags/v3.0.3" in item.evidence
                for item in violations
            ),
            violations,
        )

    def test_clean_annotated_release_tag_targeting_commit_passes(self) -> None:
        self._init()
        (self.root / "README.md").write_text("safe", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "clean")
        self._git(
            "-c", "tag.gpgSign=false", "tag", "-a", "v3.0.0", "-m", "release"
        )
        self.assertEqual(self.audit.scan_history(self.root), [])

    def test_release_tag_form_is_checked_even_when_tag_object_has_ref_alias(self) -> None:
        self._init()
        (self.root / "README.md").write_text("safe", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "clean")
        self._git(
            "-c", "tag.gpgSign=false", "tag", "-a", "source", "-m", "release"
        )
        tag_object = self._git_output("rev-parse", "refs/tags/source")
        self._git("update-ref", "refs/audit/tag-alias", tag_object)
        self._git("update-ref", "refs/tags/v3.0.0", tag_object)

        violations = self.audit.scan_history(self.root)
        self.assertTrue(
            any(
                item.kind == "invalid_release_ref"
                and item.evidence == "refs/tags/v3.0.0"
                for item in violations
            ),
            violations,
        )

    def test_history_scans_archive_bytes_renamed_markers_and_tree_modes(self) -> None:
        self._init()
        archive = self.root / "harmless.plugin"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(
                "renamed.dat",
                b"#!/usr/bin/env python3\nimport subprocess\ndef qualify_exact_binary(): pass\n",
            )
            bundle.writestr("opaque.bin", b"\xff\x00/Users/private/workspace\x00")
        target = self.root / "safe.txt"
        target.write_text("safe", encoding="utf-8")
        (self.root / "unsafe-link").symlink_to("safe.txt")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "archive and symlink")

        violations = self.audit.scan_history(self.root)
        kinds = {item.kind for item in violations}
        self.assertIn("renamed_executor_source", kinds)
        self.assertIn("private_path", kinds)
        self.assertIn("history_unsafe_mode", kinds)

    def test_history_checks_renamed_marker_for_every_blob_path_alias(self) -> None:
        self._init()
        body = b"def qualify_exact_binary():\n    return True\n"
        (self.root / "a.md").write_bytes(body)
        (self.root / "z.dat").write_bytes(body)
        self._git("add", ".")
        self._git("commit", "-q", "-m", "aliased blob")

        violations = self.audit.scan_history(self.root)
        self.assertTrue(
            any(item.kind == "renamed_executor_source" for item in violations),
            violations,
        )

    def test_history_masks_only_explicit_harmless_audit_literals(self) -> None:
        self._init()
        script = self.root / "scripts" / "check-public-export-safety.py"
        script.parent.mkdir(parents=True)
        script.write_text('PATTERN = "/Users/"\n')
        fixture = self.root / "tests" / "test_public_export_safety.py"
        fixture.parent.mkdir(parents=True)
        fixture.write_text('PRIVATE = "/Users/private/project"\n')
        self._git("add", ".")
        self._git("commit", "-q", "-m", "audit fixtures")
        self.assertEqual(self.audit.scan_history(self.root), [])

        fixture.write_text(
            'PRIVATE = "/Users/private/project"\n'
            'UNEXPECTED = "/Users/unexpected/operator-home"\n'
        )
        self._git("add", ".")
        self._git("commit", "-q", "-m", "unexpected private path")
        violations = self.audit.scan_history(self.root)
        self.assertTrue(
            any(
                item.kind == "private_path"
                and "/Users/" in item.evidence
                for item in violations
            ),
            violations,
        )

    def test_clean_history_export_passes(self) -> None:
        self._init()
        (self.root / "plugins" / "agent-collab").mkdir(parents=True)
        (self.root / "plugins" / "agent-collab" / "README.md").write_text("safe")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "clean")
        self.assertEqual(self.audit.scan_active_tree(self.root), [])
        self.assertEqual(self.audit.scan_history(self.root), [])

    def test_decompressed_archive_members_are_scanned(self) -> None:
        archive = self.root / "agent-collab.plugin"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("safe-name.dat", b"prefix\x00/Users/private/workspace\x00suffix")
            bundle.writestr("renamed.bin", b"codex_exec.py\x00opencode_exec.py")
            bundle.writestr("backend/private_executor.py", b"print('opaque')")
            bundle.writestr("nested/mcp-server/worker.py", b"print('opaque')")
        violations = self.audit.scan_active_tree(self.root)
        kinds = {item.kind for item in violations}
        self.assertIn("private_path", kinds)
        self.assertIn("executor_source", kinds)
        self.assertIn("provider_backend_source", kinds)

    def test_nested_archives_are_scanned_recursively_with_cumulative_bounds(self) -> None:
        constructed = (
            b"import subprocess\n"
            b"argv = ['co' + 'dex', 'ex' + 'ec', '--']\n"
            b"subprocess.run(argv)\n"
        )
        inner = self._zip_bytes(
            {
                "nested.py": constructed,
                "opaque.bin": b"/Users/nested/private-workspace",
            }
        )
        outer = self.root / "outer.plugin"
        outer.write_bytes(self._zip_bytes({"payload/inner.zip": inner}))
        violations = self.audit.scan_active_tree(self.root)
        kinds = {item.kind for item in violations}
        self.assertIn("raw_provider_recipe", kinds)
        self.assertIn("private_path", kinds)

        nested = b"safe"
        for depth in range(5):
            nested = self._zip_bytes({f"level-{depth}.zip": nested})
        outer.write_bytes(nested)
        with mock.patch.object(self.audit, "MAX_ARCHIVE_DEPTH", 2):
            violations = self.audit.scan_active_tree(self.root)
        self.assertTrue(any(item.kind == "archive_limit" for item in violations))

        inner = self._zip_bytes({"a.txt": b"a", "b.txt": b"b"})
        outer.write_bytes(self._zip_bytes({"inner.zip": inner}))
        with mock.patch.object(self.audit, "MAX_ARCHIVE_MEMBERS", 2):
            violations = self.audit.scan_active_tree(self.root)
        self.assertTrue(any(item.kind == "archive_limit" for item in violations))

        outer.write_bytes(self._zip_bytes({"inner.zip": inner}))
        with mock.patch.object(self.audit, "MAX_ARCHIVE_TOTAL_BYTES", 2):
            violations = self.audit.scan_active_tree(self.root)
        self.assertTrue(any(item.kind == "archive_limit" for item in violations))

    def test_constructed_provider_argv_is_detected_semantically(self) -> None:
        source = self.root / "harmless.py"
        source.write_text(
            "import subprocess\n"
            "provider = 'co' + 'dex'\n"
            "operation = 'ex' + 'ec'\n"
            "argv = [provider, operation, '--']\n"
            "subprocess.run(argv)\n",
            encoding="utf-8",
        )
        violations = self.audit.scan_active_tree(self.root)
        self.assertTrue(
            any(item.kind == "raw_provider_recipe" for item in violations),
            violations,
        )

    def test_keyword_args_provider_argv_is_detected_semantically(self) -> None:
        source = self.root / "harmless.py"
        source.write_text(
            "import subprocess\n"
            "argv = ['co' + 'dex', 'ex' + 'ec', '--']\n"
            "subprocess.run(args=argv)\n",
            encoding="utf-8",
        )
        violations = self.audit.scan_active_tree(self.root)
        self.assertTrue(
            any(item.kind == "raw_provider_recipe" for item in violations),
            violations,
        )

    def test_gemini_headless_argv_is_detected_semantically(self) -> None:
        source = self.root / "harmless.py"
        source.write_text(
            "import subprocess\n"
            "provider = 'gem' + 'ini'\n"
            "argv = [provider, '-p', 'review this']\n"
            "subprocess.run(argv)\n",
            encoding="utf-8",
        )
        violations = self.audit.scan_active_tree(self.root)
        self.assertTrue(
            any(item.kind == "raw_provider_recipe" for item in violations),
            violations,
        )

    def test_env_wrapped_provider_argv_is_detected_semantically(self) -> None:
        source = self.root / "harmless.py"
        source.write_text(
            "import subprocess\n"
            "wrapper = '/usr/bin/' + 'env'\n"
            "provider = 'co' + 'dex'\n"
            "operation = 'ex' + 'ec'\n"
            "argv = [wrapper, '-i', 'HOME=/tmp/safe', '--', provider, operation, '--']\n"
            "subprocess.run(argv)\n",
            encoding="utf-8",
        )
        violations = self.audit.scan_active_tree(self.root)
        self.assertTrue(
            any(item.kind == "raw_provider_recipe" for item in violations),
            violations,
        )

    def test_non_process_provider_argv_is_not_a_semantic_violation(self) -> None:
        source = self.root / "harmless.py"
        source.write_text(
            "def describe(value):\n"
            "    return value\n"
            "provider = 'co' + 'dex'\n"
            "operation = 'ex' + 'ec'\n"
            "describe([provider, operation, '--'])\n",
            encoding="utf-8",
        )
        violations = self.audit.scan_active_tree(self.root)
        self.assertFalse(
            any(item.kind == "raw_provider_recipe" for item in violations),
            violations,
        )

    def test_standalone_gzip_payload_is_decompressed_and_scanned(self) -> None:
        payload = self.root / "opaque.gz"
        payload.write_bytes(gzip.compress(b"prefix\x00/Users/private/workspace\x00suffix"))
        violations = self.audit.scan_active_tree(self.root)
        self.assertTrue(
            any(item.kind == "private_path" and "!gzip" in item.evidence for item in violations),
            violations,
        )

    def test_commit_message_sensitive_material_is_scanned(self) -> None:
        self._init()
        (self.root / "README.md").write_text("safe", encoding="utf-8")
        self._git("add", ".")
        self._git(
            "commit",
            "-q",
            "-m",
            "includes internal_prompt and AWS_SECRET_ACCESS_KEY material",
        )
        violations = self.audit.scan_history(self.root)
        kinds = {item.kind for item in violations}
        self.assertIn("internal_prompt", kinds)
        self.assertIn("credential_material", kinds)

    def test_non_utf8_binary_is_scanned_without_ignore_decode(self) -> None:
        payload = self.root / "opaque.bin"
        payload.write_bytes(b"\xff\xfe\x00internal_prompt_corpus\x00AWS_SECRET_ACCESS_KEY\x00")
        violations = self.audit.scan_active_tree(self.root)
        kinds = {item.kind for item in violations}
        self.assertIn("internal_prompt", kinds)
        self.assertIn("credential_material", kinds)

    def test_active_tree_rejects_symlinks_instead_of_following_them(self) -> None:
        target = self.root / "safe-target.txt"
        target.write_text("safe", encoding="utf-8")
        (self.root / "public-link").symlink_to(target)
        violations = self.audit.scan_active_tree(self.root)
        self.assertTrue(any(item.kind == "unsafe_symlink" for item in violations))

    def test_renamed_python_executor_is_detected_by_content(self) -> None:
        renamed = self.root / "harmless.dat"
        renamed.write_bytes(
            b"#!/usr/bin/env python3\nimport subprocess\ndef qualify_exact_binary():\n    pass\n"
        )
        violations = self.audit.scan_active_tree(self.root)
        self.assertTrue(any(item.kind == "renamed_executor_source" for item in violations))

    def test_compiled_runtime_requires_exact_manifest_contract(self) -> None:
        binary = (
            self.root
            / "plugins"
            / "agent-collab"
            / "runtime"
            / "darwin-arm64"
            / "agent-collab-runtime"
        )
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"compiled-binary")
        violations = self.audit.scan_active_tree(self.root)
        self.assertTrue(any(item.kind == "unmanifested_runtime" for item in violations))

    def test_compiled_runtime_rejects_partial_matrix_and_missing_signing_team(self) -> None:
        binary = (
            self.root
            / "plugins"
            / "agent-collab"
            / "runtime"
            / "darwin-arm64"
            / "agent-collab-runtime.bundle"
            / "agent-collab-runtime"
        )
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"compiled-binary")
        binary.chmod(0o500)
        binary.parent.chmod(0o500)
        records = [
            {
                "path": "agent-collab-runtime",
                "role": "entrypoint",
                "install_mode": 0o500,
                "size": len(b"compiled-binary"),
                "sha256": hashlib.sha256(b"compiled-binary").hexdigest(),
                "macho_type": "executable",
                "architecture": "arm64",
                "minimum_macos": "14.0",
                "signing_profile": "production_developer_id",
            }
        ]
        manifest = {
            "schema_version": 2,
            "protocol_version": 2,
            "contract_version": 3,
            "broker_protocol_version": 2,
            "channel": "production",
            "artifacts": [
                {
                    "platform": "darwin",
                    "arch": "arm64",
                    "kind": "standalone_bundle",
                    "minimum_macos": "14.0",
                    "path": "runtime/darwin-arm64/agent-collab-runtime.bundle",
                    "entrypoint": "agent-collab-runtime",
                    "size": len(b"compiled-binary"),
                    "sha256": self.audit.runtime_bundle.compute_bundle_identity(records),
                    "signing": {
                        "require_notarization": True,
                        "hardened_runtime": True,
                    },
                    "files": records,
                    "contracts": [{"route": "composer", "action": "codegen"}],
                }
            ],
        }
        plugin_root = binary.parents[3]
        (plugin_root / "runtime-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        violations = self.audit.scan_active_tree(self.root)
        self.assertTrue(any(item.kind == "unmanifested_runtime" for item in violations))

        manifest["artifacts"][0]["signing"].update(
            {
                "mode": "developer_id",
                "identity": "Developer ID Application: Test Operator (ABCDEFGHIJ)",
                "team_id": "ABCDEFGHIJ",
                "secure_timestamp": True,
            }
        )
        manifest["artifacts"][0]["contracts"] = [
            {"route": route, "action": action}
            for route, action in sorted(self.audit.REQUIRED_RUNTIME_CONTRACTS)
        ]
        (plugin_root / "signing_policy.py").write_text(
            'EXPECTED_DEVELOPER_ID_TEAM = "ABCDEFGHIJ"\n', encoding="utf-8"
        )
        (plugin_root / "runtime-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        violations = self.audit.scan_active_tree(self.root)
        self.assertFalse(any(item.kind == "unmanifested_runtime" for item in violations))


if __name__ == "__main__":
    unittest.main()
