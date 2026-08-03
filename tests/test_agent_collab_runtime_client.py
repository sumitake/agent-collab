"""Direct process client tests."""

from __future__ import annotations

import importlib.util
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests.test_direct_runtime_public_contract import (
    _readiness_response,
    _wire_descriptor,
)


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "plugins" / "agent-collab" / "runtime_client.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class DirectRuntimeClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = _load("direct_process_client", CLIENT)
        descriptor, digest = _wire_descriptor()
        cls.wire = cls.client.validate_wire_descriptor(
            descriptor, expected_sha256=digest
        )

    def _envelope(self, timeout_ms: int) -> dict[str, object]:
        return {
            "wire_contract_sha256": self.wire.sha256,
            "request_id": "direct-1",
            "logical_action": "architecture.conceptual",
            "target_agent": None,
            "author_lineage": None,
            "timeout_ms": timeout_ms,
            "prompt": "Think.",
            "source": {"mode": "conceptual_prompt"},
        }

    def _readiness_envelope(self, timeout_ms: int) -> dict[str, object]:
        return {
            "operation": "readiness",
            "wire_contract_sha256": self.wire.sha256,
            "request_id": "runtime-status-1",
            "author_lineage": "openai",
            "timeout_ms": timeout_ms,
        }

    def test_owned_runtime_directory_with_children_has_a_valid_identity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw) / "agent-collab-runtime.bundle"
            bundle.mkdir()
            (bundle / "nested").mkdir()

            self.assertGreater(bundle.lstat().st_nlink, 1)
            self.assertIsNotNone(self.client._identity(bundle, directory=True))

    def test_outer_deadline_terminates_and_reaps_a_frozen_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            executable.write_text("#!/bin/sh\nexec /bin/sleep 30\n", encoding="utf-8")
            executable.chmod(0o700)
            identity = self.client._identity(executable, executable=True)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=executable,
                bundle_path=Path(raw),
                manifest_digest="a" * 64,
                artifact_digest="b" * 64,
                identity=identity,
                wire=self.wire,
            )
            started = time.monotonic()
            with mock.patch.object(self.client, "resolve_runtime", return_value=resolution):
                result = self.client.invoke(envelope=self._envelope(100))
            elapsed = time.monotonic() - started
        self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)
        self.assertLess(elapsed, 2.0)

    def test_direct_invocation_does_not_need_broker_socket_plist_or_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            executable.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
            executable.chmod(0o700)
            identity = self.client._identity(executable, executable=True)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=executable,
                bundle_path=Path(raw),
                manifest_digest="a" * 64,
                artifact_digest="b" * 64,
                identity=identity,
                wire=self.wire,
            )
            env = dict(os.environ)
            env.pop("AGENT_COLLAB_BROKER_ROOT", None)
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(
                self.client, "resolve_runtime", return_value=resolution
            ):
                result = self.client.invoke(envelope=self._envelope(1000))
        self.assertEqual(result.status, self.client.RuntimeStatus.PROVIDER_ERROR)

    def test_direct_invocation_uses_the_single_protocol_entrypoint(self) -> None:
        failure_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "wire_contract_sha256",
                "request_id",
                "status",
                "error_code",
                "diagnostics",
            ],
            "properties": {
                "wire_contract_sha256": {"type": "string"},
                "request_id": {"type": "string"},
                "status": {"const": "unavailable"},
                "error_code": {"type": "string"},
                "diagnostics": {"type": "object"},
            },
        }
        wire = replace(self.wire, failure_response=failure_schema)
        response = {
            "wire_contract_sha256": wire.sha256,
            "request_id": "direct-1",
            "status": "unavailable",
            "error_code": "not_ready",
            "diagnostics": {},
        }
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            payload = json.dumps(response, separators=(",", ":"))
            executable.write_text(
                "#!/usr/bin/python3\n"
                "import sys\n"
                "if sys.argv[1:] != ['invoke', '--protocol', '3']:\n"
                "    raise SystemExit(9)\n"
                "sys.stdin.buffer.read()\n"
                "sys.stdout.write(" + repr(payload) + ")\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=executable,
                bundle_path=Path(raw),
                manifest_digest="a" * 64,
                artifact_digest="b" * 64,
                identity=self.client._identity(executable, executable=True),
                wire=wire,
            )
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=resolution
            ):
                result = self.client.invoke(envelope=self._envelope(1000))
        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        self.assertEqual(result.error, "not_ready")

    def test_post_exit_stdout_tail_is_appended_before_response_validation(self) -> None:
        class NoEventsSelector:
            def register(self, *_args: object) -> None:
                pass

            def unregister(self, *_args: object) -> None:
                pass

            def select(self, timeout: float) -> list[object]:
                time.sleep(min(timeout, 0.01))
                return []

            def close(self) -> None:
                pass

        failure_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "wire_contract_sha256",
                "request_id",
                "status",
                "error_code",
                "diagnostics",
            ],
            "properties": {
                "wire_contract_sha256": {"type": "string"},
                "request_id": {"type": "string"},
                "status": {"const": "unavailable"},
                "error_code": {"type": "string"},
                "diagnostics": {"type": "object"},
            },
        }
        wire = replace(self.wire, failure_response=failure_schema)
        response = {
            "wire_contract_sha256": wire.sha256,
            "request_id": "direct-1",
            "status": "unavailable",
            "error_code": "not_ready",
            "diagnostics": {},
        }
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            payload = json.dumps(response, separators=(",", ":"))
            executable.write_text(
                "#!/usr/bin/python3\n"
                "import sys\n"
                "sys.stdout.write(" + repr(payload) + ")\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=executable,
                bundle_path=Path(raw),
                manifest_digest="a" * 64,
                artifact_digest="b" * 64,
                identity=self.client._identity(executable, executable=True),
                wire=wire,
            )
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=resolution
            ), mock.patch.object(
                self.client.selectors, "DefaultSelector", NoEventsSelector
            ):
                result = self.client.invoke(envelope=self._envelope(1000))
        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        self.assertEqual(result.error, "not_ready")

    def test_child_stdin_epipe_does_not_abort_post_exit_output_drain(self) -> None:
        event_write = self.client.selectors.EVENT_WRITE

        class StdinThenNoEventsSelector:
            def __init__(self) -> None:
                self.stdin_key: object | None = None
                self.returned_stdin = False

            def register(self, stream: object, _events: int, kind: str) -> None:
                if kind == "stdin":
                    self.stdin_key = type(
                        "SelectorKey", (), {"fileobj": stream, "data": kind}
                    )()

            def unregister(self, *_args: object) -> None:
                pass

            def select(self, _timeout: float) -> list[tuple[object, int]]:
                if not self.returned_stdin:
                    self.returned_stdin = True
                    assert self.stdin_key is not None
                    return [(self.stdin_key, event_write)]
                return []

            def close(self) -> None:
                pass

        class ExitedProcess:
            def __init__(self, stdin: object, stdout: object, stderr: object) -> None:
                self.stdin = stdin
                self.stdout = stdout
                self.stderr = stderr

            def poll(self) -> int:
                return 0

        payload = b'{"status":"unavailable"}'
        with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            stdout.write(payload)
            stdout.seek(0)
            process = ExitedProcess(stdin, stdout, stderr)
            with mock.patch.object(
                self.client.selectors,
                "DefaultSelector",
                StdinThenNoEventsSelector,
            ), mock.patch.object(
                self.client.os,
                "write",
                side_effect=BrokenPipeError("child closed stdin"),
            ):
                out, err, terminal = self.client._collect_bounded(
                    process, b"request", time.monotonic() + 1.0
                )
        self.assertEqual(out, payload)
        self.assertEqual(err, b"")
        self.assertEqual(terminal, "")

    def test_post_exit_stdout_tail_overflow_returns_output_limit(self) -> None:
        class NoEventsSelector:
            def register(self, *_args: object) -> None:
                pass

            def unregister(self, *_args: object) -> None:
                pass

            def select(self, _timeout: float) -> list[object]:
                return []

            def close(self) -> None:
                pass

        class ExitedProcess:
            def __init__(self, stdin: object, stdout: object, stderr: object) -> None:
                self.stdin = stdin
                self.stdout = stdout
                self.stderr = stderr

            def poll(self) -> int:
                return 0

        with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            stdout.write(b"x" * (self.client.MAX_RESPONSE_BYTES + 1))
            stdout.seek(0)
            process = ExitedProcess(stdin, stdout, stderr)
            with mock.patch.object(
                self.client.selectors, "DefaultSelector", NoEventsSelector
            ):
                _out, _err, terminal = self.client._collect_bounded(
                    process, b"", time.monotonic() + 1.0
                )
        self.assertEqual(terminal, "output_limit")

    def test_native_response_request_id_must_match_dispatched_request(self) -> None:
        failure_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "wire_contract_sha256",
                "request_id",
                "status",
                "error_code",
                "diagnostics",
            ],
            "properties": {
                "wire_contract_sha256": {"type": "string"},
                "request_id": {"type": "string"},
                "status": {"const": "unavailable"},
                "error_code": {"type": "string"},
                "diagnostics": {"type": "object"},
            },
        }
        wire = replace(self.wire, failure_response=failure_schema)
        response = {
            "wire_contract_sha256": wire.sha256,
            "request_id": "different-request",
            "status": "unavailable",
            "error_code": "not_ready",
            "diagnostics": {},
        }
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            payload = json.dumps(response, separators=(",", ":"))
            executable.write_text(
                "#!/usr/bin/python3\nimport sys\nsys.stdout.write(" + repr(payload) + ")\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=executable,
                bundle_path=Path(raw),
                manifest_digest="a" * 64,
                artifact_digest="b" * 64,
                identity=self.client._identity(executable, executable=True),
                wire=wire,
            )
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=resolution
            ):
                result = self.client.invoke(envelope=self._envelope(1000))
        self.assertEqual(result.status, self.client.RuntimeStatus.PROTOCOL_ERROR)

    def test_private_temp_cleanup_failure_is_teardown_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            executable.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
            executable.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=executable,
                bundle_path=Path(raw),
                manifest_digest="a" * 64,
                artifact_digest="b" * 64,
                identity=self.client._identity(executable, executable=True),
                wire=self.wire,
            )
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=resolution
            ), mock.patch.object(
                self.client.shutil, "rmtree", side_effect=OSError("cleanup failed")
            ):
                result = self.client.invoke(envelope=self._envelope(1000))
        self.assertEqual(result.status, self.client.RuntimeStatus.TEARDOWN_ERROR)
        self.assertEqual(result.error, "private temporary directory cleanup unproven")

    def test_leader_kill_fallback_does_not_prove_process_group_teardown(self) -> None:
        class UnprovenProcess:
            pid = 424242

            def poll(self) -> None:
                return None

            def wait(self, timeout: float) -> int:
                return 0

            def kill(self) -> None:
                pass

        with mock.patch.object(
            self.client.os, "killpg", side_effect=PermissionError("unproven")
        ):
            reaped = self.client._terminate_and_reap(UnprovenProcess())
        self.assertFalse(reaped)

    def test_readiness_uses_the_same_process_and_validates_all_actions(self) -> None:
        response = _readiness_response(self.wire.sha256)
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            payload = json.dumps(response, separators=(",", ":"))
            executable.write_text(
                "#!/usr/bin/python3\n"
                "import json, sys\n"
                "if sys.argv[1:] != ['invoke', '--protocol', '3']:\n"
                "    raise SystemExit(9)\n"
                "request = json.load(sys.stdin)\n"
                "if request.get('operation') != 'readiness':\n"
                "    raise SystemExit(8)\n"
                "sys.stdout.write(" + repr(payload) + ")\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=executable,
                bundle_path=Path(raw),
                manifest_digest="a" * 64,
                artifact_digest="b" * 64,
                identity=self.client._identity(executable, executable=True),
                wire=self.wire,
            )
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=resolution
            ):
                result = self.client.readiness(
                    envelope=self._readiness_envelope(1000)
                )
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(len(result.result["actions"]), 11)
        self.assertNotIn("execution_receipt", result.provenance)

    def test_valid_response_between_one_and_four_mib_is_accepted(self) -> None:
        success_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "wire_contract_sha256", "request_id", "status", "result",
                "execution_receipt", "diagnostics",
            ],
            "properties": {
                "wire_contract_sha256": {"type": "string"},
                "request_id": {"type": "string"},
                "status": {"const": "ok"},
                "result": {"type": "string", "minLength": 1},
                "execution_receipt": {"type": "object"},
                "diagnostics": {"type": "object"},
            },
        }
        wire = replace(self.wire, success_response=success_schema)
        response = {
            "wire_contract_sha256": wire.sha256,
            "request_id": "direct-1",
            "status": "ok",
            "result": "x" * (2 * 1024 * 1024),
            "execution_receipt": {},
            "diagnostics": {},
        }
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            payload = json.dumps(response, separators=(",", ":"))
            executable.write_text(
                "#!/usr/bin/python3\nimport sys\nsys.stdout.write(" + repr(payload) + ")\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=executable,
                bundle_path=Path(raw),
                manifest_digest="a" * 64,
                artifact_digest="b" * 64,
                identity=self.client._identity(executable, executable=True),
                wire=wire,
            )
            with mock.patch.object(self.client, "resolve_runtime", return_value=resolution):
                result = self.client.invoke(envelope=self._envelope(5000))
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(len(result.result), 2 * 1024 * 1024)

    def test_exited_leader_descendant_is_killed_and_private_tree_removed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            executable = root / "agent-collab-runtime"
            pid_record = root / "descendant.pid"
            tmp_record = root / "request-tmp.txt"
            heartbeat = root / "descendant.heartbeat"
            executable.write_text(
                "#!/bin/sh\n"
                "mkdir -p \"$TMPDIR/private/nested\"\n"
                "printf secret > \"$TMPDIR/private/nested/document.txt\"\n"
                f"printf %s \"$TMPDIR\" > {str(tmp_record)!r}\n"
                "(trap '' TERM; exec >/dev/null 2>/dev/null; "
                f"while :; do printf x >> {str(heartbeat)!r}; sleep 0.02; done) &\n"
                f"printf %s $! > {str(pid_record)!r}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=executable,
                bundle_path=root,
                manifest_digest="a" * 64,
                artifact_digest="b" * 64,
                identity=self.client._identity(executable, executable=True),
                wire=self.wire,
            )
            child_pid = 0
            try:
                with mock.patch.object(self.client, "resolve_runtime", return_value=resolution):
                    result = self.client.invoke(envelope=self._envelope(500))
                child_pid = int(pid_record.read_text(encoding="utf-8"))
                private_tmp = Path(tmp_record.read_text(encoding="utf-8"))
                before = heartbeat.stat().st_size if heartbeat.exists() else 0
                time.sleep(0.2)
                after = heartbeat.stat().st_size if heartbeat.exists() else 0
                self.assertEqual(after, before, "direct-runtime descendant survived teardown")
                self.assertFalse(private_tmp.exists())
                self.assertEqual(result.status, self.client.RuntimeStatus.TEARDOWN_ERROR)
            finally:
                if child_pid:
                    try:
                        os.kill(child_pid, 9)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()
