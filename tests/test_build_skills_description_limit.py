import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_skills


class TestBuildSkillsDescriptionLimit(unittest.TestCase):
    def test_frontmatter_description_extracts_single_line_value(self):
        rendered = "---\nname: demo\ndescription: hello world\n---\nbody\n"

        self.assertEqual(
            build_skills.frontmatter_description(rendered),
            "hello world",
        )

    def test_validate_description_allows_exact_limit(self):
        rendered = (
            "---\n"
            "name: demo\n"
            f"description: {'x' * build_skills.MAX_SKILL_DESCRIPTION_CHARS}\n"
            "---\n"
        )

        build_skills.validate_description_length(rendered, "demo/SKILL.md")

    def test_validate_description_rejects_over_limit(self):
        rendered = (
            "---\n"
            "name: demo\n"
            f"description: {'x' * (build_skills.MAX_SKILL_DESCRIPTION_CHARS + 1)}\n"
            "---\n"
        )

        with self.assertRaisesRegex(ValueError, "description length 1025 exceeds 1024"):
            build_skills.validate_description_length(rendered, "demo/SKILL.md")

    def test_skill_tree_contract_rejects_extra_helpers_and_missing_specs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = root / "specs"
            skills = root / "skills"
            specs.mkdir()
            (specs / "demo.md").write_text("spec", encoding="utf-8")
            (skills / "demo").mkdir(parents=True)
            (skills / "demo" / "SKILL.md").write_text("skill", encoding="utf-8")
            self.assertEqual(build_skills.skill_tree_differences(skills, specs), ())

            (skills / "demo" / "helper.py").write_text("pass", encoding="utf-8")
            self.assertIn(
                "unexpected:demo/helper.py",
                build_skills.skill_tree_differences(skills, specs),
            )

            (skills / "demo" / "helper.py").unlink()
            (specs / "missing.md").write_text("spec", encoding="utf-8")
            differences = build_skills.skill_tree_differences(skills, specs)
            self.assertIn("missing:missing", differences)
            self.assertIn("missing:missing/SKILL.md", differences)


if __name__ == "__main__":
    unittest.main()
