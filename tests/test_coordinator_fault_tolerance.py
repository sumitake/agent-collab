"""Coordinator fault tolerance: actionable rejections + outcome classification.

Regression corpus for two recurring failure classes observed in the field:

* Bad invocation collapsing to a bare ``invalid_request`` with no field-level
  reason, so a caller cannot self-correct without re-deriving the request
  (e.g. ``timeout_ms`` over the enforced cap).
* Attempt-local / overloaded typed failures (``teardown_error``,
  ``provider_error``, ``protocol_error``) being read as a provider *outage*.

Every request-shape case is exercised through ``process`` with a stubbed
runtime, so no signed native runtime is launched; the ``invoke`` stub asserts it
is never reached for a rejected request.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
from unittest import mock
import unittest

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


class _Unreached(AssertionError):
    """Raised if the runtime is invoked for a request that should be rejected."""


class CoordinatorFaultToleranceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = _load("coord_ft_client", PLUGIN / "runtime_client.py")
        cls.coordinator = _load("coord_ft_coordinator", PLUGIN / "coordinator.py")
        cls.host_policy = _load("coord_ft_host_policy", PLUGIN / "host_policy.py")
        descriptor, digest = _wire_descriptor()
        cls.wire = cls.client.validate_wire_descriptor(descriptor, expected_sha256=digest)
        cls.profile = cls.host_policy.HostProfile(
            "codex", "openai", "gpt-test", "codex", "session-1", False,
            governance_ready=True,
        )

    # -- helpers -----------------------------------------------------------
    def _documents_request(self, **overrides) -> dict:
        request = {
            "request_id": "ft-1",
            "logical_action": "context.documents.extract",
            "quality_profile": "economical",
            "effort_class": "minimal",
            "target_agent": None,
            "timeout_ms": 5000,
            "prompt": "Extract facts.",
            "documents": [{"label": "a", "content": "one"}],
        }
        request.update(overrides)
        return request

    def _process(self, request, *, result=None):
        """Run ``process`` with a stubbed runtime; reject-path never invokes it."""

        def _invoke(**_kwargs):
            if result is None:
                raise _Unreached("invoke reached for a request that should be rejected")
            return result

        fake_client = types.SimpleNamespace(
            RuntimeStatus=self.client.RuntimeStatus,
            runtime_contract_snapshot=lambda: (self.wire, "a" * 64, ""),
            invoke=_invoke,
            readiness=_invoke,
        )
        fake_policy = types.SimpleNamespace(resolve_profile=lambda: self.profile)
        with mock.patch.object(
            self.coordinator, "_load_runtime", return_value=fake_client
        ), mock.patch.object(
            self.coordinator, "_load_host_policy", return_value=fake_policy
        ):
            return self.coordinator.process(request)

    # -- disposition classification (Class 1) ------------------------------
    def test_disposition_is_total_and_closed(self) -> None:
        allowed = {"fix_request", "retry", "inspect", "unavailable"}
        for status in self.client.RuntimeStatus:
            if status in {self.client.RuntimeStatus.OK, self.client.RuntimeStatus.ADVISORY}:
                continue
            disposition, recovery = self.coordinator._disposition(status.value)
            with self.subTest(status=status.value):
                self.assertIn(disposition, allowed)
                self.assertIsInstance(recovery, str)
                self.assertTrue(recovery)

    def test_attempt_local_and_overloaded_are_never_unavailable(self) -> None:
        # The load-bearing invariant: a transient/attempt-local outcome must not
        # be classified as a provider outage.
        for status in ("provider_error", "teardown_error", "protocol_error",
                       "timeout", "cancelled"):
            with self.subTest(status=status):
                disposition, _ = self.coordinator._disposition(status)
                self.assertNotEqual(disposition, "unavailable")

    def test_disposition_specific_mapping(self) -> None:
        cases = {
            "provider_error": "retry",
            "teardown_error": "retry",
            "timeout": "retry",
            "cancelled": "retry",
            "protocol_error": "inspect",
            "auth_error": "unavailable",
            "quota_error": "unavailable",
            "unavailable": "unavailable",
            "signature_error": "unavailable",
            "platform_unsupported": "unavailable",
            "invalid_request": "fix_request",
            "capability_error": "fix_request",
            "output_limit": "fix_request",
        }
        for status, expected in cases.items():
            with self.subTest(status=status):
                self.assertEqual(self.coordinator._disposition(status)[0], expected)

    def test_unrecognized_status_defaults_to_inspect(self) -> None:
        # Fail-safe: an unknown future status is never silently called an outage.
        self.assertEqual(self.coordinator._disposition("some_new_code")[0], "inspect")

    def test_runtime_teardown_error_surfaces_retry_not_outage(self) -> None:
        result = self.client.RuntimeResult(
            self.client.RuntimeStatus.TEARDOWN_ERROR, error="teardown could not be proven"
        )
        response, code = self._process(self._documents_request(), result=result)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "teardown_error")
        self.assertEqual(response["disposition"], "retry")

    def test_runtime_auth_error_surfaces_unavailable(self) -> None:
        result = self.client.RuntimeResult(
            self.client.RuntimeStatus.AUTH_ERROR, error="auth expired"
        )
        response, _ = self._process(self._documents_request(), result=result)
        self.assertEqual(response["disposition"], "unavailable")

    # -- actionable request validation (Class 2) ---------------------------
    def test_timeout_over_cap_is_actionable_not_bare(self) -> None:
        response, code = self._process(self._documents_request(timeout_ms=900000))
        self.assertEqual(code, 2)
        self.assertEqual(response["status"], "invalid_request")
        self.assertEqual(response["error_code"], "timeout_ms_over_cap")
        self.assertEqual(response["disposition"], "fix_request")
        self.assertEqual(response["detail"]["max"], self.coordinator.MAX_TIMEOUT_MS)
        self.assertEqual(response["detail"]["given"], 900000)

    def test_timeout_nonpositive_is_actionable(self) -> None:
        response, _ = self._process(self._documents_request(timeout_ms=0))
        self.assertEqual(response["error_code"], "timeout_ms_invalid")
        self.assertEqual(response["detail"]["max"], self.coordinator.MAX_TIMEOUT_MS)

    def test_unknown_action_lists_admitted_actions(self) -> None:
        response, _ = self._process(self._documents_request(logical_action="review.everything"))
        self.assertEqual(response["error_code"], "unknown_logical_action")
        self.assertIn("review.repository", response["detail"]["admitted"])
        self.assertEqual(response["disposition"], "fix_request")

    def test_invalid_profile_and_effort_list_admitted(self) -> None:
        bad_profile, _ = self._process(self._documents_request(quality_profile="premium"))
        self.assertEqual(bad_profile["error_code"], "quality_profile_invalid")
        self.assertEqual(bad_profile["detail"]["admitted"], ["economical", "standard", "frontier"])
        bad_effort, _ = self._process(self._documents_request(effort_class="xhigh"))
        self.assertEqual(bad_effort["error_code"], "effort_class_invalid")
        self.assertEqual(bad_effort["detail"]["admitted"], ["minimal", "standard", "maximum"])

    def test_missing_source_names_the_required_source(self) -> None:
        request = self._documents_request()
        request.pop("documents")
        response, _ = self._process(request)
        self.assertEqual(response["error_code"], "request_not_closed")
        self.assertEqual(response["detail"]["required_source"], "documents")

    def test_detail_given_is_bounded_for_oversized_input(self) -> None:
        huge_int = 10**40
        response, _ = self._process(self._documents_request(timeout_ms=huge_int))
        self.assertEqual(response["error_code"], "timeout_ms_over_cap")
        self.assertEqual(response["detail"]["given"], "int_out_of_range")
        long_action = "x" * 5000
        response, _ = self._process(self._documents_request(logical_action=long_action))
        self.assertLessEqual(len(response["detail"]["given"]), 64)

    def test_rejection_never_reaches_the_runtime(self) -> None:
        # result=None makes the invoke stub raise _Unreached if called.
        response, _ = self._process(self._documents_request(timeout_ms=900000), result=None)
        self.assertEqual(response["error_code"], "timeout_ms_over_cap")

    # -- in-place recovery + clean happy path ------------------------------
    def test_empty_target_agent_is_recovered_in_place(self) -> None:
        normalized: list = []
        native = self.coordinator.validate_request(
            self._documents_request(target_agent=""), self.wire, self.profile,
            normalized=normalized,
        )
        self.assertIsNone(native["target_agent"])
        self.assertEqual(normalized[0]["field"], "target_agent")

    def test_empty_target_recovery_recorded_on_success(self) -> None:
        result = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK, result={"artifact": "ok"}
        )
        response, code = self._process(
            self._documents_request(target_agent=""), result=result
        )
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["normalized"][0]["field"], "target_agent")

    def test_valid_request_success_has_no_diagnostic_noise(self) -> None:
        result = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK, result={"artifact": "ok"}
        )
        response, code = self._process(self._documents_request(), result=result)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "ok")
        for noisy in ("disposition", "recovery", "detail", "normalized", "error_code"):
            self.assertNotIn(noisy, response)


if __name__ == "__main__":
    unittest.main()
