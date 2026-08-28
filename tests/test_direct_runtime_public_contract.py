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
    "context.documents.intent",
    "context.documents.reason",
    "context.repository.extract",
    "context.repository.reason",
    "frontend_codegen.repository",
    "frontend_review.repository",
    "governance.repository",
    "review.repository",
)

LOGICAL_ACTION_SOURCE_MODES = {
    "architecture.conceptual": "conceptual_prompt",
    "architecture.repository": "repository",
    "codegen.repository": "repository",
    "context.documents.extract": "documents",
    "context.documents.intent": "documents",
    "context.documents.reason": "documents",
    "context.repository.extract": "repository",
    "context.repository.reason": "repository",
    "frontend_codegen.repository": "repository",
    "frontend_review.repository": "repository",
    "governance.repository": "repository",
    "review.repository": "repository",
}

TRANSPORT_ACTIONS = (
    ("claude", "context"),
    ("codex", "advisory"),
    ("codex", "codegen"),
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
    ("opencode", "governance"),
    ("opencode", "plan"),
)

ACTION_SOURCE_PAIRS = (
    ("claude", "context", "documents"),
    ("codex", "advisory", "repository"),
    ("codex", "codegen", "repository"),
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
    ("opencode", "governance", "repository"),
    ("opencode", "plan", "repository"),
)

LOGICAL_AGENTS = (
    "alibaba",
    "claude",
    "codex",
    "deepseek",
    "gemini",
    "grok",
    "moonshot",
    "zhipu",
)

MODEL_LINEAGES = (
    "alibaba",
    "anthropic",
    "deepseek",
    "google",
    "moonshot",
    "openai",
    "xai",
    "zhipu",
)

LOGICAL_ACTION_TARGETS = {
    "architecture.conceptual": ("grok",),
    "architecture.repository": (
        "alibaba", "codex", "deepseek", "grok", "moonshot", "zhipu",
    ),
    "codegen.repository": (
        "alibaba", "codex", "deepseek", "grok", "moonshot", "zhipu",
    ),
    "context.documents.extract": (
        "alibaba", "deepseek", "gemini", "grok", "moonshot", "zhipu",
    ),
    "context.documents.intent": ("claude", "gemini", "grok"),
    "context.documents.reason": (
        "alibaba", "deepseek", "gemini", "grok", "moonshot", "zhipu",
    ),
    "context.repository.extract": (
        "alibaba", "deepseek", "gemini", "grok", "moonshot", "zhipu",
    ),
    "context.repository.reason": (
        "alibaba", "deepseek", "gemini", "grok", "moonshot", "zhipu",
    ),
    "frontend_codegen.repository": (
        "alibaba", "codex", "grok", "moonshot", "zhipu",
    ),
    "frontend_review.repository": (
        "alibaba", "codex", "gemini", "grok", "moonshot", "zhipu",
    ),
    "governance.repository": (
        "alibaba", "codex", "deepseek", "gemini", "grok", "moonshot", "zhipu",
    ),
    "review.repository": (
        "alibaba", "codex", "deepseek", "gemini", "grok", "moonshot", "zhipu",
    ),
}

LOGICAL_ACTION_EFFORT_FLOORS = {
    "architecture.conceptual": "maximum",
    "architecture.repository": "maximum",
    "codegen.repository": "standard",
    "context.documents.extract": "minimal",
    "context.documents.intent": "standard",
    "context.documents.reason": "maximum",
    "context.repository.extract": "minimal",
    "context.repository.reason": "maximum",
    "frontend_codegen.repository": "standard",
    "frontend_review.repository": "maximum",
    "governance.repository": "maximum",
    "review.repository": "maximum",
}

WIRE_CONTRACT_SHA256 = (
    "9ec0c1d0c943a9ba9025dbb554847abea45d5c2dcac893a69ac09539d265a85f"
)


