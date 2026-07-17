"""Security contract for the co-packaged native agent-collab runtime client."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import os
import plistlib
import pwd
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "plugins" / "agent-collab" / "runtime_client.py"


def _load_client():
    spec = importlib.util.spec_from_file_location("agent_collab_runtime_client", CLIENT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_client_without_pwd():
    """Load the public client as on a platform without the POSIX pwd module."""

    spec = importlib.util.spec_from_file_location(
        "agent_collab_runtime_client_without_pwd", CLIENT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    original_import = __import__

    def blocked_pwd_import(name, *args, **kwargs):
        if name == "pwd":
            raise ImportError("pwd is unavailable")
        return original_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=blocked_pwd_import):
        spec.loader.exec_module(module)
    return module


class RuntimeClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = _load_client()

    def setUp(self) -> None:
        self.identity_env = mock.patch.dict(os.environ, {}, clear=True)
        self.identity_env.start()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.team_patch = mock.patch.object(
            self.client, "EXPECTED_DEVELOPER_ID_TEAM", "TESTTEAM01"
        )
        self.team_patch.start()
        self.platform_patch = mock.patch.object(
            self.client, "normalized_platform", return_value="darwin"
        )
        self.arch_patch = mock.patch.object(
            self.client, "normalized_arch", return_value="arm64"
        )
        self.platform_patch.start()
        self.arch_patch.start()
        self.kernel_sandbox_probe = self.client._sandbox_denies_broker_lifecycle
        self.sandbox_patch = mock.patch.object(
            self.client, "_sandbox_denies_broker_lifecycle", return_value=False
        )
        self.sandbox_patch.start()
        def fixture_inspector(path, record, *, signing):
            valid, error = self.client._verify_macos_signature(
                path,
                team_id=signing["team_id"],
                identity=signing["identity"],
                secure_timestamp=signing["secure_timestamp"],
                require_notarization=(
                    record["role"] == "entrypoint"
                    and signing["require_notarization"]
                ),
            )
            if not valid:
                raise self.client._RuntimeSignatureError(error)
            return {
                "macho_type": record["macho_type"],
                "architecture": record["architecture"],
                "minimum_macos": record["minimum_macos"],
                "signing_profile": record["signing_profile"],
            }

        self.inspector_patch = mock.patch.object(
            self.client,
            "_inspect_runtime_member",
            side_effect=fixture_inspector,
        )
        self.inspector_patch.start()

    def tearDown(self) -> None:
        self.sandbox_patch.stop()
        self.inspector_patch.stop()
        self.arch_patch.stop()
        self.platform_patch.stop()
        self.team_patch.stop()
        self.temp.cleanup()
        self.identity_env.stop()

    def test_manifest_team_must_equal_pinned_operator_team(self) -> None:
        self._fixture()
        manifest_path = self.root / "runtime-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"][0]["signing"]["team_id"] = "OTHERTEAM1"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
            result = self.client.resolve_runtime()
        self.assertEqual(result.status, self.client.RuntimeStatus.MANIFEST_INVALID)

    def test_module_loads_without_posix_pwd_and_omits_home(self) -> None:
        client = _load_client_without_pwd()
        self.assertIsNone(client._operator_home())
        env = client._scrubbed_env(tmpdir=self.root)
        self.assertNotIn("HOME", env)

    def test_runtime_resolution_without_posix_uid_is_typed_unsupported(self) -> None:
        client = _load_client_without_pwd()
        with mock.patch.object(client.os, "getuid", None), mock.patch.object(
            client, "PLUGIN_ROOT", self.root,
        ):
            result = client.resolve_runtime()
            identity = client._safe_file_identity(CLIENT, executable=False)

        self.assertEqual(result.status, client.RuntimeStatus.PLATFORM_UNSUPPORTED)
        self.assertIsNone(identity)
        self.assertIsNone(client._operator_home())

    def _fixture(
        self,
        *,
        body: str | None = None,
        contracts: list[tuple[str, str]] | None = None,
    ) -> Path:
        system = "darwin"
        arch = "arm64"
        bundle = (
            self.root
            / "runtime"
            / f"{system}-{arch}"
            / "agent-collab-runtime.bundle"
        )
        bundle.mkdir(parents=True, exist_ok=True)
        binary = bundle / "agent-collab-runtime"
        bundle.chmod(0o700)
        if binary.exists():
            binary.chmod(0o700)
        binary.write_text(
            body
            or """#!/usr/bin/env python3
import json, os, sys
request = json.loads(sys.stdin.readline())
families = {
    "codex": ("openai/codex-test", "openai"),
    "opencode": (request.get("model", "opencode/glm-5.2"), "zhipu"),
    "grok": ("xai/grok-4.5", "xai"),
    "composer": ("xai/grok-composer-2.5-fast", "xai"),
    "gemini": ("google/gemini-test", "google"),
}
author_model, author_family = families[request["route"]]
print(json.dumps({
    "protocol_version": 1,
    "request_id": request["request_id"],
    "status": "ok",
    "result": {
        "argv": sys.argv[1:],
        "secret_present": "LEAK_ME" in os.environ,
        "tmpdir": os.environ.get("TMPDIR", ""),
        "tmpdir_mode": oct(os.stat(os.environ["TMPDIR"]).st_mode & 0o777),
        "home": os.environ.get("HOME", ""),
        "host_context": request.get("host_context", ""),
        "governance_evidence": False,
    },
    "provenance": {
        "route": request["route"],
        "action": request["action"],
        "authority": request["authority"],
        "author_model": author_model,
        "author_family": author_family,
        "host_runtime": "fixture-runtime",
        "session_identifier": "fixture-session",
        "observation_sequence": 1,
    },
}))
""",
            encoding="utf-8",
        )
        binary.chmod(0o500)
        content = binary.read_bytes()
        records = [
            {
                "path": "agent-collab-runtime",
                "role": "entrypoint",
                "install_mode": 0o500,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "macho_type": "executable",
                "architecture": "arm64",
                "minimum_macos": "14.0",
                "signing_profile": "production_developer_id",
            }
        ]
        bundle.chmod(0o500)
        manifest = {
            "schema_version": 2,
            "protocol_version": 1,
            "contract_version": 3,
            "broker_protocol_version": 2,
            "channel": "production",
            "artifacts": [
                {
                    "platform": system,
                    "arch": arch,
                    "kind": "standalone_bundle",
                    "minimum_macos": "14.0",
                    "path": str(bundle.relative_to(self.root)),
                    "entrypoint": "agent-collab-runtime",
                    "size": len(content),
                    "sha256": self.client.runtime_bundle.compute_bundle_identity(records),
                    "signing": {
                        "mode": "developer_id",
                        "identity": "Developer ID Application: Test Operator (TESTTEAM01)",
                        "team_id": "TESTTEAM01",
                        "require_notarization": True,
                        "hardened_runtime": True,
                        "secure_timestamp": True,
                    },
                    "files": records,
                    "contracts": [
                        {"route": route, "action": action}
                        for route, action in (
                            contracts
                            if contracts is not None
                            else sorted(self.client.SUPPORTED_CONTRACTS)
                        )
                    ],
                }
            ],
        }
        (self.root / "runtime-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return binary

    def _management_fixture(self) -> None:
        tuple_keys = [
            "CODEX_SANDBOX",
            "__CFBundleIdentifier",
            "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
            "CODEX_CI",
        ]
        self._fixture(
            body=f"""#!/usr/bin/env python3
