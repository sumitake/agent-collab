"""Breaking public contract for the direct semantic runtime package."""

from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"
SPECS = ROOT / "skill-specs"
SKILLS = PLUGIN / "skills"

LOGICAL_ACTIONS = (
    "architecture.conceptual",
    "architecture.repository",
    "codegen.repository",
    "context.documents.extract",
    "context.documents.reason",
    "context.repository.extract",
    "context.repository.reason",
    "frontend_codegen.repository",
    "frontend_review.repository",
    "governance.repository",
    "review.repository",
)

TRANSPORT_ACTIONS = (
    ("codex", "advisory"),
    ("codex", "governance"),
    ("gemini", "advisory"),
    ("gemini", "context"),
    ("gemini", "governance"),
    ("grok", "architecture"),
    ("grok", "codegen"),
    ("grok", "context"),
    ("grok", "governance"),
    ("opencode", "build"),
    ("opencode", "context"),
    ("opencode", "plan"),
)

ACTION_SOURCE_PAIRS = (
    ("codex", "advisory", "repository"),
    ("codex", "governance", "repository"),
    ("gemini", "advisory", "repository"),
    ("gemini", "context", "documents"),
    ("gemini", "context", "repository"),
    ("gemini", "governance", "repository"),
    ("grok", "architecture", "conceptual_prompt"),
    ("grok", "architecture", "repository"),
    ("grok", "codegen", "repository"),
    ("grok", "context", "documents"),
    ("grok", "context", "repository"),
    ("grok", "governance", "repository"),
    ("opencode", "build", "repository"),
    ("opencode", "context", "documents"),
    ("opencode", "context", "repository"),
    ("opencode", "plan", "repository"),
)


