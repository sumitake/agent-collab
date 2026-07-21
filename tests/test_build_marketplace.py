"""Tests for the single-package marketplace compiler."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_marketplace  # noqa: E402


class TestBuildMarketplace(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "marketplace.base.json"
        self.output = self.root / "marketplace.json"
        self.codex_output = self.root / ".agents" / "plugins" / "marketplace.json"
        self.plugins = self.root / "plugins"
        self.plugins.mkdir()
        self.base.write_text(
            json.dumps(
                {
                    "name": "agent-collab",
                    "owner": {"name": "Test"},
                    "plugins": [],
                    "metadata": {"version": "3.0.0"},
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _plugin(self, name: str) -> None:
        root = self.plugins / name
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "version": "3.0.0",
                    "description": "Unified plugin",
                    "author": {"name": "Test"},
                    "license": "PolyForm-Strict-1.0.0",
                }
            ),
            encoding="utf-8",
        )
        (root / ".codex-plugin").mkdir(parents=True)
        (root / ".codex-plugin" / "plugin.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "version": "3.0.0",
                    "description": "Unified plugin",
                    "author": {"name": "Test"},
                    "license": "PolyForm-Strict-1.0.0",
                    "skills": "./skills/",
                    "interface": {
                        "displayName": "Agent Collab",
                        "shortDescription": "Unified collaboration.",
                        "longDescription": "Unified collaboration plugin.",
                        "developerName": "Test",
                        "category": "Productivity",
                        "capabilities": [],
                        "defaultPrompt": "Review this with an independent model.",
                    },
                }
            ),
            encoding="utf-8",
        )
        (root / "marketplace-fragment.json").write_text(
            json.dumps(
                {
                    "description": "Unified marketplace entry",
                    "category": "ai-collaboration",
                    "tags": ["agent-collab"],
                    "license": "LicenseRef-PolyForm-Strict-1.0.0",
                }
            ),
            encoding="utf-8",
        )

    def _run(self, argv: list[str]) -> int:
        with (
            patch("build_marketplace.BASE_PATH", self.base),
            patch("build_marketplace.OUTPUT_PATH", self.output),
            patch(
                "build_marketplace.CODEX_OUTPUT_PATH",
                self.codex_output,
                create=True,
            ),
            patch("build_marketplace.PLUGINS_DIR", self.plugins),
        ):
            return build_marketplace.main(argv)

    def test_compiles_exactly_agent_collab(self) -> None:
        self._plugin("agent-collab")
        self.assertEqual(self._run([]), 0)
        data = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual([entry["name"] for entry in data["plugins"]], ["agent-collab"])
        self.assertEqual(data["plugins"][0]["source"], "./plugins/agent-collab")
        self.assertEqual(
            data["plugins"][0].get("license"),
            "LicenseRef-PolyForm-Strict-1.0.0",
        )
        self.assertTrue(self.codex_output.is_file())
        codex = json.loads(self.codex_output.read_text(encoding="utf-8"))
        self.assertEqual([entry["name"] for entry in codex["plugins"]], ["agent-collab"])
        self.assertEqual(
            codex["plugins"][0]["policy"],
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        )
        self.assertEqual(self._run(["--check"]), 0)

    def test_rejects_missing_or_additional_package(self) -> None:
        self.assertEqual(self._run([]), 1)
        self._plugin("agent-collab")
        self._plugin("provider-worker")
        self.assertEqual(self._run([]), 1)

    def test_rejects_license_identifier_drift(self) -> None:
        self._plugin("agent-collab")
        manifest = self.plugins / "agent-collab" / ".codex-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["license"] = "MIT"
        manifest.write_text(json.dumps(data), encoding="utf-8")

        self.assertEqual(self._run([]), 1)


if __name__ == "__main__":
    unittest.main()