import json, os, sys
request = json.loads(sys.stdin.readline())
print(json.dumps({{
    "protocol_version": 1,
    "request_id": request["request_id"],
    "status": "ok",
    "result": {{
        "argv": sys.argv[1:],
        "management_action": request["management_action"],
        "host_context": request["host_context"],
        "secret_present": "LEAK_ME" in os.environ,
        "tuple_present": any(key in os.environ for key in {tuple_keys!r}),
        "home": os.environ.get("HOME", ""),
    }},
}}))
"""
        )

    def _envelope(
        self,
        *,
        route: str = "codex",
        action: str = "advisory",
        request_id: str = "req-1",
        prompt: str = "review this",
        row: dict[str, object] | None = None,
        governance: bool = False,
        artifact_model: str = "",
        timeout_ms: int = 30_000,
        opencode_model: str = "",
    ):
        defaults: dict[tuple[str, str], dict[str, object]] = {
            ("gemini", "advisory"): {"model": "google/gemini-test", "effort": "high"},
            ("gemini", "governance"): {
                "model": "google/gemini-3.1-pro",
                "effort": "high",
            },
            ("gemini", "long_context"): {
                "model": "google/gemini-test",
                "effort": "high",
                "documents": [{"label": "a", "content": "document"}],
            },
            ("codex", "advisory"): {
                "model": "openai/codex-test",
                "effort": "high",
                "mode": "prompt-only",
            },
            ("opencode", "plan"): {
                "model": "opencode/glm-5.2",
                "cwd": str(self.root),
            },
            ("opencode", "build"): {
                "model": "opencode/glm-5.2",
                "cwd": str(self.root),
            },
            ("grok", "architecture"): {"mode": "prompt-only"},
            ("grok", "governance"): {"mode": "prompt-only"},
            ("grok", "huge_context"): {
                "documents": [{"label": "a", "content": "document"}]
            },
            ("composer", "codegen"): {},
        }
        policy = self.client._load_host_policy()
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
            with mock.patch.object(policy, "PLUGIN_ROOT", self.root):
                with mock.patch.object(
                    self.client, "_verify_macos_signature", return_value=(True, "")
                ):
                    explicit = {
                        "primary_id": "claude",
                        "active_model": "anthropic/claude-opus",
                        "host_runtime": "claude-code",
                        "session_identifier": "c-1",
                    }
                    if opencode_model:
                        explicit["opencode_model"] = opencode_model
                    decision = policy.issue_policy_envelope(
                        request_id=request_id,
                        route=route,
                        action=action,
                        governance=governance,
                        prompt=prompt,
                        timeout_ms=timeout_ms,
                        artifact_author_model=artifact_model,
                        artifact_content="artifact" if artifact_model else "",
                        explicit_config=explicit,
                        row_config=row if row is not None else defaults[(route, action)],
                    )
        self.assertIsNotNone(decision.envelope, decision.warning)
        return decision.envelope

    def _fixture_broker(self, **kwargs):
        """Exercise native response parsing while substituting the test broker transport."""

        return self.client._launch_runtime(
            resolution=kwargs["resolution"],
            payload=kwargs["payload"],
            timeout_ms=kwargs["timeout_ms"],
            envelope=kwargs["envelope"],
        )

    def test_source_manifest_never_contains_unsigned_placeholder(self) -> None:
        plugin_root = ROOT / "plugins" / "agent-collab"
        manifest = json.loads(
            (plugin_root / "runtime-manifest.json").read_text(encoding="utf-8")
        )
        if manifest["artifacts"]:
            for artifact in manifest["artifacts"]:
                path = plugin_root / artifact["path"]
                self.assertTrue(path.is_dir())
                self.assertFalse(path.is_symlink())
                self.assertEqual(
                    sum((path / item["path"]).stat().st_size for item in artifact["files"]),
                    artifact["size"],
                )
                self.assertEqual(
                    self.client.runtime_bundle.compute_bundle_identity(artifact["files"]),
                    artifact["sha256"],
                )
        else:
            self.assertFalse((plugin_root / "runtime").exists())
        result = self.client.resolve_runtime()
        if not manifest["artifacts"]:
            self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)

    def test_empty_manifest_is_unavailable_before_platform_rejection(self) -> None:
        manifest = {
            "schema_version": 2,
            "protocol_version": 1,
            "contract_version": 3,
            "broker_protocol_version": 2,
            "channel": "production",
            "artifacts": [],
        }
        (self.root / "runtime-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "normalized_platform", return_value="linux"
        ), mock.patch.object(self.client, "normalized_arch", return_value="x86_64"):
            result = self.client.resolve_runtime()
        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)

    def test_invalid_manifest_is_rejected_before_platform_rejection(self) -> None:
        (self.root / "runtime-manifest.json").write_text("{}", encoding="utf-8")
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "normalized_platform", return_value="linux"
        ), mock.patch.object(self.client, "normalized_arch", return_value="x86_64"):
            result = self.client.resolve_runtime()
        self.assertEqual(result.status, self.client.RuntimeStatus.MANIFEST_INVALID)

    def test_valid_fixture_launches_fixed_protocol_with_scrubbed_env(self) -> None:
        self._fixture()
        envelope = self._envelope()
        caller_tmpdir = self.root / "caller-tmp"
        caller_tmpdir.mkdir()
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ):
            with mock.patch.dict(
                os.environ,
                {"LEAK_ME": "secret", "TMPDIR": str(caller_tmpdir)},
                clear=False,
            ):
                with mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
                    self.client, "_launch_broker", side_effect=self._fixture_broker
                ):
                    result = self.client.invoke(envelope=envelope)
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result["argv"], ["invoke", "--protocol", "1"])
        self.assertFalse(result.result["secret_present"])
        self.assertEqual(result.result["home"], pwd.getpwuid(os.getuid()).pw_dir)
        self.assertEqual(result.result["host_context"], "generic")
        self.assertEqual(result.provenance["author_family"], "openai")
        child_tmpdir = Path(result.result["tmpdir"])
        self.assertNotEqual(child_tmpdir, caller_tmpdir)
        self.assertFalse(str(child_tmpdir).startswith(str(self.root) + os.sep))
        self.assertEqual(result.result["tmpdir_mode"], "0o700")
        self.assertFalse(child_tmpdir.exists())

    def test_resolution_carries_the_verified_artifact_digest(self) -> None:
        self._fixture()
        expected = json.loads(
            (self.root / "runtime-manifest.json").read_text(encoding="utf-8")
        )["artifacts"][0]["sha256"]
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
            result = self.client.resolve_runtime()
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.artifact_digest, expected)

    def test_broker_frame_is_exact_digest_bound_and_uses_canonical_nonce(self) -> None:
        request = {
            "protocol_version": 1,
            "request_id": "broker-frame-1",
            "operation": "execute",
        }
        now = 1_234.5
        nonce = bytes(range(32))
        with mock.patch.object(self.client.time, "monotonic", return_value=now), mock.patch.object(
            self.client.os, "urandom", return_value=nonce
        ):
            frame = self.client._broker_request_frame(
                request=request,
                artifact_digest="a" * 64,
                manifest_digest="b" * 64,
                timeout_ms=30_000,
            )
        self.assertEqual(set(frame), self.client.BROKER_FRAME_KEYS)
        self.assertEqual(frame["broker_protocol_version"], 2)
        self.assertEqual(frame["runtime_protocol_version"], 1)
        self.assertEqual(frame["artifact_sha256"], "a" * 64)
        self.assertEqual(frame["manifest_sha256"], "b" * 64)
        self.assertEqual(frame["client_pid"], os.getpid())
        self.assertEqual(frame["deadline_monotonic_ms"], 1_264_500)
        self.assertEqual(
            frame["nonce"],
            base64.urlsafe_b64encode(nonce).decode("ascii").rstrip("="),
        )
        self.assertEqual(frame["request"], request)

    def test_broker_frame_codec_rejects_nan_bool_and_oversize(self) -> None:
        with self.assertRaises(ValueError):
            self.client._encode_broker_frame({"bad": float("nan")}, max_bytes=1024)
        with self.assertRaises(ValueError):
            self.client._encode_broker_frame({"bad": True}, max_bytes=True)
        with self.assertRaises(OverflowError):
            self.client._encode_broker_frame({"large": "x" * 50}, max_bytes=8)

    def _adoption_canary_request(self, **overrides: object) -> dict[str, object]:
        request: dict[str, object] = {
            "protocol_version": 1,
            "request_id": "adoption-canary-1",
            "operation": "adoption_canary",
            "provider": "gemini",
            "registry_generation": 17,
            "source_generation": 8,
            "binary_sha256": "1" * 64,
            "worker_sha256": "2" * 64,
            "adapter_contract_generation": 4,
            "routes": ["gemini/advisory", "gemini/governance"],
            "attempt_generation": 5,
            "authority_token": base64.urlsafe_b64encode(b"t" * 32)
            .decode("ascii")
            .rstrip("="),
            "timeout_ms": 30_000,
        }
        request.update(overrides)
        return request

    def test_adoption_canary_is_a_closed_internal_operation_not_a_route(self) -> None:
        request = self._adoption_canary_request()
        encoded = self.client._adoption_canary_document(request)
        document = json.loads(encoded)
        self.assertEqual(
            set(document),
            self.client.ADOPTION_CANARY_KEYS | {"host_context"},
        )
        self.assertEqual(document["operation"], "adoption_canary")
        self.assertEqual(document["host_context"], "generic")
        self.assertNotIn("route", document)
        self.assertNotIn("action", document)
        self.assertNotIn("model", document)

        invalid = (
            self._adoption_canary_request(provider="unknown"),
            self._adoption_canary_request(routes=["grok/architecture"]),
            self._adoption_canary_request(routes=["gemini/governance", "gemini/advisory"]),
            self._adoption_canary_request(authority_token="0" * 64),
            self._adoption_canary_request(provider_path="/tmp/provider"),
            self._adoption_canary_request(model="attacker/model"),
            self._adoption_canary_request(auth_root="/tmp/auth"),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                self.client._adoption_canary_document(candidate)

    def test_dispatcher_handshake_is_request_free_and_digest_bound(self) -> None:
        lane = self.client.BrokerLaneSnapshot(
            name="green",
            generation=7,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("a" * 64, "b" * 64)
            ),
            socket_path=self.root / "dispatcher.sock",
        )
        nonce = base64.urlsafe_b64encode(b"n" * 32).decode("ascii").rstrip("=")
        hello = self.client._dispatcher_build_hello(
            lane=lane,
            client_pid=4242,
            nonce=nonce,
            deadline_monotonic_ms=123_456,
        )
        self.assertEqual(set(hello), self.client.DISPATCHER_HELLO_KEYS)
        self.assertEqual(hello["frame_type"], "hello")
        self.assertNotIn("request", hello)
        hello_sha256 = hashlib.sha256(
            json.dumps(
                hello,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("ascii")
        ).hexdigest()
        ready = {
            **hello,
            "frame_type": "ready",
            "dispatcher_pid": 9001,
            "hello_sha256": hello_sha256,
        }
        session = self.client._dispatcher_accept_ready(
            hello,
            ready,
            lane=lane,
            expected_dispatcher_pid=9001,
            now_monotonic=100.0,
        )
        request = self._adoption_canary_request()
        frame = self.client._dispatcher_build_request_frame(
            session=session,
            request=request,
        )
        self.assertEqual(set(frame), self.client.DISPATCHER_REQUEST_KEYS)
        self.assertEqual(frame["request"], request)
        self.assertEqual(frame["hello_sha256"], hello_sha256)
        self.assertNotEqual(frame["ready_sha256"], hello_sha256)

        replay = dict(ready, lane_token="0" * 32)
        with self.assertRaises(ValueError):
            self.client._dispatcher_accept_ready(
                hello,
                replay,
                lane=lane,
                expected_dispatcher_pid=9001,
                now_monotonic=100.0,
            )

    def test_dispatcher_protocol_matches_the_cross_repository_fixture(self) -> None:
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "provider_dispatcher_protocol_v1.json").read_text(
                encoding="utf-8"
            )
        )
        lane = self.client.BrokerLaneSnapshot(
            name="green",
            generation=7,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("a" * 64, "b" * 64)
            ),
            socket_path=self.root / "dispatcher.sock",
        )
        hello = self.client._dispatcher_build_hello(
            lane=lane,
            client_pid=4242,
            nonce=fixture["hello"]["nonce"],
            deadline_monotonic_ms=123_456,
        )
        session = self.client._dispatcher_accept_ready(
            hello,
            fixture["ready"],
            lane=lane,
            expected_dispatcher_pid=9001,
            now_monotonic=100.0,
        )
        frame = self.client._dispatcher_build_request_frame(
            session=session,
            request=fixture["request"]["request"],
        )
        self.assertEqual(hello, fixture["hello"])
        self.assertEqual(
            self.client._dispatcher_frame_sha256(hello), fixture["hello_sha256"]
        )
        self.assertEqual(session.ready_sha256, fixture["ready_sha256"])
        self.assertEqual(frame, fixture["request"])
        self.assertEqual(
            self.client._dispatcher_frame_sha256(frame), fixture["request_sha256"]
        )

    def test_dispatcher_exchange_sends_no_request_until_ready_is_proven(self) -> None:
        lane = self.client.BrokerLaneSnapshot(
            name="green",
            generation=7,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("a" * 64, "b" * 64)
            ),
            socket_path=self.root / "dispatcher.sock",
        )
        peer = mock.Mock()
        request = self._adoption_canary_request()
        nonce = base64.urlsafe_b64encode(b"n" * 32).decode("ascii").rstrip("=")
        hello = self.client._dispatcher_build_hello(
            lane=lane,
            client_pid=os.getpid(),
            nonce=nonce,
            deadline_monotonic_ms=130_000,
        )
        ready = {
            **hello,
            "frame_type": "ready",
            "dispatcher_pid": 9001,
            "hello_sha256": self.client._dispatcher_frame_sha256(hello),
        }
        response = {
            "protocol_version": 1,
            "request_id": "adoption-canary-1",
            "status": "ok",
            "result": {"passed_routes": request["routes"]},
            "provenance": {},
        }

        with mock.patch.object(
            self.client, "_prove_dispatcher_peer", return_value=9001
        ), mock.patch.object(
            self.client, "_read_broker_frame", side_effect=(ready, response)
        ), mock.patch.object(
            self.client.time, "monotonic", return_value=100.0
        ), mock.patch.object(
            self.client.os, "urandom", return_value=b"n" * 32
        ):
            observed = self.client._dispatcher_exchange(
                peer=peer,
                lane=lane,
                request=request,
                deadline=130.0,
            )
        self.assertEqual(observed, response)
        self.assertEqual(peer.sendall.call_count, 2)
        first = peer.sendall.call_args_list[0].args[0]
        first_size = struct.unpack(">Q", first[:8])[0]
        first_frame = json.loads(first[8 : 8 + first_size])
        self.assertEqual(first_frame, hello)
        self.assertNotIn("request", first_frame)
        second = peer.sendall.call_args_list[1].args[0]
        second_size = struct.unpack(">Q", second[:8])[0]
        second_frame = json.loads(second[8 : 8 + second_size])
        self.assertEqual(second_frame["frame_type"], "request")
        self.assertEqual(second_frame["request"], request)

        peer.reset_mock()
        wrong_ready = dict(ready, dispatcher_pid=9002)
        with mock.patch.object(
            self.client, "_prove_dispatcher_peer", return_value=9001
        ), mock.patch.object(
            self.client, "_read_broker_frame", return_value=wrong_ready
        ), mock.patch.object(
            self.client.time, "monotonic", return_value=100.0
        ), mock.patch.object(
            self.client.os, "urandom", return_value=b"n" * 32
        ), self.assertRaises(self.client._DispatcherPreRequestError):
            self.client._dispatcher_exchange(
                peer=peer,
                lane=lane,
                request=request,
                deadline=130.0,
            )
        self.assertEqual(peer.sendall.call_count, 1)

    def test_dispatcher_exchange_caps_handshake_without_shortening_request(self) -> None:
        lane = self.client.BrokerLaneSnapshot(
            name="green",
            generation=7,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("a" * 64, "b" * 64)
            ),
            socket_path=self.root / "dispatcher.sock",
        )
        peer = mock.Mock()
        request = self._adoption_canary_request(timeout_ms=300_000)
        nonce = base64.urlsafe_b64encode(b"n" * 32).decode("ascii").rstrip("=")
        hello = self.client._dispatcher_build_hello(
            lane=lane,
            client_pid=os.getpid(),
            nonce=nonce,
            deadline_monotonic_ms=400_000,
        )
        ready = {
            **hello,
            "frame_type": "ready",
            "dispatcher_pid": 9001,
            "hello_sha256": self.client._dispatcher_frame_sha256(hello),
        }
        response = {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": "canary_blocked",
            "error": "fixture",
        }
        observed_deadlines: list[float] = []

        def read_frame(*_args, **kwargs):
            observed_deadlines.append(kwargs["deadline"])
            return ready if len(observed_deadlines) == 1 else response

        with mock.patch.object(
            self.client, "_prove_dispatcher_peer", return_value=9001
        ), mock.patch.object(
            self.client, "_read_broker_frame", side_effect=read_frame
        ), mock.patch.object(
            self.client.time, "monotonic", return_value=100.0
        ), mock.patch.object(
            self.client.os, "urandom", return_value=b"n" * 32
        ):
            observed = self.client._dispatcher_exchange(
                peer=peer,
                lane=lane,
                request=request,
                deadline=400.0,
            )
        self.assertEqual(observed, response)
        self.assertEqual(observed_deadlines, [130.0, 400.0])
        first = peer.sendall.call_args_list[0].args[0]
        first_size = struct.unpack(">Q", first[:8])[0]
        first_frame = json.loads(first[8 : 8 + first_size])
        self.assertEqual(first_frame["deadline_monotonic_ms"], 400_000)

    def test_dispatcher_peer_proof_rejects_uid_pid_path_and_socket_drift(self) -> None:
        lane = self.client.BrokerLaneSnapshot(
            name="green",
            generation=7,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("a" * 64, "b" * 64)
            ),
            socket_path=self.root / "dispatcher.sock",
        )
        runtime = self.root / "runtime"
        runtime.write_bytes(b"runtime")
        runtime.chmod(0o500)
        socket_identity = self.client.FileIdentity(1, 2, 0, 0, stat.S_IFSOCK | 0o600, os.getuid(), 1)
        process = mock.Mock(side_effect=[("10:1", runtime), ("10:1", runtime)])
        published = mock.Mock(
            side_effect=[
                (self.root / "bundle", runtime, self.root / "manifest"),
                (self.root / "bundle", runtime, self.root / "manifest"),
            ]
        )
        observed = self.client._prove_dispatcher_peer(
            mock.Mock(),
            lane,
            credential_observer=mock.Mock(return_value=(os.getuid(), 4242)),
            process_observer=process,
            socket_observer=mock.Mock(side_effect=[socket_identity, socket_identity]),
            published_verifier=published,
            root=self.root,
        )
        self.assertEqual(observed, 4242)

        failures = (
            {"credential_observer": mock.Mock(return_value=(os.getuid() + 1, 4242))},
            {"process_observer": mock.Mock(side_effect=[("10:1", runtime), ("10:2", runtime)])},
            {"process_observer": mock.Mock(side_effect=[("10:1", Path("/tmp/attacker"))] * 2)},
            {"socket_observer": mock.Mock(side_effect=[socket_identity, replace(socket_identity, inode=3)])},
        )
        for overrides in failures:
            values = {
                "credential_observer": mock.Mock(return_value=(os.getuid(), 4242)),
                "process_observer": mock.Mock(side_effect=[("10:1", runtime), ("10:1", runtime)]),
                "socket_observer": mock.Mock(side_effect=[socket_identity, socket_identity]),
                "published_verifier": mock.Mock(
                    side_effect=[
                        (self.root / "bundle", runtime, self.root / "manifest"),
                        (self.root / "bundle", runtime, self.root / "manifest"),
                    ]
                ),
            }
            values.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.client._prove_dispatcher_peer(
                    mock.Mock(), lane, root=self.root, **values
                )

    def test_adoption_canary_uses_only_the_staged_green_lane(self) -> None:
        request = self._adoption_canary_request()
        green = self.client.BrokerLaneSnapshot(
            name="green",
            generation=7,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("a" * 64, "b" * 64)
            ),
            socket_path=self.root / "green.sock",
        )
        selector = self._selector_document(
            generation=7,
            selected_lane="blue",
            green_artifact="a" * 64,
            green_manifest="b" * 64,
        )
        response = {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "status": "ok",
            "result": {
                "provider": "gemini",
                "registry_generation": 17,
                "attempt_generation": 5,
                "passed_routes": request["routes"],
            },
            "provenance": {
                "operation": "adoption_canary",
                "binary_sha256": "1" * 64,
                "worker_sha256": "2" * 64,
                "adapter_contract_generation": 4,
            },
        }
        with mock.patch.object(
            self.client, "_broker_root", return_value=self.root
        ), mock.patch.object(
            self.client, "_read_broker_selector", return_value=selector
        ), mock.patch.object(
            self.client, "_load_dispatcher_broker_lane", return_value=green
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge", return_value=response
        ) as bridge:
            result = self.client.invoke_adoption_canary(request=request)
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result["passed_routes"], request["routes"])
        bridge.assert_called_once()
        self.assertEqual(bridge.call_args.kwargs["lane"], green)
        self.assertEqual(bridge.call_args.kwargs["request"]["host_context"], "generic")

        missing = dict(selector, green=None)
        with mock.patch.object(
            self.client, "_broker_root", return_value=self.root
        ), mock.patch.object(
            self.client, "_read_broker_selector", return_value=missing
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge"
        ) as bridge:
            unavailable = self.client.invoke_adoption_canary(request=request)
        self.assertEqual(unavailable.status, self.client.RuntimeStatus.UNAVAILABLE)
        bridge.assert_not_called()

    def _selector_document(
        self,
        *,
        generation: int = 1,
        selected_lane: str = "blue",
        blue_artifact: str = "a" * 64,
        blue_manifest: str = "b" * 64,
        green_artifact: str | None = "c" * 64,
        green_manifest: str | None = "d" * 64,
    ) -> dict[str, object]:
        green = None
        if green_artifact is not None and green_manifest is not None:
            green = {
                "artifact_sha256": green_artifact,
                "manifest_sha256": green_manifest,
            }
        return {
            "schema_version": 1,
            "generation": generation,
            "selected_lane": selected_lane,
            "blue": {
                "artifact_sha256": blue_artifact,
                "manifest_sha256": blue_manifest,
            },
            "green": green,
        }

    def test_broker_selector_schema_generation_and_paths_are_closed(self) -> None:
        selector = self._selector_document()
        self.assertTrue(self.client._broker_selector_valid(selector))
        committed = self._selector_document(generation=2, selected_lane="green")
        self.assertTrue(
            self.client._broker_selector_transition_valid(selector, committed)
        )
        for generation in (1, 3, True, 2.0, -1):
            candidate = self._selector_document(
                generation=generation, selected_lane="green"
            )
            with self.subTest(generation=generation):
                self.assertFalse(
                    self.client._broker_selector_transition_valid(selector, candidate)
                )

        invalid = []
        extra = self._selector_document()
        extra["socket_path"] = "/tmp/attacker.sock"
        invalid.append(extra)
        missing = self._selector_document()
        missing.pop("blue")
        invalid.append(missing)
        bool_generation = self._selector_document(generation=True)
        invalid.append(bool_generation)
        float_generation = self._selector_document(generation=1.0)
        invalid.append(float_generation)
        uppercase_digest = self._selector_document(green_artifact="C" * 64)
        invalid.append(uppercase_digest)
        arbitrary_green_path = self._selector_document()
        assert isinstance(arbitrary_green_path["green"], dict)
        arbitrary_green_path["green"]["label"] = "attacker.label"
        invalid.append(arbitrary_green_path)
        selected_missing_green = self._selector_document(
            selected_lane="green", green_artifact=None, green_manifest=None
        )
        invalid.append(selected_missing_green)
        for document in invalid:
            with self.subTest(document=document):
                self.assertFalse(self.client._broker_selector_valid(document))

        lane = self.client._dispatcher_lane_snapshot(
            self.root,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            generation=2,
        )
        token = self.client._dispatcher_lane_token("c" * 64, "d" * 64)
        self.assertEqual(
            lane.label, f"com.agent-collab.provider-dispatcher.{token}"
        )
        self.assertEqual(
            lane.socket_path, self.root / f"provider-dispatcher-{token}.sock"
        )
        self.assertEqual(lane.artifact_digest, "c" * 64)
        self.assertEqual(lane.manifest_digest, "d" * 64)

    def test_selector_file_is_exact_private_regular_and_bounded(self) -> None:
        root = self.root / "selector-root"
        root.mkdir(mode=0o700)
        path = root / self.client.BROKER_SELECTOR_FILENAME
        document = self._selector_document()
        path.write_text(json.dumps(document), encoding="utf-8")
        path.chmod(0o600)
        self.assertEqual(self.client._read_broker_selector(root), document)

        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.client._read_broker_selector(root)
        path.chmod(0o600)
        path.write_text('{"schema_version":1', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.client._read_broker_selector(root)

        path.write_text(json.dumps(document), encoding="utf-8")
        hardlink = root / "selector-hardlink.json"
        os.link(path, hardlink)
        with self.assertRaises(ValueError):
            self.client._read_broker_selector(root)

    def test_dispatcher_lane_requires_exact_derived_state_plist_and_socket(self) -> None:
        root = self.root / "dispatcher-root"
        root.mkdir(mode=0o700)
        lane = self.client._dispatcher_lane_snapshot(
            root,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            generation=2,
        )
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(lane.socket_path))
        lane.socket_path.chmod(0o600)
        self.addCleanup(listener.close)
        runtime = self.root / "published-runtime"
        plist_document = self.client._broker_plist_document(
            runtime_path=runtime,
            socket_path=lane.socket_path,
            tmpdir=root / "tmp",
            home=self.root,
            uid=os.getuid(),
            label=lane.label,
        )
        plist_raw = plistlib.dumps(
            plist_document, fmt=plistlib.FMT_XML, sort_keys=True
        )
        plist_path = self.client._dispatcher_mutable_path(root, lane, "plist")
        plist_path.write_bytes(plist_raw)
        plist_path.chmod(0o600)
        state = {
            "schema_version": 1,
            "contract_version": self.client.CONTRACT_VERSION,
            "dispatcher_protocol_version": self.client.DISPATCHER_PROTOCOL_VERSION,
            "runtime_protocol_version": self.client.PROTOCOL_VERSION,
            "artifact_sha256": lane.artifact_digest,
            "manifest_sha256": lane.manifest_digest,
            "plist_sha256": hashlib.sha256(plist_raw).hexdigest(),
        }
        state_path = self.client._dispatcher_mutable_path(root, lane, "json")
        state_path.write_text(json.dumps(state), encoding="utf-8")
        state_path.chmod(0o600)
        reference = {
            "artifact_sha256": lane.artifact_digest,
            "manifest_sha256": lane.manifest_digest,
        }
        with mock.patch.object(
            self.client,
            "_verify_published_version",
            return_value=(self.root / "bundle", runtime, self.root / "manifest"),
        ), mock.patch.object(
            self.client, "_operator_home", return_value=str(self.root)
        ):
            observed = self.client._load_dispatcher_broker_lane(root, reference, 2)
        self.assertEqual(observed, lane)
        self.assertEqual(
            plist_document["ProgramArguments"],
            [str(runtime), "dispatcher", "--protocol", "1"],
        )

        state_path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.client._load_dispatcher_broker_lane(root, reference, 2)

    def test_missing_invalid_or_unproven_green_leaves_blue_selected(self) -> None:
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        blue = self.client.BrokerLaneSnapshot(
            name="blue",
            generation=0,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=self.root / self.client.BROKER_SOCKET_FILENAME,
        )
        cases = (
            None,
            ValueError("partial selector"),
            ValueError("malformed selector"),
        )
        for observed in cases:
            with self.subTest(observed=repr(observed)), mock.patch.object(
                self.client, "_load_legacy_broker_lane", return_value=blue
            ), mock.patch.object(
                self.client,
                "_read_broker_selector",
                side_effect=observed if isinstance(observed, BaseException) else None,
                return_value=observed if observed is None else mock.DEFAULT,
            ), mock.patch.object(
                self.client, "_load_dispatcher_broker_lane"
            ) as green:
                lanes, error = self.client._capture_broker_lanes(resolution)
            self.assertEqual(lanes, (blue,))
            self.assertIsNone(error)
            green.assert_not_called()

        selected_green = self._selector_document(selected_lane="green")
        with mock.patch.object(
            self.client, "_load_legacy_broker_lane", return_value=blue
        ), mock.patch.object(
            self.client, "_read_broker_selector", return_value=selected_green
        ), mock.patch.object(
            self.client,
            "_load_dispatcher_broker_lane",
            side_effect=ValueError("unproven dispatcher"),
        ):
            lanes, error = self.client._capture_broker_lanes(resolution)
        self.assertEqual(lanes, (blue,))
        self.assertIsNone(error)

    def test_selected_green_is_not_suppressed_by_stale_blue_reference(self) -> None:
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        current_blue = self.client.BrokerLaneSnapshot(
            name="blue",
            generation=0,
            artifact_digest="9" * 64,
            manifest_digest="8" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=self.root / self.client.BROKER_SOCKET_FILENAME,
        )
        green = self.client.BrokerLaneSnapshot(
            name="green",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label="com.agent-collab.provider-dispatcher.test",
            socket_path=self.root / "green.sock",
        )
        selector = self._selector_document(selected_lane="green", generation=2)
        with mock.patch.object(
            self.client, "_load_legacy_broker_lane", return_value=current_blue
        ), mock.patch.object(
            self.client, "_read_broker_selector", return_value=selector
        ), mock.patch.object(
            self.client, "_load_dispatcher_broker_lane", return_value=green
        ) as green_loader, mock.patch.object(
            self.client, "BROKER_GREEN_PROMOTION_SUPPORTED", True
        ):
            lanes, error = self.client._capture_broker_lanes(resolution)
        self.assertEqual(lanes, (green, current_blue))
        self.assertIsNone(error)
        green_loader.assert_called_once()

    def test_handshake_client_accepts_committed_green_with_blue_fallback(self) -> None:
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        blue = self.client.BrokerLaneSnapshot(
            name="blue",
            generation=0,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=self.root / self.client.BROKER_SOCKET_FILENAME,
        )
        green = self.client.BrokerLaneSnapshot(
            name="green",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label="com.agent-collab.provider-dispatcher.test",
            socket_path=self.root / "green.sock",
        )
        selector = self._selector_document(selected_lane="green", generation=2)
        with mock.patch.object(
            self.client, "_load_legacy_broker_lane", return_value=blue
        ), mock.patch.object(
            self.client, "_read_broker_selector", return_value=selector
        ), mock.patch.object(
            self.client, "_load_dispatcher_broker_lane", return_value=green
        ) as green_loader:
            lanes, error = self.client._capture_broker_lanes(resolution)
        self.assertEqual(lanes, (green, blue))
        self.assertIsNone(error)
        green_loader.assert_called_once()

    def test_inflight_lane_snapshot_stays_blue_while_next_request_selects_green(self) -> None:
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        blue = self.client.BrokerLaneSnapshot(
            name="blue",
            generation=0,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=self.root / self.client.BROKER_SOCKET_FILENAME,
        )
        green = self.client.BrokerLaneSnapshot(
            name="green",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label="com.agent-collab.provider-dispatcher.test",
            socket_path=self.root / "green.sock",
        )
        blue_selected = self._selector_document(selected_lane="blue", generation=1)
        green_selected = self._selector_document(selected_lane="green", generation=2)
        with mock.patch.object(
            self.client, "_load_legacy_broker_lane", return_value=blue
        ), mock.patch.object(
            self.client,
            "_read_broker_selector",
            side_effect=(blue_selected, green_selected),
        ), mock.patch.object(
            self.client, "_load_dispatcher_broker_lane", return_value=green
        ):
            inflight_lanes, inflight_error = self.client._capture_broker_lanes(
                resolution
            )
            next_lanes, next_error = self.client._capture_broker_lanes(resolution)

        self.assertEqual(inflight_lanes, (blue,))
        self.assertIsNone(inflight_error)
        self.assertEqual(next_lanes, (green, blue))
        self.assertIsNone(next_error)
        self.assertEqual(inflight_lanes, (blue,))

    def test_green_bridge_document_binds_lane_and_deadlines_without_path_input(self) -> None:
        lane = self.client.BrokerLaneSnapshot(
            name="green",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "green.sock",
        )
        request = {
            "protocol_version": 1,
            "request_id": "bridge-1",
            "operation": "dispatcher_ping",
            "timeout_ms": 5_000,
            "host_context": "generic",
        }
        encoded = self.client._dispatcher_bridge_document(
            lane=lane,
            request=request,
            deadline_monotonic_ms=110_000,
            handshake_deadline_monotonic_ms=109_000,
        )
        document = json.loads(encoded)
        self.assertEqual(
            set(document),
            {
                "bridge_protocol_version",
                "lane_generation",
                "artifact_sha256",
                "manifest_sha256",
                "deadline_monotonic_ms",
                "handshake_deadline_monotonic_ms",
                "request",
            },
        )
        self.assertNotIn("socket", encoded.decode("ascii"))
        self.assertNotIn(str(self.root), encoded.decode("ascii"))
        self.assertTrue(encoded.endswith(b"\n"))

    def test_lock_probe_uses_staged_bridge_and_returns_closed_namespace_proof(self) -> None:
        green = self.client.BrokerLaneSnapshot(
            name="green",
            generation=4,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "green.sock",
        )
        selector = self._selector_document(selected_lane="blue", generation=4)

        def bridge(*, lane, request, deadline, handshake_deadline):
            self.assertIs(lane, green)
            self.assertEqual(request["operation"], "dispatcher_lock_probe")
            self.assertEqual(request["provider"], "opencode")
            self.assertLessEqual(handshake_deadline, deadline)
            return {
                "protocol_version": 1,
                "request_id": request["request_id"],
                "status": "ok",
                "result": {
                    "provider": "opencode",
                    "lock_acquired": True,
                    "namespace": "legacy-compatible-v1",
                },
                "provenance": {"operation": "dispatcher_lock_probe"},
            }

        with mock.patch.object(
            self.client, "_broker_root", return_value=self.root
        ), mock.patch.object(
            self.client, "_read_broker_selector", return_value=selector
        ), mock.patch.object(
            self.client, "_load_dispatcher_broker_lane", return_value=green
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge", side_effect=bridge
        ):
            result = self.client.invoke_dispatcher_lock_probe(
                provider="opencode", timeout_ms=5_000
            )

        self.assertEqual(result.status, self.client.RuntimeStatus.OK, result.error)
        self.assertEqual(
            result.result,
            {
                "provider": "opencode",
                "lock_acquired": True,
                "namespace": "legacy-compatible-v1",
            },
        )
        self.assertEqual(
            result.provenance, {"operation": "dispatcher_lock_probe"}
        )

    def test_selected_green_uses_immutable_bridge_without_python_socket_connection(self) -> None:
        self._fixture()
        envelope = self._envelope(
            route="opencode", action="plan", request_id="green-bridge-1"
        )
        payload = self.client._native_document(envelope)
        green = self.client.BrokerLaneSnapshot(
            name="green",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "green.sock",
        )
        response = {
            "protocol_version": 1,
            "request_id": envelope.request_id,
            "status": "unavailable",
            "error": "fixture route unavailable",
        }
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=self.root / "runtime",
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        with mock.patch.object(
            self.client, "_capture_broker_lanes", return_value=((green,), None)
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge", return_value=response
        ) as bridge, mock.patch.object(
            self.client.socket, "socket"
        ) as socket_factory:
            result = self.client._launch_broker(
                resolution=resolution,
                payload=payload,
                timeout_ms=30_000,
                envelope=envelope,
            )
        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        bridge.assert_called_once()
        socket_factory.assert_not_called()

    def test_bridge_exit_phase_controls_fallback_eligibility(self) -> None:
        lane = self.client.BrokerLaneSnapshot(
            name="green",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "green.sock",
        )
        bundle = self.root / "bundle"
        bundle.mkdir()
        runtime = bundle / "runtime"
        runtime.write_bytes(b"runtime")
        runtime.chmod(0o500)
        request = {
            "protocol_version": 1,
            "request_id": "bridge-phase-1",
            "operation": "dispatcher_ping",
            "timeout_ms": 5_000,
            "host_context": "generic",
        }
        now = time.monotonic()
        for returncode, expected in (
            (3, self.client._DispatcherPreRequestError),
            (4, self.client._DispatcherPostRequestError),
            (2, self.client._DispatcherPostRequestError),
        ):
            process = mock.Mock(returncode=returncode)
            with self.subTest(returncode=returncode), mock.patch.object(
                self.client, "_broker_root", return_value=self.root
            ), mock.patch.object(
                self.client,
                "_verify_published_version",
                return_value=(bundle, runtime, self.root / "manifest"),
            ), mock.patch.object(
                self.client.subprocess, "Popen", return_value=process
            ) as popen, mock.patch.object(
                self.client,
                "_collect_bounded_output",
                return_value=(b"", b"", None),
            ):
                with self.assertRaises(expected):
                    self.client._invoke_dispatcher_bridge(
                        lane=lane,
                        request=request,
                        deadline=now + 5,
                        handshake_deadline=now + 2,
                    )
            self.assertEqual(
                popen.call_args.args[0],
                [str(runtime), "dispatcher-client", "--protocol", "1"],
            )

    def test_client_upgrade_uses_one_captured_blue_tuple(self) -> None:
        self._fixture()
        socket_path = self.root / "blue-upgrade.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(1)
        socket_path.chmod(0o600)
        self.addCleanup(listener.close)
        envelope = self._envelope(
            route="gemini", action="advisory", request_id="blue-upgrade-1"
        )
        payload = self.client._native_document(envelope)
        observed: dict[str, object] = {}
        blue = self.client.BrokerLaneSnapshot(
            name="blue",
            generation=7,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=socket_path,
        )

        def server() -> None:
            peer, _address = listener.accept()
            with peer:
                frame = self.client._read_broker_frame(
                    peer,
                    max_bytes=self.client.BROKER_MAX_REQUEST_BYTES,
                    deadline=time.monotonic() + 2,
                )
                observed.update(frame)
                response = {
                    "protocol_version": 1,
                    "request_id": envelope.request_id,
                    "status": "unavailable",
                    "error": "fixture route unavailable",
                }
                peer.sendall(
                    self.client._encode_broker_frame(
                        response, max_bytes=self.client.BROKER_MAX_RESPONSE_BYTES
                    )
                )

        thread = threading.Thread(target=server)
        thread.start()
        client_resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=self.root / "new-client-runtime",
            manifest_digest="b" * 64,
            artifact_digest="a" * 64,
        )
        with mock.patch.object(
            self.client, "_capture_broker_lanes", return_value=((blue,), None)
        ) as capture:
            result = self.client._launch_broker(
                resolution=client_resolution,
                payload=payload,
                timeout_ms=30_000,
                envelope=envelope,
            )
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        self.assertEqual(observed["artifact_sha256"], "c" * 64)
        self.assertEqual(observed["manifest_sha256"], "d" * 64)
        capture.assert_called_once_with(client_resolution)

    def test_green_connect_refusal_falls_back_before_blue_send(self) -> None:
        self._fixture()
        blue_socket = self.root / "blue-fallback.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(blue_socket))
        listener.listen(1)
        blue_socket.chmod(0o600)
        self.addCleanup(listener.close)
        envelope = self._envelope(
            route="opencode", action="plan", request_id="green-fallback-1"
        )
        payload = self.client._native_document(envelope)
        observed: dict[str, object] = {}
        green = self.client.BrokerLaneSnapshot(
            name="green",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label="com.agent-collab.provider-dispatcher.test",
            socket_path=self.root / "missing-green.sock",
        )
        blue = self.client.BrokerLaneSnapshot(
            name="blue",
            generation=2,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=blue_socket,
        )

        def server() -> None:
            peer, _address = listener.accept()
            with peer:
                frame = self.client._read_broker_frame(
                    peer,
                    max_bytes=self.client.BROKER_MAX_REQUEST_BYTES,
                    deadline=time.monotonic() + 2,
                )
                observed.update(frame)
                response = {
                    "protocol_version": 1,
                    "request_id": envelope.request_id,
                    "status": "unavailable",
                    "error": "fixture route unavailable",
                }
                peer.sendall(
                    self.client._encode_broker_frame(
                        response, max_bytes=self.client.BROKER_MAX_RESPONSE_BYTES
                    )
                )

        thread = threading.Thread(target=server)
        thread.start()
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=self.root / "runtime",
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        with mock.patch.object(
            self.client,
            "_capture_broker_lanes",
            return_value=((green, blue), None),
        ) as capture:
            result = self.client._launch_broker(
                resolution=resolution,
                payload=payload,
                timeout_ms=30_000,
                envelope=envelope,
            )
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        self.assertEqual(observed["artifact_sha256"], "a" * 64)
        self.assertEqual(observed["manifest_sha256"], "b" * 64)
        capture.assert_called_once_with(resolution)

    def test_green_connect_timeout_falls_back_with_blue_deadline_remaining(self) -> None:
        self._fixture()
        envelope = self._envelope(
            route="gemini",
            action="advisory",
            request_id="green-timeout-1",
            timeout_ms=1_000,
        )
        payload = self.client._native_document(envelope)
        green = self.client.BrokerLaneSnapshot(
            name="green",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label="com.agent-collab.provider-dispatcher.test",
            socket_path=self.root / "slow-green.sock",
        )
        blue = self.client.BrokerLaneSnapshot(
            name="blue",
            generation=2,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=self.root / "blue.sock",
        )
        blue_peer = mock.MagicMock()
        blue_peer.__enter__.return_value = blue_peer
        response = {
            "protocol_version": 1,
            "request_id": envelope.request_id,
            "status": "unavailable",
            "error": "fixture route unavailable",
        }
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=self.root / "runtime",
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        with mock.patch.object(
            self.client,
            "_capture_broker_lanes",
            return_value=((green, blue), None),
        ), mock.patch.object(
            self.client,
            "_invoke_dispatcher_bridge",
            side_effect=self.client._DispatcherPreRequestError("green timed out"),
        ) as bridge, mock.patch.object(
            self.client.socket, "socket", return_value=blue_peer
        ), mock.patch.object(
            self.client, "_read_broker_frame", return_value=response
        ):
            result = self.client._launch_broker(
                resolution=resolution,
                payload=payload,
                timeout_ms=1_000,
                envelope=envelope,
            )
        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        blue_peer.connect.assert_called_once_with(str(blue.socket_path))
        blue_peer.sendall.assert_called_once()
        bridge.assert_called_once()
        self.assertLessEqual(
            bridge.call_args.kwargs["deadline"]
            - bridge.call_args.kwargs["handshake_deadline"],
            0.5,
        )
        self.assertGreater(blue_peer.settimeout.call_args_list[0].args[0], 0)

    def test_green_handshake_reserves_time_for_blue_before_any_request(self) -> None:
        self._fixture()
        envelope = self._envelope(
            route="gemini",
            action="advisory",
            request_id="green-handshake-reserve-1",
            timeout_ms=10_000,
        )
        payload = self.client._native_document(envelope)
        green = self.client.BrokerLaneSnapshot(
            name="green",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "green.sock",
        )
        blue = self.client.BrokerLaneSnapshot(
            name="blue",
            generation=2,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=self.root / "blue.sock",
        )
        blue_peer = mock.MagicMock()
        blue_peer.__enter__.return_value = blue_peer
        response = {
            "protocol_version": 1,
            "request_id": envelope.request_id,
            "status": "unavailable",
            "error": "fixture route unavailable",
        }
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=self.root / "runtime",
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        with mock.patch.object(
            self.client,
            "_capture_broker_lanes",
            return_value=((green, blue), None),
        ), mock.patch.object(
            self.client,
            "_invoke_dispatcher_bridge",
            side_effect=self.client._DispatcherPreRequestError("fixture"),
        ) as bridge, mock.patch.object(
            self.client.socket, "socket", return_value=blue_peer
        ), mock.patch.object(
            self.client, "_read_broker_frame", return_value=response
        ), mock.patch.object(
            self.client.time, "monotonic", return_value=100.0
        ):
            result = self.client._launch_broker(
                resolution=resolution,
                payload=payload,
                timeout_ms=10_000,
                envelope=envelope,
            )
        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        self.assertEqual(bridge.call_args.kwargs["deadline"], 110.0)
        self.assertEqual(bridge.call_args.kwargs["handshake_deadline"], 109.0)
        blue_peer.sendall.assert_called_once()

    def test_green_fallback_preserves_one_absolute_broker_deadline(self) -> None:
        self._fixture()
        envelope = self._envelope(
            route="opencode", action="plan", request_id="fallback-deadline-1"
        )
        payload = self.client._native_document(envelope)
        green = self.client.BrokerLaneSnapshot(
            name="green",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label="com.agent-collab.provider-dispatcher.test",
            socket_path=self.root / "green.sock",
        )
        blue = self.client.BrokerLaneSnapshot(
            name="blue",
            generation=2,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=self.root / "blue.sock",
        )
        blue_peer = mock.MagicMock()
        blue_peer.__enter__.return_value = blue_peer
        now = [100.0]

        def reject_green(**_kwargs) -> None:
            now[0] = 101.5
            raise self.client._DispatcherPreRequestError("green refused")
        response = {
            "protocol_version": 1,
            "request_id": envelope.request_id,
            "status": "unavailable",
            "error": "fixture route unavailable",
        }
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=self.root / "runtime",
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        with mock.patch.object(
            self.client,
            "_capture_broker_lanes",
            return_value=((green, blue), None),
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge", side_effect=reject_green
        ), mock.patch.object(
            self.client.socket, "socket", return_value=blue_peer
        ), mock.patch.object(
            self.client, "_read_broker_frame", return_value=response
        ), mock.patch.object(
            self.client.time, "monotonic", side_effect=lambda: now[0]
        ):
            result = self.client._launch_broker(
                resolution=resolution,
                payload=payload,
                timeout_ms=30_000,
                envelope=envelope,
            )
        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        encoded = blue_peer.sendall.call_args.args[0]
        size = struct.unpack(">Q", encoded[:8])[0]
        frame = json.loads(encoded[8 : 8 + size])
        self.assertEqual(frame["deadline_monotonic_ms"], 130_000)

    def test_accepted_green_failure_never_retries_blue(self) -> None:
        self._fixture()
        envelope = self._envelope(
            route="grok", action="architecture", request_id="accepted-green-1"
        )
        payload = self.client._native_document(envelope)
        green = self.client.BrokerLaneSnapshot(
            name="green",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "accepted-green.sock",
        )
        blue = self.client.BrokerLaneSnapshot(
            name="blue",
            generation=2,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=self.root / "unused-blue.sock",
        )
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=self.root / "runtime",
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        with mock.patch.object(
            self.client,
            "_capture_broker_lanes",
            return_value=((green, blue), None),
        ), mock.patch.object(
            self.client,
            "_invoke_dispatcher_bridge",
            side_effect=self.client._DispatcherPostRequestError("accepted"),
        ) as bridge, mock.patch.object(
            self.client.socket, "socket"
        ) as socket_factory:
            result = self.client._launch_broker(
                resolution=resolution,
                payload=payload,
                timeout_ms=30_000,
                envelope=envelope,
            )
        self.assertEqual(result.status, self.client.RuntimeStatus.PROTOCOL_ERROR)
        bridge.assert_called_once()
        socket_factory.assert_not_called()

    def test_codex_seatbelt_blocks_mutating_lifecycle_before_any_read(self) -> None:
        for function_name in ("install_broker", "rollback_broker", "uninstall_broker"):
            with self.subTest(function_name=function_name), mock.patch.dict(
                os.environ, {"CODEX_SANDBOX": "seatbelt"}, clear=True
            ), mock.patch.object(
                self.client, "resolve_runtime"
            ) as resolve, mock.patch.object(
                self.client, "_broker_root"
            ) as root, mock.patch.object(
                self.client, "_read_current_broker_state"
            ) as read_state, mock.patch.object(
                self.client, "_launchctl"
            ) as launchctl:
                result = getattr(self.client, function_name)()
            self.assertEqual(result.status, self.client.RuntimeStatus.HOST_BLOCKED)
            self.assertEqual(
                result.error,
                "broker lifecycle is unavailable from the Codex seatbelt",
            )
            resolve.assert_not_called()
            root.assert_not_called()
            read_state.assert_not_called()
            launchctl.assert_not_called()

    def test_kernel_sandbox_guard_survives_marker_removal(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            self.client, "_sandbox_denies_broker_lifecycle", return_value=True
        ), mock.patch.object(
            self.client, "resolve_runtime"
        ) as resolve, mock.patch.object(
            self.client, "_broker_root"
        ) as root, mock.patch.object(
            self.client, "_launchctl"
        ) as launchctl:
            result = self.client.install_broker()
        self.assertEqual(result.status, self.client.RuntimeStatus.HOST_BLOCKED)
        resolve.assert_not_called()
        root.assert_not_called()
        launchctl.assert_not_called()

    def test_kernel_sandbox_probe_is_authoritative_and_fails_closed(self) -> None:
        probe = self.kernel_sandbox_probe
        check = mock.MagicMock(return_value=0)
        sandbox = mock.MagicMock()
        sandbox.sandbox_check = check
        no_report = mock.MagicMock(value=1 << 30)
        with mock.patch.object(
            self.client.platform, "system", return_value="Darwin"
        ), mock.patch.object(
            self.client.ctypes, "CDLL", return_value=sandbox
        ), mock.patch.object(
            self.client.ctypes.c_int, "in_dll", return_value=no_report
        ):
            self.assertFalse(probe())
        self.assertEqual(
            check.call_args.args[:3],
            (os.getpid(), b"mach-lookup", 2 | (1 << 30)),
        )
        self.assertEqual(check.call_args.args[3].value, b"com.apple.xpc.launchd")

        check.return_value = 1
        with mock.patch.object(
            self.client.platform, "system", return_value="Darwin"
        ), mock.patch.object(
            self.client.ctypes, "CDLL", return_value=sandbox
        ), mock.patch.object(
            self.client.ctypes.c_int, "in_dll", return_value=no_report
        ):
            self.assertTrue(probe())

        with mock.patch.object(
            self.client.platform, "system", return_value="Darwin"
        ), mock.patch.object(
            self.client.ctypes, "CDLL", side_effect=OSError("unavailable")
        ):
            self.assertTrue(probe())

        with mock.patch.object(
            self.client.platform, "system", return_value="Linux"
        ), mock.patch.object(self.client.ctypes, "CDLL") as loader:
            self.assertFalse(probe())
        loader.assert_not_called()

    def test_broker_frame_reader_rejects_truncated_and_oversize_payloads(self) -> None:
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        right.sendall(struct.pack(">Q", 20) + b"{}")
        right.close()
        with self.assertRaises(ValueError):
            self.client._read_broker_frame(left, max_bytes=1024, deadline=time.monotonic() + 1)

        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        right.sendall(struct.pack(">Q", 1025))
        with self.assertRaises(OverflowError):
            self.client._read_broker_frame(left, max_bytes=1024, deadline=time.monotonic() + 1)

        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        raw = b'{"value":NaN}'
        right.sendall(struct.pack(">Q", len(raw)) + raw)
        with self.assertRaises(ValueError):
            self.client._read_broker_frame(left, max_bytes=1024, deadline=time.monotonic() + 1)

        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        raw = b'{"value":1e309}'
        right.sendall(struct.pack(">Q", len(raw)) + raw)
        with self.assertRaises(ValueError):
            self.client._read_broker_frame(left, max_bytes=1024, deadline=time.monotonic() + 1)

        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        raw = b'{"value":1,"value":2}'
        right.sendall(struct.pack(">Q", len(raw)) + raw)
        with self.assertRaises(ValueError):
            self.client._read_broker_frame(left, max_bytes=1024, deadline=time.monotonic() + 1)

    def test_all_broker_only_routes_use_broker_without_direct_fallback(self) -> None:
        self._fixture()
        for route, action in (
            ("codex", "advisory"),
            ("opencode", "plan"),
            ("gemini", "advisory"),
            ("grok", "architecture"),
            ("composer", "codegen"),
        ):
            with self.subTest(route=route):
                envelope = self._envelope(route=route, action=action)
                expected = self.client.RuntimeResult(
                    self.client.RuntimeStatus.UNAVAILABLE,
                    error="provider broker is unavailable",
                )
                with mock.patch.object(
                    self.client, "_verify_macos_signature", return_value=(True, "")
                ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
                    self.client, "_launch_broker", return_value=expected
                ) as broker, mock.patch.object(self.client, "_launch_runtime") as direct:
                    result = self.client.invoke(envelope=envelope)
                self.assertIs(result, expected)
                broker.assert_called_once()
                direct.assert_not_called()

    def test_every_provider_route_is_broker_only(self) -> None:
        self.assertEqual(
            self.client.BROKERED_ROUTES,
            frozenset({"codex", "opencode", "gemini", "grok", "composer"}),
        )

    def test_broker_exchange_roundtrips_a_sealed_gemini_response(self) -> None:
        self._fixture()
        socket_path = self.root / "exchange.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(1)
        socket_path.chmod(0o600)
        self.addCleanup(listener.close)
        envelope = self._envelope(
            route="gemini", action="advisory", request_id="broker-exchange-1"
        )
        payload = self.client._native_document(envelope)
        observed: dict[str, object] = {}

        def server() -> None:
            peer, _address = listener.accept()
            with peer:
                frame = self.client._read_broker_frame(
                    peer,
                    max_bytes=self.client.BROKER_MAX_REQUEST_BYTES,
                    deadline=time.monotonic() + 2,
                )
                observed.update(frame)
                response = {
                    "protocol_version": 1,
                    "request_id": envelope.request_id,
                    "status": "ok",
                    "result": {
                        "review": "ok",
                        "governance_evidence": False,
                    },
                    "provenance": {
                        "route": envelope.route,
                        "action": envelope.action,
                        "authority": envelope.authority,
                        "author_model": "google/gemini-test",
                        "author_family": "google",
                        "host_runtime": "fixture-broker",
                        "session_identifier": "fixture-broker-session",
                        "observation_sequence": 1,
                    },
                }
                peer.sendall(
                    self.client._encode_broker_frame(
                        response, max_bytes=self.client.BROKER_MAX_RESPONSE_BYTES
                    )
                )

        thread = threading.Thread(target=server)
        thread.start()
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=self.root / "runtime",
            manifest_digest="b" * 64,
            artifact_digest="a" * 64,
        )
        lane = self.client.BrokerLaneSnapshot(
            name="blue",
            generation=0,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=socket_path,
        )
        with mock.patch.object(
            self.client, "_capture_broker_lanes", return_value=((lane,), None)
        ):
            result = self.client._launch_broker(
                resolution=resolution,
                payload=payload,
                timeout_ms=30_000,
                envelope=envelope,
            )
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result.status, self.client.RuntimeStatus.OK, result.error)
        self.assertEqual(set(observed), self.client.BROKER_FRAME_KEYS)
        self.assertEqual(observed["artifact_sha256"], "a" * 64)
        self.assertEqual(observed["manifest_sha256"], "b" * 64)
        self.assertEqual(observed["request"]["request_id"], envelope.request_id)

    def test_broker_local_failures_remain_typed_without_internal_detail(self) -> None:
        self._fixture()
        envelope = self._envelope(route="opencode", action="plan")
        expected = {
            "config_error": self.client.RuntimeStatus.CONFIG_ERROR,
            "integrity_error": self.client.RuntimeStatus.INTEGRITY_ERROR,
            "peer_error": self.client.RuntimeStatus.INTEGRITY_ERROR,
            "replay_error": self.client.RuntimeStatus.INTEGRITY_ERROR,
            "protocol_error": self.client.RuntimeStatus.PROTOCOL_ERROR,
        }
        for status, runtime_status in expected.items():
            with self.subTest(status=status):
                result = self.client._parse_broker_response(
                    {
                        "protocol_version": 1,
                        "request_id": envelope.request_id,
                        "status": status,
                        "error": "provider broker request was rejected",
                    },
                    envelope,
                )
                self.assertEqual(result.status, runtime_status)
                self.assertNotIn("/", result.error)

    def test_broker_state_and_socket_are_exact_and_fail_closed(self) -> None:
        root = self.root / "provider-broker"
        root.mkdir(mode=0o700)
        state = root / "state.json"
        socket_path = root / self.client.BROKER_SOCKET_FILENAME
        document = self.client._record_for(
            root=root,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            plist_digest="c" * 64,
            previous=None,
        )
        state.write_text(json.dumps(document), encoding="utf-8")
        state.chmod(0o600)
        with mock.patch.object(self.client, "_broker_root", return_value=root), mock.patch.object(
            self.client, "_verify_published_version"
        ), mock.patch.object(self.client, "_verify_plist_against_state"):
            result, error = self.client._load_broker_state(
                artifact_digest="a" * 64,
                manifest_digest="b" * 64,
                require_socket=False,
            )
        self.assertEqual(result, document)
        self.assertIsNone(error)

        state.chmod(0o644)
        with mock.patch.object(self.client, "_broker_root", return_value=root), mock.patch.object(
            self.client, "_verify_published_version"
        ), mock.patch.object(self.client, "_verify_plist_against_state"):
            result, error = self.client._load_broker_state(
                artifact_digest="a" * 64,
                manifest_digest="b" * 64,
                require_socket=False,
            )
        self.assertIsNone(result)
        self.assertEqual(error.status, self.client.RuntimeStatus.INTEGRITY_ERROR)

    def test_closed_plist_has_socket_activation_and_no_persistence_keys(self) -> None:
        runtime = self.root / "versions" / ("a" * 64) / "agent-collab-runtime"
        socket_path = self.root / "provider.sock"
        tmpdir = self.root / "tmp"
        document = self.client._broker_plist_document(
            runtime_path=runtime,
            socket_path=socket_path,
            tmpdir=tmpdir,
            home=Path(pwd.getpwuid(os.getuid()).pw_dir),
            uid=os.getuid(),
        )
        self.assertEqual(
            set(document),
            {
                "Label",
                "Program",
                "ProgramArguments",
                "EnvironmentVariables",
                "ProcessType",
                "ThrottleInterval",
                "Sockets",
            },
        )
        self.assertEqual(document["ProgramArguments"], [str(runtime), "broker", "--protocol", "2"])
        self.assertEqual(document["ThrottleInterval"], 0)
        self.assertNotIn("KeepAlive", document)
        self.assertNotIn("RunAtLoad", document)
        self.assertEqual(
            document["Sockets"]["ProviderBroker"]["SockPathMode"], 384
        )

    def _broker_lifecycle_patches(self, root: Path):
        socket_path = root / self.client.BROKER_SOCKET_FILENAME

        def bootstrap(_plist):
            if not socket_path.exists():
                peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    peer.bind(str(socket_path))
                finally:
                    peer.close()
                socket_path.chmod(0o600)
            return True

        return (
            mock.patch.object(self.client, "_broker_root", return_value=root),
            mock.patch.object(self.client, "_bootout_broker", return_value=True),
            mock.patch.object(self.client, "_bootstrap_broker", side_effect=bootstrap),
            mock.patch.object(self.client, "_broker_job_loaded", return_value=True),
            mock.patch.object(self.client, "_broker_ping", return_value=True),
        )

    def _dispatcher_bootstrap(self, root: Path):
        def bootstrap(plist_path: Path) -> bool:
            document = plistlib.loads(Path(plist_path).read_bytes())
            socket_path = Path(
                document["Sockets"][self.client.BROKER_SOCKET_NAME]["SockPathName"]
            )
            if socket_path.exists():
                socket_path.unlink()
            peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                peer.bind(str(socket_path))
            finally:
                peer.close()
            socket_path.chmod(0o600)
            return True

        return bootstrap

    def _install_legacy_blue(self, root: Path, *, body: str) -> tuple[bytes, bytes, dict]:
        self._fixture(body=body)
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), patches[0], patches[1], patches[2], patches[3], patches[4]:
            installed = self.client.install_broker()
        self.assertEqual(installed.status, self.client.RuntimeStatus.OK, installed.error)
        return (
            (root / "state.json").read_bytes(),
            (root / "broker.plist").read_bytes(),
            json.loads((root / "state.json").read_text(encoding="utf-8")),
        )

    def _stage_green(self, root: Path, *, body: str):
        self._fixture(body=body)
        ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK,
            result={"ready": True},
            provenance={"operation": "dispatcher_ping"},
        )
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_bootout_broker", return_value=True
        ), mock.patch.object(
            self.client,
            "_bootstrap_broker",
            side_effect=self._dispatcher_bootstrap(root),
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=True
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=ping
        ):
            staged = self.client.stage_dispatcher()
        self.assertEqual(staged.status, self.client.RuntimeStatus.OK, staged.error)
        return staged

    def test_stage_dispatcher_is_make_before_break_and_keeps_blue_selected(self) -> None:
        root = self.root / "broker-state"
        blue_state_raw, blue_plist_raw, blue = self._install_legacy_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        self._fixture(body="#!/bin/sh\nexit 7\n")
        bootout = mock.Mock(return_value=True)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_bootout_broker", bootout
        ), mock.patch.object(
            self.client,
            "_bootstrap_broker",
            side_effect=self._dispatcher_bootstrap(root),
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=True
        ), mock.patch.object(
            self.client,
            "invoke_dispatcher_ping",
            return_value=self.client.RuntimeResult(
                self.client.RuntimeStatus.OK,
                result={"ready": True},
                provenance={"operation": "dispatcher_ping"},
            ),
        ):
            staged = self.client.stage_dispatcher()

        self.assertEqual(staged.status, self.client.RuntimeStatus.OK, staged.error)
        self.assertEqual((root / "state.json").read_bytes(), blue_state_raw)
        self.assertEqual((root / "broker.plist").read_bytes(), blue_plist_raw)
        bootout.assert_not_called()
        selector = json.loads((root / "selector.json").read_text(encoding="utf-8"))
        self.assertEqual(selector["selected_lane"], "blue")
        self.assertEqual(
            selector["blue"],
            {
                "artifact_sha256": blue["artifact_sha256"],
                "manifest_sha256": blue["manifest_sha256"],
            },
        )
        self.assertEqual(selector["green"], staged.result["green"])
        token = self.client._dispatcher_lane_token(
            selector["green"]["artifact_sha256"],
            selector["green"]["manifest_sha256"],
        )
        self.assertTrue((root / f"provider-dispatcher-{token}.json").is_file())
        self.assertTrue((root / f"provider-dispatcher-{token}.plist").is_file())
        self.assertTrue((root / f"provider-dispatcher-{token}.sock").exists())

    def test_stage_dispatcher_failure_restores_selector_and_blue_byte_for_byte(self) -> None:
        root = self.root / "broker-state"
        blue_state_raw, blue_plist_raw, blue = self._install_legacy_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        selector_before = {
            "schema_version": 1,
            "generation": 7,
            "selected_lane": "blue",
            "blue": {
                "artifact_sha256": blue["artifact_sha256"],
                "manifest_sha256": blue["manifest_sha256"],
            },
            "green": None,
        }
        (root / "selector.json").write_text(
            json.dumps(selector_before, sort_keys=True, separators=(",", ":")),
            encoding="ascii",
        )
        (root / "selector.json").chmod(0o600)
        selector_raw = (root / "selector.json").read_bytes()
        self._fixture(body="#!/bin/sh\nexit 9\n")
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client,
            "_bootstrap_broker",
            side_effect=self._dispatcher_bootstrap(root),
        ), mock.patch.object(
            self.client, "_bootout_broker", return_value=True
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client,
            "invoke_dispatcher_ping",
            return_value=self.client.RuntimeResult(
                self.client.RuntimeStatus.PROTOCOL_ERROR,
                error="fixture ping failed",
            ),
        ):
            failed = self.client.stage_dispatcher()

        self.assertEqual(failed.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertEqual((root / "state.json").read_bytes(), blue_state_raw)
        self.assertEqual((root / "broker.plist").read_bytes(), blue_plist_raw)
        self.assertEqual((root / "selector.json").read_bytes(), selector_raw)
        candidate_files = sorted(
            item.name
            for item in root.iterdir()
            if item.name.startswith("provider-dispatcher-")
        )
        self.assertEqual(candidate_files, [])

    def test_commit_selector_is_one_generation_cas_and_never_boots_out_blue(self) -> None:
        root = self.root / "broker-state"
        self._install_legacy_blue(root, body="#!/bin/sh\nexit 0\n")
        self._fixture(body="#!/bin/sh\nexit 7\n")
        bootout = mock.Mock(return_value=True)
        ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK,
            result={"ready": True},
            provenance={"operation": "dispatcher_ping"},
        )
        common = (
            mock.patch.object(self.client, "_verify_macos_signature", return_value=(True, "")),
            mock.patch.object(self.client, "PLUGIN_ROOT", self.root),
            mock.patch.object(self.client, "_broker_root", return_value=root),
            mock.patch.object(self.client, "_bootout_broker", bootout),
            mock.patch.object(
                self.client,
                "_bootstrap_broker",
                side_effect=self._dispatcher_bootstrap(root),
            ),
            mock.patch.object(self.client, "_job_loaded", return_value=True),
            mock.patch.object(self.client, "_wait_for_job_idle", return_value=True),
            mock.patch.object(self.client, "invoke_dispatcher_ping", return_value=ping),
        )
        with common[0], common[1], common[2], common[3], common[4], common[5], common[6], common[7]:
            staged = self.client.stage_dispatcher()
            self.assertEqual(staged.status, self.client.RuntimeStatus.OK, staged.error)
            before = json.loads((root / "selector.json").read_text(encoding="utf-8"))
            committed = self.client.commit_dispatcher_selector()
        self.assertEqual(committed.status, self.client.RuntimeStatus.OK, committed.error)
        after = json.loads((root / "selector.json").read_text(encoding="utf-8"))
        self.assertEqual(after["generation"], before["generation"] + 1)
        self.assertEqual(after["selected_lane"], "green")
        self.assertEqual(after["blue"], before["blue"])
        self.assertEqual(after["green"], before["green"])
        bootout.assert_not_called()

    def test_selector_write_failure_leaves_blue_selection_byte_identical(self) -> None:
        root = self.root / "broker-state"
        self._install_legacy_blue(root, body="#!/bin/sh\nexit 0\n")
        self._fixture(body="#!/bin/sh\nexit 7\n")
        ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK,
            result={"ready": True},
            provenance={"operation": "dispatcher_ping"},
        )
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client,
            "_bootstrap_broker",
            side_effect=self._dispatcher_bootstrap(root),
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=True
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=ping
        ):
            self.assertEqual(self.client.stage_dispatcher().status, self.client.RuntimeStatus.OK)
            before = (root / "selector.json").read_bytes()
            original = self.client._write_private_atomic

            def fail_selector(path, content, *, mode):
                if Path(path).name == self.client.BROKER_SELECTOR_FILENAME:
                    raise OSError("fixture selector write denied")
                return original(path, content, mode=mode)

            with mock.patch.object(
                self.client, "_write_private_atomic", side_effect=fail_selector
            ):
                failed = self.client.commit_dispatcher_selector()
        self.assertEqual(failed.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertEqual((root / "selector.json").read_bytes(), before)

    def test_abort_candidate_removes_only_green_and_keeps_blue_byte_identical(self) -> None:
        root = self.root / "broker-state"
        blue_state_raw, blue_plist_raw, _blue = self._install_legacy_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        staged = self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        selector_before = json.loads(
            (root / "selector.json").read_text(encoding="utf-8")
        )
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_bootout_broker", return_value=True
        ) as bootout, mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ):
            aborted = self.client.abort_dispatcher_candidate()

        self.assertEqual(aborted.status, self.client.RuntimeStatus.OK, aborted.error)
        self.assertEqual((root / "state.json").read_bytes(), blue_state_raw)
        self.assertEqual((root / "broker.plist").read_bytes(), blue_plist_raw)
        selector_after = json.loads(
            (root / "selector.json").read_text(encoding="utf-8")
        )
        self.assertEqual(selector_after["generation"], selector_before["generation"] + 1)
        self.assertEqual(selector_after["selected_lane"], "blue")
        self.assertEqual(selector_after["blue"], selector_before["blue"])
        self.assertIsNone(selector_after["green"])
        token = self.client._dispatcher_lane_token(
            staged.result["green"]["artifact_sha256"],
            staged.result["green"]["manifest_sha256"],
        )
        self.assertFalse((root / f"provider-dispatcher-{token}.json").exists())
        self.assertFalse((root / f"provider-dispatcher-{token}.plist").exists())
        self.assertFalse((root / f"provider-dispatcher-{token}.sock").exists())
        bootout.assert_called_once()

    def test_recover_last_committed_blue_repairs_both_mixed_file_orders(self) -> None:
        root = self.root / "broker-state"
        blue_state_raw, blue_plist_raw, blue = self._install_legacy_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        staged = self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        green = staged.result["green"]
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ):
            _bundle, green_runtime, _manifest = self.client._verify_published_version(
                root,
                artifact_digest=green["artifact_sha256"],
                manifest_digest=green["manifest_sha256"],
            )
        candidate_plist_raw = self.client._plist_bytes(
            self.client._broker_plist_document(
                runtime_path=green_runtime,
                socket_path=root / self.client.BROKER_SOCKET_FILENAME,
                tmpdir=root / "tmp",
                home=Path(pwd.getpwuid(os.getuid()).pw_dir),
                uid=os.getuid(),
            )
        )
        candidate_state = self.client._record_for(
            root=root,
            artifact_digest=green["artifact_sha256"],
            manifest_digest=green["manifest_sha256"],
            plist_digest=hashlib.sha256(candidate_plist_raw).hexdigest(),
            previous=blue,
        )
        fixtures = (
            (self.client._state_bytes(candidate_state), blue_plist_raw),
            (blue_state_raw, candidate_plist_raw),
        )
        for state_raw, plist_raw in fixtures:
            with self.subTest(
                candidate_state=state_raw != blue_state_raw,
                candidate_plist=plist_raw != blue_plist_raw,
            ):
                (root / "state.json").write_bytes(state_raw)
                (root / "state.json").chmod(0o600)
                (root / "broker.plist").write_bytes(plist_raw)
                (root / "broker.plist").chmod(0o600)
                with mock.patch.object(
                    self.client, "_broker_root", return_value=root
                ), mock.patch.object(
                    self.client, "_verify_macos_signature", return_value=(True, "")
                ), mock.patch.object(
                    self.client, "_job_loaded", return_value=True
                ):
                    recovered = self.client.recover_last_committed_control_plane()
                self.assertEqual(
                    recovered.status, self.client.RuntimeStatus.OK, recovered.error
                )
                self.assertEqual((root / "state.json").read_bytes(), blue_state_raw)
                self.assertEqual((root / "broker.plist").read_bytes(), blue_plist_raw)

    def test_drain_retiring_boots_out_blue_only_after_green_is_committed_and_idle(self) -> None:
        root = self.root / "broker-state"
        self._install_legacy_blue(root, body="#!/bin/sh\nexit 0\n")
        self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK,
            result={"ready": True},
            provenance={"operation": "dispatcher_ping"},
        )
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=True
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=ping
        ):
            committed = self.client.commit_dispatcher_selector()
        self.assertEqual(committed.status, self.client.RuntimeStatus.OK, committed.error)
        blue_loaded = {"value": True}

        def bootout(_plist):
            blue_loaded["value"] = False
            return True

        def job_loaded(label):
            return True if label != self.client.BROKER_LABEL else blue_loaded["value"]

        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", side_effect=job_loaded
        ), mock.patch.object(
            self.client, "_observe_job_quiescent", return_value=True
        ), mock.patch.object(
            self.client, "_bootout_broker", side_effect=bootout
        ) as bootout_call, mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=ping
        ), mock.patch.object(
            self.client, "_job_process_idle", return_value=True
        ):
            drained = self.client.drain_retiring_dispatcher()

        self.assertEqual(drained.status, self.client.RuntimeStatus.OK, drained.error)
        self.assertEqual(drained.result["selected_lane"], "green")
        self.assertTrue(drained.result["blue_retired"])
        bootout_call.assert_called_once_with(root / "broker.plist")
        self.assertFalse((root / "state.json").exists())
        self.assertFalse((root / "broker.plist").exists())
        self.assertFalse((root / self.client.BROKER_SOCKET_FILENAME).exists())
        selector = json.loads((root / "selector.json").read_text(encoding="utf-8"))
        self.assertEqual(selector["selected_lane"], "green")

    def test_install_broker_publishes_exact_version_and_socket_activated_state(self) -> None:
        self._fixture()
        root = self.root / "broker-state"
        expected_artifact = json.loads(
            (self.root / "runtime-manifest.json").read_text(encoding="utf-8")
        )["artifacts"][0]["sha256"]
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = self.client.install_broker()
        self.assertEqual(result.status, self.client.RuntimeStatus.OK, result.error)
        self.assertFalse(result.result["persistent_process"])
        state = json.loads((root / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["artifact_sha256"], expected_artifact)
        self.assertIsNone(state["previous"])
        self.assertEqual(stat.S_IMODE((root / "broker.plist").stat().st_mode), 0o600)
        version = Path(state["bundle_path"]).parent
        self.assertEqual(
            version.name,
            f"{expected_artifact}-{state['manifest_sha256']}",
        )
        self.assertEqual(stat.S_IMODE(version.stat().st_mode), 0o500)
        self.assertEqual(
            self.client.runtime_bundle.compute_bundle_identity(
                json.loads((version / "runtime-manifest.json").read_text())["artifacts"][0]["files"]
            ),
            expected_artifact,
        )
        plist = plistlib.loads((root / "broker.plist").read_bytes())
        self.assertEqual(plist["Label"], self.client.BROKER_LABEL)
        self.assertNotIn("KeepAlive", plist)
        self.assertNotIn("RunAtLoad", plist)

    def test_missing_broker_root_is_uninstalled_not_an_integrity_failure(self) -> None:
        root = self.root / "never-installed"
        with mock.patch.object(self.client, "_broker_root", return_value=root):
            rolled_back = self.client.rollback_broker()
            uninstalled = self.client.uninstall_broker()

        self.assertEqual(rolled_back.status, self.client.RuntimeStatus.UNAVAILABLE)
        self.assertEqual(uninstalled.status, self.client.RuntimeStatus.OK)
        self.assertEqual(
            uninstalled.result,
            {"installed": False, "versions_retained": True},
        )

    def test_broker_update_records_one_verified_rollback_and_rollback_switches(self) -> None:
        self._fixture(body="#!/bin/sh\nexit 0\n")
        first_digest = json.loads(
            (self.root / "runtime-manifest.json").read_text(encoding="utf-8")
        )["artifacts"][0]["sha256"]
        root = self.root / "broker-state"
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), patches[0], patches[1], patches[2], patches[3], patches[4]:
            self.assertEqual(self.client.install_broker().status, self.client.RuntimeStatus.OK)
            self._fixture(body="#!/bin/sh\nexit 7\n")
            second_digest = json.loads(
                (self.root / "runtime-manifest.json").read_text(encoding="utf-8")
            )["artifacts"][0]["sha256"]
            updated = self.client.install_broker()
            self.assertEqual(updated.status, self.client.RuntimeStatus.OK, updated.error)
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["artifact_sha256"], second_digest)
            self.assertEqual(state["previous"]["artifact_sha256"], first_digest)
            rolled_back = self.client.rollback_broker()
        self.assertEqual(rolled_back.status, self.client.RuntimeStatus.OK, rolled_back.error)
        state = json.loads((root / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["artifact_sha256"], first_digest)
        self.assertEqual(state["previous"]["artifact_sha256"], second_digest)

    def test_failed_broker_update_restores_the_full_prior_rollback_state(self) -> None:
        first = self._fixture(body="#!/bin/sh\nexit 0\n")
        root = self.root / "broker-state"
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), patches[0], patches[1], patches[2], patches[3], patches[4]:
            self.assertEqual(self.client.install_broker().status, self.client.RuntimeStatus.OK)
            self._fixture(body="#!/bin/sh\nexit 7\n")
            self.assertEqual(self.client.install_broker().status, self.client.RuntimeStatus.OK)
            prior = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertIsNotNone(prior["previous"])
            self._fixture(body="#!/bin/sh\nexit 9\n")
            with mock.patch.object(
                self.client, "_bootstrap_broker", side_effect=[False, True]
            ):
                failed = self.client.install_broker()
        self.assertEqual(failed.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertTrue(failed.result["restored_previous"])
        state = json.loads((root / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state, prior)

    def test_legacy_restore_writes_committed_state_before_prior_plist_and_bootstrap(self) -> None:
        self._fixture(body="#!/bin/sh\nexit 0\n")
        root = self.root / "broker-state"
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), patches[0], patches[1], patches[2], patches[3], patches[4]:
            self.assertEqual(self.client.install_broker().status, self.client.RuntimeStatus.OK)

        self._fixture(body="#!/bin/sh\nexit 7\n")
        writes: list[str] = []
        bootstraps: list[str] = []
        original_write = self.client._write_private_atomic

        def write(path, content, *, mode):
            writes.append(Path(path).name)
            return original_write(path, content, mode=mode)

        def bootstrap(path):
            bootstraps.append(Path(path).name)
            return len(bootstraps) > 1

        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_bootout_broker", return_value=True
        ), mock.patch.object(
            self.client, "_bootstrap_broker", side_effect=bootstrap
        ), mock.patch.object(
            self.client, "_broker_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "_write_private_atomic", side_effect=write
        ):
            failed = self.client.install_broker()

        self.assertEqual(failed.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertTrue(failed.result["restored_previous"])
        self.assertEqual(writes[-2:], ["state.json", "broker.plist"])
        self.assertEqual(bootstraps, ["broker.plist", "broker.plist"])

    def test_noop_broker_install_preserves_existing_rollback_target(self) -> None:
        root = self.root / "broker-state"
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), patches[0], patches[1], patches[2], patches[3], patches[4]:
            self._fixture(body="#!/bin/sh\nexit 0\n")
            self.assertEqual(self.client.install_broker().status, self.client.RuntimeStatus.OK)
            self._fixture(body="#!/bin/sh\nexit 7\n")
            self.assertEqual(self.client.install_broker().status, self.client.RuntimeStatus.OK)
            prior = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertIsNotNone(prior["previous"])
            repeated = self.client.install_broker()

        self.assertEqual(repeated.status, self.client.RuntimeStatus.OK, repeated.error)
        state = json.loads((root / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state, prior)

    def test_same_artifact_with_new_manifest_gets_a_distinct_immutable_version(self) -> None:
        self._fixture()
        artifact_digest = json.loads(
            (self.root / "runtime-manifest.json").read_text(encoding="utf-8")
        )["artifacts"][0]["sha256"]
        root = self.root / "broker-state"
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), patches[0], patches[1], patches[2], patches[3], patches[4]:
            self.assertEqual(self.client.install_broker().status, self.client.RuntimeStatus.OK)
            first = json.loads((root / "state.json").read_text(encoding="utf-8"))
            manifest_path = self.root / "runtime-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            updated = self.client.install_broker()

        self.assertEqual(updated.status, self.client.RuntimeStatus.OK, updated.error)
        second = json.loads((root / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(second["artifact_sha256"], artifact_digest)
        self.assertNotEqual(second["manifest_sha256"], first["manifest_sha256"])
        self.assertNotEqual(second["bundle_path"], first["bundle_path"])
        self.assertEqual(second["previous"]["manifest_sha256"], first["manifest_sha256"])
        self.assertEqual(len(tuple((root / "versions").iterdir())), 2)

    def test_unverified_current_version_is_not_recorded_as_rollback(self) -> None:
        root = self.root / "broker-state"
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), patches[0], patches[1], patches[2], patches[3], patches[4]:
            self._fixture(body="#!/bin/sh\nexit 0\n")
            self.assertEqual(self.client.install_broker().status, self.client.RuntimeStatus.OK)
            current = json.loads((root / "state.json").read_text(encoding="utf-8"))
            Path(current["manifest_path"]).chmod(0o600)
            self._fixture(body="#!/bin/sh\nexit 7\n")
            updated = self.client.install_broker()

        self.assertEqual(updated.status, self.client.RuntimeStatus.OK, updated.error)
        state = json.loads((root / "state.json").read_text(encoding="utf-8"))
        self.assertIsNone(state["previous"])

    def test_uninstall_removes_mutable_state_but_retains_versions(self) -> None:
        self._fixture()
        root = self.root / "broker-state"
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), patches[0], patches[1], patches[2], patches[3], patches[4]:
            self.assertEqual(self.client.install_broker().status, self.client.RuntimeStatus.OK)
            result = self.client.uninstall_broker()
        self.assertEqual(result.status, self.client.RuntimeStatus.OK, result.error)
        self.assertTrue(result.result["versions_retained"])
        self.assertTrue(any((root / "versions").iterdir()))
        self.assertFalse((root / "state.json").exists())
        self.assertFalse((root / "broker.plist").exists())
        self.assertFalse((root / self.client.BROKER_SOCKET_FILENAME).exists())

    def test_foreign_or_malformed_broker_plist_blocks_update(self) -> None:
        self._fixture()
        root = self.root / "broker-state"
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), patches[0], patches[1], patches[2], patches[3], patches[4]:
            self.assertEqual(self.client.install_broker().status, self.client.RuntimeStatus.OK)
            (root / "broker.plist").chmod(0o644)
            result = self.client.install_broker()
        self.assertEqual(result.status, self.client.RuntimeStatus.INTEGRITY_ERROR)

    def test_launchctl_wrapper_uses_exact_binary_domain_and_scrubbed_environment(self) -> None:
        process = mock.Mock(returncode=0)
        with mock.patch.object(
            self.client.subprocess, "Popen", return_value=process
        ) as popen, mock.patch.object(
            self.client, "_collect_bounded_output", return_value=(b"state = not running\n", b"", None)
        ):
            result = self.client._launchctl(
                ["print", f"gui/{os.getuid()}/{self.client.BROKER_LABEL}"]
            )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(popen.call_args.args[0][0], "/bin/launchctl")
        self.assertEqual(
            popen.call_args.args[0][1:],
            ["print", f"gui/{os.getuid()}/{self.client.BROKER_LABEL}"],
        )
        self.assertEqual(
            set(popen.call_args.kwargs["env"]),
            {"HOME", "PATH", "LANG", "LC_ALL"},
        )

    def test_lifecycle_entrypoints_map_launchctl_runtime_errors_to_typed_failures(self) -> None:
        root = self.root / "broker-state"
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), patches[0], patches[1], patches[2], patches[3], patches[4]:
            self._fixture(body="#!/bin/sh\nexit 0\n")
            self.assertEqual(self.client.install_broker().status, self.client.RuntimeStatus.OK)
            self._fixture(body="#!/bin/sh\nexit 7\n")
            self.assertEqual(self.client.install_broker().status, self.client.RuntimeStatus.OK)

            with mock.patch.object(
                self.client, "_broker_job_loaded", side_effect=RuntimeError("timeout")
            ):
                status = self.client.broker_status()
            with mock.patch.object(
                self.client, "_activate_broker_record", side_effect=RuntimeError("timeout")
            ):
                installed = self.client.install_broker()
                rolled_back = self.client.rollback_broker()
            with mock.patch.object(
                self.client, "_bootout_broker", side_effect=RuntimeError("timeout")
            ):
                uninstalled = self.client.uninstall_broker()

        for result in (status, installed, rolled_back, uninstalled):
            with self.subTest(status=result.status):
                self.assertEqual(result.status, self.client.RuntimeStatus.INTEGRITY_ERROR)

    def test_broker_idle_requires_no_live_pid_and_an_explicit_stopped_state(self) -> None:
        cases = (
            ("state = not running\n", True),
            ("state = exited\n", True),
            ("state = running\npid = 123\n", False),
            ("pid = 123\n", False),
            ("", False),
            # A stopped job still lists its listening socket endpoints as
            # `state = active`; those must not veto the terminal job state.
            ("state = not running\nstate = active\nstate = active\n", True),
            # A running socket-activated job reports a live pid alongside the
            # active socket endpoints.
            ("state = running\npid = 123\nstate = active\n", False),
        )
        for output, expected in cases:
            with self.subTest(output=output), mock.patch.object(
                self.client,
                "_launchctl",
                return_value=subprocess.CompletedProcess([], 0, output, ""),
            ):
                self.assertEqual(self.client._broker_process_idle(), expected)

    def test_broker_ping_half_closes_so_the_broker_observes_the_peer(self) -> None:
        events: list[str] = []

        class _FakePeer:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def settimeout(self_inner, _value):
                pass

            def connect(self_inner, _address):
                events.append("connect")

            def shutdown(self_inner, how):
                events.append(f"shutdown:{how}")

            def recv(self_inner, _count):
                events.append("recv")
                return b""

        with mock.patch.object(self.client.socket, "socket", return_value=_FakePeer()), \
                mock.patch.object(self.client, "_wait_for_broker_exit", return_value=True):
            self.assertTrue(self.client._broker_ping(Path("/tmp/broker.sock")))
        # The peer connects, half-closes the write side (so the broker's frame
        # read hits end-of-stream), and waits for the broker to close before
        # polling for exit.
        self.assertEqual(
            events, ["connect", f"shutdown:{self.client.socket.SHUT_WR}", "recv"]
        )

    def test_broker_ping_hold_open_covers_the_runtime_cold_start(self) -> None:
        # The activation ping's socket timeout is the hold-open window: the
        # broker must observe a live peer before the client's recv gives up.
        # A freshly published bundle cold-starts in 6-12s (first-exec
        # signature validation + interpreter init on non-page-cached files),
        # so a short hold recreates the ENOTCONN peer-gone race on every
        # first activation after a fresh publish.
        timeouts: list[float] = []

        class _FakePeer:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def settimeout(self_inner, value):
                timeouts.append(value)

            def connect(self_inner, _address):
                pass

            def shutdown(self_inner, _how):
                pass

            def recv(self_inner, _count):
                return b""

        with mock.patch.object(self.client.socket, "socket", return_value=_FakePeer()), \
                mock.patch.object(self.client, "_wait_for_broker_exit", return_value=True):
            self.assertTrue(self.client._broker_ping(Path("/tmp/broker.sock")))
        self.assertEqual(timeouts, [self.client.BROKER_COLD_START_TIMEOUT_SECONDS])
        self.assertGreaterEqual(self.client.BROKER_COLD_START_TIMEOUT_SECONDS, 15.0)

    def test_wait_for_broker_exit_outlasts_the_runtime_cold_start(self) -> None:
        # Simulated clock: the broker only reaches a terminal launchd state
        # 12s after the poll starts (observed real cold-start upper bound).
        # The exit wait must outlast that, or the primary activation path
        # spuriously fails and the restore path masks it.
        clock = [0.0]

        def _monotonic() -> float:
            return clock[0]

        def _sleep(seconds: float) -> None:
            clock[0] += seconds

        def _idle() -> bool:
            return clock[0] >= 12.0

        with mock.patch.object(self.client.time, "monotonic", side_effect=_monotonic), \
                mock.patch.object(self.client.time, "sleep", side_effect=_sleep), \
                mock.patch.object(self.client, "_broker_process_idle", side_effect=_idle):
            self.assertTrue(self.client._wait_for_broker_exit())

    def test_host_context_requires_the_exact_complete_codex_desktop_tuple(self) -> None:
        keys = self.client.CODEX_DESKTOP_TUPLE
        exact = dict(self.client.CODEX_DESKTOP_TUPLE.items())
        cases = (
            ({}, "generic"),
            ({next(iter(keys)): next(iter(exact.values()))}, "generic"),
            (exact, "codex_desktop"),
            ({**exact, "CODEX_CI": "0"}, "generic"),
        )
        for environment, expected in cases:
            with self.subTest(environment=environment):
                with mock.patch.dict(os.environ, environment, clear=True):
                    self.assertEqual(self.client.classify_host_context(), expected)

    def test_hostile_environment_is_not_forwarded_to_native_runtime(self) -> None:
        self._fixture()
        envelope = self._envelope(request_id="hostile-environment")
        hostile = {
            "HOME": str(self.root / "attacker-home"),
            "LEAK_ME": "secret",
            "AGENT_COLLAB_GROK_RUNTIME_ROOT": str(self.root / "grok-root"),
            "AGENT_COLLAB_CODEX_RUNTIME_ROOT": str(self.root / "codex-root"),
            "AGENT_COLLAB_OPENCODE_RUNTIME_ROOT": str(self.root / "opencode-root"),
            **self.client.CODEX_DESKTOP_TUPLE,
        }
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.dict(os.environ, hostile, clear=True), mock.patch.object(
            self.client, "PLUGIN_ROOT", self.root
        ), mock.patch.object(
            self.client, "_launch_broker", side_effect=self._fixture_broker
        ):
            result = self.client.invoke(envelope=envelope)
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result["home"], pwd.getpwuid(os.getuid()).pw_dir)
        self.assertEqual(result.result["host_context"], "codex_desktop")
        self.assertFalse(result.result["secret_present"])

    def test_management_uses_fixed_signed_runtime_argv_and_scrubbed_env(self) -> None:
        self._management_fixture()
        hostile = {
            "HOME": str(self.root / "attacker-home"),
            "LEAK_ME": "secret",
            **self.client.CODEX_DESKTOP_TUPLE,
        }
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.dict(os.environ, hostile, clear=True), mock.patch.object(
            self.client, "PLUGIN_ROOT", self.root
        ):
            result = self.client.manage_runtime(
                action="status",
                request_id="management-status",
                timeout_ms=30_000,
            )
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result["argv"], ["invoke", "--protocol", "1"])
        self.assertEqual(result.result["management_action"], "status")
        self.assertEqual(result.result["host_context"], "codex_desktop")
        self.assertFalse(result.result["secret_present"])
        self.assertFalse(result.result["tuple_present"])
        self.assertEqual(result.result["home"], pwd.getpwuid(os.getuid()).pw_dir)

    def test_management_rejects_unknown_action_before_runtime_resolution(self) -> None:
        with mock.patch.object(self.client, "resolve_runtime") as resolve:
            result = self.client.manage_runtime(
                action="execute",
                request_id="management-rejected",
                timeout_ms=30_000,
            )
        self.assertEqual(result.status, self.client.RuntimeStatus.CONFIG_ERROR)
        resolve.assert_not_called()

    def test_management_malformed_response_is_protocol_error(self) -> None:
        self._fixture(
            body="#!/usr/bin/env python3\nimport sys\nsys.stdout.write('not-json\\n')\n"
        )
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
            result = self.client.manage_runtime(
                action="status",
                request_id="management-bad-json",
                timeout_ms=30_000,
            )
        self.assertEqual(result.status, self.client.RuntimeStatus.PROTOCOL_ERROR)

    def test_management_login_inherits_stderr_but_parses_stdout(self) -> None:
        self._fixture(
            body="""#!/usr/bin/env python3
