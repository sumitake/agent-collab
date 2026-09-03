#!/usr/bin/env python3
"""Guard that the unified repository test roots are wired into CI."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow_text() -> str:
    paths = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


class TestCiTestCoverage(unittest.TestCase):
    def test_top_level_tests_are_discovered(self) -> None:
        self.assertTrue(list((ROOT / "tests").glob("test_*.py")))
        self.assertRegex(
            _workflow_text(),
            re.compile(r"python3? -m unittest discover -s tests\b"),
        )

    def test_script_tests_are_discovered(self) -> None:
        self.assertTrue(list((ROOT / "scripts").glob("test_*.py")))
        self.assertRegex(
            _workflow_text(),
            re.compile(r"python3? -m unittest discover -s scripts\b"),
        )

    def test_native_boundary_tests_are_explicit(self) -> None:
        text = _workflow_text()
        for module in (
            "tests.test_routing_runtime_client",
            "tests.test_protocol5_runtime_lifecycle",
            "tests.test_agent_collab_migration",
            "tests.test_routing_coordinator",
            "tests.test_public_export_safety",
            "tests.test_protocol5_public_contract",
            "tests.test_unified_skill_runtime_contract",
        ):
            self.assertIn(module, text)


if __name__ == "__main__":
    unittest.main()
