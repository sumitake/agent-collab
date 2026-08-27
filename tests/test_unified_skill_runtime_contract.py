"""Generated semantic skill distribution contract."""

import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"


class UnifiedSkillRuntimeContractTests(unittest.TestCase):
    def _section(self, text: str, heading: str) -> str:
        section = text.split(f"## {heading}\n", 1)[1]
        return section.split("\n## ", 1)[0]

    def _assert_single_cardinality_claim(
        self, section: str, pattern: str, expected: int
    ) -> None:
        self.assertEqual([str(expected)], re.findall(pattern, section))

    def test_generated_skills_and_host_manifests_are_version_6(self) -> None:
        for path in (PLUGIN / "skills").glob("*/SKILL.md"):
            self.assertIn("\nversion: 6.3.0\n", path.read_text(encoding="utf-8"))
        for host in (".claude-plugin", ".codex-plugin"):
            manifest = json.loads((PLUGIN / host / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], "6.3.0")

    def test_readme_documents_closed_semantic_coordinator(self) -> None:
        text = (PLUGIN / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Coordinator request", text)
        self.assertIn("wire_contract_sha256", text)
        self.assertIn("12 logical actions", text)
        self.assertNotIn("runtime_setup.py", text)

    def test_readmes_match_descriptor_cardinalities(self) -> None:
        descriptor = json.loads(
            (PLUGIN / "runtime-manifest.json").read_text(encoding="utf-8")
        )["wire_contract"]
        logical = len(descriptor["logical_actions"])
        transports = len(descriptor["base_transport_actions"])
        pairs = len(descriptor["valid_action_source_pairs"])
        root_section = self._section(
            (ROOT / "README.md").read_text(encoding="utf-8"), "Semantic actions"
        )
        package_section = self._section(
            (PLUGIN / "README.md").read_text(encoding="utf-8"),
            "Direct runtime boundary",
        )

        for section, claims in (
            (
                root_section,
                (
                    (r"\b(\d+) logical actions\b", logical),
                    (r"\b(\d+)\s+transport actions\b", transports),
                    (r"\b(\d+)\s+action/source pairs\b", pairs),
                ),
            ),
            (
                package_section,
                (
                    (r"\b(\d+) logical actions\b", logical),
                    (r"\b(\d+) source-collapsed provider transport actions\b", transports),
                    (r"\b(\d+) currently valid action/source pairs\b", pairs),
                ),
            ),
        ):
            for pattern, expected in claims:
                with self.subTest(pattern=pattern, expected=expected):
                    self._assert_single_cardinality_claim(section, pattern, expected)

    def test_review_skill_examples_are_accepted_closed_coordinator_requests(self) -> None:
        def load(name: str, path: Path):
            spec = importlib.util.spec_from_file_location(name, path)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module

        coordinator = load("skill_example_coordinator", PLUGIN / "coordinator.py")
        client = load("skill_example_client", PLUGIN / "runtime_client.py")
        policy = load("skill_example_policy", PLUGIN / "host_policy.py")
        from tests.test_direct_runtime_public_contract import _wire_descriptor

        descriptor, digest = _wire_descriptor()
        wire = client.validate_wire_descriptor(descriptor, expected_sha256=digest)
        host = policy.HostProfile(
            "codex", "openai", "gpt-test", "codex", "session-1", False,
            governance_ready=True,
        )
        for skill in ("code-review", "second-opinion", "red-team"):
            text = (PLUGIN / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            match = re.search(r"```json coordinator-request\n(.+?)\n```", text, re.S)
            self.assertIsNotNone(match, skill)
            request = json.loads(match.group(1))
            request["repo_root"] = str(ROOT)
            native = coordinator.validate_request(request, wire, host)
            self.assertEqual(native["logical_action"], "review.repository")

    def test_runtime_status_uses_one_closed_all_action_request(self) -> None:
        text = (
            PLUGIN / "skills" / "agent-runtime-status" / "SKILL.md"
        ).read_text(encoding="utf-8")
        invocation = text.split("\n# Agent runtime status\n", 1)[0]
        self.assertIn("one bounded JSON readiness request", invocation)
        self.assertIn("complete all-action readiness matrix", invocation)
        self.assertIn("zero-inference", invocation)
        for routed_request_claim in (
            "logical action",
            "target agent",
            "prompt",
            "source",
            "`repo_root`",
            "`documents`",
        ):
            self.assertNotIn(routed_request_claim, invocation.lower())

        ordinary = (
            PLUGIN / "skills" / "code-review" / "SKILL.md"
        ).read_text(encoding="utf-8")
        ordinary_invocation = ordinary.split("\n# Code review\n", 1)[0]
        self.assertIn("one logical action and optional target agent", ordinary_invocation)

        matches = re.findall(r"```json coordinator-request\n(.+?)\n```", text, re.S)
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            json.loads(matches[0]),
            {
                "operation": "readiness",
                "request_id": "runtime-status-1",
                "quality_profile": "frontier",
                "effort_class": "maximum",
                "timeout_ms": 120000,
            },
        )
        self.assertRegex(text.lower(), r"do not issue one\s+request per action")

    def test_lifecycle_guide_uses_the_closed_runtime_status_request(self) -> None:
        skill = (
            PLUGIN / "skills" / "agent-runtime-status" / "SKILL.md"
        ).read_text(encoding="utf-8")
        skill_match = re.search(
            r"```json coordinator-request\n(.+?)\n```", skill, re.S
        )
        self.assertIsNotNone(skill_match)

        guide = (
            ROOT / "docs" / "architecture" / "lifecycle-and-operations.md"
        ).read_text(encoding="utf-8")
        guide_match = re.search(
            r"printf '%s\\n' '(\{.+?\})' \| python3 "
            r'"<installed-plugin-root>/coordinator\.py"',
            guide,
        )
        self.assertIsNotNone(guide_match)
        self.assertEqual(
            json.loads(guide_match.group(1)),
            json.loads(skill_match.group(1)),
        )

    def test_routed_skills_keep_provider_failures_attempt_local(self) -> None:
        """Invocation failures must never become an implicit route quarantine."""
        build_skills = self._load_build_skills()
        for name in sorted(build_skills.ROUTED_SPECS):
            with self.subTest(name=name):
                text = (
                    PLUGIN / "skills" / name / "SKILL.md"
                ).read_text(encoding="utf-8")
                invocation = text.split("\n# ", 1)[0].lower()
                self.assertIn("`provider_error` and `teardown_error`", invocation)
                self.assertIn("attempt-local", invocation)
                self.assertIn("must not quarantine", invocation)
                self.assertIn("route or provider unavailability", invocation)
                self.assertIn("must not automatically replay", invocation)
                self.assertIn("fresh readiness", invocation)

    def test_intent_check_uses_the_descriptor_owned_untargeted_action(self) -> None:
        text = (
            PLUGIN / "skills" / "intent-check" / "SKILL.md"
        ).read_text(encoding="utf-8")
        matches = re.findall(r"```json coordinator-request\n(.+?)\n```", text, re.S)
        self.assertEqual(len(matches), 1)
        request = json.loads(matches[0])
        self.assertEqual(request["logical_action"], "context.documents.intent")
        self.assertIsNone(request["target_agent"])
        # standard/standard per the operator-adjudicated verify-intent
        # effort floors (workspace #2771; skill companion in v6.0.6).
        self.assertEqual(request["quality_profile"], "standard")
        self.assertEqual(request["effort_class"], "standard")
        self.assertEqual(
            set(request),
            {
                "request_id",
                "logical_action",
                "quality_profile",
                "effort_class",
                "target_agent",
                "timeout_ms",
                "prompt",
                "documents",
            },
        )

    @staticmethod
    def _load_build_skills():
        spec = importlib.util.spec_from_file_location(
            "unified_skill_build_contract", ROOT / "scripts" / "build_skills.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


if __name__ == "__main__":
    unittest.main()
