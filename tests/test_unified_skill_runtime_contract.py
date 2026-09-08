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

    def test_generated_skills_and_host_manifests_are_version_7_0_6(self) -> None:
        for path in (PLUGIN / "skills").glob("*/SKILL.md"):
            self.assertIn("\nversion: 7.0.6\n", path.read_text(encoding="utf-8"))
        for host in (".claude-plugin", ".codex-plugin"):
            manifest = json.loads((PLUGIN / host / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], "7.0.6")

    def test_readme_documents_routing_only_protocol_five(self) -> None:
        text = (PLUGIN / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Routing request", text)
        self.assertIn("wire_contract_sha256", text)
        self.assertIn("12 logical actions", text)
        self.assertIn("protocol 5", text)
        self.assertIn("Provider final content is opaque", text)
        self.assertIn("full raw response", text)
        self.assertNotIn("## Coordinator request", text)
        self.assertNotIn("runtime_setup.py", text)

    def test_readmes_match_descriptor_cardinalities(self) -> None:
        descriptor = json.loads(
            (PLUGIN / "runtime-manifest.json").read_text(encoding="utf-8")
        )["wire_contract"]
        logical = len(descriptor["logical_actions"])
        root_section = self._section(
            (ROOT / "README.md").read_text(encoding="utf-8"), "Semantic actions"
        )
        package_section = self._section(
            (PLUGIN / "README.md").read_text(encoding="utf-8"),
            "Routing request",
        )

        for section, claims in (
            (
                root_section,
                ((r"\b(\d+) logical actions\b", logical),),
            ),
            (
                package_section,
                ((r"\b(\d+) logical actions\b", logical),),
            ),
        ):
            for pattern, expected in claims:
                with self.subTest(pattern=pattern, expected=expected):
                    self._assert_single_cardinality_claim(section, pattern, expected)

    def test_review_skills_reason_over_raw_content_without_format_gate(self) -> None:
        for skill in (
            "code-review", "second-opinion", "red-team", "qa-verify",
            "governance-review",
        ):
            with self.subTest(skill=skill):
                text = (PLUGIN / "skills" / skill / "SKILL.md").read_text(
                    encoding="utf-8"
                ).casefold()
                self.assertIn("ordinary model reasoning", text)
                self.assertIn("raw", text)
                self.assertIn("response", text)
                self.assertTrue("verdict" in text or "recommendation" in text)
                self.assertNotIn("invalid_final", text)

    def test_independence_consumers_share_caller_verified_contract(self) -> None:
        consumers = (
            "code-review",
            "debate",
            "logic-check",
            "merge-resolve",
            "qa-verify",
            "red-team",
            "second-opinion",
        )
        marker_start = "<!-- verifier-independence:start -->"
        marker_end = "<!-- verifier-independence:end -->"
        expected = None
        for name in consumers:
            spec_text = (ROOT / "skill-specs" / f"{name}.md").read_text(
                encoding="utf-8"
            )
            block = spec_text.split(marker_start, 1)[1].split(marker_end, 1)[0]
            if expected is None:
                expected = block
            with self.subTest(source=name):
                self.assertEqual(block, expected)
                self.assertIn("caller-verified governance evidence", block)
                self.assertIn("using `explicit_target`", block)
                self.assertIn("Carry that same target into planning and live", block)
                self.assertIn("Honor an operator-named provider", block)
                self.assertNotIn("only when the operator names", block)
                self.assertIn("all three\nlineages are known", block)
                self.assertIn("OpenCode name is transport information", block)
                self.assertNotIn("shared policy", block)
                self.assertNotIn("same_family_blocked", block)
                self.assertNotIn("unknown_family", block)

            rendered = (PLUGIN / "skills" / name / "SKILL.md").read_text(
                encoding="utf-8"
            )
            rendered_block = rendered.split(marker_start, 1)[1].split(marker_end, 1)[0]
            with self.subTest(generated=name):
                self.assertEqual(rendered_block, expected)

    def test_intro_does_not_assume_reviewer_family_or_promote_intent_authority(self) -> None:
        for name in ("code-review", "qa-verify", "red-team", "debate", "logic-check", "merge-resolve", "second-opinion"):
            text = (ROOT / "skill-specs" / (name + ".md")).read_text()
            intro = text.split("## When to use", 1)[0]
            with self.subTest(skill=name):
                self.assertNotIn("{{ primary_family }}", intro)
                self.assertNotIn("{{ verifier_family }}", intro)
                self.assertNotIn("for an independent cross-family", intro)
                self.assertRegex(intro, r"caller.{0,80}verif|caller establishes")
        intent = " ".join((ROOT / "skill-specs" / "intent-check.md").read_text().split())
        self.assertNotIn("Dispatch as independent governance", intent)
        self.assertIn("document intent remains context only", intent)
        self.assertIn("cannot satisfy a review or governance evidence contract", intent)

    def test_code_review_allows_advisory_without_clearing_independent_approval(self) -> None:
        for path in (ROOT / "skill-specs" / "code-review.md", PLUGIN / "skills" / "code-review" / "SKILL.md"):
            text = " ".join(path.read_text().split())
            with self.subTest(path=path):
                self.assertIn("Prefer an eligible reviewer whose known lineage differs", text)
                self.assertIn("When Gemini is the primary and only Gemini is available", text)
                self.assertIn("same-family advisory", text)
                self.assertIn("lineage-unverified advisory", text)
                self.assertIn("subscription name alone does not establish", text)
                self.assertIn("independent approval is required by the task or workflow", text)
                self.assertIn("approval requirement explicitly unmet", text)
                self.assertIn("do not keep attempting a provider", text)
                self.assertNotIn("terminal typed failure", text)

    def test_runtime_status_uses_one_zero_inference_all_action_request(self) -> None:
        text = " ".join((
            PLUGIN / "skills" / "agent-runtime-status" / "SKILL.md"
        ).read_text(encoding="utf-8").casefold().split())
        self.assertIn("dispatch_requested=false", text)
        self.assertIn("one caller-defined work unit for each of the 12", text)
        self.assertIn("do not issue one process per action", text)
        self.assertIn("do not invoke a provider as a readiness probe", text)

    def test_routed_skills_keep_one_attempt_and_preserve_content(self) -> None:
        build_skills = self._load_build_skills()
        for name in sorted(build_skills.ROUTED_SPECS):
            with self.subTest(name=name):
                text = (
                    PLUGIN / "skills" / name / "SKILL.md"
                ).read_text(encoding="utf-8")
                invocation = text.split("\n# ", 1)[0].lower()
                self.assertIn("one bounded json routing request", invocation)
                self.assertIn("one caller-defined work unit", invocation)
                self.assertIn("preserve every returned content record", invocation)
                self.assertIn("optional diagnostics", invocation)
                self.assertIn("at most one provider attempt per work unit", invocation)
                self.assertIn("never synthesize approval", invocation)

    def test_route_uses_protocol_five_explicit_target_field(self) -> None:
        text = (
            PLUGIN / "skills" / "route" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("`explicit_target`", text)
        self.assertNotIn("`target_agent`", text)

    def test_merge_resolve_uses_raw_content_without_format_replay(self) -> None:
        build_skills = self._load_build_skills()
        self.assertIn("merge-resolve", build_skills.ROUTED_SPECS)
        text = (
            PLUGIN / "skills" / "merge-resolve" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("raw response", text)
        self.assertIn("ordinary model reasoning", text)
        self.assertIn("do not replay", text.lower())
        self.assertNotIn("invalid_final", text)
        self.assertNotIn("Output ONLY these six sections", text)
        self.assertNotIn("**Retry-on-malformed.**", text)

    def test_logic_check_has_no_stale_answer_line_contract(self) -> None:
        text = (
            PLUGIN / "skills" / "logic-check" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("The `ANSWER:` line discipline", text)
        self.assertIn("constraints-explicit final-answer pattern", text)

    def test_routed_quality_repair_never_auto_replays_signed_artifact(self) -> None:
        cases = {
            "simulate-user": {
                "forbidden": (
                    "**Retry-on-out-of-character.**",
                    "Re-emit strictly in character",
                    "Push back; retry; surface if it fails twice.",
                ),
                "required": (
                    "Surface the out-of-character simulation as incomplete.",
                    "A later caller-authorized request is a new attempt.",
                ),
            },
            "qa-verify": {
                "forbidden": ("re-run the QA with the clarification",),
                "required": (
                    "Do not automatically issue a second provider request.",
                    "A later caller-authorized request is a new attempt.",
                ),
            },
            "brainstorm": {
                "forbidden": (
                    "push back with a follow-up:",
                    "Push back at least once for genuinely different angles before settling.",
                ),
                "required": (
                    "Show and synthesize the full raw response.",
                    "Only after the caller selects a cluster or explicitly authorizes a new request",
                ),
            },
            "debate": {
                "forbidden": (
                    'push back: "this is a debate, defend the side you were assigned forcefully."',
                    'push back: "you are arguing [side], defend it without hedging. The synthesis step is where balance returns."',
                ),
                "required": (
                    "Treat a conciliatory or hedged round as weaker evidence in the synthesis.",
                    "Do not issue a replacement provider request automatically.",
                ),
            },
        }

        for name, assertions in cases.items():
            for path in (
                ROOT / "skill-specs" / f"{name}.md",
                PLUGIN / "skills" / name / "SKILL.md",
            ):
                text = path.read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                for phrase in assertions["forbidden"]:
                    with self.subTest(name=name, path=path, forbidden=phrase):
                        self.assertNotIn(phrase, normalized)
                for phrase in assertions["required"]:
                    with self.subTest(name=name, path=path, required=phrase):
                        self.assertIn(phrase, normalized)

    def test_intent_check_uses_document_intent_action_without_format_gate(self) -> None:
        text = (
            PLUGIN / "skills" / "intent-check" / "SKILL.md"
        ).read_text(encoding="utf-8").casefold()
        self.assertIn("context.documents.intent", text)
        self.assertIn("quality_profile: standard", text)
        self.assertIn("effort_class: standard", text)
        self.assertIn("raw response", text)
        self.assertNotIn("invalid_final", text)

    def test_private_patch_remains_caller_owned_and_disposable(self) -> None:
        for name in ("worker", "dev-delegate"):
            with self.subTest(name=name):
                text = (
                    PLUGIN / "skills" / name / "SKILL.md"
                ).read_text(encoding="utf-8").casefold()
                for phrase in ("disposable", "patch", "caller", "cleanup", "source head"):
                    self.assertIn(phrase, text)
                self.assertIn("never infer a patch", text)

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