def _wire_descriptor() -> tuple[dict[str, object], str]:
    closed_schema = {"type": "object", "additionalProperties": False}
    semantic_request = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "wire_contract_sha256",
            "request_id",
            "logical_action",
            "target_agent",
            "author_lineage",
            "timeout_ms",
            "prompt",
            "source",
        ],
        "properties": {
            "wire_contract_sha256": {"type": "string"},
            "request_id": {"type": "string"},
            "logical_action": {"type": "string"},
            "target_agent": {"type": ["string", "null"]},
            "author_lineage": {"type": ["string", "null"]},
            "timeout_ms": {"type": "integer", "minimum": 1, "maximum": 600000},
            "prompt": {"type": "string"},
            "source": {"type": "object"},
        },
    }
    descriptor: dict[str, object] = {
        "schema_version": 2,
        "runtime_protocol_version": 3,
        "logical_actions": list(LOGICAL_ACTIONS),
        "base_transport_actions": [list(row) for row in TRANSPORT_ACTIONS],
        "valid_action_source_pairs": [list(row) for row in ACTION_SOURCE_PAIRS],
        "semantic_request": semantic_request,
        "success_response": dict(closed_schema),
        "failure_response": dict(closed_schema),
        "artifacts": {
            name: dict(closed_schema)
            for name in (
                "review_findings",
                "governance_verdict",
                "context_text",
                "private_patch",
            )
        },
        "execution_receipt": dict(closed_schema),
        "zero_inference_readiness": dict(closed_schema),
        "bounded_diagnostics": dict(closed_schema),
        "routing_source_sha256": "1" * 64,
    }
    encoded = json.dumps(
        descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return descriptor, hashlib.sha256(encoded).hexdigest()


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class DirectRuntimeSkillContractTests(unittest.TestCase):
    def test_context_is_the_only_generated_source_grounding_skill(self) -> None:
        self.assertTrue((SPECS / "context.md").is_file())
        self.assertFalse((SPECS / "long-context.md").exists())
        self.assertTrue((SKILLS / "context" / "SKILL.md").is_file())
        self.assertFalse((SKILLS / "long-context").exists())

        build_skills = _load("direct_build_skills", ROOT / "scripts" / "build_skills.py")
        self.assertIn("context", build_skills.ROUTED_SPECS)
        self.assertNotIn("long-context", build_skills.ROUTED_SPECS)
        self.assertEqual(
            build_skills.skill_tree_differences(SKILLS, SPECS),
            (),
        )

    def test_context_skill_uses_the_semantic_request_contract(self) -> None:
        text = (SKILLS / "context" / "SKILL.md").read_text(encoding="utf-8")
        for action in (
            "context.documents.extract",
            "context.documents.reason",
            "context.repository.extract",
            "context.repository.reason",
        ):
            with self.subTest(action=action):
                self.assertIn(action, text)
        self.assertIn("exactly one source mode", text.lower())
        self.assertIn("one provider process", text.lower())
        self.assertIn("no automatic whole-request replay", text.lower())

    def test_plugin_metadata_declares_the_breaking_package_version(self) -> None:
        plugin = json.loads(
            (PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        codex = json.loads(
            (PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        config = json.loads(
            (ROOT / "scripts" / "skill-build-config.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(plugin["version"], "5.0.0")
        self.assertEqual(codex["version"], "5.0.0")
        self.assertEqual(config["agent-collab"]["skill_version"], "5.0.0")


class PublicSemanticMembershipTests(unittest.TestCase):
    def test_public_membership_comes_from_one_runtime_descriptor(self) -> None:
        client = _load("direct_runtime_client", PLUGIN / "runtime_client.py")
        descriptor, descriptor_sha256 = _wire_descriptor()
        snapshot = client.validate_wire_descriptor(
            descriptor, expected_sha256=descriptor_sha256
        )
        self.assertEqual(snapshot.logical_actions, frozenset(LOGICAL_ACTIONS))
        self.assertEqual(snapshot.transport_actions, frozenset(TRANSPORT_ACTIONS))
        self.assertEqual(
            snapshot.action_source_pairs,
            frozenset(ACTION_SOURCE_PAIRS),
        )

    def test_manifest_schema_carries_only_the_top_level_wire_descriptor(self) -> None:
        schema = json.loads(
            (PLUGIN / "runtime-manifest.schema.json").read_text(encoding="utf-8")
        )
        properties = schema["properties"]
        self.assertEqual(properties["schema_version"], {"const": 4})
        self.assertEqual(properties["protocol_version"], {"const": 3})
        self.assertEqual(properties["contract_version"], {"const": 4})
        self.assertIn("wire_contract", schema["required"])
        self.assertIn("wire_contract_sha256", schema["required"])
        self.assertNotIn("broker_protocol_version", properties)
        artifact = properties["artifacts"]["items"]
        self.assertNotIn("contracts", artifact["properties"])
        self.assertNotIn("route_contract_version", artifact["properties"])

    def test_public_runtime_has_no_broker_or_setup_lifecycle_api(self) -> None:
        client = _load("direct_runtime_client_no_broker", PLUGIN / "runtime_client.py")
        for name in (
            "broker_status",
            "install_broker",
            "rollback_broker",
            "uninstall_broker",
            "stage_dispatcher",
            "dispatcher_status",
            "invoke_adoption_canary",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(client, name))

    def test_host_policy_has_no_provider_transport_or_model_pin_mirror(self) -> None:
        policy = _load("direct_host_policy", PLUGIN / "host_policy.py")
        for name in (
            "ROUTE_ACTIONS",
            "AUTHORITIES",
            "GOVERNANCE_CONTRACTS",
            "DEFAULT_OPENCODE_MODEL",
            "GEMINI_GOVERNANCE_MODEL",
            "CODEX_GOVERNANCE_MODEL",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(policy, name))

    def test_bundle_verifier_has_no_broker_store_mode(self) -> None:
        bundle = _load("direct_runtime_bundle", PLUGIN / "runtime_bundle.py")
        self.assertFalse(hasattr(bundle, "_broker_root_mode_ok"))

    def test_release_tools_have_no_transport_contract_or_setup_roots(self) -> None:
        archive = _load("direct_archive_builder", ROOT / "scripts" / "build_plugin_archive.py")
        release = _load("direct_release_verifier", ROOT / "scripts" / "verify_runtime_release.py")
        self.assertFalse(hasattr(archive, "REQUIRED_CONTRACTS"))
        self.assertFalse(hasattr(release, "REQUIRED_CONTRACTS"))
        self.assertNotIn("runtime_setup.py", archive.REQUIRED_ROOTS)
        self.assertNotIn("execute-output-contract-v1.json", archive.REQUIRED_ROOTS)


if __name__ == "__main__":
    unittest.main()