def _wire_descriptor() -> tuple[dict[str, object], str]:
    manifest = json.loads(
        (PLUGIN / "runtime-manifest.json").read_text(encoding="utf-8")
    )
    return manifest["wire_contract"], manifest["wire_contract_sha256"]


def _descriptor_sha256(descriptor: object) -> str:
    return hashlib.sha256(
        json.dumps(
            descriptor,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _readiness_response(
    wire_sha256: str, *, author_lineage: str = "openai"
) -> dict[str, object]:
    actions = []
    for logical_action in LOGICAL_ACTIONS:
        source_mode = (
            "conceptual_prompt"
            if logical_action.endswith(".conceptual")
            else "documents"
            if ".documents." in logical_action
            else "repository"
        )
        actions.append(
            {
                "logical_action": logical_action,
                "source_mode": source_mode,
                "candidates": [
                    {
                        "logical_agent": "gemini",
                        "provider_surface": "native_cli",
                        "model_lineage": "google",
                        "shared_resource": "agy_pool",
                        "activation": "active",
                        "status": "unavailable",
                        "implementation_fingerprint": None,
                        "executable_content_sha256": None,
                        "adapter_wire_sha256": None,
                        "observed_model": None,
                        "catalog_digest": None,
                        "model_resolution_method": None,
                        "effective_effort": None,
                        "metadata_process_count": 0,
                        "diagnostic_code": "not_ready",
                        "compatibility_profile": None,
                        "capability_digest": None,
                        "metadata_zero_model_calls_proven": True,
                        "cleanup_confirmed": True,
                    }
                ],
            }
        )
    return {
        "wire_contract_sha256": wire_sha256,
        "request_id": "runtime-status-1",
        "author_lineage": author_lineage,
        "status": "ok",
        "quality_profile": "standard",
        "effort_class": "standard",
        "result": {"actions": actions},
    }


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class DirectRuntimeSkillContractTests(unittest.TestCase):
    def test_routed_skills_publish_closed_quality_and_effort_profiles(self) -> None:
        for name in (
            "route", "context", "architect", "governance-review",
            "dev-delegate", "worker",
        ):
            with self.subTest(name=name):
                source = (SPECS / f"{name}.md").read_text(encoding="utf-8")
                generated = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("quality_profile", source)
                self.assertIn("effort_class", source)
                self.assertIn("quality_profile", generated)
                self.assertIn("effort_class", generated)

        joined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(SPECS.glob("*.md"))
        )
        self.assertNotIn("effort is host metadata, never a request field", joined)
        self.assertNotIn("no `tier` request field", joined)

    def test_wire_publishes_a_separate_receipt_free_advisory_response(self) -> None:
        descriptor, _digest = _wire_descriptor()
        advisory = descriptor["advisory_response"]

        self.assertFalse(advisory["additionalProperties"])
        self.assertEqual(
            set(advisory["required"]),
            {
                "wire_contract_sha256", "request_id", "status", "advisory",
                "diagnostics",
            },
        )
        self.assertEqual(advisory["properties"]["status"], {"const": "advisory"})
        self.assertNotIn("execution_receipt", advisory["properties"])
        self.assertNotIn("result", advisory["properties"])
        self.assertNotIn("error_code", advisory["properties"])

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
        self.assertEqual(plugin["version"], "7.0.0")
        self.assertEqual(codex["version"], "7.0.0")
        self.assertEqual(config["agent-collab"]["skill_version"], "7.0.0")


class PublicSemanticMembershipTests(unittest.TestCase):
    def test_public_membership_comes_from_one_runtime_descriptor(self) -> None:
        client = _load("direct_runtime_client", PLUGIN / "runtime_client.py")
        descriptor, descriptor_sha256 = _wire_descriptor()
        snapshot = client.validate_wire_descriptor(
            descriptor, expected_sha256=descriptor_sha256
        )
        self.assertEqual(snapshot.logical_actions, frozenset(LOGICAL_ACTIONS))
        self.assertEqual(
            dict(snapshot.logical_action_source_modes),
            LOGICAL_ACTION_SOURCE_MODES,
        )
        self.assertEqual(snapshot.transport_actions, frozenset(TRANSPORT_ACTIONS))
        self.assertEqual(
            snapshot.action_source_pairs,
            frozenset(ACTION_SOURCE_PAIRS),
        )
        self.assertEqual(snapshot.logical_agents, frozenset(LOGICAL_AGENTS))
        self.assertEqual(snapshot.model_lineages, frozenset(MODEL_LINEAGES))
        self.assertEqual(
            dict(snapshot.logical_action_targets),
            LOGICAL_ACTION_TARGETS,
        )
        self.assertEqual(
            dict(snapshot.logical_action_effort_floors),
            LOGICAL_ACTION_EFFORT_FLOORS,
        )

    def test_public_client_accepts_the_previous_positive_wire_schema_revision(self) -> None:
        client = _load("positive_wire_revision_runtime_client", PLUGIN / "runtime_client.py")
        descriptor, _digest = _wire_descriptor()
        descriptor["schema_version"] = 6
        for key in (
            "logical_agents",
            "model_lineages",
            "logical_action_targets",
            "logical_action_effort_floors",
        ):
            descriptor.pop(key)

        snapshot = client.validate_wire_descriptor(
            descriptor, expected_sha256=_descriptor_sha256(descriptor)
        )

        self.assertEqual(snapshot.logical_actions, frozenset(LOGICAL_ACTIONS))

    def test_public_client_accepts_only_head_bound_wire_schema_8(self) -> None:
        client = _load("wire_v8_runtime_client", PLUGIN / "runtime_client.py")
        descriptor, _digest = _wire_descriptor()
        descriptor = json.loads(json.dumps(descriptor))
        self.assertEqual(descriptor["schema_version"], 8)
        repository = descriptor["semantic_request"]["properties"]["source"]["oneOf"][0]
        self.assertIn("expected_repo_head", repository["properties"])
        self.assertIn("expected_repo_head", repository["required"])

        snapshot = client.validate_wire_descriptor(
            descriptor, expected_sha256=_descriptor_sha256(descriptor)
        )
        self.assertEqual(snapshot.logical_actions, frozenset(LOGICAL_ACTIONS))

        missing = json.loads(json.dumps(descriptor))
        missing_repository = missing["semantic_request"]["properties"]["source"]["oneOf"][0]
        missing_repository["properties"].pop("expected_repo_head")
        missing_repository["required"].remove("expected_repo_head")
        with self.assertRaisesRegex(ValueError, "not head-bound"):
            client.validate_wire_descriptor(
                missing, expected_sha256=_descriptor_sha256(missing)
            )

        zero_admitted = json.loads(json.dumps(descriptor))
        zero_repository = zero_admitted["semantic_request"]["properties"]["source"]["oneOf"][0]
        zero_repository["properties"]["expected_repo_head"] = {
            "type": "string",
            "pattern": "^(?:[0-9a-f]{40}|[0-9a-f]{64})$",
        }
        with self.assertRaisesRegex(ValueError, "admits an unbound head"):
            client.validate_wire_descriptor(
                zero_admitted, expected_sha256=_descriptor_sha256(zero_admitted)
            )

    def test_public_client_rejects_invalid_wire_schema_revisions(self) -> None:
        client = _load("invalid_wire_revision_runtime_client", PLUGIN / "runtime_client.py")
        for revision in (0, -1, True, False, 1.5, "5", None):
            with self.subTest(revision=revision):
                descriptor, _digest = _wire_descriptor()
                descriptor["schema_version"] = revision
                with self.assertRaisesRegex(ValueError, "schema version"):
                    client.validate_wire_descriptor(
                        descriptor, expected_sha256=_descriptor_sha256(descriptor)
                    )

    def test_public_client_retains_descriptor_integrity_boundaries(self) -> None:
        client = _load("wire_integrity_runtime_client", PLUGIN / "runtime_client.py")

        descriptor, _digest = _wire_descriptor()
        with self.assertRaisesRegex(ValueError, "digest"):
            client.validate_wire_descriptor(descriptor, expected_sha256="0" * 64)

        mutations = (
            ("not closed", lambda value: value.__setitem__("unknown", True)),
            (
                "JSON schema",
                lambda value: value.__setitem__(
                    "success_response", {"type": "object", "unknown": True}
                ),
            ),
            (
                "wrong cardinality",
                lambda value: value["base_transport_actions"].pop(),
            ),
            (
                "runtime protocol",
                lambda value: value.__setitem__("runtime_protocol_version", 3),
            ),
        )
        for message, mutate in mutations:
            with self.subTest(message=message):
                descriptor, _digest = _wire_descriptor()
                mutate(descriptor)
                with self.assertRaisesRegex(ValueError, message):
                    client.validate_wire_descriptor(
                        descriptor, expected_sha256=_descriptor_sha256(descriptor)
                    )

    def test_manifest_schema_carries_only_the_top_level_wire_descriptor(self) -> None:
        schema = json.loads(
            (PLUGIN / "runtime-manifest.schema.json").read_text(encoding="utf-8")
        )
        properties = schema["properties"]
        self.assertEqual(properties["schema_version"], {"const": 4})
        self.assertEqual(properties["protocol_version"], {"const": 4})
        self.assertEqual(properties["contract_version"], {"const": 4})
        self.assertIn("wire_contract", schema["required"])
        self.assertIn("wire_contract_sha256", schema["required"])
        self.assertNotIn("broker_protocol_version", properties)
        artifact = properties["artifacts"]["items"]
        self.assertNotIn("contracts", artifact["properties"])
        self.assertNotIn("route_contract_version", artifact["properties"])
        wire_schema = properties["wire_contract"]
        self.assertEqual(wire_schema["properties"]["schema_version"], {"const": 8})
        self.assertIn(
            "advisory_response",
            wire_schema["required"],
        )
        for field in (
            "logical_agents",
            "model_lineages",
            "logical_action_targets",
            "logical_action_effort_floors",
        ):
            self.assertIn(field, wire_schema["required"])
        self.assertEqual(
            wire_schema["properties"]["logical_agents"],
            {
                "type": "array",
                "minItems": len(LOGICAL_AGENTS),
                "maxItems": len(LOGICAL_AGENTS),
                "uniqueItems": True,
                "items": {"enum": list(LOGICAL_AGENTS)},
            },
        )
        self.assertEqual(
            wire_schema["properties"]["model_lineages"],
            {
                "type": "array",
                "minItems": len(MODEL_LINEAGES),
                "maxItems": len(MODEL_LINEAGES),
                "uniqueItems": True,
                "items": {"enum": list(MODEL_LINEAGES)},
            },
        )
        target_schema = wire_schema["properties"]["logical_action_targets"]
        self.assertFalse(target_schema["additionalProperties"])
        self.assertEqual(target_schema["required"], list(LOGICAL_ACTIONS))
        for action, targets in LOGICAL_ACTION_TARGETS.items():
            with self.subTest(action=action):
                self.assertEqual(
                    target_schema["properties"][action],
                    {
                        "type": "array",
                        "minItems": len(targets),
                        "maxItems": len(targets),
                        "uniqueItems": True,
                        "items": {"enum": list(targets)},
                    },
                )
        floor_schema = wire_schema["properties"]["logical_action_effort_floors"]
        self.assertFalse(floor_schema["additionalProperties"])
        self.assertEqual(floor_schema["required"], list(LOGICAL_ACTIONS))
        self.assertEqual(
            floor_schema["properties"],
            {
                action: {"const": floor}
                for action, floor in LOGICAL_ACTION_EFFORT_FLOORS.items()
            },
        )
        self.assertEqual(properties["wire_contract_sha256"], {"const": WIRE_CONTRACT_SHA256})
        self.assertEqual(
            properties["artifacts"]["items"]["properties"]["wire_contract_sha256"],
            {"const": WIRE_CONTRACT_SHA256},
        )
        self.assertEqual(
            properties["artifacts"]["items"]["properties"][
                "provider_runtime_version"
            ],
            {"const": "5.0.0"},
        )

    def test_committed_manifest_is_the_schema_four_activation(self) -> None:
        manifest = json.loads(
            (PLUGIN / "runtime-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(manifest),
            {
                "schema_version",
                "protocol_version",
                "contract_version",
                "wire_contract",
                "wire_contract_sha256",
                "channel",
                "artifacts",
            },
        )
        self.assertEqual(manifest["schema_version"], 4)
        self.assertEqual(manifest["protocol_version"], 4)
        self.assertEqual(manifest["contract_version"], 4)
        self.assertEqual(manifest["channel"], "production")
        self.assertEqual(len(manifest["artifacts"]), 2)
        self.assertEqual(
            [artifact["arch"] for artifact in manifest["artifacts"]],
            ["arm64", "x86_64"],
        )
        for artifact in manifest["artifacts"]:
            arch = artifact["arch"]
            with self.subTest(arch=arch):
                self.assertEqual(artifact["kind"], "standalone_bundle")
                self.assertEqual(artifact["platform"], "darwin")
                self.assertEqual(
                    artifact["path"],
                    f"runtime/darwin-{arch}/agent-collab-runtime.bundle",
                )
                self.assertEqual(len(artifact["files"]), 38)
                self.assertTrue(
                    all(
                        record["architecture"] == arch
                        for record in artifact["files"]
                    )
                )

        descriptor = manifest["wire_contract"]
        self.assertIs(type(descriptor["schema_version"]), int)
        self.assertGreater(descriptor["schema_version"], 0)
        self.assertEqual(descriptor["schema_version"], 8)
        self.assertEqual(descriptor["runtime_protocol_version"], 4)
        encoded = json.dumps(
            descriptor,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        self.assertEqual(
            hashlib.sha256(encoded).hexdigest(),
            manifest["wire_contract_sha256"],
        )
        self.assertEqual(manifest["wire_contract_sha256"], WIRE_CONTRACT_SHA256)
        self.assertEqual(descriptor["logical_actions"], list(LOGICAL_ACTIONS))
        self.assertEqual(
            descriptor["base_transport_actions"],
            [list(row) for row in TRANSPORT_ACTIONS],
        )
        self.assertEqual(
            descriptor["valid_action_source_pairs"],
            [list(row) for row in ACTION_SOURCE_PAIRS],
        )
        self.assertEqual(descriptor["logical_agents"], list(LOGICAL_AGENTS))
        self.assertEqual(descriptor["model_lineages"], list(MODEL_LINEAGES))
        self.assertEqual(
            descriptor["logical_action_targets"],
            {key: list(value) for key, value in LOGICAL_ACTION_TARGETS.items()},
        )
        self.assertEqual(
            descriptor["logical_action_effort_floors"],
            LOGICAL_ACTION_EFFORT_FLOORS,
        )
        for result in descriptor["success_response"]["properties"]["result"]["oneOf"][2:]:
            evidence = result["properties"]["evidence"]["properties"]
            with self.subTest(artifact=result["properties"]["artifact_type"]):
                self.assertEqual(evidence["inspected_paths"]["minItems"], 1)
                self.assertEqual(evidence["repository_evidence"]["minItems"], 1)
        for artifact in manifest["artifacts"]:
            self.assertEqual(artifact["provider_runtime_version"], "5.0.0")
            self.assertEqual(artifact["wire_contract_sha256"], WIRE_CONTRACT_SHA256)

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
