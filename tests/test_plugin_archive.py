"""Canonical agent-collab archive membership and parity contract."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import stat
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"
SCRIPT = ROOT / "scripts" / "build_plugin_archive.py"
LEGAL_FILES = ("LICENSE", "NOTICE", "COMMERCIAL-LICENSING.md")


def _load():
    spec = importlib.util.spec_from_file_location("build_plugin_archive", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PluginArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = _load()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plugin = self.root / "plugins" / "agent-collab"
        shutil.copytree(
            PLUGIN,
            self.plugin,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "runtime"),
        )
        self.archive = self.root / "agent-collab.plugin"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _activate(self) -> Path:
        runtime = (
            self.plugin
            / "runtime"
            / "darwin-arm64"
            / "agent-collab-runtime"
        )
        runtime.parent.mkdir(parents=True)
        runtime.write_bytes(b"signed-runtime-fixture")
        runtime.chmod(0o755)
        contracts = (
            ("gemini", "advisory"),
            ("gemini", "long_context"),
            ("codex", "advisory"),
            ("opencode", "plan"),
            ("opencode", "build"),
            ("grok", "architecture"),
            ("grok", "governance"),
            ("grok", "huge_context"),
            ("composer", "codegen"),
        )
        manifest = {
            "schema_version": 1,
            "protocol_version": 1,
            "contract_version": 1,
            "artifacts": [
                {
                    "platform": "darwin",
                    "arch": "arm64",
                    "minimum_macos": "14.0",
                    "path": "runtime/darwin-arm64/agent-collab-runtime",
                    "size": runtime.stat().st_size,
                    "sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
                    "signing": {
                        "team_id": "TESTTEAM01",
                        "require_notarization": True,
                        "hardened_runtime": True,
                    },
                    "contracts": [
                        {"route": route, "action": action}
                        for route, action in contracts
                    ],
                }
            ],
        }
        (self.plugin / "runtime-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return runtime

    def test_policy_only_archive_includes_policy_and_omits_runtime(self) -> None:
        mode = self.builder.build_archive(
            self.root, plugin="agent-collab", output=self.archive
        )
        self.assertEqual(mode, "policy-only")

        with tarfile.open(self.archive, "r:gz") as bundle:
            names = set(bundle.getnames())
            self.assertIn(".claude-plugin/plugin.json", names)
            self.assertIn(".codex-plugin/plugin.json", names)
            self.assertIn("runtime_client.py", names)
            self.assertIn("signing_policy.py", names)
            self.assertIn("runtime-manifest.json", names)
            for name in LEGAL_FILES:
                self.assertIn(name, names)
                member = bundle.getmember(name)
                self.assertEqual(
                    bundle.extractfile(member).read(),
                    (ROOT / name).read_bytes(),
                )
            self.assertFalse(any(name == "runtime" or name.startswith("runtime/") for name in names))
            policy = bundle.getmember("signing_policy.py")
            self.assertEqual(
                stat.S_IMODE(policy.mode),
                stat.S_IMODE((self.plugin / "signing_policy.py").stat().st_mode),
            )
            self.assertEqual(
                bundle.extractfile(policy).read(),
                (self.plugin / "signing_policy.py").read_bytes(),
            )

    def test_packaged_legal_files_match_repository_canonicals(self) -> None:
        for name in LEGAL_FILES:
            self.assertTrue((ROOT / name).is_file(), f"missing root {name}")
            self.assertTrue((PLUGIN / name).is_file(), f"missing plugin {name}")
            self.assertEqual(
                (PLUGIN / name).read_bytes(),
                (ROOT / name).read_bytes(),
                name,
            )

    def test_activation_archive_has_exactly_one_runtime_with_byte_mode_parity(self) -> None:
        runtime = self._activate()
        mode = self.builder.build_archive(
            self.root, plugin="agent-collab", output=self.archive
        )
        self.assertEqual(mode, "activation")

        with tarfile.open(self.archive, "r:gz") as bundle:
            runtime_files = [
                member
                for member in bundle.getmembers()
                if member.isfile() and member.name.startswith("runtime/")
            ]
            self.assertEqual(
                [member.name for member in runtime_files],
                ["runtime/darwin-arm64/agent-collab-runtime"],
            )
            member = runtime_files[0]
            self.assertEqual(bundle.extractfile(member).read(), runtime.read_bytes())
            self.assertEqual(stat.S_IMODE(member.mode), 0o755)

            for archived in bundle.getmembers():
                if not archived.isfile():
                    continue
                source = self.plugin / archived.name
                self.assertEqual(bundle.extractfile(archived).read(), source.read_bytes())
                self.assertEqual(
                    stat.S_IMODE(archived.mode),
                    stat.S_IMODE(source.stat().st_mode),
                )

    def test_policy_only_rejects_unadvertised_runtime_and_missing_policy(self) -> None:
        runtime = (
            self.plugin
            / "runtime"
            / "darwin-arm64"
            / "agent-collab-runtime"
        )
        runtime.parent.mkdir(parents=True)
        runtime.write_bytes(b"unadvertised")
        runtime.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "unadvertised runtime"):
            self.builder.build_archive(
                self.root, plugin="agent-collab", output=self.archive
            )

        shutil.rmtree(self.plugin / "runtime")
        (self.plugin / "signing_policy.py").unlink()
        with self.assertRaisesRegex(ValueError, "signing_policy.py"):
            self.builder.build_archive(
                self.root, plugin="agent-collab", output=self.archive
            )

    def test_archive_verifier_detects_source_byte_drift(self) -> None:
        mode = self.builder.build_archive(
            self.root, plugin="agent-collab", output=self.archive
        )
        (self.plugin / "signing_policy.py").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "byte parity"):
            self.builder.verify_archive(self.plugin, self.archive, mode=mode)

    def test_archive_size_limit_and_required_policy_member_are_canonical(self) -> None:
        self.assertEqual(self.builder.MAX_ARTIFACT_BYTES, 64 * 1024 * 1024)
        self.assertEqual(self.builder.RUNTIME_FILE_MODE, 0o755)
        self.assertIn("signing_policy.py", self.builder.REQUIRED_ROOTS)

    def test_archive_rejects_unexpected_manifest_and_skill_members(self) -> None:
        extra_manifest = self.plugin / ".claude-plugin" / "extra.dat"
        extra_manifest.write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest tree is not canonical"):
            self.builder.build_archive(
                self.root, plugin="agent-collab", output=self.archive
            )

        extra_manifest.unlink()
        helper = self.plugin / "skills" / "route" / "helper.py"
        helper.write_text("pass", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "skill tree is not canonical"):
            self.builder.build_archive(
                self.root, plugin="agent-collab", output=self.archive
            )


if __name__ == "__main__":
    unittest.main()
