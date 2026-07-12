from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_REPO = "https://github.com/sumitake/agent-collab"


class PublicDistributionContractTests(unittest.TestCase):
    def test_every_canonical_repository_pointer_targets_public_distribution(self) -> None:
        marketplace = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        codex = json.loads(
            (ROOT / "plugins" / "agent-collab" / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        schema = json.loads(
            (ROOT / "plugins" / "agent-collab" / "runtime-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(marketplace["metadata"]["repository"], PUBLIC_REPO)
        self.assertEqual(codex["repository"], PUBLIC_REPO)
        self.assertEqual(codex["homepage"], f"{PUBLIC_REPO}#readme")
        self.assertEqual(schema["$id"], f"{PUBLIC_REPO}/runtime-manifest.schema.json")

    def test_current_distributed_version_is_consistent(self) -> None:
        claude = json.loads(
            (ROOT / "plugins" / "agent-collab" / ".claude-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        codex = json.loads(
            (ROOT / "plugins" / "agent-collab" / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertEqual(claude["version"], "3.0.1")
        self.assertEqual(codex["version"], "3.0.1")
        self.assertIn("**agent-collab** (v3.0.1)", readme)
        self.assertIn("## What's new - v3.0.1", readme)

    def test_host_metadata_and_homelab_labels_are_not_distributed(self) -> None:
        self.assertFalse((ROOT / ".claude-session-owner").exists())
        self.assertIn(
            ".claude-session-owner",
            (ROOT / ".gitignore").read_text(encoding="utf-8"),
        )
        public_files = (
            ROOT / "README.md",
            ROOT / "CLAUDE.md",
            ROOT / "CHANGELOG.md",
            ROOT / "docs" / "migration-from-legacy-packages.md",
            ROOT / "docs" / "public-governance.md",
            ROOT / "SECURITY.md",
        )
        combined = "\n".join(path.read_text(encoding="utf-8") for path in public_files)
        for marker in ("RhoNAS", "LabMac", "john@osumi.com"):
            self.assertNotIn(marker, combined)

    def test_public_governance_is_self_contained(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "docs" / "public-governance.md",
                ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md",
                ROOT / ".github" / "workflows" / "compliance-trace.yml",
                ROOT / "scripts" / "check_pr_compliance.py",
            )
        )
        self.assertIn("docs/public-governance.md", combined)
        self.assertNotIn("sumitake/agent-collab-workspace", combined)
        self.assertNotIn("sumitake/agent-collab-plugin", combined)


if __name__ == "__main__":
    unittest.main()
