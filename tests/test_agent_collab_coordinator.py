"""Public semantic coordinator contract."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest import mock

from tests.test_direct_runtime_public_contract import _wire_descriptor


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SemanticCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = _load("coordinator_test_client", PLUGIN / "runtime_client.py")
        cls.coordinator = _load("semantic_coordinator", PLUGIN / "coordinator.py")
        cls.host_policy = _load("semantic_host_policy", PLUGIN / "host_policy.py")
        descriptor, digest = _wire_descriptor()
        cls.wire = cls.client.validate_wire_descriptor(
            descriptor, expected_sha256=digest
        )
        cls.profile = cls.host_policy.HostProfile(
            "codex", "openai", "gpt-test", "codex", "session-1", False,
            governance_ready=True,
        )

    def test_repository_request_adds_canonical_repo_source_and_wire_hash(self) -> None:
        request = {
            "request_id": "review-1",
            "logical_action": "review.repository",
            "quality_profile": "frontier",
            "effort_class": "maximum",
            "target_agent": None,
            "timeout_ms": 5000,
            "prompt": "Review the current repository.",
            "repo_root": str(ROOT),
        }
        host = self.host_policy.HostProfile(
            "codex", "openai", "gpt-test", "codex", "session-1", False,
            governance_ready=True,
        )
        native = self.coordinator.validate_request(request, self.wire, host)
        self.assertEqual(native["wire_contract_sha256"], self.wire.sha256)
        self.assertEqual(native["quality_profile"], "frontier")
        self.assertEqual(native["effort_class"], "maximum")
        self.assertEqual(
            native["source"], {"mode": "repository", "repo_root": str(ROOT)}
        )
        self.assertNotIn("route", native)
        self.assertNotIn("action", native)

    def test_context_repository_request_uses_descriptor_source_mode(self) -> None:
        request = {
            "request_id": "context-repository-1",
            "logical_action": "context.repository.extract",
            "quality_profile": "economical",
            "effort_class": "minimal",
            "target_agent": "grok",
            "timeout_ms": 5000,
            "prompt": "Extract repository facts.",
            "repo_root": str(ROOT),
        }
        native = self.coordinator.validate_request(request, self.wire, self.profile)
        self.assertEqual(
            native["source"], {"mode": "repository", "repo_root": str(ROOT)}
        )

    def test_old_public_route_action_request_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "closed"):
            self.coordinator.validate_request(
                {
                    "request_id": "old-1",
                    "route": "grok",
                    "action": "architecture",
                    "timeout_ms": 5000,
                    "prompt": "old wire",
                },
                self.wire,
                self.profile,
            )

    def test_repository_action_requires_repo_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "repo_root"):
            self.coordinator.validate_request(
                {
                    "request_id": "review-2",
                    "logical_action": "review.repository",
                    "quality_profile": "frontier",
                    "effort_class": "maximum",
                    "target_agent": None,
                    "timeout_ms": 5000,
                    "prompt": "Review.",
                },
                self.wire,
                self.host_policy.HostProfile(
                    "codex", "openai", "gpt-test", "codex", "session-1", False,
                    governance_ready=True,
                ),
            )

    def test_one_accepted_request_invokes_runtime_once_without_replay(self) -> None:
        calls: list[object] = []
        fake_client = types.SimpleNamespace(
            RuntimeStatus=self.client.RuntimeStatus,
            runtime_contract_snapshot=lambda: (self.wire, "a" * 64, ""),
            invoke=lambda *, envelope: calls.append(envelope)
            or self.client.RuntimeResult(self.client.RuntimeStatus.UNAVAILABLE, error="busy"),
        )
        request = {
            "request_id": "context-1",
            "logical_action": "context.documents.extract",
            "quality_profile": "economical",
            "effort_class": "minimal",
            "target_agent": None,
            "timeout_ms": 5000,
            "prompt": "Extract facts.",
            "documents": [{"label": "a", "content": "one"}],
        }
        host = self.host_policy.HostProfile(
            "codex", "openai", "gpt-test", "codex", "session-1", False,
            governance_ready=True,
        )
        fake_policy = types.SimpleNamespace(resolve_profile=lambda: host)
        with mock.patch.object(
            self.coordinator, "_load_runtime", return_value=fake_client
        ), mock.patch.object(
            self.coordinator, "_load_host_policy", return_value=fake_policy, create=True
        ):
            response, code = self.coordinator.process(request)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "unavailable")
        self.assertEqual(response["error_code"], "busy")
        self.assertNotIn("error", response)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["author_lineage"], "openai")

    def test_runtime_free_text_is_reduced_to_a_stable_public_error_code(self) -> None:
        fake_client = types.SimpleNamespace(
            RuntimeStatus=self.client.RuntimeStatus,
            runtime_contract_snapshot=lambda: (self.wire, "a" * 64, ""),
            invoke=lambda **_kwargs: self.client.RuntimeResult(
                self.client.RuntimeStatus.PROVIDER_ERROR,
                error="provider emitted private failure text",
            ),
        )
        fake_policy = types.SimpleNamespace(resolve_profile=lambda: self.profile)
        request = {
            "request_id": "context-private-error",
            "logical_action": "context.documents.extract",
            "quality_profile": "economical",
            "effort_class": "minimal",
            "target_agent": None,
            "timeout_ms": 5000,
            "prompt": "Extract facts.",
            "documents": [{"label": "a", "content": "one"}],
        }
        with mock.patch.object(
            self.coordinator, "_load_runtime", return_value=fake_client
        ), mock.patch.object(
            self.coordinator, "_load_host_policy", return_value=fake_policy
        ):
            response, code = self.coordinator.process(request)

        self.assertEqual(code, 0)
        self.assertEqual(
            response,
            {
                "request_id": "context-private-error",
                "status": "provider_error",
                "error_code": "runtime_provider_error",
            },
        )

    def test_advisory_is_exit_zero_and_preserves_non_authoritative_metadata(self) -> None:
        advisory = {
            "authority": "advisory",
            "grounding": "ungrounded",
            "reason": "insufficient_source_evidence",
            "text": "Useful but non-authoritative analysis.",
        }
        provenance = {
            "wire_contract_sha256": self.wire.sha256,
            "diagnostics": {"failure_trace": {"adapter_code": "insufficient_evidence"}},
        }
        fake_client = types.SimpleNamespace(
            RuntimeStatus=self.client.RuntimeStatus,
            runtime_contract_snapshot=lambda: (self.wire, "a" * 64, ""),
            invoke=lambda **_kwargs: self.client.RuntimeResult(
                self.client.RuntimeStatus.ADVISORY,
                result=advisory,
                provenance=provenance,
            ),
        )
        fake_policy = types.SimpleNamespace(resolve_profile=lambda: self.profile)
        request = {
            "request_id": "advisory-1",
            "logical_action": "architecture.repository",
            "quality_profile": "frontier",
            "effort_class": "maximum",
            "target_agent": "codex",
            "timeout_ms": 5000,
            "prompt": "Analyze the repository.",
            "repo_root": str(ROOT),
        }
        with mock.patch.object(
            self.coordinator, "_load_runtime", return_value=fake_client
        ), mock.patch.object(
            self.coordinator, "_load_host_policy", return_value=fake_policy
        ):
            response, code = self.coordinator.process(request)

        self.assertEqual(code, 0)
        self.assertEqual(
            response,
            {
                "request_id": "advisory-1",
                "status": "advisory",
                "result": advisory,
                "provenance": provenance,
            },
        )
        self.assertNotIn("error_code", response)

    def test_readiness_derives_host_lineage_and_uses_one_runtime_process(self) -> None:
        calls: list[object] = []
        fake_client = types.SimpleNamespace(
            RuntimeStatus=self.client.RuntimeStatus,
            runtime_contract_snapshot=lambda: (self.wire, "a" * 64, ""),
            readiness=lambda *, envelope: calls.append(envelope)
            or self.client.RuntimeResult(
                self.client.RuntimeStatus.OK, result={"actions": []}
            ),
            invoke=lambda **_kwargs: self.fail("readiness used the inference call"),
        )
        fake_policy = types.SimpleNamespace(resolve_profile=lambda: self.profile)
        request = {
            "operation": "readiness",
            "request_id": "runtime-status-1",
            "timeout_ms": 5000,
        }
        with mock.patch.object(
            self.coordinator, "_load_runtime", return_value=fake_client
        ), mock.patch.object(
            self.coordinator, "_load_host_policy", return_value=fake_policy
        ):
            response, code = self.coordinator.process(request)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0],
            {
                "operation": "readiness",
                "wire_contract_sha256": self.wire.sha256,
                "request_id": "runtime-status-1",
                "author_lineage": "openai",
                "timeout_ms": 5000,
            },
        )

    def test_readiness_rejects_unknown_host_and_caller_injected_fields(self) -> None:
        request = {
            "operation": "readiness",
            "request_id": "runtime-status-2",
            "timeout_ms": 5000,
        }
        unknown = self.host_policy.HostProfile(
            "unknown", "unknown", "", "unknown", "unknown", False
        )
        with self.assertRaisesRegex(RuntimeError, "identity"):
            self.coordinator.validate_readiness_request(
                request, self.wire, unknown
            )
        with self.assertRaisesRegex(ValueError, "closed"):
            self.coordinator.validate_readiness_request(
                {**request, "prompt": "probe"}, self.wire, self.profile
            )

    def test_caller_cannot_assert_author_lineage(self) -> None:
        request = {
            "request_id": "review-forged",
            "logical_action": "review.repository",
            "quality_profile": "frontier",
            "effort_class": "maximum",
            "target_agent": None,
            "author_lineage": "google",
            "timeout_ms": 5000,
            "prompt": "Review.",
            "repo_root": str(ROOT),
        }
        host = self.host_policy.HostProfile(
            "codex", "openai", "gpt-test", "codex", "session-1", False,
            governance_ready=True,
        )
        with self.assertRaisesRegex(ValueError, "closed"):
            self.coordinator.validate_request(request, self.wire, host)

    def test_unknown_governance_identity_fails_before_runtime_inference(self) -> None:
        calls: list[object] = []
        fake_client = types.SimpleNamespace(
            RuntimeStatus=self.client.RuntimeStatus,
            runtime_contract_snapshot=lambda: (self.wire, "a" * 64, ""),
            invoke=lambda *, envelope: calls.append(envelope),
        )
        host = self.host_policy.HostProfile(
            "unknown", "unknown", "", "unknown", "unknown", False,
        )
        fake_policy = types.SimpleNamespace(resolve_profile=lambda: host)
        request = {
            "request_id": "governance-unknown",
            "logical_action": "governance.repository",
            "quality_profile": "frontier",
            "effort_class": "maximum",
            "target_agent": None,
            "timeout_ms": 5000,
            "prompt": "Govern.",
            "repo_root": str(ROOT),
        }
        with mock.patch.object(
            self.coordinator, "_load_runtime", return_value=fake_client
        ), mock.patch.object(
            self.coordinator, "_load_host_policy", return_value=fake_policy, create=True
        ):
            response, code = self.coordinator.process(request)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "unavailable")
        self.assertEqual(calls, [])

    def test_semantic_profiles_are_required_closed_and_provider_neutral(self) -> None:
        base = {
            "request_id": "profile-1",
            "logical_action": "architecture.conceptual",
            "quality_profile": "standard",
            "effort_class": "standard",
            "target_agent": None,
            "timeout_ms": 5000,
            "prompt": "Think.",
        }
        native = self.coordinator.validate_request(base, self.wire, self.profile)
        self.assertEqual(native["quality_profile"], "standard")
        self.assertEqual(native["effort_class"], "standard")

        for field in ("quality_profile", "effort_class"):
            with self.subTest(missing=field), self.assertRaisesRegex(ValueError, "closed"):
                self.coordinator.validate_request(
                    {key: value for key, value in base.items() if key != field},
                    self.wire,
                    self.profile,
                )
        for field, value in (
            ("quality_profile", "premium"),
            ("effort_class", "xhigh"),
            ("model", "exact-model"),
            ("provider", "vendor"),
            ("transport", "native"),
            ("pool", "shared"),
            ("native_effort", "high"),
            ("shadow", True),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.coordinator.validate_request(
                    {**base, field: value}, self.wire, self.profile
                )

    def test_codex_thread_proves_family_without_a_model_pin(self) -> None:
        with mock.patch.dict(
            os.environ, {"CODEX_THREAD_ID": "thread-1"}, clear=True
        ):
            profile = self.host_policy.resolve_profile()
        self.assertEqual(profile.primary_id, "codex")
        self.assertEqual(profile.primary_family, "openai")
        self.assertEqual(profile.active_model, "")
        self.assertTrue(profile.governance_ready)

    def test_claude_uses_the_canonical_code_session_identifier(self) -> None:
        with mock.patch.dict(
            os.environ, {"CLAUDE_CODE_SESSION_ID": "session-1"}, clear=True
        ):
            profile = self.host_policy.resolve_profile()
        self.assertEqual(profile.primary_id, "claude")
        self.assertEqual(profile.primary_family, "anthropic")
        self.assertEqual(profile.session_identifier, "session-1")
        self.assertTrue(profile.governance_ready)

    def test_conflicting_canonical_and_compat_session_ids_fail_closed(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "CLAUDE_CODE_SESSION_ID": "canonical-session",
                "CLAUDE_SESSION_ID": "different-session",
            },
            clear=True,
        ):
            profile = self.host_policy.resolve_profile()
        self.assertTrue(profile.identity_conflict)
        self.assertFalse(profile.governance_ready)

    def test_first_coordinator_boundary_rejects_duplicate_and_nonfinite_json(self) -> None:
        valid_fields = (
            '"logical_action":"architecture.conceptual",'
            '"target_agent":null,"timeout_ms":5000,'
            '"prompt":"Review."'
        )
        malformed = {
            "duplicate": (
                b'{"request_id":"first","request_id":"second",'
                + valid_fields.encode("utf-8")
                + b"}"
            ),
            "nan": (
                b'{"request_id":"nan","logical_action":"architecture.conceptual",'
                b'"target_agent":null,"timeout_ms":NaN,"prompt":"Review."}'
            ),
            "positive_infinity": (
                b'{"request_id":"inf","logical_action":"architecture.conceptual",'
                b'"target_agent":null,"timeout_ms":Infinity,"prompt":"Review."}'
            ),
            "negative_infinity": (
                b'{"request_id":"ninf","logical_action":"architecture.conceptual",'
                b'"target_agent":null,"timeout_ms":-Infinity,"prompt":"Review."}'
            ),
        }
        for name, raw in malformed.items():
            with self.subTest(name=name):
                completed = subprocess.run(
                    [sys.executable, str(PLUGIN / "coordinator.py")],
                    input=raw,
                    capture_output=True,
                    check=False,
                )
                response = json.loads(completed.stdout)
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(response["status"], "invalid_request")
                self.assertEqual(response["error_code"], "invalid_json_request")
                self.assertNotIn("error", response)



if __name__ == "__main__":
    unittest.main()
