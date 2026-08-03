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
    def test_generated_skills_and_host_manifests_are_version_5(self) -> None:
        for path in (PLUGIN / "skills").glob("*/SKILL.md"):
            self.assertIn("\nversion: 5.0.0\n", path.read_text(encoding="utf-8"))
        for host in (".claude-plugin", ".codex-plugin"):
            manifest = json.loads((PLUGIN / host / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], "5.0.0")

    def test_readme_documents_closed_semantic_coordinator(self) -> None:
        text = (PLUGIN / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Coordinator request", text)
        self.assertIn("wire_contract_sha256", text)
        self.assertIn("11 logical actions", text)
        self.assertNotIn("runtime_setup.py", text)

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
                "timeout_ms": 120000,
            },
        )
        self.assertRegex(text.lower(), r"do not issue one\s+request per action")


if __name__ == "__main__":
    unittest.main()
