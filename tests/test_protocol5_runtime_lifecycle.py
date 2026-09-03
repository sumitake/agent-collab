"""Bounded protocol-5 process lifecycle regressions."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests.test_protocol5_public_contract import wire_descriptor


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "plugins" / "agent-collab" / "runtime_client.py"


def load_client():
    spec = importlib.util.spec_from_file_location("protocol5_lifecycle_client", CLIENT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ProtocolFiveLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = load_client()
        descriptor, digest = wire_descriptor()
        cls.wire = cls.client.validate_wire_descriptor(
            descriptor, expected_sha256=digest
        )

    def request(self, deadline_ms: int) -> dict[str, object]:
        return {
            "wire_contract_sha256": self.wire.sha256,
            "request_id": "lifecycle-1",
            "quality_profile": "standard",
            "effort_class": "standard",
            "deadline_ms": deadline_ms,
            "max_parallel": 1,
            "dispatch_requested": True,
            "work_units": [{
                "id": "one",
                "capability": "architecture.conceptual",
                "depends_on": [],
                "payload": {"prompt": "bounded"},
            }],
        }

    def content(self, text: str = "observed provider content") -> dict[str, object]:
        return {
            "frame_type": "content",
            "request_id": "lifecycle-1",
            "work_unit_id": "one",
            "sequence": 0,
            "content": text,
            "content_kind": "explicit final",
            "content_encoding": "utf-8",
            "content_truncated": False,
        }

    def resolution(self, executable: Path):
        return self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=executable,
            bundle_path=executable.parent,
            manifest_digest="a" * 64,
            artifact_digest="b" * 64,
            identity=self.client._identity(executable, executable=True),
            wire=self.wire,
        )

    def script(self, root: Path, body: str) -> Path:
        executable = root / "agent-collab-runtime"
        executable.write_text("#!/usr/bin/python3\n" + body, encoding="utf-8")
        executable.chmod(0o700)
        return executable

    def test_owned_runtime_directory_with_children_has_valid_identity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw) / "agent-collab-runtime.bundle"
            bundle.mkdir()
            (bundle / "nested").mkdir()
            self.assertGreater(bundle.lstat().st_nlink, 1)
            self.assertIsNotNone(self.client._identity(bundle, directory=True))

    def test_single_protocol_entrypoint_reads_stdin_and_returns_records(self) -> None:
        record = self.content()
        with tempfile.TemporaryDirectory() as raw:
            executable = self.script(
                Path(raw),
                "import json, sys\n"
                "assert sys.argv[1:] == ['invoke', '--protocol', '5']\n"
                "request = json.load(sys.stdin)\n"
                "assert request['request_id'] == 'lifecycle-1'\n"
                f"print({json.dumps(record)!r})\n",
            )
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=self.resolution(executable)
            ):
                result = self.client.invoke(envelope=self.request(5_000))
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result, [record])
        self.assertNotIn("execution_receipt", result.provenance or {})
        self.assertNotIn("verdict", result.provenance or {})

    def test_direct_invocation_preserves_caller_path(self) -> None:
        record = self.content("path preserved")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            current_bin = root / "current-provider-bin"
            stale_bin = root / "stale-system-bin"
            current_bin.mkdir()
            stale_bin.mkdir()
            observed_path = root / "observed-path"
            executable = self.script(
                root,
                "import os\n"
                "from pathlib import Path\n"
                f"Path({str(observed_path)!r}).write_text(os.environ['PATH'])\n"
                f"print({json.dumps(record)!r})\n",
            )
            caller_path = os.pathsep.join((str(current_bin), str(stale_bin)))
            with mock.patch.dict(os.environ, {"PATH": caller_path}, clear=True), \
                    mock.patch.object(
                        self.client,
                        "resolve_runtime",
                        return_value=self.resolution(executable),
                    ):
                result = self.client.invoke(envelope=self.request(5_000))
            self.assertEqual(observed_path.read_text(encoding="utf-8"), caller_path)
        self.assertEqual(result.result, [record])

    def test_missing_caller_path_uses_bounded_system_default(self) -> None:
        with tempfile.TemporaryDirectory() as raw, mock.patch.dict(
            os.environ, {}, clear=True
        ):
            environment = self.client._scrubbed_env(Path(raw))
        self.assertEqual(
            environment["PATH"],
            "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        )

    def test_zero_content_timeout_is_bounded_and_never_invalid_final(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            executable.write_text("#!/bin/sh\nexec /bin/sleep 30\n", encoding="utf-8")
            executable.chmod(0o700)
            started = time.monotonic()
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=self.resolution(executable)
            ):
                result = self.client.invoke(envelope=self.request(500))
            elapsed = time.monotonic() - started
        self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)
        self.assertEqual(result.result, [])
        self.assertLess(elapsed, 6.0)
        self.assertNotIn("invalid_final", result.error)

    def test_outer_deadline_reserves_cleanup_time(self) -> None:
        class Stream:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        class Process:
            pid = 4242

            def __init__(self) -> None:
                self.stdin = Stream()
                self.stdout = Stream()
                self.stderr = Stream()

        observed: dict[str, object] = {}

        def collect(_process, request: bytes, deadline: float):
            observed["request"] = json.loads(request)
            observed["remaining"] = deadline - time.monotonic()
            return b"", b"", "timeout"

        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=Path("/tmp/agent-collab-runtime"),
            bundle_path=Path("/tmp"),
            manifest_digest="a" * 64,
            artifact_digest="b" * 64,
            identity=self.client.FileIdentity(
                1, 1, 0o100700, 1, os.getuid(), 1, 1, 1
            ),
            wire=self.wire,
        )
        with mock.patch.object(
            self.client, "resolve_runtime", return_value=resolution
        ), mock.patch.object(
            self.client, "_identity", return_value=resolution.identity
        ), mock.patch.object(
            self.client.subprocess, "Popen", return_value=Process()
        ), mock.patch.object(
            self.client, "_collect_bounded", side_effect=collect
        ), mock.patch.object(
            self.client, "_terminate_and_reap", return_value=True
        ):
            result = self.client.invoke(envelope=self.request(5_000))
        reserve_ms = int(self.client.PROCESS_CLEANUP_RESERVE_SECONDS * 1000)
        inner_timeout = observed["request"]["deadline_ms"]
        self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)
        self.assertGreater(inner_timeout, 5_000 - reserve_ms - 100)
        self.assertLessEqual(inner_timeout, 5_000 - reserve_ms)
        self.assertAlmostEqual(
            inner_timeout / 1000, observed["remaining"], delta=0.02
        )

    def test_request_size_bound_prevents_launch(self) -> None:
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=Path("/tmp/agent-collab-runtime"),
            bundle_path=Path("/tmp"),
            manifest_digest="a" * 64,
            artifact_digest="b" * 64,
            identity=self.client.FileIdentity(
                1, 1, 0o100700, 1, os.getuid(), 1, 1, 1
            ),
            wire=self.wire,
        )
        request = self.request(5_000)
        request["work_units"][0]["payload"]["prompt"] = "x" * 256
        with mock.patch.object(
            self.client, "resolve_runtime", return_value=resolution
        ), mock.patch.object(
            self.client, "_identity", return_value=resolution.identity
        ), mock.patch.object(
            self.client, "MAX_REQUEST_BYTES", 64
        ), mock.patch.object(self.client.subprocess, "Popen") as popen:
            result = self.client.invoke(envelope=request)
        popen.assert_not_called()
        self.assertEqual(result.status, self.client.RuntimeStatus.INVALID_REQUEST)
        self.assertIn("input bound", result.error)

    def test_epipe_does_not_abort_post_exit_output_drain(self) -> None:
        event_write = self.client.selectors.EVENT_WRITE

        class Selector:
            def __init__(self) -> None:
                self.stdin_key = None
                self.returned = False

            def register(self, stream, _events, kind):
                if kind == "stdin":
                    self.stdin_key = type(
                        "SelectorKey", (), {"fileobj": stream, "data": kind}
                    )()

            def unregister(self, *_args):
                pass

            def select(self, _timeout):
                if not self.returned:
                    self.returned = True
                    return [(self.stdin_key, event_write)]
                return []

            def close(self):
                pass

        class ExitedProcess:
            def __init__(self, stdin, stdout, stderr) -> None:
                self.stdin, self.stdout, self.stderr = stdin, stdout, stderr

            def poll(self):
                return 0

        payload = (json.dumps(self.content()) + "\n").encode()
        with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, \
                tempfile.TemporaryFile() as stderr:
            stdout.write(payload)
            stdout.seek(0)
            process = ExitedProcess(stdin, stdout, stderr)
            with mock.patch.object(
                self.client.selectors, "DefaultSelector", Selector
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

    def test_output_limit_preserves_records_observed_before_diagnostic_tail(self) -> None:
        record = self.content("content before noisy tail")
        first = json.dumps(record, separators=(",", ":")) + "\n"
        with tempfile.TemporaryDirectory() as raw:
            executable = self.script(
                Path(raw),
                "import sys\n"
                f"sys.stdout.write({first!r})\n"
                "sys.stdout.write('x' * 128)\n",
            )
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=self.resolution(executable)
            ), mock.patch.object(
                self.client, "MAX_RESPONSE_BYTES", len(first.encode()) + 16
            ):
                result = self.client.invoke(envelope=self.request(5_000))
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result, [record])
        self.assertIn("output limit", result.error)
        self.assertNotIn("execution_receipt", result.provenance or {})

    def test_stderr_limit_is_bounded_and_reports_no_content(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            executable = self.script(
                Path(raw), "import sys\nsys.stderr.write('x' * 128)\n"
            )
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=self.resolution(executable)
            ), mock.patch.object(self.client, "MAX_STDERR_BYTES", 32):
                result = self.client.invoke(envelope=self.request(5_000))
        self.assertEqual(result.status, self.client.RuntimeStatus.OUTPUT_LIMIT)
        self.assertEqual(result.result, [])
        self.assertIn("output limit", result.error)

    def test_unproven_process_group_teardown_does_not_discard_content(self) -> None:
        record = self.content("content survives teardown diagnostic")
        with tempfile.TemporaryDirectory() as raw:
            executable = self.script(
                Path(raw), f"print({json.dumps(record)!r})\n"
            )
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=self.resolution(executable)
            ), mock.patch.object(
                self.client, "_terminate_and_reap", return_value=False
            ):
                result = self.client.invoke(envelope=self.request(5_000))
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result, [record])
        self.assertEqual(result.error, "process group teardown unproven")

    def test_private_temp_cleanup_failure_does_not_discard_content(self) -> None:
        record = self.content("content survives cleanup diagnostic")
        with tempfile.TemporaryDirectory() as raw:
            executable = self.script(
                Path(raw), f"print({json.dumps(record)!r})\n"
            )
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=self.resolution(executable)
            ), mock.patch.object(
                self.client.shutil, "rmtree", side_effect=OSError("cleanup failed")
            ):
                result = self.client.invoke(envelope=self.request(5_000))
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result, [record])
        self.assertIn("cleanup unproven", result.error)
        self.assertNotIn("execution_receipt", result.provenance or {})

    def test_leader_kill_fallback_does_not_prove_group_teardown(self) -> None:
        class UnprovenProcess:
            pid = 424242

            def poll(self):
                return None

            def wait(self, timeout):
                return 0

            def kill(self):
                pass

        with mock.patch.object(
            self.client.os, "killpg", side_effect=PermissionError("unproven")
        ):
            reaped = self.client._terminate_and_reap(
                UnprovenProcess(), deadline=time.monotonic() + 1
            )
        self.assertFalse(reaped)

    def test_exited_leader_descendant_is_killed_and_private_tree_removed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            pid_record = root / "descendant.pid"
            tmp_record = root / "request-tmp.txt"
            heartbeat = root / "descendant.heartbeat"
            executable = root / "agent-collab-runtime"
            executable.write_text(
                "#!/bin/sh\n"
                "mkdir -p \"$TMPDIR/private/nested\"\n"
                "printf secret > \"$TMPDIR/private/nested/document.txt\"\n"
                f"printf %s \"$TMPDIR\" > {str(tmp_record)!r}\n"
                "(trap '' TERM; exec >/dev/null 2>/dev/null; "
                f"while :; do printf x >> {str(heartbeat)!r}; sleep 0.02; done) &\n"
                f"printf %s $! > {str(pid_record)!r}\n"
                "attempt=0\n"
                f"while [ ! -s {str(heartbeat)!r} ]; do\n"
                "  attempt=$((attempt + 1))\n"
                "  [ \"$attempt\" -lt 20 ] || exit 11\n"
                "  sleep 0.01\n"
                "done\n"
                "exit 0\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            child_pid = 0
            try:
                with mock.patch.object(
                    self.client,
                    "resolve_runtime",
                    return_value=self.resolution(executable),
                ):
                    result = self.client.invoke(envelope=self.request(2_000))
                child_pid = int(pid_record.read_text(encoding="utf-8"))
                private_tmp = Path(tmp_record.read_text(encoding="utf-8"))
                before = heartbeat.stat().st_size
                time.sleep(0.2)
                self.assertEqual(heartbeat.stat().st_size, before)
                self.assertFalse(private_tmp.exists())
                self.assertIn(
                    result.status,
                    {
                        self.client.RuntimeStatus.PROTOCOL_ERROR,
                        self.client.RuntimeStatus.TIMEOUT,
                    },
                )
                self.assertEqual(result.result, [])
            finally:
                if child_pid:
                    try:
                        os.kill(child_pid, 9)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()
