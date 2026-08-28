"""Current public distribution and documentation-release contract."""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"


class PublicDistributionContractTests(unittest.TestCase):
    def test_source_generated_metadata_is_consistently_version_7(self) -> None:
        versions = {
            json.loads((PLUGIN / host / "plugin.json").read_text(encoding="utf-8"))["version"]
            for host in (".claude-plugin", ".codex-plugin")
        }
        versions.add(json.loads((ROOT / "scripts" / "skill-build-config.json").read_text(encoding="utf-8"))["agent-collab"]["skill_version"])
        versions.add(json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))["plugins"][0]["version"])
        versions.add(json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))["metadata"]["version"])
        versions.add(json.loads((ROOT / ".claude-plugin" / "marketplace.base.json").read_text(encoding="utf-8"))["metadata"]["version"])
        self.assertEqual(versions, {"7.0.0"})

    def test_current_release_documentation_matches_published_evidence(self) -> None:
        status = (
            ROOT / "docs" / "architecture" / "status-and-evidence.md"
        ).read_text(encoding="utf-8")
        match = re.search(r"^## Current snapshot — v(\d+\.\d+\.\d+)$", status, re.MULTILINE)
        self.assertIsNotNone(match)
        version = match.group(1)
        self.assertIn(
            f"[`v{version}` release](https://github.com/sumitake/agent-collab/releases/tag/v{version})",
            status,
        )
        self.assertRegex(
            status,
            rf"The signed annotated v{re.escape(version)} tag object `[^`]+` identifies public commit `[^`]+`",
        )
        current_release = f"Current published release: **{version}**"

        for path in (ROOT / "README.md", PLUGIN / "README.md"):
            with self.subTest(path=path):
                self.assertIn(current_release, path.read_text(encoding="utf-8"))

        root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"The v{version} closeout is recorded", root_readme)

        self.assertIn(f"## Current snapshot — v{version}", status)

    def test_marketplace_fragment_describes_the_direct_package(self) -> None:
        fragment = json.loads(
            (PLUGIN / "marketplace-fragment.json").read_text(encoding="utf-8")
        )
        self.assertIn("direct native runtime", fragment["description"])
        self.assertIn("moonshot", fragment["tags"])
        self.assertNotIn("glm", fragment["tags"])

    def test_distribution_documents_direct_semantic_runtime(self) -> None:
        text = (PLUGIN / "README.md").read_text(encoding="utf-8")
        for phrase in ("schema-4 manifest", "runtime protocol 4", "native contract 4", "new process group"):
            self.assertIn(phrase, text)

    def test_mit_engineering_process_pack_survives_the_version_5_cutover(self) -> None:
        names = {"architecture-review", "code-review", "decision-map", "prototype"}
        for name in names:
            skill = PLUGIN / "skills" / name / "SKILL.md"
            self.assertTrue(skill.is_file())
            text = skill.read_text(encoding="utf-8")
            self.assertIn("Copyright (c) 2026 Matt Pocock", text)
            self.assertRegex(
                text,
                r"Permission is hereby granted,\s+free of charge",
            )
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("docs/third-party-skill-provenance.md", notice)
        self.assertTrue((ROOT / "docs" / "third-party-skill-provenance.md").is_file())


if __name__ == "__main__":
    unittest.main()