import json, sys
request = json.loads(sys.stdin.readline())
sys.stderr.write("device-login-prompt\\n")
sys.stderr.flush()
print(json.dumps({
    "protocol_version": 1,
    "request_id": request["request_id"],
    "status": "ok",
    "result": {"authenticated": True},
}))
"""
        )
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
            result = self.client.manage_runtime(
                action="grok_login",
                request_id="management-login",
                timeout_ms=30_000,
            )
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertTrue(result.result["authenticated"])

    def test_management_login_relay_remains_output_bounded(self) -> None:
        self._fixture(
            body="""#!/usr/bin/env python3
import json, sys
request = json.loads(sys.stdin.readline())
sys.stderr.write("x" * 256)
sys.stderr.flush()
print(json.dumps({
    "protocol_version": 1,
    "request_id": request["request_id"],
    "status": "ok",
    "result": {"authenticated": True},
}))
"""
        )
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "MAX_RESPONSE_BYTES", 64
        ):
            result = self.client.manage_runtime(
                action="grok_login",
                request_id="management-login-limit",
                timeout_ms=30_000,
            )
        self.assertEqual(result.status, self.client.RuntimeStatus.OUTPUT_LIMIT)

    def test_each_invocation_gets_a_fresh_isolated_tmpdir(self) -> None:
        self._fixture()
        caller_tmpdir = self.root / "caller-tmp-fresh"
        caller_tmpdir.mkdir()
        observed = []
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.dict(
            os.environ, {"TMPDIR": str(caller_tmpdir)}, clear=False
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_launch_broker", side_effect=self._fixture_broker
        ):
            for request_id in ("fresh-1", "fresh-2"):
                result = self.client.invoke(
                    envelope=self._envelope(request_id=request_id)
                )
                self.assertEqual(result.status, self.client.RuntimeStatus.OK)
                observed.append(Path(result.result["tmpdir"]))

        self.assertEqual(len(set(observed)), 2)
        self.assertTrue(all(path != caller_tmpdir for path in observed))
        self.assertTrue(all(not path.exists() for path in observed))

    def test_policy_safe_mode_never_launches_native_runtime(self) -> None:
        self._fixture()
        policy = self.client._load_host_policy()
        with mock.patch.dict(os.environ, {"AGENT_COLLAB_SAFE_MODE": "1"}, clear=False):
            decision = policy.issue_policy_envelope(
                request_id="req-safe",
                route="codex",
                action="advisory",
                governance=False,
                prompt="review",
                timeout_ms=30_000,
                explicit_config={},
                row_config={"model": "openai/codex", "effort": "high", "mode": "prompt-only"},
            )
        self.assertEqual(decision.status, policy.PreflightStatus.UNAVAILABLE)
        self.assertIsNone(decision.envelope)
        self.assertIn("safe mode disables native routes", decision.warning)
        self.assertNotIn("retains async inbox", decision.warning)

    def test_symlink_and_parent_escape_are_rejected(self) -> None:
        binary = self._fixture()
        binary.parent.chmod(0o700)
        real = binary.with_name("real-runtime")
        binary.rename(real)
        binary.symlink_to(real.name)
        binary.parent.chmod(0o500)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ):
            with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
                resolution = self.client.resolve_runtime()
        self.assertEqual(resolution.status, self.client.RuntimeStatus.PATH_INVALID)

        manifest = json.loads((self.root / "runtime-manifest.json").read_text())
        manifest["artifacts"][0]["path"] = "../outside"
        (self.root / "runtime-manifest.json").write_text(json.dumps(manifest))
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
            resolution = self.client.resolve_runtime()
        self.assertEqual(
            resolution.status, self.client.RuntimeStatus.MANIFEST_INVALID
        )

    def test_size_hash_and_signature_fail_closed(self) -> None:
        binary = self._fixture()
        binary.parent.chmod(0o700)
        binary.chmod(0o700)
        binary.write_text(binary.read_text() + "# changed\n")
        binary.chmod(0o500)
        binary.parent.chmod(0o500)
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
            resolution = self.client.resolve_runtime()
        self.assertEqual(resolution.status, self.client.RuntimeStatus.INTEGRITY_ERROR)

        self._fixture()
        with mock.patch.object(
            self.client,
            "_verify_macos_signature",
            return_value=(False, "not notarized"),
        ):
            with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
                resolution = self.client.resolve_runtime()
        self.assertEqual(resolution.status, self.client.RuntimeStatus.SIGNATURE_ERROR)

    def test_hardened_runtime_requires_codesign_runtime_flag(self) -> None:
        architecture = mock.Mock(returncode=0, stdout="arm64\n", stderr="")
        load_commands = mock.Mock(
            returncode=0,
            stdout=(
                "Load command 9\n"
                "      cmd LC_BUILD_VERSION\n"
                " platform 1\n"
                "    minos 14.0\n"
            ),
            stderr="",
        )
        accepted = mock.Mock(
            returncode=0,
            stdout="",
            stderr="accepted\nsource=Notarized Developer ID\n",
        )
        verify = mock.Mock(
            returncode=0,
            stdout="",
            stderr="/tmp/agent-collab-runtime: valid on disk",
        )
        for flags, expected in (("0x0(none)", False), ("0x10000(runtime)", True)):
            with self.subTest(flags=flags):
                details = mock.Mock(
                    returncode=0,
                    stdout="",
                    stderr=(
                        "Executable=/tmp/agent-collab-runtime\n"
                        "TeamIdentifier=TESTTEAM01\n"
                        "Timestamp=Jul 12, 2026 at 12:00:00\n"
                        f"CodeDirectory v=20500 flags={flags} hashes=1\n"
                    ),
                )
                with mock.patch.object(
                    self.client.subprocess,
                    "run",
                    side_effect=[
                        architecture,
                        load_commands,
                        verify,
                        details,
                        accepted,
                    ],
                ):
                    valid, error = self.client._verify_macos_signature(
                        Path("/tmp/agent-collab-runtime"),
                        team_id="TESTTEAM01",
                        require_notarization=True,
                    )
                self.assertEqual(valid, expected)
                if not expected:
                    self.assertIn("hardened runtime", error)

    def test_runtime_requires_thin_arm64_macho_with_exact_build_minimum(self) -> None:
        valid_build = """Load command 9
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform 1
    minos 14.0
      sdk 15.0
   ntools 1
