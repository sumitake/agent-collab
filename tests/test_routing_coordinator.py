"""Routing-only public CLI contract."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
COORDINATOR = ROOT / "plugins" / "agent-collab" / "coordinator.py"


def load_coordinator():
    spec = importlib.util.spec_from_file_location("routing_only_cli", COORDINATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Result:
    status: str
    result: list[dict[str, object]]
    provenance: dict[str, object] | None = None
    error: str = ""


class RoutingOnlyCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator = load_coordinator()

    def test_cli_passes_request_through_once_and_preserves_records(self) -> None:
        request = {"request_id": "opaque-1", "work_units": [{"id": "one"}]}
        records = [{"frame_type": "content", "content": "ordinary prose"}]
        calls: list[object] = []

        def invoke(*, envelope):
            calls.append(envelope)
            return Result("ok", records, {"wire_contract_sha256": "a" * 64})

        written: list[object] = []
        fake = types.SimpleNamespace(invoke=invoke)
        with mock.patch.object(self.coordinator, "_read_request", return_value=request), \
                mock.patch.object(self.coordinator, "_load_client", return_value=fake), \
                mock.patch.object(self.coordinator, "_write", side_effect=written.append):
            code = self.coordinator.main()

        self.assertEqual(code, 0)
        self.assertEqual(calls, [request])
        self.assertEqual(written[0]["result"], records)
        self.assertNotIn("verdict", written[0])
        self.assertNotIn("execution_receipt", written[0])

    def test_duplicate_keys_and_non_object_roots_fail_before_runtime(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.coordinator._closed_object([("a", 1), ("a", 2)])

        written: list[object] = []
        with mock.patch.object(self.coordinator, "_read_request", return_value=[]), \
                mock.patch.object(self.coordinator, "_load_client") as load_client, \
                mock.patch.object(self.coordinator, "_write", side_effect=written.append):
            code = self.coordinator.main()
        self.assertEqual(code, 2)
        load_client.assert_not_called()
        self.assertEqual(written[0]["status"], "invalid_request")

    def _run_raw(self, raw: bytes, *, tty: bool = False):
        written: list[object] = []
        fake_stdin = types.SimpleNamespace(
            isatty=lambda: tty,
            buffer=io.BytesIO(raw),
        )
        with mock.patch.object(self.coordinator.sys, "stdin", fake_stdin), \
                mock.patch.object(self.coordinator, "_load_client") as load_client, \
                mock.patch.object(self.coordinator, "_write", side_effect=written.append):
            code = self.coordinator.main()
        return code, written, load_client

    def test_invalid_json_forms_fail_before_runtime(self) -> None:
        cases = {
            "empty": b"",
            "malformed": b'{"request_id":',
            "trailing": b'{} {}',
            "duplicate": b'{"a":1,"a":2}',
            "non-object": b'[]',
            "nan": b'{"value":NaN}',
            "infinity": b'{"value":Infinity}',
        }
        for name, raw in cases.items():
            with self.subTest(name=name):
                code, written, load_client = self._run_raw(raw)
                self.assertEqual(code, 2)
                load_client.assert_not_called()
                self.assertEqual(written[0]["status"], "invalid_request")
                self.assertEqual(written[0]["result"], [])

    def test_oversize_and_tty_input_fail_before_runtime(self) -> None:
        with mock.patch.object(self.coordinator, "MAX_INPUT_BYTES", 8):
            code, written, load_client = self._run_raw(b"123456789")
        self.assertEqual(code, 2)
        load_client.assert_not_called()
        self.assertIn("bound", written[0]["error"])

        code, written, load_client = self._run_raw(b"{}", tty=True)
        self.assertEqual(code, 2)
        load_client.assert_not_called()
        self.assertIn("tty", written[0]["error"])

    def test_client_exception_does_not_claim_provider_unavailability(self) -> None:
        secret = "provider-internal-secret"
        fake = types.SimpleNamespace(
            invoke=mock.Mock(side_effect=RuntimeError(secret))
        )
        written: list[object] = []
        with mock.patch.object(self.coordinator, "_read_request", return_value={}), \
                mock.patch.object(self.coordinator, "_load_client", return_value=fake), \
                mock.patch.object(self.coordinator, "_write", side_effect=written.append):
            code = self.coordinator.main()
        self.assertEqual(code, 1)
        self.assertEqual(written, [{
            "status": "client_error",
            "result": [],
            "error": "routing client failed; provider execution and state are unknown",
        }])
        self.assertNotIn(secret, str(written))
        self.assertNotIn("execution_receipt", written[0])
        self.assertNotIn("verdict", written[0])

    def test_internal_value_error_is_not_mislabeled_as_bad_caller_input(self) -> None:
        written = []
        with (
            mock.patch.object(self.coordinator, "_read_request", return_value={}),
            mock.patch.object(self.coordinator, "_load_client", side_effect=ValueError("private detail")),
            mock.patch.object(self.coordinator, "_write", side_effect=written.append),
        ):
            code = self.coordinator.main()
        self.assertEqual(code, 1)
        self.assertEqual(written[0]["status"], "client_error")
        self.assertNotIn("private detail", str(written))

    def test_stdin_read_error_is_sanitized_before_runtime_invocation(self) -> None:
        written = []
        with (
            mock.patch.object(self.coordinator, "_read_request", side_effect=OSError("private input error")),
            mock.patch.object(self.coordinator, "_load_client") as load_client,
            mock.patch.object(self.coordinator, "_write", side_effect=written.append),
        ):
            code = self.coordinator.main()
        self.assertEqual(code, 1)
        load_client.assert_not_called()
        self.assertEqual(written[0]["status"], "client_error")
        self.assertNotIn("private input error", str(written))

    def test_documented_invocation_preserves_payload_and_reads_current_identity(self) -> None:
        readme = (COORDINATOR.parent / "README.md").read_text()
        recipe = readme.split("```python\n", 1)[1].split("\n```", 1)[0]
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            plugin = root / "plugin with spaces"
            repository = root / "repository with spaces"
            plugin.mkdir()
            repository.mkdir()
            digest = "a" * 64
            (plugin / "runtime-manifest.json").write_text(json.dumps({"wire_contract_sha256": digest}))
            (plugin / "coordinator.py").write_text(
                "import json, sys\nprint(json.dumps(json.load(sys.stdin)))\n"
            )
            prompt = "Keep `literal` $(text) and Unicode 雪\nNext line."
            prompt_file = root / "prompt.txt"
            prompt_file.write_text(prompt)
            caller = root / "caller.py"
            caller.write_text(recipe)
            result = subprocess.run(
                [sys.executable, str(caller), str(plugin), str(repository), str(prompt_file)],
                capture_output=True, check=True, timeout=10,
            )
            request = json.loads(result.stdout)
            identity = repository.stat()
            unit = request["work_units"][0]
            self.assertEqual(request["wire_contract_sha256"], digest)
            self.assertEqual(unit["payload"], prompt)
            self.assertEqual(unit["native_restrictions"], {
                "cwd": str(repository.resolve()), "cwd_device": identity.st_dev,
                "cwd_inode": identity.st_ino,
            })
            self.assertNotIn("explicit_target", unit)

    def test_no_retired_semantic_or_provider_surface_exists(self) -> None:
        for name in (
            "validate_request",
            "process",
            "_load_host_policy",
            "_disposition",
            "readiness",
        ):
            self.assertFalse(hasattr(self.coordinator, name), name)


if __name__ == "__main__":
    unittest.main()
