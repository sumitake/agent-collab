"""Public authority and containment semantics for managed provider execution."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"


def _load_host_policy():
    spec = importlib.util.spec_from_file_location(
        "structural_containment_host_policy", PLUGIN / "host_policy.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class StructuralContainmentAuthorityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = _load_host_policy()

    def test_opencode_build_returns_output_without_caller_workspace_authority(
        self,
    ) -> None:
        self.assertEqual(
            self.policy.AUTHORITIES[("opencode", "build")],
            "output_only",
        )

    def test_public_worker_contract_uses_private_workspace(self) -> None:
        paths = (
            ROOT / "README.md",
            PLUGIN / "README.md",
            ROOT / "skill-specs" / "worker.md",
            ROOT / "skill-specs" / "dev-delegate.md",
            ROOT / "skill-specs" / "route.md",
            PLUGIN / "skills" / "worker" / "SKILL.md",
            PLUGIN / "skills" / "dev-delegate" / "SKILL.md",
            PLUGIN / "skills" / "route" / "SKILL.md",
        )
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        normalized = " ".join(combined.split()).lower()
        self.assertIn("private temporary workspace", normalized)
        self.assertIn("output-only", normalized)
        self.assertNotIn("opencode build is mutation-capable workspace-write", normalized)
        self.assertNotIn("opencode build with exact workspace-write authority", normalized)

    def test_public_docs_define_structural_rare_containment_failure(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "README.md", PLUGIN / "README.md")
        )
        normalized = " ".join(combined.split()).lower()
        for phrase in (
            "canonical user home",
            "same-uid read trust",
            "not a deny-all-read confidentiality boundary",
            "blocked access attempt",
            "containment success",
            "structural containment failure",
            "authentication, protocol/output, timeout, provider, teardown, and cleanup",
            "direct cli",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, normalized)


if __name__ == "__main__":
    unittest.main()
