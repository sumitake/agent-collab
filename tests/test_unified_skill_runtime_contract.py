"""Generated unified skills must be standalone and dynamically routed."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "plugins" / "agent-collab" / "skills"
SPECS = ROOT / "skill-specs"
ROUTED_SKILLS = {
    "agent-runtime-status",
    "brainstorm",
    "code-review",
    "debate",
    "delegate",
    "dev-delegate",
    "governance-review",
    "intent-check",
    "logic-check",
    "long-context",
    "migration-doctor",
    "qa-verify",
    "red-team",
    "route",
    "second-opinion",
    "simulate-user",
    "worker",
}


class UnifiedSkillRuntimeContractTests(unittest.TestCase):
    def test_routed_skills_use_plugin_relative_public_coordinator(self) -> None:
        for name in sorted(ROUTED_SKILLS):
            with self.subTest(skill=name):
                text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("coordinator.py", text)
                self.assertIn("plugin root", text.lower())
                self.assertIn("README.md", text)
                self.assertRegex(text.lower(), r"request\s+schema")
                self.assertNotIn("workspace-managed backend", text)
                self.assertNotIn("workspace collaboration core", text)

    def test_plugin_readme_documents_closed_coordinator_schema(self) -> None:
        text = (ROOT / "plugins" / "agent-collab" / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## Coordinator request schema", text)
        for field in (
            "protocol_version",
            "request_id",
            "operation",
            "route",
            "action",
            "timeout_ms",
            "governance",
            "primary",
            "row",
        ):
            with self.subTest(field=field):
                self.assertIn(f"`{field}`", text)
        for contract in (
            "gemini/advisory",
            "gemini/governance",
            "gemini/long_context",
            "codex/advisory",
            "opencode/plan",
            "opencode/build",
            "grok/architecture",
            "grok/governance",
            "grok/huge_context",
            "composer/codegen",
        ):
            with self.subTest(contract=contract):
                self.assertIn(f"`{contract}`", text)
        for unavailable in ("codex/build", "auto/worker"):
            with self.subTest(unavailable=unavailable):
                self.assertIn(f"`{unavailable}`", text)
        self.assertIn("coordinator-only", text)
        self.assertIn("never enter the signed native manifest", text)
        self.assertIn("`inbox/async`", text)
        self.assertIn("readiness", text)
        self.assertIn("never sends", text)
        self.assertIn("`async_inbox`", text)
        self.assertIn('"target_id":"claude|antigravity"', text)
        self.assertIn('"target_family":"anthropic|google"', text)
        self.assertIn('"target_session_identifier":"..."', text)
        self.assertIn("complete trustworthy primary identity", text)
        self.assertIn("conflicting current-session and explicit identity", text)
        for field in (
            '"encoding": "base64"',
            '"sha256"',
            '"size"',
            '"author_model"',
            '"author_family"',
        ):
            with self.subTest(native_artifact_field=field):
                self.assertIn(field, text)

    def test_active_skills_do_not_claim_unobserved_inbox_availability(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(SKILLS.glob("*/SKILL.md"))
        ).lower()
        for false_claim in (
            "validated async inbox/coordination remains available",
            "safe mode retains inbox/coordination",
            "only the validated asynchronous inbox",
        ):
            with self.subTest(false_claim=false_claim):
                self.assertNotIn(false_claim, combined)
        self.assertIn("public coordinator never sends", combined)

    def test_runtime_status_uses_explicit_async_target_provenance(self) -> None:
        text = (SKILLS / "agent-runtime-status" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("with an empty row", text)
        self.assertIn('"target_id":"claude|antigravity"', text)
        self.assertIn('"target_family":"anthropic|google"', text)
        self.assertIn('"target_session_identifier":"..."', text)
        self.assertIn("same-family", text)
        self.assertIn("never invoked headlessly", text)

    def test_visual_skills_disclose_missing_typed_image_transport(self) -> None:
        for name in ("visual-review", "ui-to-code"):
            with self.subTest(skill=name):
                text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("temporarily unavailable", text)
                self.assertIn("primary-only", text)
                self.assertNotIn("@path", text)
                self.assertNotIn("attach the image", text.lower())

    def test_governance_skill_uses_real_typed_statuses(self) -> None:
        text = (SKILLS / "governance-review" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        for status in ("unknown_family", "same_family_blocked", "unavailable"):
            self.assertIn(f"`{status}`", text)
        for fictional in (
            "unknown_primary_family",
            "unknown_artifact_family",
            "no_eligible_backend",
        ):
            self.assertNotIn(fictional, text)

    def test_intent_check_effort_guidance_matches_closed_route_contracts(self) -> None:
        for path in (
            SPECS / "intent-check.md",
            SKILLS / "intent-check" / "SKILL.md",
        ):
            text = path.read_text(encoding="utf-8")
            normalized = " ".join(text.split())
            with self.subTest(path=path):
                self.assertIn("Gemini governance row at high effort", normalized)
                self.assertIn("Codex advisory row at low effort", normalized)
                self.assertIn("Grok governance fallback at high effort", normalized)
                self.assertNotIn("low effort for the Gemini/Codex", normalized)

    def test_root_readme_documents_current_codex_install_commands(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "codex plugin marketplace add sumitake/agent-collab", text
        )
        self.assertIn("codex plugin add agent-collab@agent-collab", text)
        self.assertNotIn("codex plugin install agent-collab", text)

    def test_active_skills_do_not_require_private_workspace_checkout(self) -> None:
        prohibited = (
            "AGENT_COLLAB_WORKSPACE",
            "agent-collab-workspace",
            "workspace checkout",
            "workspace script",
            "Claude-as-runtime",
            "Claude-side equivalent",
        )
        for path in sorted(SKILLS.glob("*/SKILL.md")):
            text = path.read_text(encoding="utf-8")
            for marker in prohibited:
                with self.subTest(skill=path.parent.name, marker=marker):
                    self.assertNotIn(marker, text)

    def test_specs_have_no_fixed_reviewer_or_legacy_sibling_policy(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(SPECS.glob("*.md"))
        )
        for marker in (
            "Codex tiebreaker",
            "Codex is a tiebreaker",
            "{{ sibling_package }}",
            "currently claude / antigravity / codex / grok",
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, combined)

    def test_chain_has_no_family_prefixed_or_sibling_fallback(self) -> None:
        for path in (
            SPECS / "chain.md",
            SKILLS / "chain" / "SKILL.md",
        ):
            text = path.read_text(encoding="utf-8")
            for marker in (
                "<verifier-family>-skill",
                "sibling package",
                "accepts BOTH forms",
                "migration window",
                "Gemini/Anthropic calls",
            ):
                with self.subTest(path=path, marker=marker):
                    self.assertNotIn(marker, text)

    def test_chain_uses_package_neutral_application_state_paths(self) -> None:
        for path in (SPECS / "chain.md", SKILLS / "chain" / "SKILL.md"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertNotIn("~/.claude", text)
                self.assertNotIn("~/.codex", text)
                self.assertNotIn("~/.agent-collab", text)
                self.assertIn(
                    "~/Library/Application Support/agent-collab", text
                )

    def test_generator_config_has_no_hardcoded_primary_or_sibling_package(self) -> None:
        config = json.loads(
            (ROOT / "scripts" / "skill-build-config.json").read_text(encoding="utf-8")
        )["agent-collab"]
        self.assertNotIn("sibling_package", config)
        self.assertEqual(config["primary_agent"], "the active primary")
        self.assertIn("coordinator.py", config["mcp_tool_ask"])

    def test_command_substitutions_are_bare_and_generated_markdown_is_well_formed(self) -> None:
        config = json.loads(
            (ROOT / "scripts" / "skill-build-config.json").read_text(
                encoding="utf-8"
            )
        )["agent-collab"]
        command = 'python3 "<plugin-root>/coordinator.py"'
        for key in (
            "mcp_server",
            "mcp_tool_ask",
            "mcp_tool_ask_short",
            "mcp_tool_brainstorm",
            "mcp_tool_fetch_chunk",
            "google_backend_call",
            "openai_backend_call",
            "backend_cli",
        ):
            with self.subTest(key=key):
                self.assertEqual(config[key], command)

        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(SKILLS.glob("*/SKILL.md"))
        )
        self.assertNotIn(
            "through `the plugin-relative public coordinator at `python3", combined
        )
        self.assertNotIn(
            "Invoke `the plugin-relative public coordinator at `python3", combined
        )

    def test_grok_and_composer_use_exact_role_terminology(self) -> None:
        readme = (ROOT / "plugins" / "agent-collab" / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "Grok 4.5 read-only architecture consultation, governance review, "
            "huge-context ingestion, and output-only code/patch generation "
            "through the `composer/codegen` compatibility route",
            " ".join(readme.split()),
        )
        self.assertNotIn("Composer output-only code/patch generation", readme)
        self.assertIn("`protocol_version` is integer `2`", readme)
        for selection in (
            "`simple_codegen` has a low minimum",
            "`standard_codegen` a medium minimum",
            "`complex_codegen` a high minimum",
            "same author model, `xai/grok-4.5`",
        ):
            self.assertIn(selection, " ".join(readme.split()))

        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                [ROOT / "plugins" / "agent-collab" / "README.md"]
                + sorted(SPECS.glob("*.md"))
                + sorted(SKILLS.glob("*/SKILL.md"))
            )
        )
        normalized = " ".join(combined.split())
        for malformed in (
            "Grok 4.5 advisory",
            "Grok advisory row",
            "Grok advisory role",
            "Grok advisory/huge-context",
        ):
            with self.subTest(malformed=malformed):
                self.assertNotIn(malformed, normalized)


if __name__ == "__main__":
    unittest.main()
