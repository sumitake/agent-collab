"""Public semantic coordinator contract."""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import termios
import time
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


def _configurable_terminal_settings(settings: list[object]) -> list[object]:
    """Exclude the kernel-maintained pending-input status bit from comparisons."""

    normalized = list(settings)
    normalized[6] = list(settings[6])
    normalized[3] &= ~getattr(termios, "PENDIN", 0)
    return normalized


def _write_all_with_deadline(
    descriptor: int, payload: bytes, *, timeout_seconds: float = 5.0
) -> None:
    """Write a PTY frame without letting a regression hang the test process."""

    view = memoryview(payload)
    written = 0
    deadline = time.monotonic() + timeout_seconds
    while written < len(view):
        try:
            count = os.write(descriptor, view[written:])
        except BlockingIOError:
            count = 0
        if count > 0:
            written += count
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError("PTY writer exceeded its deadline")
        _, writable, _ = select.select([], [descriptor], [], remaining)
        if not writable:
            raise AssertionError("PTY writer exceeded its deadline")


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

    def test_exact_legacy_semantic_fields_are_canonicalized(self) -> None:
        normalized: list[dict[str, object]] = []
        native = self.coordinator.validate_request(
            {
                "operation": "invoke",
                "request_id": "old-1",
                "action": " architecture.repository ",
                "quality_profile": " FRONTIER ",
                "effort_class": " MAXIMUM ",
                "route": " GROK ",
                "timeout_ms": 5000,
                "prompt": "Review architecture.",
                "source": {"mode": "repository", "repo_root": str(ROOT)},
            },
            self.wire,
            self.profile,
            normalized=normalized,
        )

        self.assertEqual(native["logical_action"], "architecture.repository")
        self.assertEqual(native["quality_profile"], "frontier")
        self.assertEqual(native["effort_class"], "maximum")
        self.assertEqual(native["target_agent"], "grok")
        self.assertEqual(
            native["source"], {"mode": "repository", "repo_root": str(ROOT)}
        )
        self.assertEqual(
            normalized,
            [
                {
                    "field": "operation",
                    "from": "invoke",
                    "to": None,
                    "reason": "default_invoke_operation",
                },
                {
                    "field": "logical_action",
                    "from": "legacy:action",
                    "to": "architecture.repository",
                    "reason": "exact_legacy_semantic_field",
                },
                {
                    "field": "target_agent",
                    "from": "legacy:route",
                    "to": "grok",
                    "reason": "exact_legacy_semantic_field",
                },
                {
                    "field": "quality_profile",
                    "from": " FRONTIER ",
                    "to": "frontier",
                    "reason": "ascii_token_matches_closed_value",
                },
                {
                    "field": "effort_class",
                    "from": " MAXIMUM ",
                    "to": "maximum",
                    "reason": "ascii_token_matches_closed_value",
                },
                {
                    "field": "source",
                    "from": "closed_source_object",
                    "to": "repository",
                    "reason": "flattened_public_source",
                },
            ],
        )

    def test_product_nickname_is_not_silently_mapped_to_an_agent(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self.coordinator.validate_request(
                {
                    "request_id": "nickname-1",
                    "action": "review.repository",
                    "quality_profile": "frontier",
                    "effort_class": "maximum",
                    "route": "glm",
                    "timeout_ms": 5000,
                    "prompt": "Review.",
                    "repo_root": str(ROOT),
                },
                self.wire,
                self.profile,
            )
        self.assertEqual(caught.exception.error_code, "target_agent_invalid")
        self.assertIn("zhipu", caught.exception.detail["admitted"])
        self.assertNotIn("glm", caught.exception.detail["admitted"])

    def test_conflicting_legacy_and_canonical_fields_fail_before_runtime(self) -> None:
        request = {
            "request_id": "conflict-1",
            "logical_action": "review.repository",
            "action": "governance.repository",
            "quality_profile": "frontier",
            "effort_class": "maximum",
            "target_agent": None,
            "timeout_ms": 5000,
            "prompt": "Review.",
            "repo_root": str(ROOT),
        }
        with self.assertRaises(ValueError) as caught:
            self.coordinator.validate_request(request, self.wire, self.profile)
        self.assertEqual(caught.exception.error_code, "conflicting_fields")

    def test_repository_action_requires_repo_root(self) -> None:
        with self.assertRaises(ValueError) as caught:
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
        # The missing source is named actionably so the caller can supply it.
        self.assertEqual(caught.exception.error_code, "request_not_closed")
        self.assertEqual(caught.exception.detail["required_source"], "repo_root")
        self.assertIn("repo_root", caught.exception.detail["missing"])

    def test_one_accepted_request_invokes_runtime_once_without_replay(self) -> None:
        calls: list[object] = []
        fake_client = types.SimpleNamespace(
            RuntimeStatus=self.client.RuntimeStatus,
            runtime_contract_snapshot=lambda: (self.wire, "a" * 64, ""),
            invoke=lambda *, envelope: calls.append(envelope)
            or self.client.RuntimeResult(self.client.RuntimeStatus.UNAVAILABLE, error="busy"),
        )
        request = {
            "operation": "invoke",
            "request_id": "context-1",
            "action": " CONTEXT.DOCUMENTS.EXTRACT ",
            "quality_profile": " ECONOMICAL ",
            "effort_class": " MINIMAL ",
            "route": " GEMINI ",
            "timeout_ms": 5000,
            "prompt": "Extract facts.",
            "source": {
                "mode": "documents",
                "documents": [{"label": "a", "content": "one"}],
            },
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
        self.assertEqual(len(response["normalized"]), 6)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["logical_action"], "context.documents.extract")
        self.assertEqual(calls[0]["target_agent"], "gemini")
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
        self.assertEqual(response["request_id"], "context-private-error")
        self.assertEqual(response["status"], "provider_error")
        self.assertEqual(response["error_code"], "runtime_provider_error")
        # An attempt-local failure is classified 'retry', never 'unavailable':
        # this is what stops a transient error being read as a provider outage.
        self.assertEqual(response["disposition"], "retry")
        self.assertIsInstance(response["recovery"], str)
        self.assertTrue(response["recovery"])

    def test_attempt_local_failures_do_not_quarantine_later_request(self) -> None:
        request = {
            "request_id": "attempt-1",
            "logical_action": "context.documents.extract",
            "quality_profile": "economical",
            "effort_class": "minimal",
            "target_agent": "gemini",
            "timeout_ms": 5000,
            "prompt": "Extract facts.",
            "documents": [{"label": "a", "content": "one"}],
        }
        fake_policy = types.SimpleNamespace(resolve_profile=lambda: self.profile)

        for first_status in (
            self.client.RuntimeStatus.PROVIDER_ERROR,
            self.client.RuntimeStatus.TEARDOWN_ERROR,
        ):
            with self.subTest(first_status=first_status.value):
                calls: list[object] = []
                results = iter((
                    self.client.RuntimeResult(
                        first_status, error=f"runtime_{first_status.value}"
                    ),
                    self.client.RuntimeResult(
                        self.client.RuntimeStatus.UNAVAILABLE,
                        error="later_request_reached_runtime",
                    ),
                ))

                def invoke(*, envelope):
                    calls.append(envelope)
                    return next(results)

                fake_client = types.SimpleNamespace(
                    RuntimeStatus=self.client.RuntimeStatus,
                    runtime_contract_snapshot=lambda: (self.wire, "a" * 64, ""),
                    invoke=invoke,
                )
                with mock.patch.object(
                    self.coordinator, "_load_runtime", return_value=fake_client
                ), mock.patch.object(
                    self.coordinator, "_load_host_policy", return_value=fake_policy
                ):
                    first, first_code = self.coordinator.process(request)
                    second_request = {**request, "request_id": "attempt-2"}
                    second, second_code = self.coordinator.process(second_request)

                self.assertEqual(first_code, 0)
                self.assertEqual(first["status"], first_status.value)
                self.assertEqual(second_code, 0)
                self.assertEqual(second["error_code"], "later_request_reached_runtime")
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0]["target_agent"], "gemini")
                self.assertEqual(calls[1]["target_agent"], "gemini")

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
            "quality_profile": "frontier",
            "effort_class": "maximum",
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
                "quality_profile": "frontier",
                "effort_class": "maximum",
                "timeout_ms": 5000,
            },
        )

    def test_readiness_projection_satisfies_current_runtime_schema(self) -> None:
        native = self.coordinator.validate_readiness_request(
            {
                "operation": "readiness",
                "request_id": "runtime-status-current-schema",
                "quality_profile": "frontier",
                "effort_class": "maximum",
                "timeout_ms": 5000,
            },
            self.wire,
            self.profile,
        )

        self.client._validate_schema(native, self.wire.readiness_request)

    def test_readiness_rejects_unknown_host_and_caller_injected_fields(self) -> None:
        request = {
            "operation": "readiness",
            "request_id": "runtime-status-2",
            "quality_profile": "frontier",
            "effort_class": "maximum",
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

    def test_typed_runtime_route_error_is_not_a_cli_input_failure(self) -> None:
        fake_client = types.SimpleNamespace(
            RuntimeStatus=self.client.RuntimeStatus,
            runtime_contract_snapshot=lambda: (self.wire, "a" * 64, ""),
            invoke=lambda **_kwargs: self.client.RuntimeResult(
                self.client.RuntimeStatus.INVALID_REQUEST,
                error="unsupported_target_action",
                provenance={
                    "wire_contract_sha256": self.wire.sha256,
                    "diagnostics": {},
                },
            ),
        )
        fake_policy = types.SimpleNamespace(resolve_profile=lambda: self.profile)
        request = {
            "request_id": "unsupported-route",
            "logical_action": "architecture.repository",
            "quality_profile": "frontier",
            "effort_class": "maximum",
            "target_agent": "grok",
            "timeout_ms": 5000,
            "prompt": "Review architecture.",
            "repo_root": str(ROOT),
        }
        with mock.patch.object(
            self.coordinator, "_load_runtime", return_value=fake_client
        ), mock.patch.object(
            self.coordinator, "_load_host_policy", return_value=fake_policy
        ):
            response, code = self.coordinator.process(request)

        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "invalid_request")
        self.assertEqual(response["error_code"], "unsupported_target_action")

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
            "logical_action": "context.documents.intent",
            "quality_profile": "standard",
            "effort_class": "standard",
            "target_agent": None,
            "timeout_ms": 5000,
            "prompt": "Think.",
            "documents": [{"label": "request", "content": "Think."}],
        }
        native = self.coordinator.validate_request(base, self.wire, self.profile)
        self.assertEqual(native["quality_profile"], "standard")
        self.assertEqual(native["effort_class"], "standard")

        for field in ("quality_profile", "effort_class"):
            with self.subTest(missing=field):
                with self.assertRaises(ValueError) as caught:
                    self.coordinator.validate_request(
                        {key: value for key, value in base.items() if key != field},
                        self.wire,
                        self.profile,
                    )
                self.assertEqual(caught.exception.error_code, "missing_common_fields")
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

    def test_open_pty_request_completes_on_newline_without_eof(self) -> None:
        """An interactive caller receives one response while its PTY stays open."""

        master_fd, slave_fd = os.openpty()
        process = subprocess.Popen(
            [sys.executable, str(PLUGIN / "coordinator.py")],
            stdin=slave_fd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
        os.close(slave_fd)
        try:
            started = time.monotonic()
            os.write(master_fd, b"{}\n")
            stdout, stderr = process.communicate(timeout=5)
            self.assertLess(time.monotonic() - started, 5)
            self.assertEqual(stderr, b"")
            response = json.loads(stdout)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(response["status"], "invalid_request")
            self.assertEqual(response["error_code"], "missing_common_fields")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
            os.close(master_fd)

    def test_open_pty_long_request_bypasses_canonical_buffer_and_restores_tty(
        self,
    ) -> None:
        """A long newline frame completes while its PTY stays open and unchanged."""

        master_fd, slave_fd = os.openpty()
        observer_fd = os.dup(slave_fd)
        original = termios.tcgetattr(observer_fd)
        without_echo = list(original)
        without_echo[6] = list(original[6])
        without_echo[3] &= ~(termios.ECHO | getattr(termios, "ECHONL", 0))
        termios.tcsetattr(observer_fd, termios.TCSANOW, without_echo)
        expected = termios.tcgetattr(observer_fd)
        process = subprocess.Popen(
            [sys.executable, str(PLUGIN / "coordinator.py")],
            stdin=slave_fd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
        os.close(slave_fd)
        payload = json.dumps({"padding": "x" * (64 * 1024)}).encode("utf-8") + b"\n"
        try:
            started = time.monotonic()
            ready_deadline = started + 2
            while termios.tcgetattr(observer_fd)[3] & termios.ICANON:
                self.assertIsNone(process.poll())
                self.assertLess(time.monotonic(), ready_deadline)
                time.sleep(0.001)
            os.set_blocking(master_fd, False)
            _write_all_with_deadline(master_fd, payload)
            stdout, stderr = process.communicate(timeout=5)
            self.assertLess(time.monotonic() - started, 5)
            self.assertEqual(stderr, b"")
            response = json.loads(stdout)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(response["status"], "invalid_request")
            self.assertEqual(response["error_code"], "missing_common_fields")
            self.assertEqual(
                _configurable_terminal_settings(termios.tcgetattr(observer_fd)),
                _configurable_terminal_settings(expected),
            )
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
            termios.tcsetattr(observer_fd, termios.TCSANOW, original)
            os.close(observer_fd)
            os.close(master_fd)

    def test_open_pty_valid_slow_frame_is_not_an_incomplete_false_failure(
        self,
    ) -> None:
        """A valid frame may pause beyond the retired inter-chunk heuristic."""

        master_fd, slave_fd = os.openpty()
        process = subprocess.Popen(
            [sys.executable, str(PLUGIN / "coordinator.py")],
            stdin=slave_fd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
        os.close(slave_fd)
        try:
            started = time.monotonic()
            ready_deadline = started + 2
            while termios.tcgetattr(master_fd)[3] & termios.ICANON:
                self.assertIsNone(process.poll())
                self.assertLess(time.monotonic(), ready_deadline)
                time.sleep(0.001)
            os.write(master_fd, b"{")
            time.sleep(2.2)
            os.write(master_fd, b"}\n")
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(stderr, b"")
            response = json.loads(stdout)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(response["status"], "invalid_request")
            self.assertEqual(response["error_code"], "missing_common_fields")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
            os.close(master_fd)

    def test_tty_deadline_restores_terminal_and_maps_to_typed_error(self) -> None:
        master_fd, slave_fd = os.openpty()
        observer_fd = os.dup(slave_fd)
        stream = os.fdopen(os.dup(slave_fd), "rb", buffering=0)
        original = termios.tcgetattr(observer_fd)
        os.write(master_fd, b'{"request_id":"truncated"')
        descriptor = stream.fileno()
        with mock.patch.object(
            self.coordinator.select,
            "select",
            side_effect=[([descriptor], [], []), ([], [], [])],
        ):
            with self.assertRaises(self.coordinator._IncompleteTTYFrame):
                self.coordinator._read_tty_request(stream)
        self.assertEqual(
            _configurable_terminal_settings(termios.tcgetattr(observer_fd)),
            _configurable_terminal_settings(original),
        )
        with (
            mock.patch.object(
                self.coordinator,
                "_read_one_request",
                side_effect=self.coordinator._IncompleteTTYFrame,
            ),
            mock.patch.object(self.coordinator.sys, "stdout", io.StringIO()) as output,
        ):
            result = self.coordinator.main()
        response = json.loads(output.getvalue())
        self.assertEqual(result, 2)
        self.assertEqual(response["status"], "invalid_request")
        self.assertEqual(response["error_code"], "tty_frame_incomplete")
        self.assertEqual(response["detail"]["max_wait_ms"], 120000)
        stream.close()
        os.close(observer_fd)
        os.close(slave_fd)
        os.close(master_fd)

    def test_post_decode_failure_is_not_mislabeled_invalid_json(self) -> None:
        stdin = types.SimpleNamespace(buffer=io.BytesIO(b"{}"))
        stdout = io.StringIO()
        with mock.patch.object(self.coordinator.sys, "stdin", stdin), mock.patch.object(
            self.coordinator.sys, "stdout", stdout
        ), mock.patch.object(
            self.coordinator, "process", side_effect=ValueError("internal")
        ):
            code = self.coordinator.main()

        response = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "unavailable")
        self.assertEqual(response["error_code"], "coordinator_unavailable")

    def test_non_tty_pipe_waits_for_eof_and_rejects_trailing_object(self) -> None:
        process = subprocess.Popen(
            [sys.executable, str(PLUGIN / "coordinator.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdin is not None
        try:
            process.stdin.write(b"{}\n")
            process.stdin.flush()
            with self.assertRaises(subprocess.TimeoutExpired):
                process.wait(timeout=0.5)

            process.stdin.write(b"{}\n")
            process.stdin.close()
            process.stdin = None
            stdout, stderr = process.communicate(timeout=5)
            response = json.loads(stdout)
            self.assertEqual(stderr, b"")
            self.assertEqual(process.returncode, 2)
            self.assertEqual(response["error_code"], "invalid_json_request")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)



if __name__ == "__main__":
    unittest.main()