"""
        cases = (
            ("x86_64", valid_build, False),
            ("arm64 x86_64", valid_build, False),
            (
                "arm64",
                "Load command 9\n      cmd LC_VERSION_MIN_MACOSX\n  version 14.0\n",
                False,
            ),
            ("arm64", valid_build.replace("minos 14.0", "minos 13.0"), False),
            ("arm64", valid_build.replace("platform 1", "platform 2"), False),
            ("arm64", valid_build, True),
        )

        for architectures, load_commands, expected in cases:
            with self.subTest(architectures=architectures, expected=expected):
                def run(command, **_kwargs):
                    if command[0] == "/usr/bin/lipo":
                        return mock.Mock(returncode=0, stdout=architectures + "\n", stderr="")
                    if command[0] == "/usr/bin/otool":
                        return mock.Mock(returncode=0, stdout=load_commands, stderr="")
                    if command[0] == "/usr/bin/codesign" and "-dv" in command:
                        return mock.Mock(
                            returncode=0,
                            stdout="",
                            stderr=(
                                "TeamIdentifier=TESTTEAM01 flags=0x10000(runtime)\n"
                                "Timestamp=Jul 12, 2026 at 12:00:00\n"
                            ),
                        )
                    return mock.Mock(
                        returncode=0,
                        stdout="",
                        stderr="accepted\nsource=Notarized Developer ID\n",
                    )

                with mock.patch.object(self.client.subprocess, "run", side_effect=run):
                    valid, error = self.client._verify_macos_signature(
                        Path("/tmp/agent-collab-runtime"),
                        team_id="TESTTEAM01",
                        require_notarization=True,
                    )
                self.assertEqual(valid, expected)
                if not expected:
                    self.assertIn("Mach-O", error)

    def test_signature_requires_secure_timestamp_and_notarization(self) -> None:
        valid_build = (
            "Load command 9\n"
            "      cmd LC_BUILD_VERSION\n"
            " platform 1\n"
            "    minos 14.0\n"
        )
        # A bare command-line Mach-O is not an app bundle, so notarization is
        # verified via codesign's `=notarized` requirement (binds to the CDHash),
        # never `spctl --assess`. The check is purely returncode-driven: a
        # notarized Developer-ID binary passes (0); un-notarized fails (3).
        cases = (
            ("", 0, False),
            ("Timestamp=none", 0, False),
            ("Timestamp=Jul 12, 2026 at 12:00:00", 3, False),
            ("Timestamp=Jul 12, 2026 at 12:00:00", 0, True),
        )
        for timestamp, notarized_rc, expected in cases:
            with self.subTest(timestamp=timestamp, notarized_rc=notarized_rc):
                observed: list[list[str]] = []

                def run(command, **_kwargs):
                    observed.append(list(command))
                    if command[0] == "/usr/bin/lipo":
                        return mock.Mock(returncode=0, stdout="arm64\n", stderr="")
                    if command[0] == "/usr/bin/otool":
                        return mock.Mock(returncode=0, stdout=valid_build, stderr="")
                    if command[0] == "/usr/bin/codesign" and "-dv" in command:
                        return mock.Mock(
                            returncode=0,
                            stdout="",
                            stderr=(
                                "TeamIdentifier=TESTTEAM01\n"
                                "CodeDirectory v=20500 flags=0x10000(runtime)\n"
                                f"{timestamp}\n"
                            ),
                        )
                    if (
                        command[0] == "/usr/bin/codesign"
                        and "--test-requirement" in command
                    ):
                        return mock.Mock(returncode=notarized_rc, stdout="", stderr="")
                    return mock.Mock(returncode=0, stdout="", stderr="valid")

                with mock.patch.object(self.client.subprocess, "run", side_effect=run):
                    valid, error = self.client._verify_macos_signature(
                        Path("/tmp/agent-collab-runtime"),
                        team_id="TESTTEAM01",
                        require_notarization=True,
                    )
                self.assertEqual(valid, expected, error)
                # Notarization must be proven by codesign's `=notarized`
                # requirement, never by spctl.
                self.assertFalse(
                    any(cmd and cmd[0] == "/usr/sbin/spctl" for cmd in observed),
                    "notarization must not shell out to spctl",
                )
                if timestamp.startswith("Timestamp=Jul"):
                    self.assertTrue(
                        any(
                            cmd[:1] == ["/usr/bin/codesign"]
                            and "--test-requirement" in cmd
                            and "=notarized" in cmd
                            for cmd in observed
                        ),
                        "expected a codesign =notarized notarization check",
                    )
                # `--check-notarization` must never be combined with the
                # requirement — it makes ad-hoc / un-notarized binaries pass.
                self.assertFalse(
                    any("--check-notarization" in cmd for cmd in observed),
                    "--check-notarization must not be combined (fails open)",
                )

    def test_notarization_tool_failure_is_fail_closed(self) -> None:
        valid_build = (
            "Load command 9\n"
            "      cmd LC_BUILD_VERSION\n"
            " platform 1\n"
            "    minos 14.0\n"
        )
        # If the notarization codesign call raises (missing tool / timeout), the
        # verifier must fail closed — never treat an un-run check as a pass.
        for exc in (
            OSError("codesign missing"),
            subprocess.TimeoutExpired(cmd="codesign", timeout=20),
        ):
            with self.subTest(exc=type(exc).__name__):
                def run(command, **_kwargs):
                    if command[0] == "/usr/bin/lipo":
                        return mock.Mock(returncode=0, stdout="arm64\n", stderr="")
                    if command[0] == "/usr/bin/otool":
                        return mock.Mock(returncode=0, stdout=valid_build, stderr="")
                    if command[0] == "/usr/bin/codesign" and "-dv" in command:
                        return mock.Mock(
                            returncode=0,
                            stdout="",
                            stderr=(
                                "TeamIdentifier=TESTTEAM01\n"
                                "CodeDirectory v=20500 flags=0x10000(runtime)\n"
                                "Timestamp=Jul 12, 2026 at 12:00:00\n"
                            ),
                        )
                    if (
                        command[0] == "/usr/bin/codesign"
                        and "--test-requirement" in command
                    ):
                        raise exc
                    return mock.Mock(returncode=0, stdout="", stderr="valid")

                with mock.patch.object(self.client.subprocess, "run", side_effect=run):
                    valid, error = self.client._verify_macos_signature(
                        Path("/tmp/agent-collab-runtime"),
                        team_id="TESTTEAM01",
                        require_notarization=True,
                    )
                self.assertFalse(valid)
                self.assertIn("verification tool failed", error)

    def test_manifest_rejects_cross_platform_path_mismatch(self) -> None:
        self._fixture()
        manifest_path = self.root / "runtime-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        artifact = manifest["artifacts"][0]
        artifact["platform"] = (
            "linux" if artifact["platform"] == "darwin" else "darwin"
        )
        manifest_path.write_text(json.dumps(manifest))
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
            resolution = self.client.resolve_runtime()
        self.assertEqual(
            resolution.status, self.client.RuntimeStatus.MANIFEST_INVALID
        )

    def test_role_target_authority_contract_is_exact(self) -> None:
        policy = self.client._load_host_policy()
        decision = policy.issue_policy_envelope(
            request_id="req-invalid",
            route="composer",
            action="codegen",
            governance=True,
            prompt="generate a patch",
            timeout_ms=30_000,
            artifact_author_model="google/gemini",
            artifact_content="artifact",
            explicit_config={
                "primary_id": "claude",
                "active_model": "anthropic/claude-opus",
                "host_runtime": "claude-code",
                "session_identifier": "c-1",
            },
            row_config={},
        )
        self.assertEqual(decision.status, policy.PreflightStatus.CONFIG_ERROR)

        malformed = policy.issue_policy_envelope(
            request_id="bad\nrequest",
            route="codex",
            action="advisory",
            governance=False,
            prompt="review",
            timeout_ms=30_000,
            explicit_config={},
            row_config={"model": "openai/codex", "effort": "high", "mode": "prompt-only"},
        )
        self.assertEqual(malformed.status, policy.PreflightStatus.CONFIG_ERROR)

    def test_unadvertised_native_role_is_typed_unavailable(self) -> None:
        self._fixture(contracts=[("codex", "advisory")])
        policy = self.client._load_host_policy()
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ):
            with mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
                policy, "PLUGIN_ROOT", self.root
            ):
                decision = policy.issue_policy_envelope(
                    request_id="req-composer",
                    route="composer",
                    action="codegen",
                    governance=False,
                    prompt="generate",
                    timeout_ms=30_000,
                    explicit_config={
                        "primary_id": "claude",
                        "active_model": "anthropic/claude-opus",
                        "host_runtime": "claude-code",
                        "session_identifier": "c-1",
                    },
                    row_config={},
                )
        self.assertEqual(decision.status, policy.PreflightStatus.UNAVAILABLE)

    def test_gemini_advisory_is_read_only_native_execution(self) -> None:
        self._fixture()
        envelope = self._envelope(
            route="gemini", action="advisory", request_id="req-gemini", prompt="review"
        )
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ):
            with mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
                self.client, "_launch_broker", side_effect=self._fixture_broker
            ):
                result = self.client.invoke(envelope=envelope)
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.provenance["author_family"], "google")

    def test_codex_build_is_resolvable_but_typed_unavailable(self) -> None:
        policy = self.client._load_host_policy()
        decision = policy.issue_policy_envelope(
            request_id="req-codex-build",
            route="codex",
            action="build",
            governance=False,
            prompt="implement",
            timeout_ms=30_000,
            explicit_config={},
            row_config={},
        )
        self.assertEqual(decision.status, policy.PreflightStatus.UNAVAILABLE)
        self.assertIsNone(decision.envelope)
        self.assertIn(("codex", "build"), self.client.TEMPORARILY_UNAVAILABLE_CONTRACTS)
        self.assertNotIn(("codex", "build"), self.client.SUPPORTED_CONTRACTS)

    def test_response_provenance_must_match_sealed_author_family(self) -> None:
        self._fixture()
        envelope = self._envelope(
            route="opencode", action="plan", request_id="req-family", prompt="plan"
        )
        envelope = replace(envelope, target_author_family="google")
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ):
            with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
                result = self.client.invoke(envelope=envelope)
        self.assertEqual(result.status, self.client.RuntimeStatus.CONFIG_ERROR)

    def test_response_family_is_derived_from_author_model(self) -> None:
        for author_model, author_family in (
            ("google/gemini-2.5-pro", "zhipu"),
            ("custom/unknown-model", "zhipu"),
        ):
            with self.subTest(author_model=author_model, author_family=author_family):
                self._fixture(
                    body=f"""#!/usr/bin/env python3
