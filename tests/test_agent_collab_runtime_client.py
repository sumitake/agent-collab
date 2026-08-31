"""Direct process client tests."""

from __future__ import annotations

import importlib.util
from dataclasses import replace
import hashlib
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
        descriptor = dict(descriptor)
        descriptor["schema_version"] = 9
        descriptor["logical_action_timeout_modes"] = {
            action: (
                "admitted_progress_inactivity"
                if action in {
                    "codegen.repository",
                    "frontend_codegen.repository",
                    "review.repository",
                    "frontend_review.repository",
                    "governance.repository",
                }
                else "total_deadline"
            )
            for action in descriptor["logical_actions"]
        }
        cls.descriptor = descriptor
        digest = hashlib.sha256(
            json.dumps(
                descriptor,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        cls.wire = cls.client.validate_wire_descriptor(
            descriptor, expected_sha256=digest
        )

    def test_wire_v9_retains_repository_head_binding(self) -> None:
        descriptor = json.loads(json.dumps(self.descriptor))
        for variant in descriptor["semantic_request"]["properties"]["source"][
            "oneOf"
        ]:
            properties = variant.get("properties", {})
            if properties.get("mode") == {"const": "repository"}:
                properties.pop("expected_repo_head")
                variant["required"].remove("expected_repo_head")
                break
        digest = hashlib.sha256(
            json.dumps(
                descriptor,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

        with self.assertRaisesRegex(ValueError, "v9 repository source"):
            self.client.validate_wire_descriptor(
                descriptor, expected_sha256=digest
            )

    def test_rejects_future_wire_schema_without_a_paired_client(self) -> None:
        descriptor = json.loads(json.dumps(self.descriptor))
        descriptor["schema_version"] = 10
        digest = hashlib.sha256(
            json.dumps(
                descriptor,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

        with self.assertRaisesRegex(ValueError, "schema version"):
            self.client.validate_wire_descriptor(
                descriptor, expected_sha256=digest
            )

    def _envelope(self, timeout_ms: int) -> dict[str, object]:
        return {
            "wire_contract_sha256": self.wire.sha256,
            "request_id": "direct-1",
            "logical_action": "architecture.conceptual",
            "quality_profile": "standard",
            "effort_class": "standard",
            "target_agent": None,
            "author_lineage": None,
            "timeout_ms": timeout_ms,
            "prompt": "Think.",
            "source": {"mode": "conceptual_prompt"},
            "occupied_model_lineages": [],
            "evidence_anchors": [],
        }

    def _readiness_envelope(self, timeout_ms: int) -> dict[str, object]:
        return {
            "operation": "readiness",
            "wire_contract_sha256": self.wire.sha256,
            "request_id": "runtime-status-1",
            "author_lineage": "openai",
            "quality_profile": "standard",
            "effort_class": "standard",
            "timeout_ms": timeout_ms,
        }

    def _codegen_document(self, timeout_ms: int) -> dict[str, object]:
        return {
            "request_id": "codegen-1",
            "logical_action": "codegen.repository",
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

    def test_outer_deadline_reserves_inner_cleanup_time_for_nonidle_provider(self) -> None:
        class Stream:
            closed = False

            def close(self) -> None:
                self.closed = True

        class Process:
            pid = 4242
            stdin = Stream()
            stdout = Stream()
            stderr = Stream()

        process = Process()
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
            identity=self.client.FileIdentity(1, 1, 0o100700, 1, os.getuid(), 1, 1, 1),
            wire=self.wire,
        )
        with mock.patch.object(
            self.client, "resolve_runtime", return_value=resolution
        ), mock.patch.object(
            self.client, "_identity", return_value=resolution.identity
        ), mock.patch.object(
            self.client.subprocess, "Popen", return_value=process
        ), mock.patch.object(
            self.client, "_collect_bounded", side_effect=collect
        ), mock.patch.object(
            self.client, "_terminate_and_reap", return_value=True
        ):
            result = self.client.invoke(envelope=self._envelope(5_000))

        self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)
        inner_timeout = observed["request"]["timeout_ms"]
        reserve_ms = int(
            self.client.PROCESS_CLEANUP_RESERVE_SECONDS * 1000
        )
        self.assertGreater(inner_timeout, 5_000 - reserve_ms - 100)
        self.assertLessEqual(inner_timeout, 5_000 - reserve_ms)
        self.assertLess(inner_timeout / 1000, observed["remaining"])

    def test_elapsed_setup_time_is_removed_from_the_inner_runtime_budget(self) -> None:
        class Stream:
            closed = False

            def close(self) -> None:
                self.closed = True

        class Process:
            pid = 4242
            stdin = Stream()
            stdout = Stream()
            stderr = Stream()

        observed: dict[str, object] = {}

        def collect(_process, request: bytes, deadline: float):
            observed["request"] = json.loads(request)
            observed["collection_deadline"] = deadline
            return b"", b"", "timeout"

        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=Path("/tmp/agent-collab-runtime"),
            bundle_path=Path("/tmp"),
            manifest_digest="a" * 64,
            artifact_digest="b" * 64,
            identity=self.client.FileIdentity(1, 1, 0o100700, 1, os.getuid(), 1, 1, 1),
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
        ) as reap, mock.patch.object(
            self.client.time, "monotonic", side_effect=(100.0, 101.0, 102.0)
        ):
            result = self.client.invoke(envelope=self._envelope(5_000))

        self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)
        self.assertEqual(observed["request"]["timeout_ms"], 2_000)
        self.assertEqual(observed["collection_deadline"], 104.0)
        # Teardown proof runs on its own bounded budget, independent of the
        # request deadline (third mocked monotonic reading + the reap grace).
        reap.assert_called_once_with(
            mock.ANY,
            deadline=102.0 + self.client.TEARDOWN_REAP_SECONDS,
        )

    def test_codegen_progress_marks_renew_only_the_stall_lease(self) -> None:
        class Stream:
            def __init__(self, descriptor: int) -> None:
                self.descriptor = descriptor
                self.closed = False

            def fileno(self) -> int:
                return self.descriptor

            def close(self) -> None:
                self.closed = True

        class Process:
            stdin = Stream(10)
            stdout = Stream(11)
            stderr = Stream(12)

            def __init__(self) -> None:
                self.polls = 0

            def poll(self) -> int | None:
                self.polls += 1
                return None if self.polls == 1 else 0

        class Selector:
            latest: "Selector | None" = None

            def __init__(self) -> None:
                self.keys: dict[str, object] = {}
                self.timeouts: list[float] = []
                self.calls = 0
                type(self).latest = self

            def register(self, fileobj: object, _events: int, kind: str) -> None:
                self.keys[kind] = type(
                    "SelectorKey", (), {"fileobj": fileobj, "data": kind}
                )()

            def unregister(self, *_args: object) -> None:
                pass

            def select(self, timeout: float) -> list[tuple[object, int]]:
                self.timeouts.append(timeout)
                self.calls += 1
                if self.calls == 1:
                    return [(self.keys["progress"], 0)]
                return [
                    (self.keys["stdout"], 0),
                    (self.keys["stderr"], 0),
                ]

            def close(self) -> None:
                pass

        reads = {99: b"\x01", 11: b"", 12: b""}
        with mock.patch.object(
            self.client.selectors, "DefaultSelector", Selector
        ), mock.patch.object(
            self.client.os, "set_blocking"
        ), mock.patch.object(
            self.client.os, "read", side_effect=lambda descriptor, _size: reads[descriptor]
        ), mock.patch.object(
            self.client.time, "monotonic", side_effect=(9.95, 10.0, 10.1)
        ):
            _out, _err, terminal = self.client._collect_bounded(
                Process(), b"", 10.0, progress_reader=99, stall_interval=5.0
            )

        self.assertEqual(terminal, "")
        self.assertAlmostEqual(Selector.latest.timeouts[0], 0.05)
        self.assertEqual(Selector.latest.timeouts[1], 0.1)

        reads[99] = b"\x02"
        with mock.patch.object(
            self.client.selectors, "DefaultSelector", Selector
        ), mock.patch.object(
            self.client.os, "set_blocking"
        ), mock.patch.object(
            self.client.os, "read", side_effect=lambda descriptor, _size: reads[descriptor]
        ), mock.patch.object(
            self.client.time, "monotonic", return_value=9.95
        ):
            _out, _err, malformed = self.client._collect_bounded(
                Process(), b"", 10.0, progress_reader=99, stall_interval=5.0
            )

        self.assertEqual(malformed, "progress_pipe_lost")

    def test_codegen_progress_eof_does_not_renew_the_response_lease(self) -> None:
        class Stream:
            def __init__(self, descriptor: int) -> None:
                self.descriptor = descriptor
                self.closed = False

            def fileno(self) -> int:
                return self.descriptor

            def close(self) -> None:
                self.closed = True

        class Process:
            stdin = Stream(10)
            stdout = Stream(11)
            stderr = Stream(12)

            def poll(self) -> int | None:
                return 0

        class Selector:
            latest: "Selector | None" = None

            def __init__(self) -> None:
                self.keys: dict[str, object] = {}
                self.timeouts: list[float] = []
                self.calls = 0
                type(self).latest = self

            def register(self, fileobj: object, _events: int, kind: str) -> None:
                self.keys[kind] = type(
                    "SelectorKey", (), {"fileobj": fileobj, "data": kind}
                )()

            def unregister(self, fileobj: object) -> None:
                for kind, key in tuple(self.keys.items()):
                    if key.fileobj is fileobj or key.fileobj == fileobj:
                        del self.keys[kind]

            def select(self, timeout: float) -> list[tuple[object, int]]:
                self.timeouts.append(timeout)
                self.calls += 1
                if self.calls == 1:
                    return [(self.keys["progress"], 0)]
                return [
                    (key, 0)
                    for kind, key in self.keys.items()
                    if kind in {"stdout", "stderr"}
                ]

            def close(self) -> None:
                pass

        reads = {99: b"", 11: b"response\n", 12: b""}

        def read(descriptor: int, _size: int) -> bytes:
            value = reads[descriptor]
            if descriptor == 11:
                reads[descriptor] = b""
            return value

        with mock.patch.object(
            self.client.selectors, "DefaultSelector", Selector
        ), mock.patch.object(
            self.client.os, "set_blocking"
        ), mock.patch.object(
            self.client.os, "read", side_effect=read
        ), mock.patch.object(
            self.client.time,
            "monotonic",
            # A clean EOF may precede the runtime's already-formed stdout
            # response, but it is not an admitted progress mark.  If EOF
            # reset the lease to five seconds, the 6.05 observation would
            # time out before the response could be collected.
            side_effect=(1.0, 1.0, 6.05),
        ):
            out, _err, terminal = self.client._collect_bounded(
                Process(), b"", 10.0, progress_reader=99, stall_interval=5.0
            )

        self.assertEqual(terminal, "")
        self.assertEqual(out, b"response\n")
        self.assertEqual(Selector.latest.timeouts[0], 0.1)
        self.assertEqual(Selector.latest.timeouts[1], 0.1)

    def test_codegen_launch_passes_private_progress_writer_and_lost_pipe_reaps(self) -> None:
        class Stream:
            closed = False

            def close(self) -> None:
                self.closed = True

        class Process:
            pid = 4242
            stdin = Stream()
            stdout = Stream()
            stderr = Stream()

        process = Process()
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=Path("/tmp/agent-collab-runtime"),
            bundle_path=Path("/tmp"),
            manifest_digest="a" * 64,
            artifact_digest="b" * 64,
            identity=self.client.FileIdentity(1, 1, 0o100700, 1, os.getuid(), 1, 1, 1),
            wire=self.wire,
        )
        collected: dict[str, object] = {}
        collections = 0

        def collect(_process, request: bytes, _deadline: float, **kwargs: object):
            nonlocal collections
            collections += 1
            if collections == 2:
                with self.assertRaises(OSError):
                    os.fstat(collected["progress_reader"])
                self.assertEqual(request, b"")
                self.assertEqual(kwargs, {})
                return b"", b"", ""
            collected["request"] = json.loads(request)
            collected.update(kwargs)
            reader = kwargs["progress_reader"]
            assert type(reader) is int
            return b"", b"", "progress_pipe_lost"

        with mock.patch.object(
            self.client, "resolve_runtime", return_value=resolution
        ), mock.patch.object(
            self.client, "_envelope_document", return_value=self._codegen_document(5000)
        ), mock.patch.object(
            self.client, "_identity", return_value=resolution.identity
        ), mock.patch.object(
            self.client.subprocess, "Popen", return_value=process
        ) as popen, mock.patch.object(
            self.client, "_collect_bounded", side_effect=collect
        ), mock.patch.object(
            self.client, "_terminate_and_reap", return_value=True
        ) as reap:
            result = self.client.invoke(envelope={})

        self.assertEqual(result.status, self.client.RuntimeStatus.CANCELLED)
        self.assertEqual(collected["request"]["timeout_ms"], 5000)
        self.assertEqual(collected["stall_interval"], 5.0)
        self.assertIn("pass_fds", popen.call_args.kwargs)
        writer = popen.call_args.kwargs["pass_fds"][0]
        self.assertEqual(
            popen.call_args.kwargs["env"][self.client._PROGRESS_FD_ENV],
            str(writer),
        )
        with self.assertRaises(OSError):
            os.fstat(writer)
        with self.assertRaises(OSError):
            os.fstat(collected["progress_reader"])
        self.assertEqual(collections, 2)
        reap.assert_called_once()

    def test_repository_progress_pipe_follows_signed_timeout_mode(self) -> None:
        """Repository actions use the descriptor, including non-codegen names."""

        class Stream:
            closed = False

            def close(self) -> None:
                self.closed = True

        class Process:
            pid = 4242
            stdin = Stream()
            stdout = Stream()
            stderr = Stream()

        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=Path("/tmp/agent-collab-runtime"),
            bundle_path=Path("/tmp"),
            manifest_digest="a" * 64,
            artifact_digest="b" * 64,
            identity=self.client.FileIdentity(1, 1, 0o100700, 1, os.getuid(), 1, 1, 1),
            wire=self.wire,
        )

        for action, expects_pipe in (
            ("review.repository", True),
            ("governance.repository", True),
            ("architecture.repository", False),
        ):
            process = Process()
            documents = {
                "request_id": f"{action}-1",
                "logical_action": action,
                "timeout_ms": 5_000,
            }
            calls = 0

            def collect(_process, _request, _deadline, **kwargs):
                nonlocal calls
                calls += 1
                if expects_pipe:
                    self.assertIn("progress_reader", kwargs)
                    self.assertIn("stall_interval", kwargs)
                    return (b"", b"", "timeout" if calls == 1 else "")
                self.assertEqual(kwargs, {})
                return b"", b"", "timeout"

            with mock.patch.object(
                self.client, "resolve_runtime", return_value=resolution
            ), mock.patch.object(
                self.client, "_envelope_document", return_value=documents
            ), mock.patch.object(
                self.client, "_identity", return_value=resolution.identity
            ), mock.patch.object(
                self.client.subprocess, "Popen", return_value=process
            ) as popen, mock.patch.object(
                self.client, "_collect_bounded", side_effect=collect
            ), mock.patch.object(
                self.client, "_terminate_and_reap", return_value=True
            ):
                result = self.client.invoke(envelope={})

            self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)
            self.assertEqual("pass_fds" in popen.call_args.kwargs, expects_pipe)
            if expects_pipe:
                writer = popen.call_args.kwargs["pass_fds"][0]
                self.assertEqual(
                    popen.call_args.kwargs["env"][self.client._PROGRESS_FD_ENV],
                    str(writer),
                )
            self.assertEqual(calls, 2 if expects_pipe else 1)

    def test_codegen_lease_expiry_allows_bounded_runtime_cleanup_before_reap(self) -> None:
        class Stream:
            closed = False

            def close(self) -> None:
                self.closed = True

        class Process:
            pid = 4242
            stdin = Stream()
            stdout = Stream()
            stderr = Stream()

        process = Process()
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
        collected: list[tuple[bytes, float, dict[str, object]]] = []

        def collect(
            _process, request: bytes, deadline: float, **kwargs: object
        ) -> tuple[bytes, bytes, str]:
            collected.append((request, deadline, kwargs))
            return (b"", b"", "timeout") if len(collected) == 1 else (b"", b"", "")

        with mock.patch.object(
            self.client, "resolve_runtime", return_value=resolution
        ), mock.patch.object(
            self.client, "_envelope_document", return_value=self._codegen_document(5000)
        ), mock.patch.object(
            self.client, "_identity", return_value=resolution.identity
        ), mock.patch.object(
            self.client.subprocess, "Popen", return_value=process
        ), mock.patch.object(
            self.client, "_collect_bounded", side_effect=collect
        ), mock.patch.object(
            self.client, "_terminate_and_reap", return_value=True
        ) as reap:
            result = self.client.invoke(envelope={})

        self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)
        self.assertEqual(len(collected), 2)
        self.assertEqual(collected[1][0], b"")
        self.assertEqual(collected[1][2], {})
        self.assertLessEqual(
            collected[1][1] - collected[0][1],
            self.client.PROCESS_CLEANUP_RESERVE_SECONDS + 0.1,
        )
        reap.assert_called_once()

    def test_advisory_is_a_usable_receipt_free_runtime_result(self) -> None:
        self.assertTrue(hasattr(self.client.RuntimeStatus, "ADVISORY"))
        self.assertTrue(hasattr(self.wire, "advisory_response"))
        if not (
            hasattr(self.client.RuntimeStatus, "ADVISORY")
            and hasattr(self.wire, "advisory_response")
        ):
            return
        response = {
            "wire_contract_sha256": self.wire.sha256,
            "request_id": "direct-1",
            "status": "advisory",
            "advisory": {
                "authority": "advisory",
                "grounding": "ungrounded",
                "reason": "insufficient_source_evidence",
                "text": "Useful but non-authoritative analysis.",
            },
            "diagnostics": {
                "logical_agent": "codex",
                "provider_surface": "native_cli",
                "model_lineage": "openai",
                "observed_model": None,
                "implementation_fingerprint": "a" * 64,
                "executable_content_sha256": "b" * 64,
                "adapter_wire_sha256": "c" * 64,
                "catalog_digest": None,
                "model_resolution_method": "provider_default",
                "effective_effort": "standard",
                "metadata_process_count": 0,
                "provider_processes": 1,
                "provider_model_calls": 1,
                "provider_turns": 1,
                "selection_failure": None,
                "failure_trace": {
                    "failure_phase": "artifact",
                    "adapter_code": "insufficient_evidence",
                    "terminal_state": None,
                    "tool_outcomes": {
                        "success": 0, "failed": 0,
                        "incomplete": 0, "unknown": 0,
                    },
                    "outside_source_observed": False,
                    "native_envelope_sha256": "d" * 64,
                    "cleanup_confirmed": True,
                    "containment_detail": None,
                    "failed_operation_counts": {
                        "repository_read": 0,
                        "repository_search": 0,
                        "repository_list": 0,
                        "other_tool": 0,
                        "unclassified": 0,
                    },
                },
            },
        }
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            executable.write_text(
                "#!/usr/bin/python3\nimport json,sys\n"
                "json.load(sys.stdin)\n"
                "sys.stdout.write(" + repr(json.dumps(response)) + ")\n",
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
                result = self.client.invoke(envelope=self._envelope(2_000))

        self.assertEqual(result.status, self.client.RuntimeStatus.ADVISORY)
        self.assertEqual(result.result, response["advisory"])
        self.assertEqual(
            result.provenance,
            {
                "wire_contract_sha256": self.wire.sha256,
                "diagnostics": response["diagnostics"],
            },
        )
        self.assertNotIn("execution_receipt", result.provenance)

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

    def test_direct_invocation_preserves_caller_path_for_all_provider_clis(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            current_bin = root / "current-provider-bin"
            stale_bin = root / "stale-system-bin"
            current_bin.mkdir()
            stale_bin.mkdir()
            provider_names = ("codex", "agy", "grok", "opencode")
            for directory in (current_bin, stale_bin):
                for name in provider_names:
                    executable = directory / name
                    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                    executable.chmod(0o700)

            observed_path = root / "observed-path"
            runtime = root / "agent-collab-runtime"
            runtime.write_text(
                "#!/bin/sh\n"
                f"printf '%s' \"$PATH\" > {str(observed_path)!r}\n"
                "exit 7\n",
                encoding="utf-8",
            )
            runtime.chmod(0o700)
            resolution = self.client.RuntimeResolution(
                self.client.RuntimeStatus.OK,
                path=runtime,
                bundle_path=root,
                manifest_digest="a" * 64,
                artifact_digest="b" * 64,
                identity=self.client._identity(runtime, executable=True),
                wire=self.wire,
            )
            caller_path = os.pathsep.join((str(current_bin), str(stale_bin)))
            with mock.patch.dict(
                os.environ, {"PATH": caller_path}, clear=True
            ), mock.patch.object(
                self.client, "resolve_runtime", return_value=resolution
            ):
                result = self.client.invoke(envelope=self._envelope(1000))

            launched_path = observed_path.read_text(encoding="utf-8")
            resolved = {
                name: self.client.shutil.which(name, path=launched_path)
                for name in provider_names
            }
            self.assertEqual(result.status, self.client.RuntimeStatus.PROVIDER_ERROR)
            self.assertEqual(
                resolved,
                {name: str(current_bin / name) for name in provider_names},
            )
            self.assertEqual(launched_path, caller_path)

    def test_scrubbed_environment_uses_system_path_only_when_path_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as raw, mock.patch.dict(
            os.environ, {}, clear=True
        ):
            environment = self.client._scrubbed_env(Path(raw))

        self.assertEqual(
            environment["PATH"],
            "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        )

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
                "if sys.argv[1:] != ['invoke', '--protocol', '4']:\n"
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

    def test_typed_route_error_survives_nonzero_native_exit(self) -> None:
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
                "status": {"const": "invalid_request"},
                "error_code": {"const": "unsupported_target_action"},
                "diagnostics": {"type": "object"},
            },
        }
        wire = replace(self.wire, failure_response=failure_schema)
        response = {
            "wire_contract_sha256": wire.sha256,
            "request_id": "direct-1",
            "status": "invalid_request",
            "error_code": "unsupported_target_action",
            "diagnostics": {},
        }
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            payload = json.dumps(response, separators=(",", ":"))
            executable.write_text(
                "#!/usr/bin/python3\n"
                "import sys\n"
                "sys.stdin.buffer.read()\n"
                "sys.stdout.write(" + repr(payload) + ")\n"
                "raise SystemExit(2)\n",
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

        self.assertEqual(result.status, self.client.RuntimeStatus.INVALID_REQUEST)
        self.assertEqual(result.error, "unsupported_target_action")
        self.assertEqual(
            result.provenance,
            {"wire_contract_sha256": wire.sha256, "diagnostics": {}},
        )

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
            reaped = self.client._terminate_and_reap(
                UnprovenProcess(), deadline=time.monotonic() + 1
            )
        self.assertFalse(reaped)

    def test_readiness_uses_the_same_process_and_validates_all_actions(self) -> None:
        response = _readiness_response(self.wire.sha256)
        with tempfile.TemporaryDirectory() as raw:
            executable = Path(raw) / "agent-collab-runtime"
            payload = json.dumps(response, separators=(",", ":"))
            executable.write_text(
                "#!/usr/bin/python3\n"
                "import json, sys\n"
                "if sys.argv[1:] != ['invoke', '--protocol', '4']:\n"
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
        self.assertEqual(len(result.result["actions"]), 12)
        self.assertNotIn("execution_receipt", result.provenance)

    def test_readiness_accepts_catalog_resolved_native_cli_candidate(self) -> None:
        response = _readiness_response(self.wire.sha256)
        group = next(
            item
            for item in response["result"]["actions"]
            if item["logical_action"] == "architecture.repository"
        )
        group["candidates"] = [
            {
                "logical_agent": "codex",
                "provider_surface": "native_cli",
                "model_lineage": "openai",
                "shared_resource": "codex_cli_pool",
                "activation": "active",
                "status": "ready",
                "implementation_fingerprint": "a" * 64,
                "executable_content_sha256": "b" * 64,
                "adapter_wire_sha256": "c" * 64,
                "observed_model": "current-default",
                "catalog_digest": "d" * 64,
                "model_resolution_method": "provider_catalog",
                "effective_effort": "standard",
                "metadata_process_count": 1,
                "diagnostic_code": None,
                "compatibility_profile": "app_server_v2_minimum",
                "capability_digest": "e" * 64,
                "metadata_zero_model_calls_proven": True,
                "cleanup_confirmed": True,
            }
        ]

        validated = self.client.validate_readiness_response(
            response,
            self.wire,
            request_id="runtime-status-1",
            author_lineage="openai",
        )

        self.assertEqual(validated, response)

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

    def _tolerance_fixture(self, raw: str):
        """A runtime script that emits a valid minimal success and exits 0."""
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
            "result": "answer",
            "execution_receipt": {},
            "diagnostics": {},
        }
        executable = Path(raw) / "agent-collab-runtime"
        payload = json.dumps(response, separators=(",", ":"))
        executable.write_text(
            "#!/usr/bin/python3\nimport sys\nsys.stdout.write(" + repr(payload) + ")\n",
            encoding="utf-8",
        )
        executable.chmod(0o700)
        return self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=executable,
            bundle_path=Path(raw),
            manifest_digest="a" * 64,
            artifact_digest="b" * 64,
            identity=self.client._identity(executable, executable=True),
            wire=wire,
        )

    def test_unproven_teardown_never_voids_a_valid_response(self) -> None:
        """Release 4.0.4/agy regression: a cleanly exited runtime with a valid
        collected response must return OK even when process-group teardown
        cannot be proven; the unproven teardown degrades to a client note."""
        with tempfile.TemporaryDirectory() as raw:
            resolution = self._tolerance_fixture(raw)
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=resolution
            ), mock.patch.object(
                self.client, "_terminate_and_reap", return_value=False
            ):
                result = self.client.invoke(envelope=self._envelope(5000))
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result, "answer")
        self.assertEqual(result.error, "process group teardown unproven")

    def test_reap_crash_never_voids_a_valid_response(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            resolution = self._tolerance_fixture(raw)
            with mock.patch.object(
                self.client, "resolve_runtime", return_value=resolution
            ), mock.patch.object(
                self.client,
                "_terminate_and_reap",
                side_effect=OSError("reap machinery failed"),
            ):
                result = self.client.invoke(envelope=self._envelope(5000))
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result, "answer")
        self.assertEqual(result.error, "process group teardown unproven")

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
                # The descendant was killed within the dedicated reap budget
                # and the runtime exited cleanly, so teardown no longer masks
                # the actual defect: the empty response is a typed protocol
                # failure, not a false teardown verdict.
                self.assertEqual(result.status, self.client.RuntimeStatus.PROTOCOL_ERROR)
            finally:
                if child_pid:
                    try:
                        os.kill(child_pid, 9)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()
