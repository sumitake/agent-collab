"""Protocol-5 public runtime distribution contract."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"
SPECS = ROOT / "skill-specs"
SKILLS = PLUGIN / "skills"
LOGICAL_ACTIONS = frozenset({
    "architecture.conceptual",
    "architecture.repository",
    "codegen.repository",
    "context.documents.extract",
    "context.documents.intent",
    "context.documents.reason",
    "context.repository.extract",
    "context.repository.reason",
    "frontend_codegen.repository",
    "frontend_review.repository",
    "governance.repository",
    "review.repository",
})


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def wire_descriptor() -> tuple[dict[str, object], str]:
    manifest = json.loads(
        (PLUGIN / "runtime-manifest.json").read_text(encoding="utf-8")
    )
    descriptor = copy.deepcopy(manifest["wire_contract"])
    return descriptor, manifest["wire_contract_sha256"]


def synthetic_wire_descriptor() -> tuple[dict[str, object], str]:
    """Build the schema-12 wire fixture used by lifecycle-only tests."""
    descriptor, _ = wire_descriptor()
    descriptor["schema_version"] = 12
    descriptor["logical_action_timeout_modes"] = {
        action: "total_deadline" for action in descriptor["logical_actions"]
    }
    encoded = json.dumps(
        descriptor, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return descriptor, hashlib.sha256(encoded).hexdigest()


class ProtocolFivePublicContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = load_module(
            "protocol5_public_client", PLUGIN / "runtime_client.py"
        )
        cls.manifest = json.loads(
            (PLUGIN / "runtime-manifest.json").read_text(encoding="utf-8")
        )

    def test_manifest_protocol_and_source_client_are_protocol_five_generation(self) -> None:
        self.assertEqual(self.manifest["schema_version"], 4)
        self.assertEqual(self.manifest["protocol_version"], 5)
        self.assertEqual(self.manifest["contract_version"], 4)
        self.assertEqual(self.manifest["channel"], "production")
        self.assertEqual(self.client.PROTOCOL_VERSION, 5)
        self.assertEqual(self.client.CONTRACT_VERSION, 4)
        self.assertEqual(self.client.PROVIDER_RUNTIME_VERSION, "5.0.5")

    def test_wire_is_routing_only_and_descriptor_derived(self) -> None:
        descriptor, digest = wire_descriptor()
        snapshot = self.client.validate_wire_descriptor(
            descriptor, expected_sha256=digest
        )
        self.assertEqual(snapshot.sha256, digest)
        self.assertEqual(snapshot.logical_actions, LOGICAL_ACTIONS)
        self.assertEqual(descriptor["schema_version"], 12)
        self.assertEqual(descriptor["runtime_protocol_version"], 5)
        self.assertEqual(
            set(descriptor),
            {
                "$defs",
                "content_frame",
                "logical_actions",
                "logical_action_timeout_modes",
                "logical_agents",
                "routing_request",
                "routing_source_sha256",
                "runtime_protocol_version",
                "schema_version",
                "terminal_planning_record",
            },
        )
        for retired in (
            "semantic_request",
            "success_response",
            "failure_response",
            "advisory_response",
            "execution_receipt",
            "artifacts",
        ):
            self.assertNotIn(retired, descriptor)

    def test_dual_architecture_artifacts_are_exactly_runtime_5_0_4(self) -> None:
        artifacts = self.manifest["artifacts"]
        self.assertEqual({item["arch"] for item in artifacts}, {"arm64", "x86_64"})
        self.assertEqual(
            {item["provider_runtime_version"] for item in artifacts}, {"5.0.4"}
        )
        self.assertEqual(
            {item["wire_contract_sha256"] for item in artifacts},
            {self.manifest["wire_contract_sha256"]},
        )
        for item in artifacts:
            self.assertEqual(item["kind"], "standalone_bundle")
            self.assertEqual(item["platform"], "darwin")
            self.assertEqual(
                item["path"],
                f"runtime/darwin-{item['arch']}/agent-collab-runtime.bundle",
            )
            self.assertEqual(len(item["files"]), 42)
            self.assertTrue(
                all(record["architecture"] == item["arch"] for record in item["files"])
            )

        schema = json.loads(
            (PLUGIN / "runtime-manifest.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["schema_version"], {"const": 4})
        self.assertEqual(schema["properties"]["protocol_version"], {"const": 5})
        self.assertEqual(schema["properties"]["contract_version"], {"const": 4})
        self.assertEqual(
            schema["properties"]["wire_contract_sha256"]["const"],
            self.manifest["wire_contract_sha256"],
        )

    def test_distribution_metadata_is_version_7_0_3(self) -> None:
        for host in (".claude-plugin", ".codex-plugin"):
            value = json.loads((PLUGIN / host / "plugin.json").read_text())
            self.assertEqual(value["version"], "7.0.3")
        config = json.loads(
            (ROOT / "scripts" / "skill-build-config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(config["agent-collab"]["skill_version"], "7.0.3")

    def test_routed_skills_publish_provider_neutral_quality_and_effort(self) -> None:
        build = load_module("protocol5_build_skills", ROOT / "scripts" / "build_skills.py")
        for name in sorted(build.ROUTED_SPECS):
            with self.subTest(name=name):
                source = (SPECS / f"{name}.md").read_text(encoding="utf-8")
                generated = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
                if name == "migration-doctor":
                    self.assertIn("provider-free", source)
                else:
                    self.assertTrue(
                        "quality_profile" in source or "defaults_block" in source
                    )
                    self.assertIn("quality_profile", generated)
                    self.assertIn("effort_class", generated)
                invocation = generated.split("\n# ", 1)[0].casefold()
                self.assertIn("caller-defined work unit", invocation)
                self.assertIn("never invent fields or provider actions", invocation)
                self.assertIn("never discover a provider executable", invocation)

    def test_public_runtime_has_no_broker_setup_or_provider_model_mirror(self) -> None:
        for name in (
            "broker_status",
            "install_broker",
            "rollback_broker",
            "uninstall_broker",
            "stage_dispatcher",
            "dispatcher_status",
            "invoke_adoption_canary",
        ):
            self.assertFalse(hasattr(self.client, name), name)

        policy = load_module("protocol5_host_policy", PLUGIN / "host_policy.py")
        for name in (
            "ROUTE_ACTIONS",
            "AUTHORITIES",
            "GOVERNANCE_CONTRACTS",
            "DEFAULT_OPENCODE_MODEL",
            "GEMINI_GOVERNANCE_MODEL",
            "CODEX_GOVERNANCE_MODEL",
        ):
            self.assertFalse(hasattr(policy, name), name)

        bundle = load_module("protocol5_runtime_bundle", PLUGIN / "runtime_bundle.py")
        self.assertFalse(hasattr(bundle, "_broker_root_mode_ok"))
        archive = load_module(
            "protocol5_archive_builder", ROOT / "scripts" / "build_plugin_archive.py"
        )
        release = load_module(
            "protocol5_release_verifier", ROOT / "scripts" / "verify_runtime_release.py"
        )
        self.assertFalse(hasattr(archive, "REQUIRED_CONTRACTS"))
        self.assertFalse(hasattr(release, "REQUIRED_CONTRACTS"))
        self.assertNotIn("runtime_setup.py", archive.REQUIRED_ROOTS)
        self.assertNotIn("execute-output-contract-v1.json", archive.REQUIRED_ROOTS)


if __name__ == "__main__":
    unittest.main()
