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

    def _wire(self):
        wire, _digest, _note = self.coordinator._load_client().runtime_contract_snapshot()
        self.assertIsNotNone(wire)
        return wire

    @staticmethod
    def _repository(root: Path, name: str) -> Path:
        repository = root / name
        (repository / ".git").mkdir(parents=True)
        (repository / "src").mkdir()
        (repository / "src" / "module.py").write_text("x = 1\n")
        return repository.resolve()

    @staticmethod
    def _identity(path: Path) -> dict[str, object]:
        observed = path.stat()
        return {"cwd": str(path), "cwd_device": observed.st_dev, "cwd_inode": observed.st_ino}

    def test_loose_request_becomes_one_strictly_valid_envelope(self) -> None:
        wire = self._wire()
        client = self.coordinator._load_client()
        with tempfile.TemporaryDirectory() as raw:
            repository = self._repository(Path(raw), "repo")
            request = {
                "action": "review",
                "prompt": "Review the change.",
                "effort": "High",
                "quality": "pro",
                "timeout_ms": 10**12,
                "wire_contract_sha256": "0" * 64,
                "telemetry": True,
            }
            document, repairs = self.coordinator._normalize_request(
                request, wire, repository / "src"
            )
            client._envelope_document(document, wire)
            expected = self._identity(repository)
        unit = document["work_units"][0]
        self.assertEqual(document["wire_contract_sha256"], wire.sha256)
        self.assertEqual(document["effort_class"], "maximum")
        self.assertEqual(document["quality_profile"], "frontier")
        self.assertEqual(document["deadline_ms"], self.coordinator.MAX_DEADLINE_MS)
        self.assertIs(document["dispatch_requested"], True)
        self.assertEqual(document["max_parallel"], 1)
        self.assertEqual(unit["capability"], "review.repository")
        self.assertEqual(unit["payload"], "Review the change.")
        self.assertEqual(unit["depends_on"], [])
        self.assertEqual(unit["native_restrictions"], expected)
        self.assertNotIn("telemetry", unit)
        self.assertTrue(any("stale wire" in item for item in repairs))
        self.assertTrue(any("telemetry" in item for item in repairs))

    def test_correction_without_cwd_binds_the_repository_its_payload_names(self) -> None:
        wire = self._wire()
        with tempfile.TemporaryDirectory() as raw:
            caller = self._repository(Path(raw), "primary")
            review_copy = self._repository(Path(raw), "review-copy")
            request = {"work_units": [{
                "id": "corrected",
                "capability": "review.repository",
                "payload": f"Read {review_copy}/src/module.py and report findings.",
            }]}
            document, _repairs = self.coordinator._normalize_request(request, wire, caller)
            self.assertEqual(
                document["work_units"][0]["native_restrictions"],
                self._identity(review_copy),
            )

            request["work_units"][0]["payload"] = f"Compare {caller}/src and {review_copy}/src."
            document, _repairs = self.coordinator._normalize_request(request, wire, caller)
            self.assertEqual(
                document["work_units"][0]["native_restrictions"],
                self._identity(caller),
            )

    def test_supplied_binding_is_refreshed_and_codegen_is_never_bound(self) -> None:
        wire = self._wire()
        with tempfile.TemporaryDirectory() as raw:
            repository = self._repository(Path(raw), "repo")
            request = {"work_units": [
                {"id": "review", "capability": "review.repository", "payload": "p",
                 "native_restrictions": {"cwd": "repo", "cwd_device": 1, "cwd_inode": 2}},
                {"id": "patch", "capability": "codegen.repository", "payload": "p"},
                {"id": "missing", "capability": "architecture.repository", "payload": "p",
                 "cwd": str(Path(raw) / "absent")},
            ]}
            document, repairs = self.coordinator._normalize_request(request, wire, Path(raw))
            expected = self._identity(repository)
        review, patch, missing = document["work_units"]
        self.assertEqual(review["native_restrictions"], expected)
        self.assertNotIn("native_restrictions", patch)
        self.assertEqual(set(missing["native_restrictions"]), {"cwd"})
        self.assertTrue(any("not an existing directory" in item for item in repairs))
        self.assertEqual(document["max_parallel"], 3)

    def test_named_targets_and_actions_are_normalized_but_never_dropped(self) -> None:
        wire = self._wire()
        request = {"work_units": [
            {"capability": "context.documents.extract", "payload": "p", "target_agent": " Google "},
            {"capability": "context.documents.extract", "payload": "p", "target": "someone-else"},
            {"capability": "context", "payload": "p"},
        ]}
        document, _repairs = self.coordinator._normalize_request(request, wire, Path("/"))
        first, second, third = document["work_units"]
        self.assertEqual(first["explicit_target"], "gemini")
        self.assertEqual(second["explicit_target"], "someone-else")
        self.assertEqual(third["capability"], "context")
        self.assertEqual([unit["id"] for unit in document["work_units"]], ["unit-1", "unit-2", "unit-3"])

    def test_cli_reports_repairs_and_still_invokes_once(self) -> None:
        wire = self._wire()
        calls: list[object] = []

        def invoke(*, envelope):
            calls.append(envelope)
            return Result("ok", [], {"wire_contract_sha256": wire.sha256})

        fake = types.SimpleNamespace(
            invoke=invoke,
            runtime_contract_snapshot=lambda: (wire, "", ""),
        )
        written: list[object] = []
        raw = b"```json\n" + json.dumps({
            "capability": "context.documents.extract", "payload": "p",
        }).encode() + b"\n```\n"
        fake_stdin = types.SimpleNamespace(isatty=lambda: False, buffer=io.BytesIO(raw))
        with mock.patch.object(self.coordinator.sys, "stdin", fake_stdin), \
                mock.patch.object(self.coordinator, "_load_client", return_value=fake), \
                mock.patch.object(self.coordinator, "_write", side_effect=written.append):
            code = self.coordinator.main()
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["wire_contract_sha256"], wire.sha256)
        self.assertIn("repairs", written[0])

    def test_repair_failure_passes_the_original_request_through(self) -> None:
        request = {"work_units": [{"id": "one"}]}
        calls: list[object] = []
        fake = types.SimpleNamespace(
            invoke=lambda *, envelope: calls.append(envelope) or Result("ok", []),
            runtime_contract_snapshot=lambda: (object(), "", ""),
        )
        written: list[object] = []
        with mock.patch.object(self.coordinator, "_read_request", return_value=request), \
                mock.patch.object(self.coordinator, "_load_client", return_value=fake), \
                mock.patch.object(self.coordinator, "_write", side_effect=written.append):
            code = self.coordinator.main()
        self.assertEqual(code, 0)
        self.assertEqual(calls, [request])
        self.assertEqual(len(written[0]["repairs"]), 1)

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
