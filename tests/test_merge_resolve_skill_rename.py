"""Public contract for the merge-resolve skill rename."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MergeResolveSkillRenameTests(unittest.TestCase):
    def test_only_merge_resolve_is_a_publishable_skill(self) -> None:
        self.assertTrue((ROOT / "skill-specs" / "merge-resolve.md").is_file())
        self.assertFalse((ROOT / "skill-specs" / "ai-merge-resolve.md").exists())
        self.assertTrue(
            (
                ROOT
                / "plugins"
                / "agent-collab"
                / "skills"
                / "merge-resolve"
                / "SKILL.md"
            ).is_file()
        )
        self.assertFalse(
            (
                ROOT
                / "plugins"
                / "agent-collab"
                / "skills"
                / "ai-merge-resolve"
            ).exists()
        )

    def test_spec_and_generated_frontmatter_use_the_new_name(self) -> None:
        for path in (
            ROOT / "skill-specs" / "merge-resolve.md",
            ROOT
            / "plugins"
            / "agent-collab"
            / "skills"
            / "merge-resolve"
            / "SKILL.md",
        ):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIn("\nname: merge-resolve\n", path.read_text(encoding="utf-8"))

    def test_generator_configuration_has_no_old_skill_identifier(self) -> None:
        config_path = ROOT / "scripts" / "skill-build-config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        keys = set(config["agent-collab"])
        self.assertIn("merge_resolve_defaults_block", keys)
        self.assertIn("merge_resolve_call_params", keys)
        self.assertNotIn("ai_merge_resolve_defaults_block", keys)
        self.assertNotIn("ai_merge_resolve_call_params", keys)

    def test_retired_namespaces_migrate_to_the_new_command(self) -> None:
        migration = (
            ROOT / "docs" / "migration-from-legacy-packages.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "`/agent-collab:ai-merge-resolve`, "
            "`/claude-collab:ai-merge-resolve`, "
            "`/codex-collab:ai-merge-resolve`, "
            "`/antigravity-collab:ai-merge-resolve` | "
            "`/agent-collab:merge-resolve`",
            migration,
        )
        self.assertNotIn("| `/agent-collab:ai-merge-resolve` |", migration)


if __name__ == "__main__":
    unittest.main()
