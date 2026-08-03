"""Provider-neutral private-patch authority boundary."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StructuralContainmentAuthorityContractTests(unittest.TestCase):
    def test_codegen_skills_return_private_patch_without_caller_authority(self) -> None:
        for name in ("worker", "dev-delegate"):
            source = (ROOT / "skill-specs" / f"{name}.md").read_text(encoding="utf-8").lower()
            with self.subTest(name=name):
                self.assertIn("private", source)
                self.assertIn("patch", source)
                self.assertIn("never", source)
                self.assertIn("caller", source)


if __name__ == "__main__":
    unittest.main()