import json, sys
request = json.loads(sys.stdin.readline())
print(json.dumps({{
    "protocol_version": 1,
    "request_id": request["request_id"],
    "status": "ok",
    "result": {{"review": "ok"}},
    "provenance": {{
        "route": request["route"],
        "action": request["action"],
        "authority": request["authority"],
        "author_model": "{author_model}",
        "author_family": "{author_family}",
        "host_runtime": "fixture-runtime",
        "session_identifier": "fixture-session",
        "observation_sequence": 1
    }}
}}))
"""
                )
                envelope = self._envelope(route="opencode", action="plan")
                with mock.patch.object(
                    self.client, "_verify_macos_signature", return_value=(True, "")
                ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
                    self.client, "_launch_broker", side_effect=self._fixture_broker
                ):
                    result = self.client.invoke(envelope=envelope)
                self.assertEqual(result.status, self.client.RuntimeStatus.PROTOCOL_ERROR)

    def test_opencode_model_switch_updates_accepted_provenance(self) -> None:
        cases = (
            ("opencode/glm-5.2", "zhipu"),
            ("google/gemini-2.5-pro", "google"),
        )
        for model, family in cases:
            with self.subTest(model=model, family=family):
                self._fixture(
                    body=f"""#!/usr/bin/env python3
import json, sys
request = json.loads(sys.stdin.readline())
print(json.dumps({{
    "protocol_version": 1,
    "request_id": request["request_id"],
    "status": "ok",
    "result": {{"review": "ok"}},
    "provenance": {{
        "route": request["route"],
        "action": request["action"],
        "authority": request["authority"],
        "author_model": request["model"],
        "author_family": "{family}",
        "host_runtime": "fixture-runtime",
        "session_identifier": "fixture-session",
        "observation_sequence": 1
    }}
}}))
"""
                )
                envelope = self._envelope(
                    route="opencode",
                    action="plan",
                    row={"model": model, "cwd": str(self.root)},
                    opencode_model=model,
                )
                with mock.patch.object(
                    self.client, "_verify_macos_signature", return_value=(True, "")
                ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
                    self.client, "_launch_broker", side_effect=self._fixture_broker
                ):
                    result = self.client.invoke(envelope=envelope)
                self.assertEqual(result.status, self.client.RuntimeStatus.OK)
                self.assertEqual(result.provenance["author_family"], family)

    def test_response_model_is_bound_to_exact_sealed_route_model(self) -> None:
        cases = (
            (
                "opencode",
                "plan",
                {"model": "opencode/glm-5.2", "cwd": str(self.root)},
                "zhipu/glm-5.1",
                "zhipu",
            ),
            ("grok", "architecture", {"mode": "prompt-only"},
             "xai/grok-composer-2.5-fast", "xai"),
            ("composer", "codegen", {}, "xai/grok-4.5", "xai"),
        )
        for route, action, row, wrong_model, family in cases:
            with self.subTest(route=route, action=action):
                self._fixture(
                    body=f"""#!/usr/bin/env python3
