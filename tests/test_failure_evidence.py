"""Closed, private host-local failure-evidence capture contract."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "plugins" / "agent-collab" / "failure_evidence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("plugin_failure_evidence", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FailureEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.capture = _load_module()

    def _response(self) -> dict[str, object]:
        return {
            "request_id": "private-request-name",
            "status": "temporarily_unavailable",
            "error_code": "protocol_capability_drift",
            "manifest_digest": "a" * 64,
            "provenance": {
                "wire_contract_sha256": "b" * 64,
                "diagnostics": {
                    "logical_agent": "grok",
                    "provider_surface": "native_cli",
                    "model_lineage": "xai",
                    "observed_model": "must-not-cross",
                    "implementation_fingerprint": "c" * 64,
                    "executable_content_sha256": "d" * 64,
                    "adapter_wire_sha256": "e" * 64,
                    "catalog_digest": None,
                    "model_resolution_method": "provider_default",
                    "effective_effort": "maximum",
                    "metadata_process_count": 1,
                    "provider_processes": 1,
                    "provider_model_calls": None,
                    "provider_turns": 2,
                    "failure_trace": {
                        "failure_phase": "prompt",
                        "adapter_code": "missing_terminal",
                        "terminal_state": "failed",
                        "tool_outcomes": {
                            "success": 0,
                            "failed": 1,
                            "incomplete": 0,
                            "unknown": 0,
                        },
                        "outside_source_observed": False,
                        "containment_detail": "/secret/repository/path",
                        "failed_operation_counts": {
                            "repository_read": 1,
                            "repository_search": 0,
                            "repository_list": 0,
                            "other_tool": 0,
                            "unclassified": 0,
                        },
                        "native_envelope_sha256": "f" * 64,
                        "cleanup_confirmed": True,
                    },
                    "provider_prose": "secret provider output",
                },
            },
            "result": {"patch": "secret patch"},
            "detail": {"reason": "secret request value"},
        }

    def test_terminal_failure_writes_allowlist_only_private_event(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"AGENT_COLLAB_FAILURE_EVIDENCE_ROOT": td}
        ):
            path = self.capture.capture_terminal_failure(
                surface="plugin_coordinator",
                response=self._response(),
                request_trusted=True,
                request={
                    "logical_action": "codegen.repository",
                    "target_agent": "grok",
                    "quality_profile": "frontier",
                    "effort_class": "maximum",
                    "prompt": "private prompt",
                    "repo_root": "/secret/repository/path",
                },
            )

            self.assertIsNotNone(path)
            event = json.loads(Path(path).read_text(encoding="utf-8"))
            rendered = json.dumps(event, sort_keys=True)
            for forbidden in (
                "private-request-name",
                "private prompt",
                "/secret/repository/path",
                "secret provider output",
                "secret patch",
                "must-not-cross",
                "containment_detail",
                "provider_prose",
            ):
                self.assertNotIn(forbidden, rendered)
            self.assertEqual(event["schema"], "agent-collab.failure-evidence/v1")
            self.assertEqual(event["surface"], "plugin_coordinator")
            self.assertEqual(event["status"], "temporarily_unavailable")
            self.assertEqual(event["error_code"], "protocol_capability_drift")
            self.assertEqual(event["invocation"]["logical_action"], "codegen.repository")
            self.assertEqual(event["diagnostics"]["logical_agent"], "grok")
            self.assertEqual(
                event["diagnostics"]["failure_trace"]["adapter_code"],
                "missing_terminal",
            )
            self.assertRegex(event["request_id_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(event["fingerprint"], r"^[0-9a-f]{64}$")
            self.assertEqual(stat.S_IMODE(Path(path).stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE((Path(td) / "pending").stat().st_mode), 0o700)

    def test_untrusted_invocation_values_are_omitted_even_when_code_shaped(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"AGENT_COLLAB_FAILURE_EVIDENCE_ROOT": td}
        ):
            path = self.capture.capture_terminal_failure(
                surface="plugin_coordinator",
                response={
                    "request_id": "private-request-name",
                    "status": "invalid_request",
                    "error_code": "unsupported_logical_action",
                },
                request={
                    "logical_action": "secret.token-shaped-value",
                    "target_agent": "secret-agent-shaped-value",
                },
            )

            event = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertNotIn("invocation", event)
            self.assertNotIn("secret", json.dumps(event, sort_keys=True))

    def test_unclosed_identity_diagnostics_are_omitted(self) -> None:
        for key in ("logical_agent", "provider_surface", "model_lineage"):
            with self.subTest(key=key):
                event = self.capture.build_event(
                    surface="plugin_coordinator",
                    response={
                        "status": "provider_error",
                        "error_code": "missing_terminal",
                        "diagnostics": {key: "sk-live-secret"},
                    },
                    event_id="e" * 32,
                    occurred_at="2026-08-25T12:00:00Z",
                )
                self.assertNotIn(key, event.get("diagnostics", {}))
                self.assertNotIn("sk-live-secret", json.dumps(event, sort_keys=True))

    def test_plugin_identity_and_closed_request_shape_are_captured(self) -> None:
        response = {
            "status": "invalid_request",
            "error_code": "request_not_closed",
            "detail": {
                "field": "request_keys",
                "missing": ["repo_root"],
                "unexpected": ["documents", "secret-field-name"],
                "required_source": "repo_root",
                "expected_source_mode": "repository",
            },
        }
        with mock.patch.object(
            self.capture,
            "_plugin_identity",
            return_value=("6.3.0", "a" * 64),
        ):
            event = self.capture.build_event(
                surface="plugin_coordinator",
                response=response,
                request_shape={
                    "request_id": "private-id",
                    "logical_action": "review.repository",
                    "quality_profile": "frontier",
                    "effort_class": "maximum",
                    "target_agent": None,
                    "timeout_ms": 5000,
                    "prompt": "private prompt",
                    "documents": [],
                    "secret-field-name": "must-not-cross",
                },
                event_id="c" * 32,
                occurred_at="2026-08-25T12:00:00Z",
            )

        self.assertEqual(event["plugin_version"], "6.3.0")
        self.assertEqual(event["manifest_digest"], "a" * 64)
        self.assertEqual(
            event["request_shape"]["present_fields"],
            [
                "documents",
                "effort_class",
                "logical_action",
                "prompt",
                "quality_profile",
                "request_id",
                "target_agent",
                "timeout_ms",
            ],
        )
        self.assertEqual(event["request_shape"]["unknown_field_count"], 1)
        self.assertEqual(
            event["request_shape"]["difference"]["missing_fields"],
            ["repo_root"],
        )
        self.assertEqual(
            event["request_shape"]["difference"]["unexpected_fields"],
            ["documents"],
        )
        rendered = json.dumps(event, sort_keys=True)
        self.assertNotIn("secret-field-name", rendered)
        self.assertNotIn("must-not-cross", rendered)
        self.assertNotIn("private prompt", rendered)

    def test_installed_public_identity_is_read_from_packaged_metadata(self) -> None:
        event = self.capture.build_event(
            surface="plugin_coordinator",
            response={
                "status": "unavailable",
                "error_code": "runtime_descriptor_unavailable",
            },
            request_shape={},
            event_id="d" * 32,
            occurred_at="2026-08-25T12:00:00Z",
        )

        manifest = (MODULE_PATH.parent / "runtime-manifest.json").read_bytes()
        self.assertEqual(event["plugin_version"], "6.3.0")
        self.assertEqual(
            event["manifest_digest"], hashlib.sha256(manifest).hexdigest()
        )

    def test_unencodable_request_id_does_not_suppress_failure_event(self) -> None:
        event = self.capture.build_event(
            surface="plugin_coordinator",
            response={
                "request_id": "\ud800",
                "status": "invalid_request",
                "error_code": "request_id_invalid",
            },
            event_id="b" * 32,
            occurred_at="2026-08-25T12:00:00Z",
        )

        self.assertEqual(event["error_code"], "request_id_invalid")
        self.assertNotIn("request_id_sha256", event)

    def test_success_and_advisory_do_not_create_events(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"AGENT_COLLAB_FAILURE_EVIDENCE_ROOT": td}
        ):
            for status in ("ok", "advisory"):
                with self.subTest(status=status):
                    self.assertIsNone(
                        self.capture.capture_terminal_failure(
                            surface="plugin_coordinator",
                            response={"request_id": "x", "status": status},
                        )
                    )
            self.assertFalse((Path(td) / "pending").exists())

    def test_fingerprint_ignores_event_and_request_identity(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"AGENT_COLLAB_FAILURE_EVIDENCE_ROOT": td}
        ):
            first = self._response()
            second = self._response()
            second["request_id"] = "another-private-request"
            paths = [
                self.capture.capture_terminal_failure(
                    surface="plugin_coordinator", response=response
                )
                for response in (first, second)
            ]
            events = [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths]
            self.assertNotEqual(events[0]["event_id"], events[1]["event_id"])
            self.assertNotEqual(events[0]["request_id_sha256"], events[1]["request_id_sha256"])
            self.assertEqual(events[0]["fingerprint"], events[1]["fingerprint"])

    def test_symlink_outbox_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "target"
            target.mkdir()
            link = Path(td) / "outbox"
            link.symlink_to(target, target_is_directory=True)
            with mock.patch.dict(
                os.environ, {"AGENT_COLLAB_FAILURE_EVIDENCE_ROOT": str(link)}
            ):
                with self.assertRaises(OSError):
                    self.capture.capture_terminal_failure(
                        surface="plugin_coordinator", response=self._response()
                    )

    def test_existing_nonprivate_root_is_rejected_without_chmod(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "shared"
            root.mkdir(mode=0o755)
            root.chmod(0o755)
            with mock.patch.dict(
                os.environ, {"AGENT_COLLAB_FAILURE_EVIDENCE_ROOT": str(root)}
            ):
                with self.assertRaises(OSError):
                    self.capture.capture_terminal_failure(
                        surface="plugin_coordinator", response=self._response()
                    )
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o755)

    def test_local_event_store_has_a_hard_file_bound(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"AGENT_COLLAB_FAILURE_EVIDENCE_ROOT": td}
        ), mock.patch.object(self.capture, "_MAX_EVENT_FILES", 1):
            self.capture.capture_terminal_failure(
                surface="plugin_coordinator", response=self._response()
            )
            with self.assertRaises(OSError):
                self.capture.capture_terminal_failure(
                    surface="plugin_coordinator", response=self._response()
                )
            self.assertEqual(len(list((Path(td) / "pending").glob("*.json"))), 1)

    def test_capture_lock_waits_for_brief_contention(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"AGENT_COLLAB_FAILURE_EVIDENCE_ROOT": td}
        ), mock.patch.object(
            self.capture.fcntl,
            "flock",
            side_effect=[BlockingIOError(), None],
        ) as flock, mock.patch.object(self.capture.time, "sleep") as sleep:
            path = self.capture.capture_terminal_failure(
                surface="plugin_coordinator", response=self._response()
            )
            self.assertTrue(Path(path).is_file())
            self.assertEqual(flock.call_count, 2)
            sleep.assert_called_once()

    def test_first_capture_fsyncs_each_created_directory_entry(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "new-parent" / "failure-evidence"
            fsynced: list[Path] = []
            with mock.patch.dict(
                os.environ, {"AGENT_COLLAB_FAILURE_EVIDENCE_ROOT": str(root)}
            ), mock.patch.object(
                self.capture,
                "_fsync_directory",
                side_effect=lambda created: fsynced.append(created),
            ):
                path = self.capture.capture_terminal_failure(
                    surface="plugin_coordinator", response=self._response()
                )

            self.assertTrue(Path(path).is_file())
            self.assertIn(root.parent, fsynced)
            self.assertIn(root, fsynced)

    def test_accepted_history_does_not_consume_active_capture_cap(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ, {"AGENT_COLLAB_FAILURE_EVIDENCE_ROOT": td}
        ), mock.patch.object(self.capture, "_MAX_EVENT_FILES", 1):
            accepted = Path(td) / "accepted"
            accepted.mkdir(mode=0o700)
            historical = accepted / "historical.json"
            historical.write_text("{}", encoding="utf-8")
            historical.chmod(0o600)

            path = self.capture.capture_terminal_failure(
                surface="plugin_coordinator", response=self._response()
            )

            self.assertTrue(Path(path).is_file())


if __name__ == "__main__":
    unittest.main()
