"""Release evidence delegates contract validation to the direct release gate."""

from pathlib import Path
import importlib
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseEvidenceTests(unittest.TestCase):
    def test_release_sources_exist_without_legacy_setup_surface(self) -> None:
        self.assertTrue((ROOT / "scripts" / "build_release_evidence.py").is_file())
        self.assertTrue((ROOT / "scripts" / "verify_runtime_release.py").is_file())
        self.assertFalse((ROOT / "plugins" / "agent-collab" / "runtime_setup.py").exists())

    def test_release_evidence_preserves_mit_skill_membership(self) -> None:
        scripts = str(ROOT / "scripts")
        sys.path.insert(0, scripts)
        try:
            module = importlib.import_module("build_release_evidence")
        finally:
            sys.path.remove(scripts)
        self.assertEqual(
            module.MIT_DERIVED_SKILL_MEMBERS,
            frozenset(
                {
                    "skills/architecture-review/SKILL.md",
                    "skills/decision-map/SKILL.md",
                    "skills/prototype/SKILL.md",
                }
            ),
        )
        self.assertEqual(
            module.MIXED_LICENSE_SKILL_MEMBERS,
            frozenset(
                {
                    "skills/code-review/SKILL.md",
                    "skills/orchestrate/SKILL.md",
                    "skills/teamwork/SKILL.md",
                }
            ),
        )
        self.assertEqual(
            module.PACKAGE_LICENSE_EXPRESSION,
            "LicenseRef-PolyForm-Strict-1.0.0 AND MIT",
        )
        self.assertEqual(
            module._file_license("skills/code-review/SKILL.md", mode="policy-only"),
            module.PACKAGE_LICENSE_EXPRESSION,
        )
        self.assertEqual(
            module._file_license("skills/worker/SKILL.md", mode="policy-only"),
            module.SPDX_LICENSE,
        )


if __name__ == "__main__":
    unittest.main()
