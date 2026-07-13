from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_REPO = "https://github.com/sumitake/agent-collab"


class PublicDistributionContractTests(unittest.TestCase):
    def test_agent_neutral_guidance_is_canonical(self) -> None:
        agents_path = ROOT / "AGENTS.md"
        self.assertTrue(agents_path.is_file(), "AGENTS.md must be canonical")
        agents = agents_path.read_text(encoding="utf-8")
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

        self.assertIn("# agent-collab development guide", agents)
        self.assertIn("## Source boundaries", agents)
        self.assertEqual(claude, "# Claude Code compatibility\n\n@AGENTS.md\n")
        self.assertNotIn("## Source boundaries", claude)

    def test_public_licensing_identifies_owner_and_approval_boundary(self) -> None:
        self.assertTrue((ROOT / "NOTICE").is_file(), "NOTICE must exist")
        self.assertTrue(
            (ROOT / "COMMERCIAL-LICENSING.md").is_file(),
            "COMMERCIAL-LICENSING.md must exist",
        )
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        commercial = (ROOT / "COMMERCIAL-LICENSING.md").read_text(
            encoding="utf-8"
        )

        self.assertEqual(
            notice,
            "Copyright (c) 2026 John Osumi. All rights reserved except as "
            "expressly granted.\nCommercial licensing is administered by "
            "Osumi Consulting LLC.\n",
        )
        for phrase in (
            "explicit written approval",
            "Repository access",
            "installation",
            "GitHub interaction",
            "acceptance of a contribution",
        ):
            self.assertIn(phrase, commercial)

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

        version = claude["version"]
        self.assertEqual(codex["version"], version)
        self.assertIn(f"**agent-collab** (v{version})", readme)
        self.assertIn(f"## What's new - v{version}", readme)

        generated_skills = sorted(
            (ROOT / "plugins" / "agent-collab" / "skills").glob("*/SKILL.md")
        )
        self.assertTrue(generated_skills)
        for path in generated_skills:
            self.assertIn(f"\nversion: {version}\n", path.read_text(encoding="utf-8"))

    def test_host_metadata_and_homelab_labels_are_not_distributed(self) -> None:
        self.assertFalse((ROOT / ".claude-session-owner").exists())
        self.assertIn(
            ".claude-session-owner",
            (ROOT / ".gitignore").read_text(encoding="utf-8"),
        )
        public_files = (
            ROOT / "README.md",
            ROOT / "AGENTS.md",
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
