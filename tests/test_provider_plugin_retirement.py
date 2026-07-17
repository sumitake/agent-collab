"""Regression contract for immediate codex-tools and glm-worker retirement."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETIRED = (
    "claude-collab",
    "codex-collab",
    "antigravity-collab",
    "codex-tools",
    "glm-worker",
    "grok-worker",
)


class ProviderPluginRetirementTests(unittest.TestCase):
    def test_standalone_provider_plugins_are_deleted(self) -> None:
        for name in RETIRED:
            with self.subTest(plugin=name):
                self.assertFalse((ROOT / "plugins" / name).exists())

    def test_generated_marketplace_has_only_unified_package(self) -> None:
        marketplace = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        names = {entry["name"] for entry in marketplace["plugins"]}
        self.assertEqual(names, {"agent-collab"})
        base = (ROOT / ".claude-plugin" / "marketplace.base.json").read_text(
            encoding="utf-8"
        )
        for name in RETIRED:
            self.assertNotIn(name, base)

    def test_generic_agent_collab_plugin_owns_central_roles(self) -> None:
        root = ROOT / "plugins" / "agent-collab"
        manifest = json.loads(
            (root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["name"], "agent-collab")
        readme = (root / "README.md").read_text(encoding="utf-8")
        for phrase in (
            "target=codex",
            "target=opencode",
            "target=gemini",
            "target=grok",
            "target=composer",
            "Gemini advisory",
            "Codex advisory",
            "Codex build",
            "OpenCode plan",
            "OpenCode build",
            "opencode/glm-5.2",
            "Zhipu",
            "Grok 4.5",
            "`composer/codegen` compatibility",
            "Claude",
            "async inbox",
            "temporarily unavailable",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)

    def test_active_skills_have_no_raw_provider_recipe_or_retired_namespace(self) -> None:
        paths = list((ROOT / "skill-specs").glob("*.md"))
        paths.extend((ROOT / "plugins" / "agent-collab" / "skills").rglob("SKILL.md"))
        forbidden = (
            "codex-tools:",
            "glm-worker:",
            "plugin install codex-tools",
            "plugin install glm-worker",
            "codex exec --sandbox workspace-write",
            "command -v codex",
            "opencode run -m",
            "scripts/opencode_exec.py",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                for token in forbidden:
                    self.assertNotIn(token, text)

    def test_generated_skills_do_not_promise_unsupported_public_inputs(self) -> None:
        paths = list((ROOT / "skill-specs").glob("*.md"))
        paths.extend((ROOT / "plugins" / "agent-collab" / "skills").rglob("SKILL.md"))
        forbidden = (
            "@path",
            "@file",
            "role payload",
            "depending on backend",
            "underlying CLI supports local attachments",
            "Attach the image",
            "Attach files",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                for token in forbidden:
                    self.assertNotIn(token, text)

    def test_public_package_has_no_provider_executor_or_compatibility_source(self) -> None:
        root = ROOT / "plugins" / "agent-collab"
        for directory in ("backend", "mcp-server", "scripts", "agents", "hooks"):
            with self.subTest(directory=directory):
                self.assertFalse((root / directory).exists())
        python_files = {path.name for path in root.glob("*.py")}
        self.assertEqual(
            python_files,
            {
                "coordinator.py",
                "runtime_bundle.py",
                "runtime_client.py",
                "runtime_setup.py",
                "host_policy.py",
                "migration_doctor.py",
                "signing_policy.py",
            },
        )

    def test_release_tooling_has_no_retired_tag_mapping(self) -> None:
        paths = [
            ROOT / ".github" / "workflows" / "release.yml",
            ROOT / "scripts" / "merge-and-tag.py",
            ROOT / "scripts" / "check_release_consistency.py",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("v-codex-tools-", text)
                self.assertNotIn("v-glm-worker-", text)

    def test_public_security_workflows_are_present(self) -> None:
        codeql = (ROOT / ".github" / "workflows" / "codeql.yml").read_text(
            encoding="utf-8"
        )
        secret_scan = (
            ROOT / ".github" / "workflows" / "secret-scan.yml"
        ).read_text(encoding="utf-8")
        self.assertRegex(
            codeql, r"github/codeql-action/init@[0-9a-f]{40} # v4"
        )
        self.assertRegex(
            codeql, r"github/codeql-action/analyze@[0-9a-f]{40} # v4"
        )
        self.assertRegex(codeql, r"(?m)^  actions: read$")
        self.assertIn("id: analyze", codeql)
        self.assertIn(
            "upload: ${{ github.event.repository.private && 'never' || 'always' }}",
            codeql,
        )
        self.assertIn("if: github.event.repository.private", codeql)
        self.assertRegex(
            codeql, r"actions/upload-artifact@[0-9a-f]{40} # v4"
        )
        self.assertIn("path: ${{ steps.analyze.outputs.sarif-output }}", codeql)
        self.assertIn("scripts/secret_scan.py", secret_scan)

    def test_active_docs_use_migration_paths_not_retired_install_surfaces(self) -> None:
        paths = [ROOT / "README.md"]
        paths.append(ROOT / "plugins" / "agent-collab" / "README.md")
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("plugin install codex-tools", text)
                self.assertNotIn("plugin install glm-worker", text)
                self.assertNotIn("codex-tools:", text)
                self.assertNotIn("glm-worker:", text)

        root = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("codex-tools →", root)
        self.assertIn("glm-worker →", root)
        self.assertIn("managed Codex backend", root)
        self.assertIn("managed OpenCode backend", root)

    def test_breaking_change_fragment_records_both_replacements(self) -> None:
        fragment = (
            ROOT / "changelog.d" / "2026-07-12-provider-plugin-retirement.md"
        ).read_text(encoding="utf-8")
        self.assertIn("codex-tools", fragment)
        self.assertIn("glm-worker", fragment)
        self.assertIn("agent-collab", fragment)
        self.assertIn("opencode/glm-5.2", fragment)
        self.assertIn("breaking", fragment.lower())

    def test_migration_table_covers_every_retired_skill_namespace(self) -> None:
        migration = (
            ROOT / "docs" / "migration-from-legacy-packages.md"
        ).read_text(encoding="utf-8")
        # Historical coverage must be pinned independently of the current
        # unified spec set: new agent-collab-only skills never existed under
        # the retired namespaces and therefore need no fictitious old command.
        shared = {
            "agent-readiness",
            "agent-runtime-status",
            "autonomy-readiness",
            "brainstorm",
            "chain",
            "chain-configurator",
            "code-review",
            "compose-skills",
            "debate",
            "delegate",
            "dev-delegate",
            "intent-check",
            "knowledge-compile",
            "logic-check",
            "long-context",
            "orchestrate",
            "qa-verify",
            "red-team",
            "second-opinion",
            "simulate-user",
            "teamwork",
            "ui-to-code",
            "untrusted-audit",
            "visual-review",
        }
        for package in ("claude-collab", "codex-collab", "antigravity-collab"):
            for skill in sorted(shared - ({"teamwork"} if package != "claude-collab" else set())):
                with self.subTest(package=package, skill=skill):
                    self.assertIn(f"/{package}:{skill}", migration)
                    self.assertIn(f"/agent-collab:{skill}", migration)
        for package in (
            "agent-collab",
            "claude-collab",
            "codex-collab",
            "antigravity-collab",
        ):
            self.assertIn(f"/{package}:ai-merge-resolve", migration)
        self.assertIn("/agent-collab:merge-resolve", migration)
        for command in (
            "/codex-tools:codex-build-coding",
            "/codex-tools:codex-high-stakes-advisor",
            "/codex-tools:codex-second-opinion",
            "/codex-tools:codex-tiebreaker",
            "/glm-worker:glm-coding",
            "/glm-worker:glm-huge-context",
            "/grok-worker:grok-build-coding",
            "/grok-worker:grok-huge-context",
            "/grok-worker:grok-parallel-execution",
        ):
            with self.subTest(command=command):
                self.assertIn(command, migration)


if __name__ == "__main__":
    unittest.main()
