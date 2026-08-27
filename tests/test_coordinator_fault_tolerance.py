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

import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
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

    def _v7_descriptor(
        self,
        *,
        review_targets: list[str] | None = None,
        review_floor: str = "maximum",
    ) -> dict:
        descriptor, _digest = _wire_descriptor()
        descriptor = copy.deepcopy(descriptor)
        descriptor["schema_version"] = 7
        agents = [
            "alibaba", "codex", "deepseek", "gemini", "grok", "moonshot", "zhipu"
        ]
        descriptor["logical_agents"] = agents
        descriptor["model_lineages"] = [
            "alibaba", "deepseek", "google", "moonshot", "openai", "xai", "zhipu"
        ]
        descriptor["logical_action_targets"] = {
            action: (
                review_targets or ["gemini", "grok"]
                if action == "review.repository"
                else agents
            )
            for action in descriptor["logical_actions"]
        }
        descriptor["logical_action_effort_floors"] = {
            action: (review_floor if action == "review.repository" else "minimal")
            for action in descriptor["logical_actions"]
        }
        semantic = descriptor["semantic_request"]
        semantic["properties"]["occupied_model_lineages"] = {
            "type": "array",
            "items": {"type": "string", "enum": descriptor["model_lineages"]},
            "maxItems": 16,
            "uniqueItems": True,
        }
        semantic["properties"]["evidence_anchors"] = {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "path"],
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": "^[A-Za-z0-9._:-]{1,128}$",
                    },
                    "path": {
                        "type": "string",
                        "pattern": "^[^\\u0000-\\u001f\\u007f]+$",
                        "x-maxUtf8Bytes": 4096,
                    },
                },
            },
            "maxItems": 16,
            "uniqueItems": True,
        }
        for field in ("occupied_model_lineages", "evidence_anchors"):
            if field not in semantic["required"]:
                semantic["required"].append(field)
        return descriptor

    def _v6_descriptor(self) -> dict:
        descriptor, _digest = _wire_descriptor()
        descriptor = copy.deepcopy(descriptor)
        descriptor["schema_version"] = 6
        for field in (
            "logical_agents",
            "model_lineages",
            "logical_action_targets",
            "logical_action_effort_floors",
        ):
            descriptor.pop(field, None)
        semantic = descriptor["semantic_request"]
        for field in ("occupied_model_lineages", "evidence_anchors"):
            semantic["properties"].pop(field, None)
        semantic["required"] = [
            field
            for field in semantic["required"]
            if field not in {"occupied_model_lineages", "evidence_anchors"}
        ]
        return descriptor

    def _v6_wire(self):
        descriptor = self._v6_descriptor()
        digest = hashlib.sha256(
            json.dumps(
                descriptor, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        return self.client.validate_wire_descriptor(
            descriptor, expected_sha256=digest
        )

    def _v7_wire(
        self,
        *,
        review_targets: list[str] | None = None,
        review_floor: str = "maximum",
    ):
        descriptor = self._v7_descriptor(
            review_targets=review_targets, review_floor=review_floor
        )
        digest = hashlib.sha256(
            json.dumps(
                descriptor, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        return self.client.validate_wire_descriptor(
            descriptor, expected_sha256=digest
        )

    def _process(self, request, *, result=None, wire=None):
        """Run ``process`` with a stubbed runtime; reject-path never invokes it."""

        active_wire = wire or self.wire

        def _invoke(**_kwargs):
            if result is None:
                raise _Unreached("invoke reached for a request that should be rejected")
            return result

        fake_client = types.SimpleNamespace(
            RuntimeStatus=self.client.RuntimeStatus,
            runtime_contract_snapshot=lambda: (active_wire, "a" * 64, ""),
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

    def test_provider_started_timeout_at_cap_is_terminal_not_retryable(self) -> None:
        disposition, recovery = self.coordinator._disposition(
            "timeout",
            timeout_ms=self.coordinator.MAX_TIMEOUT_MS,
            error_code="timeout",
            failure_trace={
                "adapter_code": "provider_timeout",
                "failure_phase": "inference",
                "tool_outcomes": {
                    "success": 0,
                    "failed": 0,
                    "incomplete": 0,
                    "unknown": 1,
                },
            },
        )
        self.assertEqual(disposition, "inspect")
        self.assertIn("terminal", recovery.lower())
        self.assertIn("separately authorized", recovery.lower())
        self.assertNotIn("increase", recovery.lower())

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

    def test_detail_never_reflects_c1_or_nonascii_input(self) -> None:
        # A hostile key mixing a C1 control (U+009B CSI) and other Unicode must
        # not survive into the echoed diagnostic.
        hostile = "review .\U0001f4a3repo"
        response, _ = self._process(self._documents_request(logical_action=hostile))
        self.assertEqual(response["error_code"], "unknown_logical_action")
        given = response["detail"]["given"]
        self.assertTrue(all(0x20 <= ord(ch) < 0x7F for ch in given))

    def test_generic_validation_fallback_is_inspect_not_fix_request(self) -> None:
        # A malformed 'documents' payload raises a plain ValueError deep in
        # validation; it must NOT be asserted as 'fix_request' (it could be
        # environmental), only surfaced for inspection.
        response, code = self._process(self._documents_request(documents=123))
        self.assertEqual(code, 2)
        self.assertEqual(response["status"], "invalid_request")
        self.assertEqual(response["disposition"], "inspect")
        self.assertIn("reason", response["detail"])

    def test_unexpected_key_list_is_bounded(self) -> None:
        request = self._documents_request()
        request.update({f"extra{i}": 1 for i in range(40)})
        response, _ = self._process(request)
        self.assertEqual(response["error_code"], "request_not_closed")
        unexpected = response["detail"]["unexpected"]
        self.assertLessEqual(len(unexpected), 17)  # 16 items + one overflow marker
        self.assertTrue(unexpected[-1].startswith("...(+"))

    def test_rejection_never_reaches_the_runtime(self) -> None:
        # result=None makes the invoke stub raise _Unreached if called.
        response, _ = self._process(self._documents_request(timeout_ms=900000), result=None)
        self.assertEqual(response["error_code"], "timeout_ms_over_cap")

    def test_ambiguous_compatibility_requests_start_no_provider(self) -> None:
        conflicting_route = self._documents_request(route="grok")
        product_alias = self._documents_request(route="glm")
        product_alias.pop("target_agent")
        source_conflict = self._documents_request(
            source={
                "mode": "documents",
                "documents": [{"label": "different", "content": "two"}],
            }
        )
        missing_action = self._documents_request()
        missing_action.pop("logical_action")
        missing_effort = self._documents_request()
        missing_effort.pop("effort_class")
        cases = {
            "conflicting_route": (conflicting_route, "conflicting_fields"),
            "product_alias": (product_alias, "target_agent_invalid"),
            "source_conflict": (source_conflict, "conflicting_fields"),
            "missing_action": (missing_action, "missing_common_fields"),
            "missing_effort": (missing_effort, "missing_common_fields"),
        }
        for name, (request, expected) in cases.items():
            with self.subTest(name=name):
                response, code = self._process(request, result=None)
                self.assertEqual(code, 2)
                self.assertEqual(response["error_code"], expected)

    def test_one_edit_operation_is_recovered_in_place(self) -> None:
        result = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK, result={"artifact": "ok"}
        )
        response, code = self._process(
            self._documents_request(operation="invok"), result=result
        )
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "ok")
        self.assertIn(
            {
                "field": "operation",
                "from": "invok",
                "to": None,
                "reason": "unique_one_edit_closed_value",
            },
            response["normalized"],
        )

    def test_one_edit_closed_invocation_tokens_recover_without_touching_prose(self) -> None:
        request = self._documents_request(
            operation="invok",
            action="context.documents.extarct",
            quality_profile="standrad",
            effort_class="minimla",
            route="gmeini",
            prompt="Extrcat facts exactly as written.",
            source={
                "mode": "docuemnts",
                "documents": [{"label": "a", "content": "one"}],
            },
        )
        request.pop("logical_action")
        request.pop("target_agent")
        request.pop("documents")
        normalized: list = []
        native = self.coordinator.validate_request(
            request, self.wire, self.profile, normalized=normalized
        )

        self.assertEqual(native["logical_action"], "context.documents.extract")
        self.assertEqual(native["quality_profile"], "standard")
        self.assertEqual(native["effort_class"], "minimal")
        self.assertEqual(native["target_agent"], "gemini")
        self.assertEqual(native["prompt"], "Extrcat facts exactly as written.")
        corrected_fields = {
            item["field"]
            for item in normalized
            if item["reason"] == "unique_one_edit_closed_value"
        }
        self.assertEqual(
            corrected_fields,
            {
                "operation",
                "logical_action",
                "quality_profile",
                "effort_class",
                "target_agent",
                "source.mode",
            },
        )
        self.assertNotIn("prompt", {item["field"] for item in normalized})

    def test_ambiguous_one_edit_token_is_rejected_before_provider_start(self) -> None:
        wire = replace(
            self.wire,
            logical_actions=frozenset({"review.a", "review.b"}),
            logical_action_source_modes={
                "review.a": "documents",
                "review.b": "documents",
            },
        )
        response, code = self._process(
            self._documents_request(logical_action="review.x"),
            result=None,
            wire=wire,
        )
        self.assertEqual(code, 2)
        self.assertEqual(response["error_code"], "unknown_logical_action")
        self.assertEqual(response["detail"]["given"], "review.x")

    # -- in-place recovery + clean happy path ------------------------------
    def test_empty_target_agent_is_recovered_in_place(self) -> None:
        normalized: list = []
        native = self.coordinator.validate_request(
            self._documents_request(target_agent=""), self.wire, self.profile,
            normalized=normalized,
        )
        self.assertIsNone(native["target_agent"])
        self.assertEqual(normalized[0]["field"], "target_agent")

    def test_missing_target_agent_is_recovered_only_as_untargeted(self) -> None:
        request = self._documents_request()
        request.pop("target_agent")
        normalized: list = []
        native = self.coordinator.validate_request(
            request, self.wire, self.profile, normalized=normalized
        )
        self.assertIsNone(native["target_agent"])
        self.assertEqual(normalized[0]["reason"], "missing_target_is_untargeted")

    def test_v6_runtime_rejects_nonempty_future_context_before_invoke(self) -> None:
        wire = self._v6_wire()
        request = self._documents_request(
            occupied_model_lineages=["google"]
        )
        response, code = self._process(request, wire=wire)
        self.assertEqual(code, 2)
        self.assertEqual(response["error_code"], "runtime_feature_unavailable")
        self.assertEqual(response["detail"]["field"], "occupied_model_lineages")

        request = self._documents_request(
            evidence_anchors=[{"id": "check", "path": "tests/check.py"}]
        )
        response, code = self._process(request, wire=wire)
        self.assertEqual(code, 2)
        self.assertEqual(response["error_code"], "runtime_feature_unavailable")
        self.assertEqual(response["detail"]["field"], "evidence_anchors")

    def test_v6_runtime_never_receives_empty_future_context(self) -> None:
        wire = self._v6_wire()
        request = self._documents_request(
            occupied_model_lineages=[], evidence_anchors=[]
        )
        native = self.coordinator.validate_request(
            request, wire, self.profile
        )
        self.assertNotIn("occupied_model_lineages", native)
        self.assertNotIn("evidence_anchors", native)

    def test_v7_descriptor_drives_target_and_effort_criteria(self) -> None:
        wire = self._v7_wire()
        request = {
            "request_id": "review-v7",
            "logical_action": "review.repository",
            "quality_profile": "frontier",
            "effort_class": "standard",
            "target_agent": "gemini",
            "timeout_ms": 5000,
            "prompt": "Review.",
            "repo_root": str(ROOT),
        }
        with self.assertRaises(self.coordinator._InvalidRequest) as caught:
            self.coordinator.validate_request(request, wire, self.profile)
        self.assertEqual(caught.exception.error_code, "effort_below_floor")
        self.assertEqual(caught.exception.detail["required"], "maximum")

        request["effort_class"] = "maximum"
        request["target_agent"] = "zhipu"
        with self.assertRaises(self.coordinator._InvalidRequest) as caught:
            self.coordinator.validate_request(request, wire, self.profile)
        self.assertEqual(caught.exception.error_code, "unsupported_target_action")
        self.assertEqual(caught.exception.detail["admitted"], ["gemini", "grok"])

        request["target_agent"] = "gemini"
        native = self.coordinator.validate_request(request, wire, self.profile)
        self.assertEqual(native["target_agent"], "gemini")
        self.assertEqual(native["effort_class"], "maximum")
        self.assertEqual(native["occupied_model_lineages"], [])
        self.assertEqual(native["evidence_anchors"], [])
        self.assertEqual(self.client._envelope_document(native, wire), native)

    def test_v7_context_is_forwarded_only_when_descriptor_admits_it(self) -> None:
        wire = self._v7_wire(
            review_targets=[
                "alibaba", "codex", "deepseek", "gemini", "grok", "moonshot", "zhipu"
            ]
        )
        request = {
            "request_id": "review-context-v7",
            "logical_action": "review.repository",
            "quality_profile": "frontier",
            "effort_class": "maximum",
            "target_agent": None,
            "timeout_ms": 5000,
            "prompt": "Review the disclosed blocker.",
            "repo_root": str(ROOT),
            "occupied_model_lineages": [" GOOGLE "],
            "evidence_anchors": [
                {"id": "tests", "path": "tests/test_agent_collab_coordinator.py"}
            ],
        }
        normalized: list = []
        native = self.coordinator.validate_request(
            request, wire, self.profile, normalized=normalized
        )
        self.assertEqual(native["occupied_model_lineages"], ["google"])
        self.assertEqual(
            native["evidence_anchors"],
            [{"id": "tests", "path": "tests/test_agent_collab_coordinator.py"}],
        )
        self.assertEqual(
            normalized[0]["field"], "occupied_model_lineages[0]"
        )

    def test_v7_context_rejects_ambiguous_or_unsafe_values(self) -> None:
        wire = self._v7_wire()
        cases = {
            "unknown_lineage": {"occupied_model_lineages": ["unknown"]},
            "duplicate_lineage": {"occupied_model_lineages": ["google", "google"]},
            "absolute_anchor": {
                "evidence_anchors": [{"id": "a", "path": "/tests/a.py"}]
            },
            "traversal_anchor": {
                "evidence_anchors": [{"id": "a", "path": "tests/../a.py"}]
            },
            "duplicate_anchor": {
                "evidence_anchors": [
                    {"id": "a", "path": "tests/a.py"},
                    {"id": "a", "path": "tests/b.py"},
                ]
            },
            "open_anchor": {
                "evidence_anchors": [
                    {"id": "a", "path": "tests/a.py", "extra": "x"}
                ]
            },
            "newline_anchor": {
                "evidence_anchors": [{"id": "a", "path": "tests/a.py\nlog"}]
            },
            "nul_anchor": {
                "evidence_anchors": [{"id": "a", "path": "tests/a.py\x00log"}]
            },
            "tab_anchor": {
                "evidence_anchors": [{"id": "a", "path": "tests/a.py\tlog"}]
            },
            "del_anchor": {
                "evidence_anchors": [{"id": "a", "path": "tests/a.py\x7flog"}]
            },
        }
        for name, fields in cases.items():
            request = {
                "request_id": f"invalid-{name}",
                "logical_action": "review.repository",
                "quality_profile": "frontier",
                "effort_class": "maximum",
                "target_agent": "gemini",
                "timeout_ms": 5000,
                "prompt": "Review.",
                "repo_root": str(ROOT),
                **fields,
            }
            with self.subTest(name=name), self.assertRaises(
                self.coordinator._InvalidRequest
            ):
                self.coordinator.validate_request(request, wire, self.profile)

    def test_v7_descriptor_rejects_incompatible_schema_and_floor_types(self) -> None:
        descriptor = self._v7_descriptor()
        descriptor["semantic_request"]["properties"].pop("evidence_anchors")
        descriptor["semantic_request"]["required"].remove("evidence_anchors")
        digest = hashlib.sha256(
            json.dumps(
                descriptor, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "inconsistent with v7"):
            self.client.validate_wire_descriptor(
                descriptor, expected_sha256=digest
            )

        descriptor = self._v7_descriptor()
        descriptor["logical_action_effort_floors"]["review.repository"] = []
        digest = hashlib.sha256(
            json.dumps(
                descriptor, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "recovery projections"):
            self.client.validate_wire_descriptor(
                descriptor, expected_sha256=digest
            )

    def test_v7_descriptor_bounds_recovery_projection_cardinality(self) -> None:
        descriptor = self._v7_descriptor()
        descriptor["logical_agents"] = ["gemini", "grok"] + [
            f"agent{i}" for i in range(63)
        ]
        digest = hashlib.sha256(
            json.dumps(
                descriptor, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "logical agents are invalid"):
            self.client.validate_wire_descriptor(
                descriptor, expected_sha256=digest
            )

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