import json, sys
request = json.loads(sys.stdin.readline())
print(json.dumps({{
    "protocol_version": 1,
    "request_id": request["request_id"],
    "status": "ok",
    "result": {{"text": "wrong model"}},
    "provenance": {{
        "route": request["route"],
        "action": request["action"],
        "authority": request["authority"],
        "author_model": "{wrong_model}",
        "author_family": "{family}",
        "host_runtime": "fixture-runtime",
        "session_identifier": "fixture-session",
        "observation_sequence": 1
    }}
}}))
"""
                )
                envelope = self._envelope(route=route, action=action, row=row)
                with mock.patch.object(
                    self.client, "_verify_macos_signature", return_value=(True, "")
                ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
                    self.client, "_launch_broker", side_effect=self._fixture_broker
                ):
                    result = self.client.invoke(envelope=envelope)
                self.assertEqual(result.status, self.client.RuntimeStatus.PROTOCOL_ERROR)

    def test_manifest_versions_reject_bool_and_float(self) -> None:
        for field in ("schema_version", "protocol_version"):
            for value in (True, 1.0):
                with self.subTest(field=field, value=value):
                    self._fixture()
                    manifest_path = self.root / "runtime-manifest.json"
                    manifest = json.loads(manifest_path.read_text())
                    manifest[field] = value
                    manifest_path.write_text(json.dumps(manifest))
                    with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
                        result = self.client.resolve_runtime()
                    self.assertEqual(
                        result.status, self.client.RuntimeStatus.MANIFEST_INVALID
                    )

    def test_manifest_schema_allows_only_exact_route_action_pairs(self) -> None:
        schema = json.loads(
            CLIENT.with_name("runtime-manifest.schema.json").read_text(encoding="utf-8")
        )
        item_schema = schema["properties"]["artifacts"]["items"]["properties"][
            "contracts"
        ]["items"]
        self.assertEqual(set(item_schema), {"oneOf"})
        observed = {
            (
                row["properties"]["route"]["const"],
                row["properties"]["action"]["const"],
            )
            for row in item_schema["oneOf"]
        }
        self.assertEqual(observed, self.client.SUPPORTED_CONTRACTS)
        for row in item_schema["oneOf"]:
            self.assertFalse(row["additionalProperties"])
            self.assertEqual(set(row["required"]), {"route", "action"})
        size_schema = schema["properties"]["artifacts"]["items"]["properties"][
            "size"
        ]
        self.assertEqual(self.client.MAX_ARTIFACT_BYTES, 64 * 1024 * 1024)
        self.assertEqual(size_schema["maximum"], self.client.MAX_ARTIFACT_BYTES)
        artifacts_schema = schema["properties"]["artifacts"]
        self.assertEqual(artifacts_schema["maxItems"], 1)
        self.assertTrue(artifacts_schema["uniqueItems"])

    def test_non_darwin_arm64_release_target_is_typed_unsupported(self) -> None:
        self._fixture()
        with mock.patch.object(self.client, "normalized_platform", return_value="linux"):
            with mock.patch.object(self.client, "normalized_arch", return_value="x86_64"):
                with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
                    result = self.client.resolve_runtime()
        self.assertEqual(result.status, self.client.RuntimeStatus.PLATFORM_UNSUPPORTED)

    def test_native_typed_failures_are_preserved(self) -> None:
        cases = {
            "auth_error": self.client.RuntimeStatus.AUTH_ERROR,
            "quota_error": self.client.RuntimeStatus.QUOTA_ERROR,
            "containment_error": self.client.RuntimeStatus.CONTAINMENT_ERROR,
            "cancelled": self.client.RuntimeStatus.CANCELLED,
            "input_limit": self.client.RuntimeStatus.INPUT_LIMIT,
            "timeout": self.client.RuntimeStatus.TIMEOUT,
            "output_limit": self.client.RuntimeStatus.OUTPUT_LIMIT,
            "teardown_error": self.client.RuntimeStatus.TEARDOWN_ERROR,
            "provider_error": self.client.RuntimeStatus.PROVIDER_ERROR,
            "unavailable": self.client.RuntimeStatus.UNAVAILABLE,
        }
        for native_status, expected in cases.items():
            with self.subTest(status=native_status):
                self._fixture(
                    body=f"""#!/usr/bin/env python3
