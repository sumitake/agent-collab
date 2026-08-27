"""Behavioral contract for the generated project-estimation skill."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "skill-specs" / "project-estimation.md"
GENERATED = ROOT / "plugins" / "agent-collab" / "skills" / "project-estimation" / "SKILL.md"
PLANNERS = ("architect", "orchestrate", "teamwork")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def frontmatter(text: str) -> str:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    return match.group(1) if match else ""


class ProjectEstimationSkillTests(unittest.TestCase):
    def test_source_and_generated_skill_exist_with_discoverable_triggers(self) -> None:
        self.assertTrue(SPEC.is_file(), "project-estimation source spec is missing")
        self.assertTrue(GENERATED.is_file(), "project-estimation generated skill is missing")
        description = frontmatter(read(SPEC))
        self.assertRegex(description, r"(?m)^description: Use when")
        for trigger in (
            "estimate this project",
            "scope this enhancement",
            "reconcile this estimate with actuals",
            "calibrate project estimates",
            "audit the estimation data",
            "how long an agent-led project",
            "API-equivalent token cost",
            "formal implementation design",
            "formal implementation plan",
        ):
            self.assertIn(trigger, description)

    def test_skill_contract_covers_request_modes_outputs_and_semantics(self) -> None:
        text = read(GENERATED)
        self.assertIn("## Modes", text)
        for mode in ("Estimate", "Reconcile", "Calibrate", "Audit"):
            self.assertRegex(text, rf"(?m)^\d+\. \*\*{mode}\*\*")
        for field in (
            "artifact_kind",
            "invocation_source",
            "artifact_scope_hash",
            "auto_invocation_depth",
            "requested_completion_boundary",
            "phases",
            "dependency_edges",
            "routes",
        ):
            self.assertIn(f"`{field}`", text)
        self.assertNotIn("`planned_agent_roles`", text)
        self.assertIn("each phase's `owner`, `prior_phase`, and optional `route_id`", text)
        self.assertIn("`<plugin-root>/project-estimation-data/`", text)
        for headline in (
            "focused agent wall-clock",
            "calendar elapsed",
            "API-equivalent token cost",
            "pricing status",
            "last successful official retrieval date",
        ):
            self.assertIn(headline, text)
        self.assertIn("not person-hours", text)
        self.assertIn("actual marginal cash", text)
        self.assertIn("quota", text)
        self.assertIn("completion taxonomy", text.lower())
        for state in (
            "planned",
            "source_present",
            "executed_unverified",
            "gate_verified",
            "merged",
            "released",
            "deployed",
            "operationally_verified",
        ):
            self.assertIn(f"`{state}`", text)
        for status in ("official", "proxy", "estimated", "estimated_stale", "unpriced"):
            self.assertIn(f"`{status}`", text)
        self.assertIn("reconcile", text.lower())

    def test_auto_checkpoint_is_pinned_compact_safe_and_non_recursive(self) -> None:
        text = read(GENERATED)
        normalized = " ".join(text.split())
        self.assertIn("`Delivery estimate`", text)
        self.assertIn("design_provisional", text)
        self.assertIn("implementation_plan", text)
        self.assertIn("once per distinct artifact-scope hash", normalized)
        self.assertIn("prior, pricing, and estimator hashes", normalized)
        self.assertIn("`auto_invocation_depth` of `0`", normalized)
        self.assertIn("`recursive_invocation`", text)
        self.assertIn("`estimate_unavailable`", text)
        self.assertIn("`insufficient_scope`", text)
        self.assertIn("read-only", text.lower())
        self.assertIn("explicitly requests persistence", normalized)
        self.assertIn("unsupported hosts", text.lower())
        self.assertIn("explicit invocation", text.lower())

    def test_package_planners_compose_one_checkpoint_at_finalization_boundary(self) -> None:
        for name in PLANNERS:
            with self.subTest(planner=name):
                text = read(ROOT / "skill-specs" / f"{name}.md")
                normalized = " ".join(text.split()).lower()
                self.assertEqual(text.count("project-estimation"), 1)
                self.assertIn("scope", normalized)
                self.assertIn("completion boundary", normalized)
                self.assertIn("phases", normalized)
                self.assertIn("dependencies", normalized)
                self.assertIn("gates", normalized)
                self.assertIn("before final presentation", normalized)
                self.assertIn("delivery estimate", normalized)
                self.assertIn("estimate_unavailable", normalized)
                self.assertIn("unsupported host", normalized)
                self.assertIn("explicit invocation", normalized)

    def test_package_planners_preserve_typed_unavailable_cost(self) -> None:
        for name in PLANNERS:
            with self.subTest(planner=name):
                normalized = " ".join(read(ROOT / "skill-specs" / f"{name}.md").split())
                self.assertIn("`unavailable_no_token_prior`", normalized)
                self.assertIn("must remain visible", normalized)
                self.assertIn("must not become zero or a workflow failure", normalized)

    def test_additive_version_is_consistent_across_canonical_distribution_surfaces(self) -> None:
        expected = "6.3.0"
        config = json.loads((ROOT / "scripts" / "skill-build-config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["agent-collab"]["skill_version"], expected)
        for manifest in (
            ROOT / "plugins" / "agent-collab" / ".claude-plugin" / "plugin.json",
            ROOT / "plugins" / "agent-collab" / ".codex-plugin" / "plugin.json",
        ):
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["version"], expected)
        marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(marketplace["metadata"]["version"], expected)
        self.assertEqual(marketplace["plugins"][0]["version"], expected)


if __name__ == "__main__":
    unittest.main()
