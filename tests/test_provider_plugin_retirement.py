"""Breaking removal of retired public provider surfaces."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"


class ProviderPluginRetirementTests(unittest.TestCase):
    def test_only_unified_package_and_context_skill_are_published(self) -> None:
        self.assertEqual([path.name for path in (ROOT / "plugins").iterdir() if path.is_dir()], ["agent-collab"])
        self.assertTrue((PLUGIN / "skills" / "context" / "SKILL.md").is_file())
        self.assertFalse((PLUGIN / "skills" / "long-context").exists())

    def test_no_public_setup_or_separate_output_contract_remains(self) -> None:
        self.assertFalse((PLUGIN / "runtime_setup.py").exists())
        self.assertFalse((PLUGIN / "execute-output-contract-v1.json").exists())


if __name__ == "__main__":
    unittest.main()