import json, sys
request = json.loads(sys.stdin.readline())
print(json.dumps({{
    "protocol_version": 1,
    "request_id": request["request_id"],
    "status": "{native_status}",
    "error": "typed failure",
}}))
raise SystemExit(7)
"""
                )
                envelope = self._envelope(
                    request_id=f"typed-{native_status}", prompt="review"
                )
                with mock.patch.object(
                    self.client, "_verify_macos_signature", return_value=(True, "")
                ):
                    with mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
                        self.client, "_launch_broker", side_effect=self._fixture_broker
                    ):
                        result = self.client.invoke(envelope=envelope)
                self.assertEqual(result.status, expected)

    def test_output_limit_terminates_and_reaps_child_while_running(self) -> None:
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                marker = self.root / f"{stream}-survived"
                tmpdir_marker = self.root / f"{stream}-tmpdir"
                caller_tmpdir = self.root / f"{stream}-caller-tmp"
                caller_tmpdir.mkdir(exist_ok=True)
                target = "sys.stdout.buffer" if stream == "stdout" else "sys.stderr.buffer"
                self._fixture(
                    body=f"""#!/usr/bin/env python3
import os, pathlib, sys, time
pathlib.Path({str(tmpdir_marker)!r}).write_text(os.environ["TMPDIR"])
{target}.write(b"x" * 8192)
{target}.flush()
time.sleep(1)
pathlib.Path({str(marker)!r}).write_text("survived")
"""
                )
                envelope = self._envelope()
                with mock.patch.object(
                    self.client, "_verify_macos_signature", return_value=(True, "")
                ), mock.patch.object(
                    self.client, "PLUGIN_ROOT", self.root
                ), mock.patch.object(
                    self.client, "MAX_RESPONSE_BYTES", 1024
                ), mock.patch.dict(
                    os.environ, {"TMPDIR": str(caller_tmpdir)}, clear=False
                ), mock.patch.object(
                    self.client, "_launch_broker", side_effect=self._fixture_broker
                ):
                    result = self.client.invoke(envelope=envelope)
                self.assertEqual(result.status, self.client.RuntimeStatus.OUTPUT_LIMIT)
                self.assertFalse(marker.exists())
                child_tmpdir = Path(tmpdir_marker.read_text(encoding="utf-8"))
                self.assertNotEqual(child_tmpdir, caller_tmpdir)
                self.assertFalse(child_tmpdir.exists())

    def test_timeout_reaps_child_and_removes_isolated_tmpdir(self) -> None:
        tmpdir_marker = self.root / "timeout-tmpdir"
        caller_tmpdir = self.root / "timeout-caller-tmp"
        caller_tmpdir.mkdir()
        self._fixture(
            body=f"""#!/usr/bin/env python3
