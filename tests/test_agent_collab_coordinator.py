"""Standalone, bounded public coordinator contract tests."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity_env = mock.patch.dict(os.environ, {}, clear=True)
        self.identity_env.start()
        self.addCleanup(self.identity_env.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "agent-collab"
        shutil.copytree(
            PLUGIN, self.root, ignore=shutil.ignore_patterns("runtime")
        )
        # The committed repo is now an ACTIVATION release (runtime committed). These
        # coordinator tests are runtime-agnostic and exercise the no-native-runtime
        # routing behavior, so the fixture is normalized to a policy-only manifest
        # (empty artifacts, no runtime copied).
        (self.root / "runtime-manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "protocol_version": 2,
                    "contract_version": 3,
                    "broker_protocol_version": 2,
                    "channel": "production",
                    "artifacts": [],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(
        self, document: object, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        process_env = {"PATH": "/usr/bin:/bin", "HOME": self.temp.name}
        process_env.update(env or {})
        return subprocess.run(
            [sys.executable, str(self.root / "coordinator.py")],
            input=json.dumps(document) + "\n",
            capture_output=True,
            text=True,
            cwd=self.temp.name,
            env=process_env,
            timeout=10,
            check=False,
        )

    def test_plugin_only_checkout_is_callable_and_empty_manifest_is_unavailable(self) -> None:
        result = self._run(
            {
                "protocol_version": 2,
                "request_id": "standalone-1",
                "operation": "readiness",
                "route": "codex",
                "action": "advisory",
                "timeout_ms": 30_000,
                "governance": False,
                "primary": {
                    "primary_id": "claude",
                    "active_model": "anthropic/claude-opus",
                    "host_runtime": "claude-code",
                    "session_identifier": "c-1",
                },
                "row": {
                    "model": "openai/codex",
                    "effort": "high",
                    "mode": "prompt-only",
                },
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response["status"], "unavailable")
        self.assertNotIn("workspace", result.stderr.lower())

    def test_public_schema_rejects_provider_escape_fields(self) -> None:
        base = {
            "protocol_version": 2,
            "request_id": "standalone-2",
            "operation": "readiness",
            "route": "codex",
            "action": "advisory",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": {
                "primary_id": "custom",
                "active_model": "custom/unknown",
                "host_runtime": "custom",
                "session_identifier": "s-1",
            },
            "row": {
                "model": "openai/codex",
                "effort": "high",
                "mode": "prompt-only",
            },
        }
        for key, value in {
            "argv": ["codex", "exec"],
            "tools": ["shell"],
            "model_override": "anthropic/claude-opus",
            "cwd": "/",
            "paths": ["/private"],
        }.items():
            with self.subTest(key=key):
                document = dict(base)
                document[key] = value
                result = self._run(document)
                self.assertEqual(result.returncode, 2)
                response = json.loads(result.stdout)
                self.assertEqual(response["status"], "config_error")

    def test_adoption_canary_is_internal_token_gated_and_bypasses_policy_routes(self) -> None:
        coordinator = _load(
            "agent_collab_adoption_canary_coordinator", PLUGIN / "coordinator.py"
        )
        request = {
            "protocol_version": 2,
            "request_id": "adoption-canary-1",
            "operation": "adoption_canary",
            "provider": "grok",
            "registry_generation": 12,
            "source_generation": 9,
            "binary_sha256": "1" * 64,
            "worker_sha256": "2" * 64,
            "adapter_contract_generation": 4,
            "routes": ["composer/codegen", "grok/architecture", "grok/governance", "grok/huge_context"],
            "attempt_generation": 3,
            "authority_token": "dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHQ",
            "timeout_ms": 30_000,
        }
        validated, request_id, error = coordinator._validate(request)
        self.assertEqual(validated, request)
        self.assertEqual(request_id, "adoption-canary-1")
        self.assertEqual(error, "")
        runtime_client = _load(
            "agent_collab_adoption_canary_runtime", PLUGIN / "runtime_client.py"
        )
        self.assertEqual(
            coordinator.ADOPTION_PROVIDER_ROUTES,
            runtime_client.ADOPTION_PROVIDER_ROUTES,
        )

        runtime = mock.Mock()
        runtime.RuntimeStatus.OK = "ok"
        runtime.invoke_adoption_canary.return_value = mock.Mock(
            status=mock.Mock(value="ok"), result={"passed_routes": request["routes"]}, provenance=None, error=""
        )
        with mock.patch.object(
            coordinator,
            "_load",
            side_effect=lambda _name, filename: runtime
            if filename == "runtime_client.py"
            else mock.Mock(),
        ):
            response, code = coordinator.process(request)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "ok")
        runtime.invoke_adoption_canary.assert_called_once_with(request=request)

        for key, value in {
            "route": "grok",
            "provider_path": "/tmp/grok",
            "auth_root": "/tmp/auth",
            "model": "attacker/model",
        }.items():
            hostile = dict(request, **{key: value})
            rejected, _label, _error = coordinator._validate(hostile)
            self.assertIsNone(rejected)

        unknown_route = dict(request, routes=["grok/not-a-governed-route"])
        rejected, _label, _error = coordinator._validate(unknown_route)
        self.assertIsNone(rejected)

        invalid_request_id = dict(request, request_id="contains whitespace")
        rejected, _label, _error = coordinator._validate(invalid_request_id)
        self.assertIsNone(rejected)

    def test_governance_rejects_empty_artifact_content_or_model(self) -> None:
        base = {
            "protocol_version": 2,
            "request_id": "empty-governance-artifact",
            "operation": "execute",
            "route": "grok",
            "action": "governance",
            "timeout_ms": 30_000,
            "governance": True,
            "primary": {
                "primary_id": "codex",
                "active_model": "openai/gpt-5",
                "host_runtime": "codex",
                "session_identifier": "c-2",
            },
            "row": {"mode": "prompt-only"},
            "prompt": "review",
            "artifact": {
                "content": "",
                "author_model": "google/gemini-test",
            },
        }
        for content in ("", " \n\t"):
            with self.subTest(content=content):
                empty_content = json.loads(json.dumps(base))
                empty_content["artifact"]["content"] = content
                rejected = self._run(empty_content)
                self.assertEqual(rejected.returncode, 2)
                self.assertEqual(json.loads(rejected.stdout)["status"], "config_error")

        blank_model = json.loads(json.dumps(base))
        blank_model["artifact"] = {"content": "material", "author_model": "  "}
        blank = self._run(blank_model)
        self.assertEqual(blank.returncode, 2)
        self.assertEqual(json.loads(blank.stdout)["status"], "config_error")

    def test_non_governance_rejects_model_without_artifact_content(self) -> None:
        request = {
            "protocol_version": 2,
            "request_id": "empty-optional-artifact",
            "operation": "execute",
            "route": "composer",
            "action": "codegen",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": {
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "c-optional",
            },
            "row": {"task_class": "standard_codegen", "effort": "medium"},
            "prompt": "generate",
            "artifact": {
                "content": " \n\t",
                "author_model": "google/gemini-test",
            },
        }
        rejected = self._run(request)
        self.assertEqual(rejected.returncode, 2)
        response = json.loads(rejected.stdout)
        self.assertEqual(response["status"], "config_error")
        self.assertIn("artifact", response["error"])

    def test_action_authority_errors_are_role_neutral_and_shared(self) -> None:
        coordinator = _load(
            "agent_collab_authority_coordinator", PLUGIN / "coordinator.py"
        )
        primary = {
            "primary_id": "codex",
            "active_model": "openai/gpt-5",
            "host_runtime": "codex",
            "session_identifier": "authority-1",
        }
        auto = {
            "protocol_version": 2,
            "request_id": "auto-authority",
            "operation": "execute",
            "route": "auto",
            "action": "governance",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": primary,
            "row": {"gemini": {}, "codex": {}, "grok": {}},
            "prompt": "review",
        }
        grok = {
            **auto,
            "request_id": "grok-authority",
            "route": "grok",
            "action": "architecture",
            "governance": True,
            "row": {"mode": "prompt-only"},
            "artifact": {
                "content": "material",
                "author_model": "google/gemini-test",
            },
        }

        errors = []
        for request in (auto, grok):
            validated, _request_id, error = coordinator._validate(request)
            self.assertIsNone(validated)
            errors.append(error)
        self.assertEqual(errors, ["route action/authority mismatch"] * 2)

    def test_async_inbox_has_observed_readiness_only_coordinator_contract(self) -> None:
        base = {
            "protocol_version": 2,
            "request_id": "inbox-readiness-1",
            "operation": "readiness",
            "route": "inbox",
            "action": "async",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": {
                "primary_id": "custom",
                "primary_family": "openai",
                "active_model": "openai/gpt-5",
                "host_runtime": "custom",
                "session_identifier": "custom-inbox",
            },
            "row": {
                "target_id": "claude",
                "target_family": "anthropic",
                "target_session_identifier": "claude-target-1",
            },
        }
        unavailable = self._run(base)
        self.assertEqual(unavailable.returncode, 0, unavailable.stderr)
        self.assertEqual(json.loads(unavailable.stdout)["status"], "unavailable")

        observed = json.loads(json.dumps(base))
        observed["primary"]["async_inbox"] = "available"
        available = self._run(observed)
        self.assertEqual(available.returncode, 0, available.stderr)
        response = json.loads(available.stdout)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(
            response["result"],
            {
                "available": True,
                "transport": "host_async_inbox",
                "target": {
                    "target_id": "claude",
                    "target_family": "anthropic",
                    "target_session_identifier": "claude-target-1",
                },
            },
        )

        execute = dict(observed, operation="execute", prompt="send asynchronously")
        rejected = self._run(execute)
        self.assertEqual(rejected.returncode, 2, rejected.stderr)
        self.assertEqual(json.loads(rejected.stdout)["status"], "config_error")

    def test_async_inbox_requires_consistent_target_family_and_session(self) -> None:
        base = {
            "protocol_version": 2,
            "request_id": "inbox-target-provenance",
            "operation": "readiness",
            "route": "inbox",
            "action": "async",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": {
                "primary_id": "custom",
                "primary_family": "openai",
                "active_model": "openai/gpt-5",
                "host_runtime": "custom",
                "session_identifier": "custom-target-check",
                "async_inbox": "available",
            },
            "row": {
                "target_id": "antigravity",
                "target_family": "google",
                "target_session_identifier": "agy-target-1",
            },
        }
        accepted = self._run(base)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(json.loads(accepted.stdout)["status"], "ok")

        mixed_case = json.loads(json.dumps(base))
        mixed_case["row"]["target_id"] = "Antigravity"
        mixed_case["row"]["target_family"] = "Google"
        normalized = self._run(mixed_case)
        self.assertEqual(normalized.returncode, 0, normalized.stderr)
        self.assertEqual(
            json.loads(normalized.stdout)["result"]["target"],
            {
                "target_id": "antigravity",
                "target_family": "google",
                "target_session_identifier": "agy-target-1",
            },
        )

        cases = (
            {},
            {**base["row"], "target_family": "anthropic"},
            {**base["row"], "target_session_identifier": ""},
            {**base["row"], "target_id": "custom-agent"},
        )
        for row in cases:
            with self.subTest(row=row):
                rejected = self._run({**base, "row": row})
            self.assertEqual(rejected.returncode, 2, rejected.stderr)
            self.assertEqual(json.loads(rejected.stdout)["status"], "config_error")

    def test_async_inbox_excludes_same_family_in_both_target_directions(self) -> None:
        cases = (
            (
                {
                    "primary_id": "claude",
                    "primary_family": "anthropic",
                    "active_model": "anthropic/claude-opus",
                    "host_runtime": "claude-code",
                    "session_identifier": "claude-primary",
                    "async_inbox": "available",
                },
                {
                    "target_id": "claude",
                    "target_family": "anthropic",
                    "target_session_identifier": "claude-target",
                },
            ),
            (
                {
                    "primary_id": "antigravity",
                    "primary_family": "google",
                    "active_model": "google/gemini-pro",
                    "host_runtime": "antigravity",
                    "session_identifier": "agy-primary",
                    "async_inbox": "available",
                },
                {
                    "target_id": "antigravity",
                    "target_family": "google",
                    "target_session_identifier": "agy-target",
                },
            ),
        )
        for primary, row in cases:
            with self.subTest(primary=primary["primary_id"]):
                result = self._run(
                    {
                        "protocol_version": 2,
                        "request_id": f"same-family-{primary['primary_id']}",
                        "operation": "readiness",
                        "route": "inbox",
                        "action": "async",
                        "timeout_ms": 30_000,
                        "governance": False,
                        "primary": primary,
                        "row": row,
                    }
                )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout)["status"], "same_family_blocked"
            )

    def test_async_inbox_never_invokes_a_headless_runtime(self) -> None:
        coordinator = _load(
            "agent_collab_async_only_coordinator", PLUGIN / "coordinator.py"
        )
        policy = _load("agent_collab_async_only_policy", PLUGIN / "host_policy.py")
        runtime = _load("agent_collab_async_only_runtime", PLUGIN / "runtime_client.py")
        request = {
            "protocol_version": 2,
            "request_id": "claude-inbox-no-headless",
            "operation": "readiness",
            "route": "inbox",
            "action": "async",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": {
                "primary_id": "antigravity",
                "primary_family": "google",
                "active_model": "google/gemini-pro",
                "host_runtime": "antigravity",
                "session_identifier": "agy-primary-async",
                "async_inbox": "available",
            },
            "row": {
                "target_id": "claude",
                "target_family": "anthropic",
                "target_session_identifier": "claude-async-target",
            },
        }
        with (
            mock.patch.object(coordinator, "_inventory_legacy", return_value=()),
            mock.patch.object(runtime, "invoke") as invoke,
            mock.patch.object(
                coordinator,
                "_load",
                side_effect=lambda _name, filename: (
                    policy if filename == "host_policy.py" else runtime
                ),
            ),
        ):
            response, code = coordinator.process(request)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["target"]["target_id"], "claude")
        invoke.assert_not_called()

    def test_async_inbox_surfaces_incomplete_primary_independence_warning(self) -> None:
        result = self._run(
            {
                "protocol_version": 2,
                "request_id": "inbox-incomplete-primary",
                "operation": "readiness",
                "route": "inbox",
                "action": "async",
                "timeout_ms": 30_000,
                "governance": False,
                "primary": {
                    "primary_id": "custom",
                    "primary_family": "openai",
                    "active_model": "openai/gpt-5",
                    "host_runtime": "custom",
                    "async_inbox": "available",
                },
                "row": {
                    "target_id": "claude",
                    "target_family": "anthropic",
                    "target_session_identifier": "claude-warning-target",
                },
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response["status"], "ok")
        self.assertIn("independence warning", response["warning"])

    def test_exact_integer_versions_and_timeout_are_required(self) -> None:
        base = {
            "protocol_version": 2,
            "request_id": "standalone-3",
            "operation": "readiness",
            "route": "composer",
            "action": "codegen",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": {
                "primary_id": "custom",
                "active_model": "custom/unknown",
                "host_runtime": "custom",
                "session_identifier": "s-1",
            },
            "row": {"task_class": "standard_codegen", "effort": "medium"},
        }
        for field, value in (
            ("protocol_version", True),
            ("protocol_version", 1),
            ("protocol_version", 1.0),
            ("timeout_ms", True),
            ("timeout_ms", 30_000.0),
            ("timeout_ms", 0),
            ("timeout_ms", 600_001),
        ):
            with self.subTest(field=field, value=value):
                document = dict(base)
                document[field] = value
                result = self._run(document)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["status"], "config_error")

    def test_automatic_advisory_has_closed_candidates_and_no_raw_fallback(self) -> None:
        request = {
            "protocol_version": 2,
            "request_id": "auto-1",
            "operation": "readiness",
            "route": "auto",
            "action": "advisory",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": {
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "c-1",
            },
            "row": {
                "gemini": {"model": "google/gemini-test", "effort": "high"},
                "codex": {
                    "model": "openai/codex-test",
                    "effort": "high",
                    "mode": "prompt-only",
                },
            },
        }
        result = self._run(request)
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response["status"], "unavailable")
        self.assertEqual(response["attempts"], [])

        request["row"] = {
            "gemini": {"model": "google/gemini-test", "effort": "high"},
            "codex": {"model": "openai/codex-test", "effort": "high", "mode": "prompt-only"},
            "grok": {"mode": "prompt-only"},
        }
        result = self._run(request)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "config_error")

    def test_automatic_advisory_is_sealed_as_non_explicit(self) -> None:
        coordinator = _load("agent_collab_test_coordinator", PLUGIN / "coordinator.py")
        policy = _load("agent_collab_test_policy", PLUGIN / "host_policy.py")
        runtime = _load("agent_collab_test_runtime", PLUGIN / "runtime_client.py")
        captured: list[bool] = []

        def invoke(*, envelope):
            captured.append(envelope.explicit_target)
            return runtime.RuntimeResult(
                runtime.RuntimeStatus.OK,
                result={"review": "ok"},
                provenance={"route": envelope.route},
            )

        request = {
            "protocol_version": 2,
            "request_id": "auto-seal-1",
            "operation": "execute",
            "route": "auto",
            "action": "advisory",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": {
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "c-1",
            },
            "row": {
                "gemini": {"model": "google/gemini-test", "effort": "high"},
                "codex": {
                    "model": "openai/codex-test",
                    "effort": "high",
                    "mode": "prompt-only",
                },
            },
            "prompt": "review",
        }
        with (
            mock.patch.object(
                policy,
                "_runtime_contracts",
                return_value=(frozenset({("codex", "advisory")}), "digest-1"),
            ),
            mock.patch.object(runtime, "invoke", side_effect=invoke),
            mock.patch.object(coordinator, "_inventory_legacy", return_value=()),
            mock.patch.object(
                coordinator,
                "_load",
                side_effect=lambda _name, filename: (
                    policy if filename == "host_policy.py" else runtime
                ),
            ),
        ):
            response, code = coordinator.process(request)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(captured, [False])

    def test_empty_primary_reobserves_zcode_model_on_each_request(self) -> None:
        coordinator = _load("agent_collab_switch_coordinator", PLUGIN / "coordinator.py")
        policy = _load("agent_collab_switch_policy", PLUGIN / "host_policy.py")
        runtime = _load("agent_collab_switch_runtime", PLUGIN / "runtime_client.py")
        observed: list[str] = []

        def invoke(*, envelope):
            observed.append(envelope.primary_family)
            return runtime.RuntimeResult(
                runtime.RuntimeStatus.OK,
                result={"review": "ok"},
                provenance={"route": envelope.route},
            )

        request = {
            "protocol_version": 2,
            "request_id": "switch-1",
            "operation": "execute",
            "route": "codex",
            "action": "advisory",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": {},
            "row": {
                "model": "openai/codex-test",
                "effort": "high",
                "mode": "prompt-only",
            },
            "prompt": "review",
        }
        with (
            mock.patch.object(
                policy,
                "_runtime_contracts",
                return_value=(frozenset({("codex", "advisory")}), "digest-1"),
            ),
            mock.patch.object(runtime, "invoke", side_effect=invoke),
            mock.patch.object(coordinator, "_inventory_legacy", return_value=()),
            mock.patch.object(
                coordinator,
                "_load",
                side_effect=lambda _name, filename: (
                    policy if filename == "host_policy.py" else runtime
                ),
            ),
        ):
            for model, expected in (
                ("opencode/glm-5.2", "zhipu"),
                ("google/gemini-2.5-pro", "google"),
            ):
                with mock.patch.dict(
                    os.environ,
                    {
                        "ZCODE_SESSION_ID": "zcode-1",
                        "OPENCODE_ACTIVE_MODEL": model,
                    },
                    clear=True,
                ):
                    response, code = coordinator.process(request)
                self.assertEqual(code, 0)
                self.assertEqual(response["status"], "ok")
                self.assertEqual(observed[-1], expected)
        self.assertEqual(observed, ["zhipu", "google"])

    def test_automatic_governance_normalizes_unknown_family_status(self) -> None:
        request = {
            "protocol_version": 2,
            "request_id": "auto-governance-1",
            "operation": "execute",
            "route": "auto",
            "action": "governance",
            "timeout_ms": 30_000,
            "governance": True,
            "primary": {},
            "row": {
                "gemini": {"model": "google/gemini-test", "effort": "high"},
                "codex": {
                    "model": "openai/codex-test",
                    "effort": "high",
                    "mode": "prompt-only",
                },
                "grok": {"mode": "prompt-only"},
            },
            "prompt": "review",
            "artifact": {
                "content": "artifact",
                "author_model": "google/gemini-test",
            },
        }
        result = self._run(request)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "unknown_family")

    def test_grok_is_reachable_only_for_sealed_architecture_or_governance(self) -> None:
        coordinator = _load("agent_collab_grok_role_coordinator", PLUGIN / "coordinator.py")
        policy = _load("agent_collab_grok_role_policy", PLUGIN / "host_policy.py")
        runtime = _load("agent_collab_grok_role_runtime", PLUGIN / "runtime_client.py")
        observed: list[tuple[str, str]] = []

        def invoke(*, envelope):
            observed.append((envelope.route, envelope.action))
            return runtime.RuntimeResult(
                runtime.RuntimeStatus.OK,
                result={"architecture": "ok"},
                provenance={"route": envelope.route, "action": envelope.action},
            )

        request = {
            "protocol_version": 2,
            "request_id": "architecture-1",
            "operation": "execute",
            "route": "auto",
            "action": "architecture",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": {
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "architect-1",
            },
            "row": {
                "gemini": {"model": "google/gemini-test", "effort": "high"},
                "codex": {
                    "model": "openai/codex-test",
                    "effort": "high",
                    "mode": "prompt-only",
                },
                "grok": {"mode": "prompt-only"},
            },
            "prompt": "Design the system.",
        }
        with (
            mock.patch.object(
                policy,
                "_runtime_contracts",
                return_value=(frozenset({("grok", "architecture")}), "digest-1"),
            ),
            mock.patch.object(runtime, "invoke", side_effect=invoke),
            mock.patch.object(coordinator, "_inventory_legacy", return_value=()),
            mock.patch.object(
                coordinator,
                "_load",
                side_effect=lambda _name, filename: (
                    policy if filename == "host_policy.py" else runtime
                ),
            ),
        ):
            response, code = coordinator.process(request)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(observed, [("grok", "architecture")])

        generic = dict(request, request_id="generic-1", action="advisory")
        generic["row"] = {key: value for key, value in request["row"].items() if key != "grok"}
        with (
            mock.patch.object(
                policy,
                "_runtime_contracts",
                return_value=(frozenset({("grok", "architecture")}), "digest-1"),
            ),
            mock.patch.object(coordinator, "_inventory_legacy", return_value=()),
            mock.patch.object(
                coordinator,
                "_load",
                side_effect=lambda _name, filename: (
                    policy if filename == "host_policy.py" else runtime
                ),
            ),
        ):
            response, code = coordinator.process(generic)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "unavailable")
        self.assertEqual(observed, [("grok", "architecture")])

        explicit_generic = dict(request, request_id="bad-grok-1", route="grok", action="advisory")
        explicit_generic["row"] = {"mode": "prompt-only"}
        response, code = coordinator.process(explicit_generic)
        self.assertEqual(code, 2)
        self.assertEqual(response["status"], "config_error")

    def test_declared_unavailable_worker_roles_are_not_config_errors(self) -> None:
        base = {
            "protocol_version": 2,
            "request_id": "worker-unavailable-1",
            "operation": "execute",
            "route": "codex",
            "action": "build",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": {
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "c-1",
            },
            "row": {},
            "prompt": "implement",
        }
        result = self._run(base)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "unavailable")

        automatic = dict(base)
        automatic.update(
            request_id="automatic-worker-unavailable-1",
            route="auto",
            action="worker",
        )
        result = self._run(automatic)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "unavailable")

    def test_non_governance_worker_accepts_exact_artifact_snapshot_for_exclusion(self) -> None:
        coordinator = _load("agent_collab_artifact_coordinator", PLUGIN / "coordinator.py")
        policy = _load("agent_collab_artifact_policy", PLUGIN / "host_policy.py")
        runtime = _load("agent_collab_artifact_runtime", PLUGIN / "runtime_client.py")
        request = {
            "protocol_version": 2,
            "request_id": "worker-artifact-1",
            "operation": "execute",
            "route": "opencode",
            "action": "build",
            "timeout_ms": 30_000,
            "governance": False,
            "primary": {
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "c-worker",
            },
            "row": {"cwd": "/tmp/work", "model": "opencode/glm-5.2"},
            "prompt": "generate",
            "artifact": {
                "content": "existing implementation",
                "author_model": "zhipu/glm-5.2",
            },
        }
        with (
            mock.patch.object(
                policy,
                "_runtime_contracts",
                return_value=(frozenset({("opencode", "build")}), "digest-1"),
            ),
            mock.patch.object(coordinator, "_inventory_legacy", return_value=()),
            mock.patch.object(
                coordinator,
                "_load",
                side_effect=lambda _name, filename: (
                    policy if filename == "host_policy.py" else runtime
                ),
            ),
        ):
            response, code = coordinator.process(request)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "same_family_blocked")

        advisory = dict(request, route="codex", action="advisory")
        advisory["row"] = {
            "model": "openai/codex",
            "effort": "high",
            "mode": "prompt-only",
        }
        captured = []

        def invoke(*, envelope):
            captured.append(envelope)
            return runtime.RuntimeResult(
                runtime.RuntimeStatus.OK,
                result={"review": "ok"},
                provenance={"route": envelope.route},
            )

        with (
            mock.patch.object(
                policy,
                "_runtime_contracts",
                return_value=(
                    frozenset({("opencode", "build"), ("codex", "advisory")}),
                    "digest-1",
                ),
            ),
            mock.patch.object(runtime, "invoke", side_effect=invoke),
            mock.patch.object(coordinator, "_inventory_legacy", return_value=()),
            mock.patch.object(
                coordinator,
                "_load",
                side_effect=lambda _name, filename: (
                    policy if filename == "host_policy.py" else runtime
                ),
            ),
        ):
            response, code = coordinator.process(advisory)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(captured[0].artifact_author_family, "zhipu")
        self.assertTrue(captured[0].artifact_present)

    def test_unhashable_row_values_return_config_error(self) -> None:
        cases = (
            (
                "codex",
                {
                    "model": "openai/codex-test",
                    "effort": [],
                    "mode": "prompt-only",
                },
            ),
            ("grok", {"mode": {"not": "hashable"}}),
        )
        for route, row in cases:
            with self.subTest(route=route):
                result = self._run(
                    {
                        "protocol_version": 2,
                        "request_id": f"bad-row-{route}",
                        "operation": "execute",
                        "route": route,
                        "action": "advisory",
                        "timeout_ms": 30_000,
                        "governance": False,
                        "primary": {
                            "primary_id": "claude",
                            "active_model": "anthropic/claude-opus",
                            "host_runtime": "claude-code",
                            "session_identifier": "c-1",
                        },
                        "row": row,
                        "prompt": "review",
                    }
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "config_error")

    def test_incomplete_legacy_inventory_is_a_hard_conflict(self) -> None:
        coordinator = _load(
            "agent_collab_inventory_closed_coordinator", PLUGIN / "coordinator.py"
        )
        inventory = type(
            "Inventory",
            (),
            {
                "active_packages": (),
                "installed_packages": (),
                "errors": ("registry unreadable",),
            },
        )()
        doctor = type(
            "Doctor",
            (),
            {"inventory_legacy_packages": staticmethod(lambda _home: inventory)},
        )()
        with mock.patch.object(coordinator, "_load", return_value=doctor):
            self.assertEqual(
                coordinator._inventory_legacy(), ("inventory-unavailable",)
            )

    def test_home_lookup_failures_close_legacy_inventory(self) -> None:
        coordinator = _load(
            "agent_collab_home_closed_coordinator", PLUGIN / "coordinator.py"
        )
        doctor = mock.Mock()
        for failure in (KeyError("missing passwd entry"), RuntimeError("no home")):
            with self.subTest(failure=type(failure).__name__), mock.patch.object(
                coordinator, "_load", return_value=doctor
            ), mock.patch.object(coordinator.Path, "home", side_effect=failure):
                self.assertEqual(
                    coordinator._inventory_legacy(), ("inventory-unavailable",)
                )
                doctor.inventory_legacy_packages.assert_not_called()

    def test_main_contains_keyerror_and_runtimeerror_from_processing(self) -> None:
        coordinator = _load(
            "agent_collab_main_closed_coordinator", PLUGIN / "coordinator.py"
        )
        for failure in (KeyError("missing passwd entry"), RuntimeError("no home")):
            with self.subTest(failure=type(failure).__name__):
                fake_stdin = mock.Mock()
                fake_stdin.buffer.read.return_value = b"{}"
                with mock.patch.object(
                    coordinator.sys, "stdin", fake_stdin
                ), mock.patch.object(
                    coordinator, "process", side_effect=failure
                ), mock.patch.object(coordinator, "_emit") as emit:
                    self.assertEqual(coordinator.main(), 2)
                response = emit.call_args.args[0]
                self.assertEqual(response["status"], "host_blocked")


if __name__ == "__main__":
    unittest.main()
