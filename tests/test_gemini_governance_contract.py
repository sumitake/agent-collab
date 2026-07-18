"""End-to-end public contract tests for managed Gemini governance."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PLUGIN / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class GeminiGovernancePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = _load("gemini_governance_policy", "host_policy.py")
        cls.coordinator = _load(
            "gemini_governance_coordinator", "coordinator.py"
        )
        cls.runtime = _load("gemini_governance_runtime", "runtime_client.py")

    def _profile(self):
        return self.policy.HostProfile(
            primary_id="claude",
            primary_family="anthropic",
            active_model="anthropic/claude-opus",
            host_runtime="claude-code",
            session_identifier="claude-session",
            explicit=True,
            governance_ready=True,
        )

    def test_route_is_a_distinct_contract_v3_governance_action(self) -> None:
        self.assertEqual(self.runtime.CONTRACT_VERSION, 3)
        self.assertIn(("gemini", "governance"), self.runtime.SUPPORTED_CONTRACTS)
        self.assertIn(("gemini", "governance"), self.policy.ROUTE_ACTIONS)
        self.assertIn(("gemini", "governance"), self.policy.GOVERNANCE_CONTRACTS)
        self.assertNotIn(("gemini", "advisory"), self.policy.GOVERNANCE_CONTRACTS)
        self.assertEqual(
            self.policy.AUTHORITIES[("gemini", "governance")], "read_only"
        )

    def test_governance_row_is_exact_model_and_high_effort_only(self) -> None:
        for effort in ("high", "xhigh"):
            with self.subTest(effort=effort):
                row, family, error = self.policy._validate_row(
                    "gemini",
                    "governance",
                    {"model": "google/gemini-3.1-pro", "effort": effort},
                    self._profile(),
                    None,
                )
                self.assertEqual(
                    row,
                    {"model": "google/gemini-3.1-pro", "effort": effort},
                    error,
                )
                self.assertEqual(family, "google")

        for row in (
            {"model": "google/gemini-3.1-pro", "effort": "medium"},
            {"model": "google/gemini-2.5-pro", "effort": "high"},
            {
                "model": "google/gemini-3.1-pro",
                "effort": "high",
                "cwd": "/tmp",
            },
        ):
            with self.subTest(row=row):
                validated, _family, error = self.policy._validate_row(
                    "gemini", "governance", row, self._profile(), None
                )
                self.assertIsNone(validated)
                self.assertIn("Gemini governance", error)

    def test_direct_schema_requires_governance_authority(self) -> None:
        request = {
            "protocol_version": 2,
            "request_id": "gemini-governance-direct",
            "operation": "execute",
            "route": "gemini",
            "action": "governance",
            "timeout_ms": 30_000,
            "governance": True,
            "primary": {
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "claude-session",
            },
            "row": {
                "model": "google/gemini-3.1-pro",
                "effort": "high",
            },
            "prompt": "Review the captured artifact.",
            "artifact": {
                "content": "artifact",
                "author_model": "openai/gpt-5",
            },
        }
        validated, _request_id, error = self.coordinator._validate(request)
        self.assertEqual(validated, request, error)

        ordinary = dict(request, governance=False)
        ordinary.pop("artifact")
        rejected, _request_id, error = self.coordinator._validate(ordinary)
        self.assertIsNone(rejected)
        self.assertEqual(error, self.coordinator.ACTION_AUTHORITY_ERROR)

    def test_automatic_governance_maps_gemini_to_governance_not_advisory(self) -> None:
        policy = self.policy
        runtime = self.runtime
        coordinator = self.coordinator
        observed: list[tuple[str, str]] = []

        def invoke(*, envelope):
            observed.append((envelope.route, envelope.action))
            return runtime.RuntimeResult(
                runtime.RuntimeStatus.OK,
                result={"text": "approved"},
                provenance={"route": envelope.route, "action": envelope.action},
            )

        request = {
            "protocol_version": 2,
            "request_id": "gemini-governance-auto",
            "operation": "execute",
            "route": "auto",
            "action": "governance",
            "timeout_ms": 30_000,
            "governance": True,
            "primary": {
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "claude-session",
            },
            "row": {
                "gemini": {
                    "model": "google/gemini-3.1-pro",
                    "effort": "high",
                },
                "codex": {
                    "model": "openai/codex-test",
                    "effort": "high",
                    "mode": "prompt-only",
                },
                "grok": {"mode": "prompt-only"},
            },
            "prompt": "Review the captured artifact.",
            "artifact": {
                "content": "artifact",
                "author_model": "openai/gpt-5",
            },
        }
        contracts = frozenset(
            {
                ("gemini", "governance"),
                ("codex", "advisory"),
                ("grok", "governance"),
            }
        )
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(
                policy, "_runtime_contracts", return_value=(contracts, "digest-2")
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
        self.assertEqual(response["status"], "ok", response)
        self.assertEqual(response["selected_route"], "gemini")
        self.assertEqual(observed, [("gemini", "governance")])


class GeminiGovernanceResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = _load("gemini_governance_response_client", "runtime_client.py")

    def _envelope(self, *, action: str = "governance", operation: str = "execute"):
        model = "google/gemini-3.1-pro"
        return types.SimpleNamespace(
            request_id="governance-response-1",
            route="gemini",
            action=action,
            authority="read_only",
            operation=operation,
            row_json=json.dumps(
                {"model": model, "effort": "high"},
                sort_keys=True,
                separators=(",", ":"),
            ),
            target_author_family="google",
            governance=action == "governance",
            primary_family="anthropic",
            artifact_present=action == "governance",
            artifact_sha256=hashlib.sha256(b"artifact").hexdigest(),
            artifact_author_model="openai/gpt-5",
            artifact_author_family="openai",
        )

    def _provenance(
        self,
        envelope,
        *,
        host_runtime: object = "agent-collab-provider-runtime/2.0.0",
    ):
        return {
            "route": envelope.route,
            "action": envelope.action,
            "authority": envelope.authority,
            "author_model": "google/gemini-3.1-pro",
            "author_family": "google",
            "host_runtime": host_runtime,
            "session_identifier": "gemini-session",
            "observation_sequence": 1,
        }

    def _proof(
        self,
        envelope,
        text: str,
        *,
        runtime_version: str = "2.0.0",
        contract_version: int = 2,
    ) -> dict[str, object]:
        proof: dict[str, object] = {
            "version": 1,
            "request_id": envelope.request_id,
            "action": "governance",
            "authority": "read_only",
            "transport": "broker",
            "backend": "agy",
            "runtime_version": runtime_version,
            "contract_version": contract_version,
            "artifact_sha256": envelope.artifact_sha256,
            "artifact_author_model": envelope.artifact_author_model,
            "artifact_author_family": envelope.artifact_author_family,
            "reviewer_model": "google/gemini-3.1-pro",
            "reviewer_family": "google",
            "selected_display": "Gemini 3.1 Pro (High)",
            "effective_effort": "high",
            "containment_level": "write_contained_shared_home",
            "tools_disabled": False,
            "pty_used": True,
            "lock_acquired": True,
            "cleanup_confirmed": True,
            "provider_process_started": True,
            "returncode": 0,
            "model_source": "agy-selected",
            "failed_over": False,
            "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
        canonical = json.dumps(
            proof, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
        proof["proof_sha256"] = hashlib.sha256(canonical).hexdigest()
        return proof

    def _response(
        self,
        envelope,
        *,
        text: str = "approved",
        runtime_version: str = "2.0.0",
        contract_version: int = 2,
        provenance_host_runtime: object = "agent-collab-provider-runtime/2.0.0",
    ) -> dict[str, object]:
        result = {
            "text": text,
            "containment_level": "write_contained_shared_home",
            "tools_disabled": False,
            "pty_used": True,
            "lock_acquired": True,
            "cleanup_confirmed": True,
            "selected_display": "Gemini 3.1 Pro (High)",
            "governance_evidence": True,
            "artifact_sha256": envelope.artifact_sha256,
            "artifact_author_model": envelope.artifact_author_model,
            "artifact_author_family": envelope.artifact_author_family,
        }
        result["governance_proof"] = self._proof(
            envelope,
            text,
            runtime_version=runtime_version,
            contract_version=contract_version,
        )
        return {
            "protocol_version": 2,
            "request_id": envelope.request_id,
            "status": "ok",
            "result": result,
            "provenance": self._provenance(
                envelope,
                host_runtime=provenance_host_runtime,
            ),
        }

    def _parse(self, response: dict[str, object], envelope):
        return self.client._parse_response(
            json.dumps(response, separators=(",", ":")).encode("utf-8"),
            envelope,
            0,
        )

    def test_execute_requires_complete_artifact_bound_broker_proof(self) -> None:
        envelope = self._envelope()
        result = self._parse(self._response(envelope), envelope)
        self.assertEqual(result.status, self.client.RuntimeStatus.OK, result.error)
        self.assertTrue(result.result["governance_evidence"])

        mutators = (
            lambda response: response["result"].__setitem__("pty_used", False),
            lambda response: response["result"]["governance_proof"].__setitem__(
                "artifact_sha256", "0" * 64
            ),
            lambda response: response["result"]["governance_proof"].__setitem__(
                "proof_sha256", "0" * 64
            ),
            lambda response: response["result"]["governance_proof"].__setitem__(
                "response_sha256", "0" * 64
            ),
            lambda response: response["result"]["governance_proof"].__setitem__(
                "transport", "direct"
            ),
            lambda response: response["result"]["governance_proof"].pop(
                "runtime_version"
            ),
            lambda response: response["result"]["governance_proof"].__setitem__(
                "unexpected", True
            ),
        )
        for mutate in mutators:
            with self.subTest(mutate=mutate):
                response = self._response(envelope)
                mutate(response)
                rejected = self._parse(response, envelope)
                self.assertEqual(
                    rejected.status, self.client.RuntimeStatus.PROTOCOL_ERROR
                )

    def test_execute_accepts_provider_runtime_v2_governance_proof(self) -> None:
        envelope = self._envelope()
        response = self._response(
            envelope,
            runtime_version="2.0.0",
            contract_version=2,
        )
        result = self._parse(response, envelope)
        self.assertEqual(result.status, self.client.RuntimeStatus.OK, result.error)

    def test_execute_rejects_legacy_or_crossed_proof_versions(self) -> None:
        envelope = self._envelope()
        for runtime_version, contract_version in (
            ("1.2.0", 3),
            ("2.0.0", 3),
            ("1.2.0", 2),
        ):
            with self.subTest(
                runtime_version=runtime_version,
                contract_version=contract_version,
            ):
                response = self._response(
                    envelope,
                    runtime_version=runtime_version,
                    contract_version=contract_version,
                )
                result = self._parse(response, envelope)
                self.assertEqual(
                    result.status,
                    self.client.RuntimeStatus.PROTOCOL_ERROR,
                )

    def test_execute_rejects_proof_runtime_mismatched_with_provenance(self) -> None:
        envelope = self._envelope()
        response = self._response(
            envelope,
            runtime_version="2.0.0",
            contract_version=2,
            provenance_host_runtime="agent-collab-provider-runtime/1.2.0",
        )
        result = self._parse(response, envelope)
        self.assertEqual(
            result.status,
            self.client.RuntimeStatus.PROTOCOL_ERROR,
        )

    def test_execute_rejects_malformed_provenance_runtime_identity(self) -> None:
        envelope = self._envelope()
        for host_runtime in (
            None,
            2,
            "",
            "agent-collab-provider-runtime/",
            "agent-collab-provider-runtime/2.0.0-extra",
            "Agent-collab-provider-runtime/2.0.0",
            "agent-collab-provider-runtime/\uff12.0.0",
            " agent-collab-provider-runtime/2.0.0 ",
        ):
            with self.subTest(host_runtime=host_runtime):
                response = self._response(
                    envelope,
                    provenance_host_runtime=host_runtime,
                )
                result = self._parse(response, envelope)
                self.assertEqual(
                    result.status,
                    self.client.RuntimeStatus.PROTOCOL_ERROR,
                )

        response = self._response(envelope)
        response["provenance"].pop("host_runtime")
        result = self._parse(response, envelope)
        self.assertEqual(
            result.status,
            self.client.RuntimeStatus.PROTOCOL_ERROR,
        )

    def test_governance_readiness_rejects_incompatible_runtime_provenance(
        self,
    ) -> None:
        envelope = self._envelope(operation="readiness")
        result = {
            "ready": True,
            "containment_level": "write_contained_shared_home",
            "tools_disabled": False,
            "pty_used": True,
            "lock_acquired": True,
            "cleanup_confirmed": True,
            "selected_display": "Gemini 3.1 Pro (High)",
            "governance_ready": True,
            "artifact_sha256": envelope.artifact_sha256,
            "artifact_author_model": envelope.artifact_author_model,
            "artifact_author_family": envelope.artifact_author_family,
        }
        response = {
            "protocol_version": 2,
            "request_id": envelope.request_id,
            "status": "ok",
            "result": result,
            "provenance": self._provenance(
                envelope,
                host_runtime="agent-collab-provider-runtime/1.2.0",
            ),
        }
        rejected = self._parse(response, envelope)
        self.assertEqual(
            rejected.status,
            self.client.RuntimeStatus.PROTOCOL_ERROR,
        )

    def test_governance_readiness_requires_shared_home_pty_proof_tuple(self) -> None:
        envelope = self._envelope(operation="readiness")
        result = {
            "ready": True,
            "containment_level": "write_contained_shared_home",
            "tools_disabled": False,
            "pty_used": True,
            "lock_acquired": True,
            "cleanup_confirmed": True,
            "selected_display": "Gemini 3.1 Pro (High)",
            "governance_ready": True,
            "artifact_sha256": envelope.artifact_sha256,
            "artifact_author_model": envelope.artifact_author_model,
            "artifact_author_family": envelope.artifact_author_family,
        }
        response = {
            "protocol_version": 2,
            "request_id": envelope.request_id,
            "status": "ok",
            "result": result,
            "provenance": self._provenance(envelope),
        }
        accepted = self._parse(response, envelope)
        self.assertEqual(
            accepted.status, self.client.RuntimeStatus.OK, accepted.error
        )
        result["pty_used"] = False
        rejected = self._parse(response, envelope)
        self.assertEqual(rejected.status, self.client.RuntimeStatus.PROTOCOL_ERROR)

    def test_advisory_cannot_emit_governance_evidence(self) -> None:
        envelope = self._envelope(action="advisory")
        response = {
            "protocol_version": 2,
            "request_id": envelope.request_id,
            "status": "ok",
            "result": {"text": "advice", "governance_evidence": True},
            "provenance": self._provenance(envelope),
        }
        rejected = self._parse(response, envelope)
        self.assertEqual(rejected.status, self.client.RuntimeStatus.PROTOCOL_ERROR)

        response["result"]["governance_evidence"] = False
        accepted = self._parse(response, envelope)
        self.assertEqual(accepted.status, self.client.RuntimeStatus.OK, accepted.error)


if __name__ == "__main__":
    unittest.main()
