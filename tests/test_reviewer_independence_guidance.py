"""Generation and policy-scenario tests for reviewer selection evidence."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"
SPECS = ROOT / "skill-specs"
INDEPENDENCE_CONSUMERS = (
    "code-review",
    "debate",
    "logic-check",
    "merge-resolve",
    "qa-verify",
    "red-team",
    "second-opinion",
)
MARKER_START = "<!-- verifier-independence:start -->"
MARKER_END = "<!-- verifier-independence:end -->"
NATIVE_INTERNALS = (
    "sqlite",
    "protobuf",
    "conversations.db",
    "antigravity-cli",
    "field19",
    "gen_metadata",
    "trajectory_meta",
    "/.gemini/",
    "nolock",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _independence_block(text: str) -> str:
    return text.split(MARKER_START, 1)[1].split(MARKER_END, 1)[0]


class ReviewerIndependenceGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scaffold = _load_module(
            "reviewer_independence_scaffold",
            ROOT / "scripts" / "scaffold-skill-spec.py",
        )
        cls.build_skills = _load_module(
            "reviewer_independence_build_skills",
            ROOT / "scripts" / "build_skills.py",
        )
        cls.shared_block = _independence_block(
            cls.scaffold.VERIFIER_INDEPENDENCE_BLOCK
        )

    def test_authoring_template_and_seven_specs_share_the_independence_block(self) -> None:
        for name in INDEPENDENCE_CONSUMERS:
            spec = (SPECS / f"{name}.md").read_text(encoding="utf-8")
            generated = (PLUGIN / "skills" / name / "SKILL.md").read_text(
                encoding="utf-8"
            )
            with self.subTest(name=name):
                self.assertEqual(_independence_block(spec), self.shared_block)
                self.assertEqual(_independence_block(generated), self.shared_block)

    def test_planning_proves_route_eligibility_not_model_identity(self) -> None:
        normalized = " ".join(self.shared_block.split())
        self.assertIn(
            "Provider-free planning inspects eligible actions and routes; "
            "it does not prove model identity.",
            normalized,
        )
        self.assertIn(
            "Selecting a candidate and accepting independent approval are "
            "different stages.",
            normalized,
        )
        self.assertNotIn("inspect known family evidence", normalized)
        route = " ".join(
            (SPECS / "route.md").read_text(encoding="utf-8").split()
        )
        self.assertIn("planning does not prove model identity", route)
        self.assertNotIn("inspect known family evidence", route)
        invocation = self.build_skills.inject_runtime_invocation(
            "second-opinion",
            "---\nname: second-opinion\n---\n# Title\nbody\n",
        )
        self.assertIn(
            "Planning reports route eligibility, not model identity, "
            "live availability, or authentication.",
            invocation,
        )
        self.assertIn(
            "verify returned response-scoped native evidence before "
            "accepting independence",
            invocation,
        )
        self.assertNotIn(
            "verify returned native lineage before accepting independence",
            invocation,
        )

    def test_candidate_selection_uses_known_observations_then_binds_target(self) -> None:
        normalized = " ".join(self.shared_block.split())
        self.assertIn(
            "Use currently known native configuration or response-scoped "
            "observations for potential family selection only.",
            normalized,
        )
        self.assertIn("using `explicit_target`", normalized)
        self.assertIn(
            "Carry that same target into planning and live dispatch",
            normalized,
        )
        self.assertIn(
            "explain the missing capability or evidence before an expensive dispatch",
            normalized,
        )
        self.assertIn(
            "Do not classify an untried provider unavailable",
            normalized,
        )
        self.assertIn("An authorized advisory review may still proceed.", normalized)
        self.assertIn(
            "Do not classify an untried provider unavailable, loop operator "
            "waivers, or invent a required identity probe or schema service "
            "before every review.",
            normalized,
        )

    def test_same_family_contributors_cannot_count_as_independent(self) -> None:
        normalized = " ".join(self.shared_block.split())
        self.assertIn(
            "distinct from the primary and every contributing author family",
            normalized,
        )
        self.assertIn(
            "known primary, contributing-author, and reviewer lineages",
            normalized,
        )
        merge = " ".join(
            (SPECS / "merge-resolve.md").read_text(encoding="utf-8").split()
        )
        self.assertIn(
            "select and verify a resolver distinct from the primary and every "
            "known side-author family",
            merge,
        )

    def test_configuration_is_not_response_evidence(self) -> None:
        normalized = " ".join(self.shared_block.split())
        self.assertIn(
            "Configuration-scoped observations remain configuration; they "
            "never prove the model that produced the returned response.",
            normalized,
        )
        self.assertIn(
            "Independent approval requires response-scoped native evidence "
            "correlated to that returned response",
            normalized,
        )
        self.assertIn(
            "self-assertion, or configuration observation alone does not "
            "prove lineage",
            normalized,
        )
        governance = " ".join(
            (ROOT / "docs" / "public-governance.md").read_text(encoding="utf-8").split()
        )
        self.assertIn(
            "generation metadata at response scope",
            governance,
        )
        self.assertIn(
            "does not expand the public routing wire",
            governance,
        )
        self.assertIn(
            "Missing observation is evidence unavailability, not a "
            "provider-health verdict",
            governance,
        )

    def test_only_candidate_is_used_initially_and_tiebreaker_is_spare(self) -> None:
        text = " ".join(
            (SPECS / "second-opinion.md").read_text(encoding="utf-8").split()
        )
        generated = " ".join(
            (PLUGIN / "skills" / "second-opinion" / "SKILL.md").read_text(
                encoding="utf-8"
            ).split()
        )
        for label, body in (("spec", text), ("generated", generated)):
            with self.subTest(source=label):
                self.assertIn("Seat required initial reviewers first.", body)
                self.assertIn(
                    "Use a sole eligible independent reviewer in the initial wave",
                    body,
                )
                self.assertIn(
                    "reserve a tiebreaker only from spare independent eligible "
                    "reviewers after those seats are filled",
                    body,
                )
                self.assertIn(
                    "If the governing panel requires more reviewers than "
                    "available, keep that unmet requirement visible.",
                    body,
                )
                self.assertIn("A tiebreaker is spare capacity only.", body)
                self.assertNotIn(
                    "Hold one known-distinct eligible reviewer as the tiebreaker",
                    body,
                )

    def test_no_replay_for_missing_identity_and_corrected_review_policy_remains(self) -> None:
        normalized = " ".join(self.shared_block.split())
        self.assertIn(
            "Do not replay a consumed review to repair missing lineage, "
            "formatting, or adverse findings",
            normalized,
        )
        allowance = self.build_skills.FRESH_REVIEW_ALLOWANCE
        self.assertIn(
            "at most one new corrected request as a new work unit",
            allowance,
        )
        self.assertIn("repair formatting or missing lineage", allowance)
        self.assertNotIn("fresh-review allowance", self.shared_block)
        self.assertNotIn("new corrected request", self.shared_block)
        for name in sorted(self.build_skills.REVIEW_GOVERNANCE_SPECS):
            generated = (PLUGIN / "skills" / name / "SKILL.md").read_text(
                encoding="utf-8"
            )
            with self.subTest(name=name):
                self.assertIn(allowance, generated.split("\n# ", 1)[0])

    def test_governance_review_uses_shared_semantics_without_the_long_block(self) -> None:
        spec = (SPECS / "governance-review.md").read_text(encoding="utf-8")
        generated = (PLUGIN / "skills" / "governance-review" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        for label, text in (("spec", spec), ("generated", generated)):
            normalized = " ".join(text.split())
            with self.subTest(source=label):
                self.assertIn("every contributing author family", normalized)
                self.assertIn("every contributing artifact author", normalized)
                self.assertIn(
                    "planning reports route eligibility, not model identity",
                    normalized.casefold(),
                )
                self.assertIn("`explicit_target`", text)
                self.assertIn("response-scoped native evidence", normalized)
                self.assertIn("Missing evidence is not a provider outage.", normalized)
                self.assertIn(
                    "An authorized advisory review may still proceed.",
                    normalized,
                )
                self.assertIn("keep useful advisory content", normalized)
                self.assertIn("Public repository governance", normalized)
                self.assertNotIn(MARKER_START, text)
                self.assertNotIn("OpenCode name is transport information", text)

    def test_readme_invocation_matches_independence_semantics_and_keeps_history(self) -> None:
        text = (PLUGIN / "README.md").read_text(encoding="utf-8")
        preamble, rest = text.split("## Routing request", 1)
        invocation = rest.split("\n## ", 1)[0]
        normalized = " ".join(invocation.split())
        self.assertIn("every contributing author family", normalized)
        self.assertIn(
            "Planning reports route eligibility, not model identity, live "
            "availability, or authentication.",
            normalized,
        )
        self.assertIn("`explicit_target`", invocation)
        self.assertIn(
            "Verify returned response-scoped native evidence before accepting "
            "independent approval.",
            normalized,
        )
        self.assertIn(
            "Missing evidence keeps useful advisory content and does not "
            "imply a provider outage.",
            normalized,
        )
        self.assertIn("Configuration may identify a candidate", normalized)
        self.assertNotIn("verify the returned native lineage", invocation)
        self.assertIn(
            "The 7.0.6 content update corrects reviewer-independence instructions",
            preamble,
        )
        self.assertIn(
            "establishes the primary and artifact-author families",
            preamble,
        )
        self.assertIn("The 7.0.5 release restored migration-doctor reports", preamble)

    def test_chain_keeps_routing_exclusions_and_defers_identity_to_the_caller(self) -> None:
        spec = (SPECS / "chain.md").read_text(encoding="utf-8")
        generated = (PLUGIN / "skills" / "chain" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        for label, text in (("spec", spec), ("generated", generated)):
            normalized = " ".join(text.split())
            with self.subTest(source=label):
                self.assertIn(
                    "excludes both immutable primary and artifact-author families",
                    normalized,
                )
                self.assertIn(
                    "Anthropic, Google, OpenAI, xAI, Zhipu, and unknown lineage",
                    normalized,
                )
                self.assertIn(
                    "Route exclusions alone do not establish response identity "
                    "or all-contributor independence.",
                    normalized,
                )
                self.assertIn(
                    "The caller verifies those facts rather than claiming "
                    "changed chain execution.",
                    normalized,
                )

    def test_public_guidance_stays_provider_neutral(self) -> None:
        surfaces = [
            self.shared_block,
            (SPECS / "second-opinion.md").read_text(encoding="utf-8"),
            (SPECS / "route.md").read_text(encoding="utf-8"),
            (SPECS / "governance-review.md").read_text(encoding="utf-8"),
            (SPECS / "chain.md").read_text(encoding="utf-8"),
            (ROOT / "docs" / "public-governance.md").read_text(encoding="utf-8"),
            (SPECS / "README.md").read_text(encoding="utf-8"),
            (SPECS / "_AUTHORING_BRIEF.md").read_text(encoding="utf-8"),
            (PLUGIN / "README.md").read_text(encoding="utf-8"),
        ]
        for text in surfaces:
            lowered = text.casefold()
            for token in NATIVE_INTERNALS:
                with self.subTest(token=token):
                    self.assertNotIn(token.casefold(), lowered)


if __name__ == "__main__":
    unittest.main()
