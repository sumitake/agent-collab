"""Codex-native metadata for the single unified plugin package."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"


class CodexNativePackagingTests(unittest.TestCase):
    def test_codex_manifest_matches_unified_claude_package(self) -> None:
        claude = json.loads(
            (PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        codex_path = PLUGIN / ".codex-plugin" / "plugin.json"
        self.assertTrue(codex_path.is_file())
        codex = json.loads(codex_path.read_text(encoding="utf-8"))
        self.assertEqual(codex["name"], "agent-collab")
        self.assertEqual(codex["name"], claude["name"])
        self.assertEqual(codex["version"], claude["version"])
        self.assertEqual(codex.get("license"), claude.get("license"))
        self.assertEqual(codex.get("license"), "PolyForm-Strict-1.0.0")
        self.assertEqual(codex["skills"], "./skills/")
        self.assertEqual(codex["author"], claude["author"])
        self.assertEqual(
            set(codex["interface"]),
            {
                "displayName",
                "shortDescription",
                "longDescription",
                "developerName",
                "category",
                "capabilities",
                "defaultPrompt",
            },
        )

    def test_repo_codex_marketplace_has_one_policy_complete_entry(self) -> None:
        path = ROOT / ".agents" / "plugins" / "marketplace.json"
        self.assertTrue(path.is_file())
        marketplace = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(set(marketplace), {"name", "interface", "plugins"})
        self.assertEqual(marketplace["name"], "agent-collab")
        self.assertEqual(marketplace["interface"], {"displayName": "Agent Collab"})
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(
            entry,
            {
                "name": "agent-collab",
                "source": {"source": "local", "path": "./plugins/agent-collab"},
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Productivity",
            },
        )

    def test_release_archive_includes_both_host_manifests(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("scripts/build_plugin_archive.py", workflow)
        self.assertIn("policy-only", workflow)
        self.assertIn("activation", workflow)
        self.assertNotIn("INCLUDE=(", workflow)


if __name__ == "__main__":
    unittest.main()
