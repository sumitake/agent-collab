"""Protocol-5 routing-only public client regressions."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "plugins" / "agent-collab" / "runtime_client.py"


def _load():
    spec = importlib.util.spec_from_file_location("routing_runtime_client", CLIENT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _descriptor() -> tuple[dict[str, object], str]:
    descriptor = {
        "schema_version": 12,
        "runtime_protocol_version": 5,
        "routing_source_sha256": "a" * 64,
        "logical_actions": [f"action-{index}" for index in range(12)],
        "logical_action_timeout_modes": {
            f"action-{index}": (
                "admitted_progress_inactivity" if index == 0 else "total_deadline"
            ) for index in range(12)
        },
        "logical_agents": ["claude", "codex", "gemini", "grok", "opencode"],
        "routing_request": {"type": "object"},
        "content_frame": {"type": "object"},
        "terminal_planning_record": {"type": "object"},
        "$defs": {},
    }
    encoded = json.dumps(
        descriptor,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return descriptor, hashlib.sha256(encoded).hexdigest()


class RoutingRuntimeClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = _load()

    def test_progressing_runtime_outlives_initial_deadline_without_replay(self) -> None:
        result, calls = self._timed_runtime(progress=True)
        self.assertEqual(calls, 1)
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result, [{"content": "finished"}])
        self.assertEqual(result.error, "")

    def test_silent_runtime_expires_once(self) -> None:
        result, calls = self._timed_runtime(progress=False)
        self.assertEqual(calls, 1)
        self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)
        self.assertEqual(result.result, [])

    def test_total_deadline_does_not_inherit_progress_channel(self) -> None:
        result, calls = self._timed_runtime(progress=True, action="action-1")
        self.assertEqual(calls, 1)
        self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)

    def test_local_io_failure_preserves_already_received_content(self) -> None:
        native_read = os.read
        received_content = False
        content_fd = None

        def fail_after_content(fd, size):
            nonlocal received_content, content_fd
            if fd == content_fd:
                raise OSError("synthetic local I/O failure")
            value = native_read(fd, size)
            if b'"content"' in value:
                received_content = True
                content_fd = fd
            return value

        with mock.patch.object(self.client.os, "read", side_effect=fail_after_content):
            result, calls = self._timed_runtime(progress=True, early_content=True)
        self.assertEqual(calls, 1)
        self.assertTrue(received_content)
        self.assertEqual(result.result, [{"content": "partial"}])
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertIn("runtime io error", result.error)

    def _timed_runtime(self, *, progress: bool, action: str = "action-0", early_content: bool = False):
        descriptor, digest = _descriptor()
        wire = self.client.validate_wire_descriptor(descriptor, expected_sha256=digest)
        request = {
            "wire_contract_sha256": digest, "request_id": "progress-fixture",
            "quality_profile": "standard", "effort_class": "standard",
            "deadline_ms": 2_000, "max_parallel": 1, "dispatch_requested": True,
            "work_units": [{"id": "one", "capability": action,
                            "depends_on": [], "payload": "work"}],
        }
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "runtime"
            executable.write_text(
                f"#!{sys.executable}\nimport json, os, sys, time\n"
                "request = json.load(sys.stdin)\n"
                "fd = os.environ.get('AGENT_COLLAB_RUNTIME_PROGRESS_FD')\n"
                + ("print(json.dumps({'content': 'partial'}), flush=True)\n" if early_content else "")
                + "for _ in range(30):\n"
                + ("    if fd: os.write(int(fd), b'\\x01')\n" if progress else "")
                + "    time.sleep(0.1)\n"
                "print(json.dumps({'content': 'finished'}), flush=True)\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK, path=executable, bundle_path=Path(raw),
                identity=self.client._identity(executable, executable=True), wire=wire,
            )
            with (
                mock.patch.object(self.client, "resolve_runtime", return_value=resolution),
                mock.patch.object(self.client.subprocess, "Popen", wraps=self.client.subprocess.Popen) as launch,
            ):
                result = self.client.invoke(envelope=request)
            return result, launch.call_count

    def test_null_deadline_uses_default_instead_of_crashing(self) -> None:
        descriptor, digest = _descriptor()
        wire = self.client.validate_wire_descriptor(descriptor, expected_sha256=digest)
        request = {
            "wire_contract_sha256": digest, "request_id": "null-deadline",
            "quality_profile": "standard", "effort_class": "standard",
            "deadline_ms": None, "max_parallel": 1, "dispatch_requested": False,
            "work_units": [{"id": "one", "capability": "action-1", "depends_on": []}],
        }
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "runtime"
            path.write_text('#!/bin/sh\necho \'{"frame_type":"terminal"}\'\n')
            path.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK, path=path, bundle_path=Path(raw),
                identity=self.client._identity(path, executable=True), wire=wire,
            )
            with mock.patch.object(self.client, "resolve_runtime", return_value=resolution):
                result = self.client.invoke(envelope=request)
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)

    def test_protocol5_client_returns_opaque_routing_records(self) -> None:
        descriptor, digest = _descriptor()
        wire = self.client.validate_wire_descriptor(
            descriptor, expected_sha256=digest
        )
        request = {
            "wire_contract_sha256": digest,
            "request_id": "routing-client-1",
            "quality_profile": "standard",
            "effort_class": "maximum",
            "deadline_ms": 15_000,
            "max_parallel": 1,
            "dispatch_requested": True,
            "work_units": [{
                "id": "unit-1",
                "capability": "action-0",
                "depends_on": [],
                "payload": {"prompt": "Return ordinary prose."},
            }],
        }
        records = [
            {
                "frame_type": "content",
                "request_id": "routing-client-1",
                "work_unit_id": "unit-1",
                "sequence": 0,
                "content": "ordinary prose, not provider-authored JSON",
                "content_kind": "explicit final",
                "content_encoding": "utf-8",
                "content_truncated": False,
            },
            {
                "frame_type": "terminal",
                "request_id": "routing-client-1",
                "decisions": [],
                "waves": [],
                "aggregate": {},
            },
        ]
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            payload = "".join(
                json.dumps(record, separators=(",", ":")) + "\n"
                for record in records
            )
            executable.write_text(
                "#!/usr/bin/python3\nimport sys\nsys.stdout.write(" + repr(payload) + ")\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=executable,
                bundle_path=Path(raw),
                manifest_digest="b" * 64,
                artifact_digest="c" * 64,
                identity=self.client._identity(executable, executable=True),
                wire=wire,
            )
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=resolution
            ):
                result = self.client.invoke(envelope=request)

        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result, records)
        self.assertNotIn("execution_receipt", result.provenance or {})
        self.assertNotIn("verdict", result.provenance or {})

    def test_protocol_or_digest_drift_is_rejected(self) -> None:
        descriptor, digest = _descriptor()
        with self.assertRaisesRegex(ValueError, "digest"):
            self.client.validate_wire_descriptor(
                descriptor, expected_sha256="0" * 64
            )
        descriptor["runtime_protocol_version"] = 4
        changed = hashlib.sha256(
            json.dumps(
                descriptor,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "protocol"):
            self.client.validate_wire_descriptor(
                descriptor, expected_sha256=changed
            )

    def test_zero_deadline_is_admitted_and_expires_before_launch(self) -> None:
        descriptor, digest = _descriptor()
        wire = self.client.validate_wire_descriptor(
            descriptor, expected_sha256=digest
        )
        request = {
            "wire_contract_sha256": digest,
            "request_id": "routing-client-expired",
            "quality_profile": "standard",
            "effort_class": "maximum",
            "deadline_ms": 0,
            "max_parallel": 1,
            "dispatch_requested": True,
            "work_units": [{
                "id": "unit-1",
                "capability": "action-0",
                "depends_on": [],
                "payload": {"prompt": "Do not launch."},
            }],
        }
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            executable.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            executable.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=executable,
                bundle_path=Path(raw),
                manifest_digest="b" * 64,
                artifact_digest="c" * 64,
                identity=self.client._identity(executable, executable=True),
                wire=wire,
            )
            with (
                mock.patch.object(
                    self.client, "resolve_runtime", return_value=resolution
                ),
                mock.patch.object(self.client.subprocess, "Popen") as launch,
            ):
                result = self.client.invoke(envelope=request)

        self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)
        self.assertIsNone(result.result)
        launch.assert_not_called()

    def test_noncanonical_later_records_do_not_discard_prior_content(self) -> None:
        content = {
            "frame_type": "content",
            "request_id": "routing-client-preserved",
            "work_unit_id": "unit-1",
            "sequence": 0,
            "content": "bounded provider content remains available",
            "content_kind": "recovered deltas",
            "content_encoding": "utf-8",
            "content_truncated": False,
        }
        raw = (
            json.dumps(content, separators=(",", ":")).encode("utf-8")
            + b'\n{"diagnostic":NaN}\n'
            + b'{"diagnostic":"\\ud800"}\n'
        )

        records, note = self.client._parse_routing_records(raw)

        self.assertEqual(records, [content])
        self.assertIn("malformed runtime output was excluded", note)

    def test_records_are_split_and_decoded_from_original_bytes(self) -> None:
        first = {
            "frame_type": "content",
            "content": "provider content before malformed bytes",
        }
        unicode_content = {
            "frame_type": "content",
            "content": "line separator stays inside content: \u2028",
        }
        raw = (
            json.dumps(first, separators=(",", ":")).encode("utf-8")
            + b"\n"
            + b'{"frame_type":"content","content":"ab\xffcd"}\n'
            + json.dumps(
                unicode_content,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            + b"\n"
        )

        records, note = self.client._parse_routing_records(raw)

        self.assertEqual(records, [first, unicode_content])
        self.assertIn("malformed runtime output was excluded", note)

    def test_valid_unterminated_final_record_is_retained(self) -> None:
        content = {
            "frame_type": "content",
            "content": "complete content before abrupt stream close",
        }

        records, note = self.client._parse_routing_records(
            json.dumps(content, separators=(",", ":")).encode("utf-8")
        )

        self.assertEqual(records, [content])
        self.assertEqual(note, "")

    def test_nonzero_exit_and_missing_terminal_do_not_discard_content(self) -> None:
        descriptor, digest = _descriptor()
        wire = self.client.validate_wire_descriptor(
            descriptor, expected_sha256=digest
        )
        request = {
            "wire_contract_sha256": digest,
            "request_id": "routing-client-partial",
            "quality_profile": "standard",
            "effort_class": "maximum",
            "deadline_ms": 15_000,
            "max_parallel": 1,
            "dispatch_requested": True,
            "work_units": [{
                "id": "unit-1",
                "capability": "action-0",
                "depends_on": [],
                "payload": {"prompt": "Return partial prose."},
            }],
        }
        content = {
            "frame_type": "content",
            "request_id": "routing-client-partial",
            "work_unit_id": "unit-1",
            "sequence": 0,
            "content": "bounded partial provider text",
            "content_kind": "recovered deltas",
            "content_encoding": "utf-8",
            "content_truncated": False,
            "optional_diagnostics": {"malformed": [object.__name__]},
        }
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            payload = json.dumps(content, separators=(",", ":")) + "\n"
            executable.write_text(
                "#!/usr/bin/python3\nimport sys\nsys.stdout.write("
                + repr(payload)
                + ")\nraise SystemExit(7)\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=executable,
                bundle_path=Path(raw),
                manifest_digest="b" * 64,
                artifact_digest="c" * 64,
                identity=self.client._identity(executable, executable=True),
                wire=wire,
            )
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=resolution
            ):
                result = self.client.invoke(envelope=request)

        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result, [content])
        self.assertIn("status 7", result.error)
        self.assertNotIn("execution_receipt", result.provenance or {})


if __name__ == "__main__":
    unittest.main()
