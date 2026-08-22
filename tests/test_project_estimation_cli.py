"""CLI safety checks for the public estimator."""

from __future__ import annotations

import json
import importlib.util
import errno
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "agent-collab" / "project_estimation.py"
FIXTURES = ROOT / "tests" / "fixtures" / "project_estimation"


def _load():
    spec = importlib.util.spec_from_file_location("project_estimation_cli_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class EstimatorCliTests(unittest.TestCase):
    def _command(self, request: Path, *, out: Path | None = None) -> list[str]:
        command = [sys.executable, str(SCRIPT), "estimate", "--request", str(request),
                   "--prior", str(FIXTURES / "prior-small.json"),
                   "--pricing", str(FIXTURES / "pricing-small.json"),
                   "--quota", str(FIXTURES / "quota-small.json")]
        if out is not None:
            command += ["--out", str(out)]
        return command

    def test_estimate_writes_canonical_json_to_stdout(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "estimate", "--request", str(FIXTURES / "request-enhancement.json"), "--prior", str(FIXTURES / "prior-small.json"), "--pricing", str(FIXTURES / "pricing-small.json"), "--quota", str(FIXTURES / "quota-small.json")], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("\n"))

    def test_out_requires_consent_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as raw:
            # macOS exposes TemporaryDirectory through /var, an intermediate
            # symlink.  The CLI intentionally rejects that alias, so exercise
            # successful persistence through the canonical real parent.
            output = Path(raw).resolve() / "result.json"
            result = subprocess.run([sys.executable, str(SCRIPT), "estimate", "--request", str(FIXTURES / "request-enhancement.json"), "--prior", str(FIXTURES / "prior-small.json"), "--pricing", str(FIXTURES / "pricing-small.json"), "--quota", str(FIXTURES / "quota-small.json"), "--out", str(output)], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            second = subprocess.run([sys.executable, str(SCRIPT), "estimate", "--request", str(FIXTURES / "request-enhancement.json"), "--prior", str(FIXTURES / "prior-small.json"), "--pricing", str(FIXTURES / "pricing-small.json"), "--quota", str(FIXTURES / "quota-small.json"), "--out", str(output)], capture_output=True, text=True, check=False)
            self.assertNotEqual(second.returncode, 0)

    def test_stdin_is_bounded_and_only_one_dash_is_allowed(self):
        payload = (FIXTURES / "request-enhancement.json").read_text(encoding="utf-8")
        command = [sys.executable, str(SCRIPT), "estimate", "--request", "-",
                   "--prior", str(FIXTURES / "prior-small.json"),
                   "--pricing", str(FIXTURES / "pricing-small.json"),
                   "--quota", str(FIXTURES / "quota-small.json")]
        result = subprocess.run(command, input=payload, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        duplicate = command.copy()
        duplicate[duplicate.index(str(FIXTURES / "prior-small.json"))] = "-"
        result = subprocess.run(duplicate, input=payload, capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)

    def test_duplicate_json_and_fifo_are_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            result = subprocess.run(self._command(duplicate), capture_output=True, text=True, timeout=5, check=False)
            self.assertNotEqual(result.returncode, 0)
            fifo = root / "input.fifo"
            os.mkfifo(fifo)
            result = subprocess.run(self._command(fifo), capture_output=True, text=True, timeout=5, check=False)
            self.assertNotEqual(result.returncode, 0)

    def test_intermediate_input_and_output_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            real = root / "real"
            real.mkdir()
            request = real / "request.json"
            request.write_bytes((FIXTURES / "request-enhancement.json").read_bytes())
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            result = subprocess.run(self._command(alias / "request.json"), capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            result = subprocess.run(self._command(request, out=alias / "result.json"), capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((real / "result.json").exists())

    def test_parent_traversal_growing_input_and_failed_output_are_cleaned_up(self):
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            request = root / "request.json"
            request.write_bytes((FIXTURES / "request-enhancement.json").read_bytes())
            with self.assertRaisesRegex(module.EstimationError, "may not contain"):
                module._read_json(str(root / "child" / ".." / "request.json"))

            fd = os.open(request, os.O_RDONLY)
            real_read = os.read
            calls = 0

            def growing_read(target: int, size: int) -> bytes:
                nonlocal calls
                calls += 1
                if calls == 2:
                    with request.open("ab") as stream:
                        stream.write(b"x")
                return real_read(target, size)

            try:
                with mock.patch.object(module.os, "read", side_effect=growing_read):
                    with self.assertRaisesRegex(module.EstimationError, "grew"):
                        module._read_bounded_fd(fd, "input")
            finally:
                os.close(fd)

            output = root / "result.json"
            with mock.patch.object(module.os, "fsync", side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    module._write_exclusive(str(output), b"{}\n")
            self.assertFalse(output.exists())

    def test_reconcile_output_requires_actual_consent(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            estimate = subprocess.run(self._command(FIXTURES / "request-enhancement.json"), capture_output=True, text=True, check=True)
            prior_result = root / "result.json"
            prior_result.write_text(estimate.stdout, encoding="utf-8")
            actual = root / "actual.json"
            actual.write_text(json.dumps({
                "schema_version": 1, "completion_boundary": "merged",
                "focused_agent_wall_clock_seconds": 1, "calendar_elapsed_seconds": 1,
                "summed_agent_runtime_seconds": 1, "token_usage": [],
                "wait_decomposition": {"operator_seconds": 0, "vendor_seconds": 0, "quota_seconds": 0},
                "actual_marginal_cash": {"status": "unknown"}, "persistence_consent": False,
            }), encoding="utf-8")
            output = root / "reconciled.json"
            result = subprocess.run([sys.executable, str(SCRIPT), "reconcile", "--prior-result", str(prior_result),
                                     "--actual", str(actual), "--pricing", str(FIXTURES / "pricing-small.json"),
                                     "--out", str(output)], capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

    def test_output_readback_is_bound_to_created_name_and_cleanup_is_guarded(self):
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            output = root / "result.json"
            displaced = root / "created-inode.json"
            real_fsync = os.fsync
            substituted = False

            def substitute_after_file_sync(fd: int) -> None:
                nonlocal substituted
                real_fsync(fd)
                if not substituted:
                    substituted = True
                    os.replace(output, displaced)
                    output.write_bytes(b"substituted\n")

            with mock.patch.object(module.os, "fsync", side_effect=substitute_after_file_sync):
                with self.assertRaises(module.EstimationError):
                    module._write_exclusive(str(output), b"created\n")
            self.assertEqual(output.read_bytes(), b"substituted\n")
            self.assertEqual(displaced.read_bytes(), b"created\n")

    def test_directory_fsync_tolerates_only_documented_unsupported_errors(self):
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            output = root / "portable.json"
            real_fsync = os.fsync
            calls = 0

            def unsupported_directory(fd: int) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError(errno.EINVAL, "directory fsync unsupported")
                real_fsync(fd)

            with mock.patch.object(module.os, "fsync", side_effect=unsupported_directory):
                module._write_exclusive(str(output), b"portable\n")
            self.assertEqual(calls, 2)
            self.assertEqual(output.read_bytes(), b"portable\n")

            failing = root / "failure.json"
            calls = 0

            def failing_directory(fd: int) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError(errno.EIO, "directory fsync failed")
                real_fsync(fd)

            with mock.patch.object(module.os, "fsync", side_effect=failing_directory):
                with self.assertRaises(OSError):
                    module._write_exclusive(str(failing), b"failure\n")
            self.assertFalse(failing.exists())

    def test_output_readback_mismatch_removes_only_created_file(self):
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw).resolve() / "mismatch.json"
            with mock.patch.object(module, "_read_bounded_fd", return_value=b"wrong\n"):
                with self.assertRaisesRegex(module.EstimationError, "readback"):
                    module._write_exclusive(str(output), b"expected\n")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