import os, pathlib, time
pathlib.Path({str(tmpdir_marker)!r}).write_text(os.environ["TMPDIR"])
time.sleep(10)
"""
        )
        envelope = self._envelope(request_id="timeout-cleanup", timeout_ms=500)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "PLUGIN_ROOT", self.root
        ), mock.patch.dict(
            os.environ, {"TMPDIR": str(caller_tmpdir)}, clear=False
        ), mock.patch.object(
            self.client, "_launch_broker", side_effect=self._fixture_broker
        ):
            result = self.client.invoke(envelope=envelope)

        self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)
        child_tmpdir = Path(tmpdir_marker.read_text(encoding="utf-8"))
        self.assertNotEqual(child_tmpdir, caller_tmpdir)
        self.assertFalse(child_tmpdir.exists())

    def test_spawn_error_removes_fresh_isolated_tmpdir(self) -> None:
        self._fixture()
        envelope = self._envelope(request_id="spawn-cleanup")
        created: list[Path] = []
        real_mkdtemp = tempfile.mkdtemp

        def recording_mkdtemp(*args, **kwargs):
            path = Path(real_mkdtemp(*args, **kwargs))
            created.append(path)
            return str(path)

        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "PLUGIN_ROOT", self.root
        ), mock.patch.object(
            self.client.tempfile, "mkdtemp", side_effect=recording_mkdtemp
        ), mock.patch.object(
            self.client.subprocess, "Popen", side_effect=OSError("spawn failed")
        ), mock.patch.object(
            self.client, "_launch_broker", side_effect=self._fixture_broker
        ):
            result = self.client.invoke(envelope=envelope)

        self.assertEqual(result.status, self.client.RuntimeStatus.SPAWN_ERROR)
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].exists())
        self.assertFalse(str(created[0]).startswith(str(self.root) + os.sep))

    def test_unexpected_collector_errors_terminate_and_reap_child(self) -> None:
        for failure_point in ("select", "read"):
            with self.subTest(failure_point=failure_point):
                marker = self.root / f"collector-{failure_point}-survived"
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import pathlib,sys,time; "
                            "sys.stdout.write('x'); sys.stdout.flush(); "
                            "time.sleep(0.5); "
                            f"pathlib.Path({str(marker)!r}).write_text('survived')"
                        ),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
                patch_target = (
                    mock.patch.object(
                        self.client.selectors.DefaultSelector,
                        "select",
                        side_effect=OSError("selector failed"),
                    )
                    if failure_point == "select"
                    else mock.patch.object(
                        self.client.os, "read", side_effect=OSError("read failed")
                    )
                )
                raised: OSError | None = None
                collected = None
                try:
                    with patch_target:
                        collected = self.client._collect_bounded_output(
                            process, timeout_ms=5_000
                        )
                except OSError as exc:
                    raised = exc
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                self.assertIsNone(raised)
                self.assertIsNotNone(collected)
                assert collected is not None
                self.assertIsNotNone(collected[2])
                self.assertEqual(
                    collected[2].status, self.client.RuntimeStatus.TEARDOWN_ERROR
                )
                time.sleep(0.6)
                self.assertFalse(marker.exists())

    def test_unsealed_or_tampered_envelope_cannot_launch(self) -> None:
        self._fixture()
        envelope = self._envelope(request_id="sealed-launch", prompt="review")
        tampered = replace(envelope, action="build")
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
            result = self.client.invoke(envelope=tampered)
        self.assertEqual(result.status, self.client.RuntimeStatus.CONFIG_ERROR)

    def test_hardlinked_or_group_writable_runtime_is_rejected(self) -> None:
        binary = self._fixture()
        binary.parent.chmod(0o700)
        hardlink = binary.with_name("hardlink")
        os.link(binary, hardlink)
        binary.parent.chmod(0o500)
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
            result = self.client.resolve_runtime()
        self.assertEqual(result.status, self.client.RuntimeStatus.PATH_INVALID)
        binary.parent.chmod(0o700)
        hardlink.unlink()
        binary.parent.chmod(0o500)

        binary.chmod(0o775)
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
            result = self.client.resolve_runtime()
        self.assertEqual(result.status, self.client.RuntimeStatus.PATH_INVALID)

    def test_native_protocol_uses_exact_route_action_fields(self) -> None:
        self._fixture()
        expected_row_fields = {
            ("gemini", "advisory"): {"model", "effort"},
            ("gemini", "long_context"): {"model", "effort", "documents"},
            ("codex", "advisory"): {"model", "effort", "mode"},
            ("opencode", "plan"): {"model", "cwd"},
            ("opencode", "build"): {"model", "cwd"},
            ("grok", "architecture"): {"mode"},
            ("grok", "governance"): {"mode"},
            ("grok", "huge_context"): {"documents"},
            ("composer", "codegen"): set(),
        }
        base = {
            "protocol_version",
            "request_id",
            "operation",
            "route",
            "action",
            "authority",
            "timeout_ms",
            "host_context",
            "prompt",
        }
        for contract, row_fields in expected_row_fields.items():
            with self.subTest(contract=contract):
                is_grok_governance = contract == ("grok", "governance")
                envelope = self._envelope(
                    route=contract[0],
                    action=contract[1],
                    governance=is_grok_governance,
                    artifact_model=(
                        "google/gemini-test" if is_grok_governance else ""
                    ),
                )
                document = json.loads(self.client._native_document(envelope))
                expected_fields = base | row_fields
                if is_grok_governance:
                    expected_fields = expected_fields | {"artifact"}
                self.assertEqual(set(document), expected_fields)
                self.assertNotIn("backend", document)
                self.assertNotIn("argv", document)
                self.assertNotIn("tools", document)
                self.assertNotIn("model_override", document)

    def test_native_protocol_binds_exact_artifact_bytes_model_and_hash(self) -> None:
        policy = self.client._load_host_policy()
        artifact_bytes = b"exact\x00artifact\xffbytes\nnot duplicated in prompt"
        with mock.patch.object(
            policy,
            "_runtime_contracts",
            return_value=(frozenset({("codex", "advisory")}), "digest-1"),
        ):
            decision = policy.issue_policy_envelope(
                request_id="artifact-native-1",
                route="codex",
                action="advisory",
                governance=True,
                prompt="Review the separately attached artifact.",
                timeout_ms=30_000,
                explicit_config={
                    "primary_id": "claude",
                    "active_model": "anthropic/claude-opus",
                    "host_runtime": "claude-code",
                    "session_identifier": "c-artifact",
                },
                row_config={
                    "model": "openai/codex",
                    "effort": "high",
                    "mode": "prompt-only",
                },
                artifact_author_model="google/gemini-2.5-pro",
                artifact_content=artifact_bytes,
            )
        self.assertIsNotNone(decision.envelope, decision.warning)
        envelope = decision.envelope
        assert envelope is not None
        document = json.loads(self.client._native_document(envelope))
        self.assertEqual(document["prompt"], "Review the separately attached artifact.")
        self.assertIn("artifact", document)
        self.assertEqual(
            set(document["artifact"]),
            {"encoding", "content", "sha256", "size", "author_model", "author_family"},
        )
        self.assertEqual(document["artifact"]["encoding"], "base64")
        self.assertEqual(
            base64.b64decode(document["artifact"]["content"], validate=True),
            artifact_bytes,
        )
        self.assertEqual(
            document["artifact"]["sha256"], hashlib.sha256(artifact_bytes).hexdigest()
        )
        self.assertEqual(document["artifact"]["size"], len(artifact_bytes))
        self.assertEqual(document["artifact"]["author_model"], "google/gemini-2.5-pro")
        self.assertEqual(document["artifact"]["author_family"], "google")

        tampered = replace(
            envelope,
            artifact_content_base64=base64.b64encode(b"different").decode("ascii"),
            seal="",
        )
        tampered = replace(
            tampered,
            seal=hmac.new(
                policy._SEAL_KEY,
                policy._unsigned_envelope(tampered),
                hashlib.sha256,
            ).hexdigest(),
        )
        with self.assertRaisesRegex(ValueError, "artifact hash"):
            self.client._native_document(tampered)

    def test_row_escape_fields_fail_and_row_model_cannot_select_anthropic(self) -> None:
        policy = self.client._load_host_policy()
        with mock.patch.object(
            policy,
            "_runtime_contracts",
            return_value=(frozenset({("opencode", "plan")}), "digest-1"),
        ):
            for row in (
                {
                    "model": "opencode/glm-5.2",
                    "cwd": "/tmp/project",
                    "argv": ["opencode", "run"],
                },
                {
                    "model": "opencode/glm-5.2",
                    "cwd": "/tmp/project",
                    "tools": ["shell"],
                },
            ):
                with self.subTest(row=row):
                    decision = policy.issue_policy_envelope(
                        request_id="deny-row",
                        route="opencode",
                        action="plan",
                        governance=False,
                        prompt="plan",
                        timeout_ms=30_000,
                        explicit_config={
                            "primary_id": "custom",
                            "active_model": "custom/unknown",
                            "host_runtime": "custom",
                            "session_identifier": "s-1",
                        },
                        row_config=row,
                    )
                    self.assertIsNone(decision.envelope)

            decision = policy.issue_policy_envelope(
                request_id="ignore-row-model",
                route="opencode",
                action="plan",
                governance=False,
                prompt="plan",
                timeout_ms=30_000,
                explicit_config={
                    "primary_id": "custom",
                    "active_model": "custom/unknown",
                    "host_runtime": "custom",
                    "session_identifier": "s-1",
                },
                row_config={"model": "anthropic/claude-sonnet", "cwd": "/tmp/project"},
            )
            self.assertIsNotNone(decision.envelope)
            assert decision.envelope is not None
            self.assertEqual(
                json.loads(decision.envelope.row_json)["model"],
                policy.DEFAULT_OPENCODE_MODEL,
            )


if __name__ == "__main__":
    unittest.main()
