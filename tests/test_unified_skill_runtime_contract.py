"""Generated semantic skill distribution contract."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"


class UnifiedSkillRuntimeContractTests(unittest.TestCase):
    def test_generated_skills_and_host_manifests_are_version_5(self) -> None:
        for path in (PLUGIN / "skills").glob("*/SKILL.md"):
            self.assertIn("\nversion: 5.0.0\n", path.read_text(encoding="utf-8"))
        for host in (".claude-plugin", ".codex-plugin"):
            manifest = json.loads((PLUGIN / host / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], "5.0.0")

    def test_readme_documents_closed_semantic_coordinator(self) -> None:
        text = (PLUGIN / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Coordinator request", text)
        self.assertIn("wire_contract_sha256", text)
        self.assertIn("11 logical actions", text)
        self.assertNotIn("runtime_setup.py", text)


if __name__ == "__main__":
    unittest.main()
