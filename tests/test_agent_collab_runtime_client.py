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


def _load_client_without_fcntl():
    """Load the public client as on a platform without POSIX file locking."""

    spec = importlib.util.spec_from_file_location(
        "agent_collab_runtime_client_without_fcntl", CLIENT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    original_import = __import__

    def blocked_fcntl_import(name, *args, **kwargs):
        if name == "fcntl":
            raise ImportError("fcntl is unavailable")
        return original_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=blocked_fcntl_import):
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

    def test_module_loads_without_fcntl_and_locking_fails_before_io(self) -> None:
        client = _load_client_without_fcntl()
        with mock.patch.object(client.os, "getuid", None), mock.patch.object(
            client, "PLUGIN_ROOT", self.root,
        ):
            result = client.resolve_runtime()
        self.assertEqual(result.status, client.RuntimeStatus.PLATFORM_UNSUPPORTED)

        with mock.patch.object(client, "_exact_mode") as exact_mode, mock.patch.object(
            client.os, "open"
        ) as open_file:
            with self.assertRaisesRegex(ValueError, "locking is unavailable"):
                with client._broker_control_lock(self.root):
                    self.fail("unsupported locking must not enter the context")
        exact_mode.assert_not_called()
        open_file.assert_not_called()

    def _fixture(
        self,
        *,
        body: str | None = None,
        contracts: list[tuple[str, str]] | None = None,
        schema_version: int = 3,
        runtime_protocol_version: int = 2,
        provider_runtime_version: str = "2.0.0",
        route_contract_version: int = 2,
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
    "composer": ("xai/grok-4.5", "xai"),
    "gemini": ("google/gemini-test", "google"),
}
author_model, author_family = families[request["route"]]
print(json.dumps({
    "protocol_version": 2,
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
            "schema_version": schema_version,
            "protocol_version": runtime_protocol_version,
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
        if schema_version == 3:
            manifest["artifacts"][0].update(
                {
                    "provider_runtime_version": provider_runtime_version,
                    "route_contract_version": route_contract_version,
                }
            )
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
    "protocol_version": 2,
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
            ("composer", "codegen"): {
                "task_class": "standard_codegen",
                "effort": "medium",
            },
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
            "schema_version": 3,
            "protocol_version": 2,
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

    def test_schema3_manifest_carries_the_authenticated_runtime_contract_anchor(
        self,
    ) -> None:
        self._fixture(
            provider_runtime_version="2.0.0",
            route_contract_version=2,
        )
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ):
            resolution = self.client.resolve_runtime()

        self.assertEqual(resolution.status, self.client.RuntimeStatus.OK, resolution.error)
        self.assertEqual(
            resolution.anchor,
            self.client.RuntimeContractAnchor("2.0.0", 2),
        )

    def test_resolve_runtime_accepts_git_normalized_member_modes(self) -> None:
        # The release-critical call-site scoping: the plugin tree is git-installed,
        # so members are 0o755/0o700, and resolve_runtime() must resolve OK
        # (verify_bundle_tree tolerant=True). This is the test that would FAIL if a
        # future edit inverted the call-site tolerance flag.
        bundle = (self.root / "runtime" / "darwin-arm64" / "agent-collab-runtime.bundle")
        for member_mode, root_mode in ((0o755, 0o755), (0o700, 0o700)):
            binary = self._fixture(provider_runtime_version="2.0.0", route_contract_version=2)
            binary.chmod(member_mode)
            bundle.chmod(root_mode)
            with mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
                self.client, "_verify_macos_signature", return_value=(True, "")
            ):
                resolution = self.client.resolve_runtime()
            with self.subTest(member_mode=oct(member_mode)):
                self.assertEqual(
                    resolution.status, self.client.RuntimeStatus.OK, resolution.error
                )

    def test_resolve_runtime_admits_group_writable_member(self) -> None:
        # Trust-the-checkout: a git clone under umask 002 yields group/other-writable
        # members AND bundle dir (0o775). Those bits reflect the operator's umask on
        # their own checkout, not a grant to an attacker (a peer who can write the
        # checkout already owns the Python control plane), so resolve_runtime ADMITS
        # them; the per-member SHA-256 + Developer-ID signature remain the integrity
        # gate. This is the release-critical umask-0002 install case.
        bundle = (self.root / "runtime" / "darwin-arm64" / "agent-collab-runtime.bundle")
        binary = self._fixture(provider_runtime_version="2.0.0", route_contract_version=2)
        binary.chmod(0o775)  # group-write member (umask 002)
        bundle.chmod(0o775)  # group-write bundle dir (umask 002)
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ):
            resolution = self.client.resolve_runtime()
        self.assertEqual(
            resolution.status, self.client.RuntimeStatus.OK, resolution.error
        )

    def test_resolve_runtime_rejects_fifo_member(self) -> None:
        # The source floor still rejects a non-regular member. A FIFO swapped in for
        # a member must fail closed AND must not hang the open (O_NONBLOCK); under
        # trust-the-checkout the tolerated modes leave this type guard load-bearing.
        bundle = (self.root / "runtime" / "darwin-arm64" / "agent-collab-runtime.bundle")
        binary = self._fixture(provider_runtime_version="2.0.0", route_contract_version=2)
        bundle.chmod(0o700)
        binary.unlink()
        os.mkfifo(binary, 0o600)
        bundle.chmod(0o500)
        try:
            with mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
                self.client, "_verify_macos_signature", return_value=(True, "")
            ):
                resolution = self.client.resolve_runtime()
            self.assertNotEqual(resolution.status, self.client.RuntimeStatus.OK)
        finally:
            bundle.chmod(0o700)
            binary.unlink()

    def test_published_version_rejects_git_normalized_member(self) -> None:
        # The BROKER store is privately extracted, so exact 0o500 IS achievable and
        # is kept strict (_verify_published_version calls verify_bundle_tree with
        # tolerant=False). This pins that scoping the OTHER direction from the
        # plugin-tree test: a 0o755 member — which the tolerant plugin-tree source
        # path ACCEPTS — must be REJECTED here (the broker store requires exact
        # 0o500). It is the test that FAILS if the broker call site is flipped to
        # tolerant=True: 0o755 differs from 0o500, so it separates strict from the
        # source floor.
        self._fixture(provider_runtime_version="2.0.0", route_contract_version=2)
        (self.root / "versions").mkdir(mode=0o700)
        (self.root / "tmp").mkdir(mode=0o700)
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ):
            resolution = self.client.resolve_runtime()
            self.assertEqual(
                resolution.status, self.client.RuntimeStatus.OK, resolution.error
            )
            # Publish a clean version; its own tail self-verify (tolerant=False)
            # confirms the strict path ACCEPTS a correctly-published 0o500 tree.
            self.client._publish_broker_version(self.root, resolution=resolution)
            version = self.client._broker_version_path(
                self.root,
                artifact_digest=resolution.artifact_digest,
                manifest_digest=resolution.manifest_digest,
            )
            member = version / "agent-collab-runtime.bundle" / "agent-collab-runtime"
            original = stat.S_IMODE(member.stat().st_mode)
            self.assertEqual(original, 0o500)  # sanity: broker extracts strict
            member.chmod(0o755)  # git-normalized; the tolerant path would accept it
            try:
                with self.assertRaises(ValueError):
                    self.client._verify_published_version(
                        self.root,
                        artifact_digest=resolution.artifact_digest,
                        manifest_digest=resolution.manifest_digest,
                    )
            finally:
                member.chmod(original)

    def test_manifest_classifier_enforces_the_closed_compatibility_matrix(self) -> None:
        self._fixture()
        manifest = json.loads(
            (self.root / "runtime-manifest.json").read_text(encoding="utf-8")
        )

        current, error = self.client._manifest_entry(
            manifest,
            role="candidate",
            dispatcher_protocol_version=2,
        )
        self.assertIsNotNone(current, error)
        self.assertEqual(
            current["_anchor"],
            self.client.RuntimeContractAnchor("2.0.0", 2),
        )

        legacy = json.loads(json.dumps(manifest))
        legacy["schema_version"] = 2
        legacy["artifacts"][0].pop("provider_runtime_version")
        legacy["artifacts"][0].pop("route_contract_version")
        selected, error = self.client._manifest_entry(
            legacy,
            role="selected",
            dispatcher_protocol_version=1,
        )
        self.assertIsNotNone(selected, error)
        self.assertEqual(
            selected["_anchor"],
            self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        selected_broker, error = self.client._manifest_entry(
            legacy,
            role="selected",
            transport="broker",
            dispatcher_protocol_version=None,
        )
        self.assertIsNotNone(selected_broker, error)
        self.assertEqual(
            selected_broker["_anchor"],
            self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        for role, dispatcher_protocol in (
            ("candidate", 1),
            ("selected", 2),
            ("lifecycle", 1),
        ):
            with self.subTest(role=role, dispatcher_protocol=dispatcher_protocol):
                rejected, _error = self.client._manifest_entry(
                    legacy,
                    role=role,
                    dispatcher_protocol_version=dispatcher_protocol,
                )
                self.assertIsNone(rejected)

        lifecycle = json.loads(json.dumps(legacy))
        lifecycle["protocol_version"] = 1
        accepted_lifecycle, error = self.client._manifest_entry(
            lifecycle,
            role="lifecycle",
            dispatcher_protocol_version=None,
        )
        self.assertIsNotNone(accepted_lifecycle, error)
        self.assertIsNone(accepted_lifecycle["_anchor"])
        for role in ("candidate", "selected", "retained"):
            with self.subTest(role=role):
                rejected, _error = self.client._manifest_entry(
                    lifecycle,
                    role=role,
                    dispatcher_protocol_version=1,
                )
                self.assertIsNone(rejected)

    def test_distribution_hook_cannot_bypass_schema_anchor_or_role_matrix(self) -> None:
        self._fixture()
        manifest = json.loads(
            (self.root / "runtime-manifest.json").read_text(encoding="utf-8")
        )
        item = manifest["artifacts"][0]
        manifest["channel"] = "development"
        for record in item["files"]:
            record["signing_profile"] = "development_adhoc"
        item["sha256"] = self.client.runtime_bundle.compute_bundle_identity(
            item["files"]
        )
        development_signing = {
            "mode": "adhoc",
            "hardened_runtime": True,
            "require_notarization": False,
            "library_validation": "disabled_for_adhoc_entrypoint",
            "entrypoint_entitlements_sha256": "a" * 64,
        }
        item["signing"] = development_signing
        normalized = {
            "mode": "adhoc",
            "identity": "",
            "team_id": "",
            "require_notarization": False,
            "hardened_runtime": True,
            "secure_timestamp": False,
        }

        def development_policy(*, channel, signing, file_signing_profiles):
            self.assertEqual(channel, "development")
            self.assertEqual(signing, development_signing)
            self.assertEqual(file_signing_profiles, ("development_adhoc",))
            return dict(normalized)

        rejected, _error = self.client._manifest_entry(manifest)
        self.assertIsNone(rejected)
        with mock.patch.object(
            self.client,
            "_distribution_signing_policy",
            side_effect=development_policy,
        ):
            accepted, error = self.client._manifest_entry(manifest)
            self.assertIsNotNone(accepted, error)
            self.assertEqual(accepted["signing"], normalized)
            self.assertEqual(
                accepted["_anchor"],
                self.client.RuntimeContractAnchor("2.0.0", 2),
            )

            invalid_schema = json.loads(json.dumps(manifest))
            invalid_schema["schema_version"] = 2
            invalid_anchor = json.loads(json.dumps(manifest))
            invalid_anchor["artifacts"][0].pop("route_contract_version")
            for invalid, kwargs in (
                (invalid_schema, {}),
                (invalid_anchor, {}),
                (
                    manifest,
                    {
                        "role": "selected",
                        "transport": "broker",
                        "dispatcher_protocol_version": None,
                    },
                ),
            ):
                bypassed, _error = self.client._manifest_entry(invalid, **kwargs)
                self.assertIsNone(bypassed)

        with mock.patch.object(
            self.client,
            "_distribution_signing_policy",
            return_value={**normalized, "unexpected": True},
        ):
            malformed, _error = self.client._manifest_entry(manifest)
        self.assertIsNone(malformed)
        with mock.patch.object(
            self.client,
            "_distribution_signing_policy",
            side_effect=RuntimeError("injected policy failure"),
        ):
            failed_closed, _error = self.client._manifest_entry(manifest)
        self.assertIsNone(failed_closed)

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
        self.assertEqual(result.result["argv"], ["invoke", "--protocol", "2"])
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
            "protocol_version": 2,
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
        self.assertEqual(frame["runtime_protocol_version"], 2)
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
            "protocol_version": 2,
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
        original = dict(request)
        encoded = self.client._adoption_canary_document(request)
        document = json.loads(encoded)
        self.assertEqual(
            set(document),
            self.client.ADOPTION_CANARY_KEYS | {"host_context"},
        )
        self.assertEqual(document["operation"], "adoption_canary")
        self.assertEqual(
            document["protocol_version"],
            self.client.PROTOCOL_VERSION,
        )
        self.assertEqual(document["host_context"], "generic")
        self.assertEqual(request, original)
        self.assertEqual(request["protocol_version"], self.client.PROTOCOL_VERSION)
        self.assertNotIn("route", document)
        self.assertNotIn("action", document)
        self.assertNotIn("model", document)

        invalid = (
            self._adoption_canary_request(provider="unknown"),
            self._adoption_canary_request(protocol_version=1),
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
        request = self._adoption_canary_request()
        lane = self.client.BrokerLaneSnapshot(
            name="candidate",
            generation=7,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("a" * 64, "b" * 64)
            ),
            socket_path=self.root / "dispatcher.sock",
            transport="dispatcher",
            protocol_version=2,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        nonce = base64.urlsafe_b64encode(b"n" * 32).decode("ascii").rstrip("=")
        hello = self.client._dispatcher_build_hello(
            lane=lane,
            client_pid=4242,
            nonce=nonce,
            deadline_monotonic_ms=123_456,
            request=request,
        )
        self.assertEqual(set(hello), self.client.DISPATCHER_HELLO_KEYS)
        self.assertEqual(hello["frame_type"], "hello")
        self.assertNotIn("request", hello)
        canonical_request = self.client._dispatcher_canonical_json(request)
        self.assertEqual(hello["request_size"], len(canonical_request))
        self.assertEqual(
            hello["request_sha256"], hashlib.sha256(canonical_request).hexdigest()
        )
        self.assertEqual(hello["execution_key"], "gemini")
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
        frame = self.client._dispatcher_build_request_frame(
            session=session,
            request=request,
        )
        self.assertEqual(set(frame), self.client.DISPATCHER_REQUEST_KEYS)
        self.assertEqual(frame["request"], request)
        self.assertEqual(frame["hello_sha256"], hello_sha256)
        self.assertNotEqual(frame["ready_sha256"], hello_sha256)

        mappings = {
            ("execute", "gemini", None): "gemini",
            ("execute", "grok", None): "grok",
            ("execute", "composer", None): "grok",
            ("execute", "opencode", None): "opencode",
            ("execute", "codex", None): "codex",
            ("adoption_canary", None, "grok"): "grok",
            ("dispatcher_lock_probe", None, "opencode"): "opencode",
            ("dispatcher_ping", None, None): "dispatcher_ping",
        }
        for (operation, route, provider), expected in mappings.items():
            candidate = {"operation": operation}
            if route is not None:
                candidate["route"] = route
            if provider is not None:
                candidate["provider"] = provider
            with self.subTest(candidate=candidate):
                self.assertEqual(
                    self.client._dispatcher_execution_key(candidate), expected
                )

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
            name="selected",
            generation=7,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("a" * 64, "b" * 64)
            ),
            socket_path=self.root / "dispatcher.sock",
            transport="dispatcher",
            protocol_version=1,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        hello = self.client._dispatcher_build_hello(
            lane=lane,
            client_pid=4242,
            nonce=fixture["hello"]["nonce"],
            deadline_monotonic_ms=123_456,
            request=fixture["request"]["request"],
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

    def test_dispatcher_launchd_readiness_retries_only_root_pid_one(self) -> None:
        now = [100.0]
        sleeps: list[float] = []
        observer = mock.Mock(side_effect=[(0, 1), (0, 1), (0, 9001)])

        def sleep(delay: float) -> None:
            sleeps.append(delay)
            now[0] += delay

        credentials = self.client._await_dispatcher_launchd_credentials(
            mock.Mock(),
            deadline=101.0,
            credential_observer=observer,
            now_monotonic=lambda: now[0],
            sleeper=sleep,
        )

        self.assertEqual(credentials, (0, 9001))
        self.assertEqual(sleeps, [0.01, 0.02])
        self.assertEqual(observer.call_count, 3)

    def test_dispatcher_launchd_readiness_is_bounded_and_fail_closed(self) -> None:
        now = [100.0]
        sleeps: list[float] = []
        observer = mock.Mock(return_value=(0, 1))

        def sleep(delay: float) -> None:
            sleeps.append(delay)
            now[0] += delay

        with self.assertRaises(ValueError):
            self.client._await_dispatcher_launchd_credentials(
                mock.Mock(),
                deadline=100.025,
                credential_observer=observer,
                now_monotonic=lambda: now[0],
                sleeper=sleep,
            )
        self.assertEqual(len(sleeps), 2)
        self.assertAlmostEqual(sleeps[0], 0.01)
        self.assertAlmostEqual(sleeps[1], 0.015)
        self.assertAlmostEqual(now[0], 100.025)

        invalid = (
            (1, 1),
            (0, 0),
            (0, -1),
            (False, 1),
            (0, True),
            OSError("closed"),
        )
        for value in invalid:
            observer = mock.Mock(
                side_effect=value if isinstance(value, BaseException) else None,
                return_value=None if isinstance(value, BaseException) else value,
            )
            sleeper = mock.Mock()
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.client._await_dispatcher_launchd_credentials(
                    mock.Mock(),
                    deadline=101.0,
                    credential_observer=observer,
                    now_monotonic=lambda: 100.0,
                    sleeper=sleeper,
                )
            observer.assert_called_once()
            sleeper.assert_not_called()

    def test_dispatcher_launchd_readiness_caps_exponential_sleep(self) -> None:
        now = [100.0]
        sleeps: list[float] = []
        observer = mock.Mock(side_effect=[(0, 1)] * 6 + [(0, 9001)])

        def sleep(delay: float) -> None:
            sleeps.append(delay)
            now[0] += delay

        self.client._await_dispatcher_launchd_credentials(
            mock.Mock(),
            deadline=102.0,
            credential_observer=observer,
            now_monotonic=lambda: now[0],
            sleeper=sleep,
        )

        self.assertEqual(sleeps, [0.01, 0.02, 0.04, 0.08, 0.1, 0.1])

    def test_dispatcher_launchd_proof_pins_listener_runtime_and_final_reread(
        self,
    ) -> None:
        lane = self.client.BrokerLaneSnapshot(
            name="selected",
            generation=7,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("a" * 64, "b" * 64)
            ),
            socket_path=self.root / "dispatcher.sock",
            transport="dispatcher",
            protocol_version=2,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        peer = mock.Mock()
        waiter = mock.Mock(return_value=(0, 9001))
        final_observer = mock.Mock(return_value=(0, 9001))
        prover = mock.Mock(return_value=9001)

        observed = self.client._prove_dispatcher_launchd_peer(
            peer,
            lane,
            deadline=130.0,
            credential_waiter=waiter,
            credential_observer=final_observer,
            peer_prover=prover,
        )

        self.assertEqual(observed, 9001)
        waiter.assert_called_once_with(
            peer,
            deadline=130.0,
            credential_observer=final_observer,
        )
        call = prover.call_args
        self.assertEqual(call.args, (peer, lane))
        self.assertEqual(call.kwargs["credentials"], (0, 9001))
        self.assertEqual(call.kwargs["expected_credential_uid"], 0)
        self.assertEqual(call.kwargs["expected_pid"], 9001)
        call.kwargs["final_credential_observer"]()
        final_observer.assert_called_once_with(peer)

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
            request=request,
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

        def prove_before_send(*_args, **kwargs):
            self.assertEqual(peer.sendall.call_count, 0)
            self.assertEqual(kwargs["deadline"], 130.0)
            return 9001

        with mock.patch.object(
            self.client,
            "_prove_dispatcher_launchd_peer",
            side_effect=prove_before_send,
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
            self.client,
            "_prove_dispatcher_launchd_peer",
            return_value=9001,
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

    def test_dispatcher2_ready_consumes_fallback_but_dispatcher1_keeps_legacy_boundary(
        self,
    ) -> None:
        request = self._adoption_canary_request()
        nonce = base64.urlsafe_b64encode(b"n" * 32).decode("ascii").rstrip("=")
        for protocol_version, expected_error in (
            (2, self.client._DispatcherPostRequestError),
            (1, self.client._DispatcherPreRequestError),
        ):
            lane = self.client.BrokerLaneSnapshot(
                name="selected",
                generation=7,
                artifact_digest="a" * 64,
                manifest_digest="b" * 64,
                label=(
                    "com.agent-collab.provider-dispatcher."
                    + self.client._dispatcher_lane_token("a" * 64, "b" * 64)
                ),
                socket_path=self.root / f"dispatcher-{protocol_version}.sock",
                transport="dispatcher",
                protocol_version=protocol_version,
                anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
            )
            hello = self.client._dispatcher_build_hello(
                lane=lane,
                client_pid=os.getpid(),
                nonce=nonce,
                deadline_monotonic_ms=130_000,
                request=request,
            )
            ready = {
                **hello,
                "frame_type": "ready",
                "dispatcher_pid": 9001,
                "hello_sha256": self.client._dispatcher_frame_sha256(hello),
            }
            peer = mock.Mock()
            with self.subTest(protocol_version=protocol_version), mock.patch.object(
                self.client, "_prove_dispatcher_launchd_peer", return_value=9001
            ), mock.patch.object(
                self.client, "_read_broker_frame", return_value=ready
            ), mock.patch.object(
                self.client.time,
                "monotonic",
                side_effect=(100.0, 100.0, 100.0, 131.0),
            ), mock.patch.object(
                self.client.os, "urandom", return_value=b"n" * 32
            ), self.assertRaises(expected_error):
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
            request=request,
        )
        ready = {
            **hello,
            "frame_type": "ready",
            "dispatcher_pid": 9001,
            "hello_sha256": self.client._dispatcher_frame_sha256(hello),
        }
        response = {
            "protocol_version": 2,
            "request_id": request["request_id"],
            "status": "canary_blocked",
            "error": "fixture",
        }
        observed_deadlines: list[float] = []

        def read_frame(*_args, **kwargs):
            observed_deadlines.append(kwargs["deadline"])
            return ready if len(observed_deadlines) == 1 else response

        with mock.patch.object(
            self.client,
            "_prove_dispatcher_launchd_peer",
            return_value=9001,
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
            name="selected",
            generation=7,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("a" * 64, "b" * 64)
            ),
            socket_path=self.root / "dispatcher.sock",
            transport="dispatcher",
            protocol_version=2,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        runtime = self.root / "runtime"
        runtime.write_bytes(b"runtime")
        runtime.chmod(0o500)
        socket_identity = self.client.FileIdentity(1, 2, 0, 0, stat.S_IFSOCK | 0o600, os.getuid(), 1)
        process = mock.Mock(side_effect=[("10:1", runtime), ("10:1", runtime)])
        published = mock.Mock(
            side_effect=[
                (self.root / "bundle", runtime, self.root / "manifest", lane.anchor),
                (self.root / "bundle", runtime, self.root / "manifest", lane.anchor),
            ]
        )

        with self.assertRaises(ValueError):
            self.client._prove_dispatcher_peer(
                mock.Mock(),
                lane,
                credentials=(0, 4242),
                expected_credential_uid=0,
                expected_pid=4242,
                process_observer=mock.Mock(
                    side_effect=[("10:1", runtime), ("10:1", runtime)]
                ),
                socket_observer=mock.Mock(
                    side_effect=[socket_identity, socket_identity]
                ),
                published_verifier=mock.Mock(
                    side_effect=[
                        (self.root / "bundle", runtime, self.root / "manifest", lane.anchor),
                        (self.root / "bundle", runtime, self.root / "manifest", lane.anchor),
                    ]
                ),
                root=self.root,
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

        launchd_final = mock.Mock(return_value=(0, 4242))
        launchd_observed = self.client._prove_dispatcher_peer(
            mock.Mock(),
            lane,
            credentials=(0, 4242),
            expected_credential_uid=0,
            expected_pid=4242,
            final_credential_observer=launchd_final,
            process_observer=mock.Mock(
                side_effect=[("10:1", runtime), ("10:1", runtime)]
            ),
            socket_observer=mock.Mock(
                side_effect=[socket_identity, socket_identity]
            ),
            published_verifier=mock.Mock(
                side_effect=[
                    (self.root / "bundle", runtime, self.root / "manifest", lane.anchor),
                    (self.root / "bundle", runtime, self.root / "manifest", lane.anchor),
                ]
            ),
            root=self.root,
        )
        self.assertEqual(launchd_observed, 4242)
        launchd_final.assert_called_once_with()

        with self.assertRaises(ValueError):
            self.client._prove_dispatcher_peer(
                mock.Mock(),
                lane,
                credentials=(0, 4242),
                expected_credential_uid=0,
                expected_pid=4242,
                final_credential_observer=mock.Mock(return_value=(0, 4242)),
                process_observer=mock.Mock(
                    side_effect=ValueError("operator process UID was rejected")
                ),
                socket_observer=mock.Mock(return_value=socket_identity),
                published_verifier=mock.Mock(
                    return_value=(
                        self.root / "bundle",
                        runtime,
                        self.root / "manifest",
                        lane.anchor,
                    )
                ),
                root=self.root,
            )

        with self.assertRaises(ValueError):
            self.client._prove_dispatcher_peer(
                mock.Mock(),
                lane,
                credentials=(0, 4242),
                expected_credential_uid=0,
                expected_pid=4242,
                final_credential_observer=mock.Mock(return_value=(0, 4243)),
                process_observer=mock.Mock(
                    side_effect=[("10:1", runtime), ("10:1", runtime)]
                ),
                socket_observer=mock.Mock(
                    side_effect=[socket_identity, socket_identity]
                ),
                published_verifier=mock.Mock(
                    side_effect=[
                        (self.root / "bundle", runtime, self.root / "manifest", lane.anchor),
                        (self.root / "bundle", runtime, self.root / "manifest", lane.anchor),
                    ]
                ),
                root=self.root,
            )

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
                        (self.root / "bundle", runtime, self.root / "manifest", lane.anchor),
                        (self.root / "bundle", runtime, self.root / "manifest", lane.anchor),
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
            name="candidate",
            generation=7,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("a" * 64, "b" * 64)
            ),
            socket_path=self.root / "green.sock",
            transport="dispatcher",
            protocol_version=2,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        selector = self._selector_document(
            generation=7,
            selected_lane="blue",
            green_artifact="a" * 64,
            green_manifest="b" * 64,
        )
        response = {
            "protocol_version": self.client.PROTOCOL_VERSION,
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
            self.client,
            "_read_broker_selector_v2",
            return_value={"candidate": selector["green"]},
        ), mock.patch.object(
            self.client, "_load_selector_v2_lane", return_value=green
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge", return_value=response
        ) as bridge:
            result = self.client.invoke_adoption_canary(request=request)
        self.assertEqual(result.status, self.client.RuntimeStatus.OK)
        self.assertEqual(result.result["passed_routes"], request["routes"])
        bridge.assert_called_once()
        self.assertEqual(bridge.call_args.kwargs["lane"], green)
        self.assertEqual(bridge.call_args.kwargs["request"]["host_context"], "generic")
        self.assertEqual(
            bridge.call_args.kwargs["request"]["protocol_version"],
            self.client.PROTOCOL_VERSION,
        )
        self.assertEqual(request["protocol_version"], self.client.PROTOCOL_VERSION)

        legacy_dispatcher_response = {
            **response,
            "protocol_version": self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
        }
        rejected = self.client._parse_adoption_canary_response(
            legacy_dispatcher_response,
            request=bridge.call_args.kwargs["request"],
        )
        self.assertEqual(rejected.status, self.client.RuntimeStatus.PROTOCOL_ERROR)

        failure = self.client._parse_adoption_canary_response(
            {
                "protocol_version": self.client.PROTOCOL_VERSION,
                "request_id": request["request_id"],
                "status": "timeout",
                "error": "candidate deadline expired",
            },
            request=bridge.call_args.kwargs["request"],
        )
        self.assertEqual(failure.status, self.client.RuntimeStatus.TIMEOUT)

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

    def _selector_v2_document(
        self,
        *,
        generation: int = 1,
        v1_sha256: str = "e" * 64,
        selected: dict[str, object] | None = None,
        retained: dict[str, object] | None = None,
        candidate: dict[str, object] | None = None,
        lifecycle: dict[str, object] | None = None,
    ) -> dict[str, object]:
        def lane(
            artifact: str,
            manifest: str,
            *,
            transport: str,
            protocol_version: int,
            lane_generation: int,
        ) -> dict[str, object]:
            return {
                "artifact_sha256": artifact,
                "manifest_sha256": manifest,
                "transport": transport,
                "protocol_version": protocol_version,
                "lane_generation": lane_generation,
            }

        return {
            "schema_version": 2,
            "generation": generation,
            "selector_v1_sha256": v1_sha256,
            "selected": selected
            or lane(
                "a" * 64,
                "b" * 64,
                transport="dispatcher",
                protocol_version=1,
                lane_generation=28,
            ),
            "retained": retained,
            "candidate": candidate
            or lane(
                "c" * 64,
                "d" * 64,
                transport="dispatcher",
                protocol_version=2,
                lane_generation=29,
            ),
            "lifecycle": lifecycle
            or lane(
                "1" * 64,
                "2" * 64,
                transport="broker",
                protocol_version=1,
                lane_generation=0,
            ),
        }

    def test_selector_v2_has_independent_roles_and_closed_transitions(self) -> None:
        staged = self._selector_v2_document()
        self.assertTrue(self.client._broker_selector_v2_valid(staged))
        committed = self._selector_v2_document(
            generation=2,
            selected=dict(staged["candidate"]),
            retained=dict(staged["selected"]),
            candidate=None,
        )
        committed["candidate"] = None
        self.assertTrue(
            self.client._broker_selector_v2_transition_valid(
                staged, committed, action="commit"
            )
        )
        aborted = self._selector_v2_document(generation=2, candidate=None)
        aborted["candidate"] = None
        self.assertTrue(
            self.client._broker_selector_v2_transition_valid(
                staged, aborted, action="abort"
            )
        )
        self.assertEqual(committed["selector_v1_sha256"], staged["selector_v1_sha256"])
        self.assertEqual(committed["lifecycle"], staged["lifecycle"])
        self.assertEqual(committed["selected"]["lane_generation"], 29)
        self.assertEqual(committed["retained"]["lane_generation"], 28)

        crossed = json.loads(json.dumps(committed))
        crossed["selected"]["protocol_version"] = 1
        self.assertFalse(
            self.client._broker_selector_v2_transition_valid(
                staged, crossed, action="commit"
            )
        )

    def test_malformed_selector_v2_never_downgrades_to_valid_selector_v1(self) -> None:
        root = self.root / "selector-overlap"
        root.mkdir(mode=0o700)
        v1 = self._selector_document(selected_lane="green", generation=28)
        v1_raw = self.client._state_bytes(v1)
        (root / self.client.BROKER_SELECTOR_FILENAME).write_bytes(v1_raw)
        (root / self.client.BROKER_SELECTOR_FILENAME).chmod(0o600)
        (root / self.client.BROKER_SELECTOR_V2_FILENAME).write_text(
            '{"schema_version":2', encoding="ascii"
        )
        (root / self.client.BROKER_SELECTOR_V2_FILENAME).chmod(0o600)

        with self.assertRaises(ValueError):
            self.client._read_broker_selector_view(root)

    def test_historical_committed_broker2_remains_a_normal_selected_lane(self) -> None:
        root = self.root / "historical-broker2"
        root.mkdir(mode=0o700)
        selected = {
            "artifact_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
            "transport": "broker",
            "protocol_version": 2,
            "lane_generation": 0,
        }
        selector = self._selector_v2_document(selected=selected)
        selector["candidate"] = None
        selector["lifecycle"] = None
        self.assertTrue(self.client._broker_selector_v2_valid(selector))
        lane = self.client.BrokerLaneSnapshot(
            name="selected",
            generation=0,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=root / self.client.BROKER_SOCKET_FILENAME,
            transport="broker",
            protocol_version=2,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_read_broker_selector_view", return_value=selector
        ), mock.patch.object(
            self.client, "_load_selector_v2_lane", return_value=lane
        ) as loader:
            lanes, error = self.client._capture_broker_lanes(resolution)
        self.assertIsNone(error)
        self.assertEqual(lanes, (lane,))
        loader.assert_called_once_with(root, selected, role="selected")

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
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
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
            return_value=(
                self.root / "bundle",
                runtime,
                self.root / "manifest",
                self.client.RuntimeContractAnchor("2.0.0", 2),
            ),
        ), mock.patch.object(
            self.client, "_operator_home", return_value=str(self.root)
        ):
            observed = self.client._load_dispatcher_broker_lane(root, reference, 2)
        self.assertEqual(observed, lane)
        self.assertEqual(
            plist_document["ProgramArguments"],
            [str(runtime), "dispatcher", "--protocol", "2"],
        )

        state_path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.client._load_dispatcher_broker_lane(root, reference, 2)

    def test_missing_or_malformed_selector_v2_fails_closed(self) -> None:
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        cases = (
            None,
            ValueError("partial selector"),
            ValueError("malformed selector"),
        )
        for observed in cases:
            with self.subTest(observed=repr(observed)), mock.patch.object(
                self.client,
                "_read_broker_selector_view",
                side_effect=observed if isinstance(observed, BaseException) else None,
                return_value=observed if observed is None else mock.DEFAULT,
            ):
                lanes, error = self.client._capture_broker_lanes(resolution)
            self.assertEqual(lanes, ())
            self.assertIsNotNone(error)

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
            name="candidate",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label="com.agent-collab.provider-dispatcher.test",
            socket_path=self.root / "green.sock",
        )
        selector = self._selector_v2_document()
        selector["candidate"] = None
        selector["retained"] = {
            "artifact_sha256": current_blue.artifact_digest,
            "manifest_sha256": current_blue.manifest_digest,
            "transport": "broker",
            "protocol_version": 2,
            "lane_generation": 0,
        }
        with mock.patch.object(
            self.client, "_read_broker_selector_view", return_value=selector
        ), mock.patch.object(
            self.client, "_load_selector_v2_lane", side_effect=(green, current_blue)
        ) as loader, mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ) as job_loaded:
            lanes, error = self.client._capture_broker_lanes(resolution)
        self.assertEqual(lanes, (green, current_blue))
        self.assertIsNone(error)
        self.assertEqual(loader.call_count, 2)
        job_loaded.assert_called_once_with(current_blue.label, deadline=mock.ANY)

    def test_capture_omits_retained_lane_with_unloaded_job(self) -> None:
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        selected = self.client.BrokerLaneSnapshot(
            name="selected",
            generation=29,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label="com.agent-collab.provider-dispatcher.selected",
            socket_path=self.root / "selected.sock",
        )
        retained = self.client.BrokerLaneSnapshot(
            name="retained",
            generation=28,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label="com.agent-collab.provider-dispatcher.retained",
            socket_path=self.root / "retained.sock",
        )
        selector = self._selector_v2_document(
            selected={
                "artifact_sha256": selected.artifact_digest,
                "manifest_sha256": selected.manifest_digest,
                "transport": "dispatcher",
                "protocol_version": 2,
                "lane_generation": selected.generation,
            },
            retained={
                "artifact_sha256": retained.artifact_digest,
                "manifest_sha256": retained.manifest_digest,
                "transport": "dispatcher",
                "protocol_version": 1,
                "lane_generation": retained.generation,
            },
        )
        with mock.patch.object(
            self.client, "_broker_root", return_value=self.root
        ), mock.patch.object(
            self.client, "_read_broker_selector_view", return_value=selector
        ), mock.patch.object(
            self.client,
            "_load_selector_v2_lane",
            side_effect=(selected, retained),
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=False
        ) as job_loaded:
            lanes, error = self.client._capture_broker_lanes(resolution)

        self.assertEqual(lanes, (selected,))
        self.assertIsNone(error)
        job_loaded.assert_called_once_with(retained.label, deadline=mock.ANY)

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
        selector = self._selector_v2_document()
        selector["candidate"] = None
        selector["retained"] = {
            "artifact_sha256": blue.artifact_digest,
            "manifest_sha256": blue.manifest_digest,
            "transport": "broker",
            "protocol_version": 2,
            "lane_generation": 0,
        }
        with mock.patch.object(
            self.client, "_read_broker_selector_view", return_value=selector
        ), mock.patch.object(
            self.client, "_load_selector_v2_lane", side_effect=(green, blue)
        ) as loader, mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ) as job_loaded:
            lanes, error = self.client._capture_broker_lanes(resolution)
        self.assertEqual(lanes, (green, blue))
        self.assertIsNone(error)
        self.assertEqual(loader.call_count, 2)
        job_loaded.assert_called_once_with(blue.label, deadline=mock.ANY)

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
        blue_selected = self._selector_v2_document(selected={
            "artifact_sha256": blue.artifact_digest,
            "manifest_sha256": blue.manifest_digest,
            "transport": "broker",
            "protocol_version": 2,
            "lane_generation": 0,
        })
        blue_selected["candidate"] = None
        blue_selected["lifecycle"] = None
        green_selected = self._selector_v2_document()
        green_selected["candidate"] = None
        green_selected["retained"] = dict(blue_selected["selected"])
        with mock.patch.object(
            self.client,
            "_read_broker_selector_view",
            side_effect=(blue_selected, green_selected),
        ), mock.patch.object(
            self.client, "_load_selector_v2_lane", side_effect=(blue, green, blue)
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ) as job_loaded:
            inflight_lanes, inflight_error = self.client._capture_broker_lanes(
                resolution
            )
            next_lanes, next_error = self.client._capture_broker_lanes(resolution)

        self.assertEqual(inflight_lanes, (blue,))
        self.assertIsNone(inflight_error)
        self.assertEqual(next_lanes, (green, blue))
        self.assertIsNone(next_error)
        self.assertEqual(inflight_lanes, (blue,))
        job_loaded.assert_called_once_with(blue.label, deadline=mock.ANY)

    def test_green_bridge_document_binds_lane_and_deadlines_without_path_input(self) -> None:
        lane = self.client.BrokerLaneSnapshot(
            name="selected",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "green.sock",
            transport="dispatcher",
            protocol_version=2,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        request = {
            "protocol_version": self.client.DISPATCHER_PROTOCOL_VERSION,
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
        # The v2 bridge document is exactly the seven-key contract the receiving
        # bridge validator accepts. The request reservation
        # (execution_key/request_size/request_sha256) is NOT echoed here — the
        # bridge derives it from `request` and it crosses the trust boundary only
        # on the wire frame, so over-sending it here is a schema error.
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
        for reserved in ("execution_key", "request_size", "request_sha256"):
            self.assertNotIn(reserved, document)
        self.assertNotIn("socket", encoded.decode("ascii"))
        self.assertNotIn(str(self.root), encoded.decode("ascii"))
        self.assertTrue(encoded.endswith(b"\n"))

    def test_ping_uses_dispatcher_protocol_and_keeps_failure_protocol_distinct(
        self,
    ) -> None:
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
            transport="dispatcher",
            protocol_version=2,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        selector = self._selector_v2_document()

        def bridge(*, lane, request, deadline, handshake_deadline):
            self.assertIs(lane, green)
            self.assertEqual(
                request["protocol_version"],
                self.client.DISPATCHER_PROTOCOL_VERSION,
            )
            self.assertEqual(request["operation"], "dispatcher_ping")
            self.assertLessEqual(handshake_deadline, deadline)
            return {
                "protocol_version": self.client.DISPATCHER_PROTOCOL_VERSION,
                "request_id": request["request_id"],
                "status": "ok",
                "result": {"ready": True},
                "provenance": {"operation": "dispatcher_ping"},
            }

        with mock.patch.object(
            self.client, "_broker_root", return_value=self.root
        ), mock.patch.object(
            self.client, "_read_broker_selector_view", return_value=selector
        ), mock.patch.object(
            self.client, "_load_selector_v2_lane", return_value=green
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge", side_effect=bridge
        ):
            result = self.client.invoke_dispatcher_ping(timeout_ms=5_000)

        self.assertEqual(result.status, self.client.RuntimeStatus.OK, result.error)
        self.assertEqual(result.result, {"ready": True})

        request_id = "dispatcher-ping-contract"
        typed_failure = {
            "protocol_version": self.client.PROTOCOL_VERSION,
            "request_id": request_id,
            "status": "protocol_error",
            "error": "provider dispatcher ping was rejected",
        }
        failure = self.client._dispatcher_ping_response(
            typed_failure, request_id=request_id
        )
        self.assertEqual(failure.status, self.client.RuntimeStatus.PROTOCOL_ERROR)
        self.assertEqual(failure.error, typed_failure["error"])

        legacy_lane_failure = self.client._dispatcher_ping_response(
            typed_failure,
            request_id=request_id,
            dispatcher_protocol_version=self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
        )
        self.assertEqual(
            legacy_lane_failure.status, self.client.RuntimeStatus.PROTOCOL_ERROR
        )
        self.assertEqual(legacy_lane_failure.error, typed_failure["error"])

        swapped_success = {
            "protocol_version": self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
            "request_id": request_id,
            "status": "ok",
            "result": {"ready": True},
            "provenance": {"operation": "dispatcher_ping"},
        }
        rejected_success = self.client._dispatcher_ping_response(
            swapped_success, request_id=request_id
        )
        self.assertEqual(
            rejected_success.status, self.client.RuntimeStatus.PROTOCOL_ERROR
        )
        self.assertEqual(
            rejected_success.error,
            "provider dispatcher ping success was rejected",
        )

        swapped_failure = {
            **typed_failure,
            "protocol_version": self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
        }
        rejected_failure = self.client._dispatcher_ping_response(
            swapped_failure, request_id=request_id
        )
        self.assertEqual(
            rejected_failure.status, self.client.RuntimeStatus.PROTOCOL_ERROR
        )
        self.assertEqual(
            rejected_failure.error,
            "provider dispatcher ping failure was rejected",
        )

        malformed_failure = {**typed_failure, "unexpected": True}
        malformed = self.client._dispatcher_ping_response(
            malformed_failure, request_id=request_id
        )
        self.assertEqual(malformed.status, self.client.RuntimeStatus.PROTOCOL_ERROR)
        self.assertEqual(
            malformed.error,
            "provider dispatcher ping failure was rejected",
        )

    def test_ping_uses_selected_legacy_lane_protocol_during_upgrade(self) -> None:
        selected = self.client.BrokerLaneSnapshot(
            name="selected",
            generation=28,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "selected.sock",
            transport="dispatcher",
            protocol_version=self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        selector = self._selector_v2_document()

        def bridge(*, lane, request, deadline, handshake_deadline):
            self.assertIs(lane, selected)
            self.assertEqual(
                request["protocol_version"],
                self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
            )
            self.assertEqual(request["operation"], "dispatcher_ping")
            self.assertLessEqual(handshake_deadline, deadline)
            return {
                "protocol_version": self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
                "request_id": request["request_id"],
                "status": "ok",
                "result": {"ready": True},
                "provenance": {"operation": "dispatcher_ping"},
            }

        with mock.patch.object(
            self.client, "_broker_root", return_value=self.root
        ), mock.patch.object(
            self.client, "_read_broker_selector_view", return_value=selector
        ), mock.patch.object(
            self.client, "_load_selector_v2_lane", return_value=selected
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge", side_effect=bridge
        ):
            result = self.client.invoke_dispatcher_ping(timeout_ms=5_000)

        self.assertEqual(result.status, self.client.RuntimeStatus.OK, result.error)
        self.assertEqual(result.result, {"ready": True})

    def test_lock_probe_uses_staged_bridge_and_returns_closed_namespace_proof(self) -> None:
        green = self.client.BrokerLaneSnapshot(
            name="candidate",
            generation=4,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "green.sock",
            transport="dispatcher",
            protocol_version=2,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        selector = self._selector_v2_document()

        def bridge(*, lane, request, deadline, handshake_deadline):
            self.assertIs(lane, green)
            self.assertEqual(
                request["protocol_version"],
                self.client.DISPATCHER_PROTOCOL_VERSION,
            )
            self.assertEqual(request["operation"], "dispatcher_lock_probe")
            self.assertEqual(request["provider"], "opencode")
            self.assertLessEqual(handshake_deadline, deadline)
            return {
                "protocol_version": self.client.DISPATCHER_PROTOCOL_VERSION,
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
            self.client, "_read_broker_selector_v2", return_value=selector
        ), mock.patch.object(
            self.client, "_load_selector_v2_lane", return_value=green
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

        request_id = "dispatcher-lock-probe-contract"
        typed_failure = {
            "protocol_version": self.client.PROTOCOL_VERSION,
            "request_id": request_id,
            "status": "provider_error",
            "error": "provider dispatcher lock probe failed",
        }
        failure = self.client._dispatcher_lock_probe_response(
            typed_failure, request_id=request_id, provider="opencode"
        )
        self.assertEqual(failure.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertEqual(failure.error, typed_failure["error"])

        swapped_success = {
            "protocol_version": self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
            "request_id": request_id,
            "status": "ok",
            "result": {
                "provider": "opencode",
                "lock_acquired": True,
                "namespace": "legacy-compatible-v1",
            },
            "provenance": {"operation": "dispatcher_lock_probe"},
        }
        rejected_success = self.client._dispatcher_lock_probe_response(
            swapped_success, request_id=request_id, provider="opencode"
        )
        self.assertEqual(
            rejected_success.status, self.client.RuntimeStatus.PROTOCOL_ERROR
        )
        self.assertEqual(
            rejected_success.error,
            "provider dispatcher lock probe success was rejected",
        )

        swapped_failure = {
            **typed_failure,
            "protocol_version": self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
        }
        rejected_failure = self.client._dispatcher_lock_probe_response(
            swapped_failure, request_id=request_id, provider="opencode"
        )
        self.assertEqual(
            rejected_failure.status, self.client.RuntimeStatus.PROTOCOL_ERROR
        )
        self.assertEqual(
            rejected_failure.error,
            "provider dispatcher lock probe failure was rejected",
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
            "protocol_version": 2,
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
            name="selected",
            generation=2,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "green.sock",
            transport="dispatcher",
            protocol_version=2,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        bundle = self.root / "bundle"
        bundle.mkdir()
        runtime = bundle / "runtime"
        runtime.write_bytes(b"runtime")
        runtime.chmod(0o500)
        request = {
            "protocol_version": 2,
            "request_id": "bridge-phase-1",
            "operation": "dispatcher_ping",
            "timeout_ms": 5_000,
            "host_context": "generic",
        }
        now = time.monotonic()
        for returncode, output, expected in (
            (3, b"", self.client._DispatcherPreRequestError),
            (4, b"", self.client._DispatcherPostRequestError),
            (2, b"", self.client._DispatcherPostRequestError),
            (0, b"{", self.client._DispatcherPostRequestError),
        ):
            process = mock.Mock(returncode=returncode)
            with self.subTest(returncode=returncode, output=output), mock.patch.object(
                self.client, "_broker_root", return_value=self.root
            ), mock.patch.object(
                self.client,
                "_verify_published_version",
                return_value=(bundle, runtime, self.root / "manifest", lane.anchor),
            ), mock.patch.object(
                self.client.subprocess, "Popen", return_value=process
            ) as popen, mock.patch.object(
                self.client,
                "_collect_bounded_output",
                return_value=(output, b"", None),
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
                [str(runtime), "dispatcher-client", "--protocol", "2"],
            )

        timeout = self.client.RuntimeResult(
            self.client.RuntimeStatus.TIMEOUT,
            error="native runtime timed out",
        )
        process = mock.Mock(returncode=-9)
        with mock.patch.object(
            self.client, "_broker_root", return_value=self.root
        ), mock.patch.object(
            self.client,
            "_verify_published_version",
            return_value=(bundle, runtime, self.root / "manifest", lane.anchor),
        ), mock.patch.object(
            self.client.subprocess, "Popen", return_value=process
        ), mock.patch.object(
            self.client,
            "_collect_bounded_output",
            return_value=(b"", b"", timeout),
        ), self.assertRaises(
            self.client._DispatcherPostRequestError
        ) as raised:
            self.client._invoke_dispatcher_bridge(
                lane=lane,
                request=request,
                deadline=now + 5,
                handshake_deadline=now + 2,
            )
        self.assertIs(raised.exception.result, timeout)

        process = mock.Mock(returncode=0)
        with self.subTest(collection_exception=True), mock.patch.object(
            self.client, "_broker_root", return_value=self.root
        ), mock.patch.object(
            self.client,
            "_verify_published_version",
            return_value=(bundle, runtime, self.root / "manifest", lane.anchor),
        ), mock.patch.object(
            self.client.subprocess, "Popen", return_value=process
        ) as popen, mock.patch.object(
            self.client,
            "_collect_bounded_output",
            side_effect=subprocess.SubprocessError("collection failed"),
        ):
            with self.assertRaises(self.client._DispatcherPostRequestError):
                self.client._invoke_dispatcher_bridge(
                    lane=lane,
                    request=request,
                    deadline=now + 5,
                    handshake_deadline=now + 2,
                )
        self.assertEqual(
            popen.call_args.args[0],
            [str(runtime), "dispatcher-client", "--protocol", "2"],
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
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
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
                    "protocol_version": 2,
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
        capture.assert_called_once_with(client_resolution, deadline=mock.ANY)

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
                    "protocol_version": 2,
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
        capture.assert_called_once_with(resolution, deadline=mock.ANY)

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
            "protocol_version": 2,
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
            "protocol_version": 2,
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
            "protocol_version": 2,
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

    def test_accepted_dispatcher_timeout_remains_typed_without_blue_retry(
        self,
    ) -> None:
        self._fixture()
        envelope = self._envelope(
            route="gemini", action="advisory", request_id="accepted-timeout-1"
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
            socket_path=self.root / "accepted-timeout.sock",
        )
        blue = self.client.BrokerLaneSnapshot(
            name="blue",
            generation=2,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
            label=self.client.BROKER_LABEL,
            socket_path=self.root / "unused-timeout-blue.sock",
        )
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=self.root / "runtime",
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        timeout = self.client.RuntimeResult(
            self.client.RuntimeStatus.TIMEOUT,
            error="native runtime timed out",
        )
        accepted = self.client._DispatcherPostRequestError(
            "accepted request deadline expired",
            result=timeout,
        )
        with mock.patch.object(
            self.client,
            "_capture_broker_lanes",
            return_value=((green, blue), None),
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge", side_effect=accepted
        ) as bridge, mock.patch.object(
            self.client.socket, "socket"
        ) as socket_factory:
            result = self.client._launch_broker(
                resolution=resolution,
                payload=payload,
                timeout_ms=30_000,
                envelope=envelope,
            )

        self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)
        self.assertEqual(result.error, "native runtime timed out")
        bridge.assert_called_once()
        socket_factory.assert_not_called()

    def test_legacy_dispatcher_response_waits_for_one_shot_job_idle(self) -> None:
        self._fixture()
        envelope = self._envelope(
            route="gemini", action="advisory", request_id="legacy-idle-1"
        )
        payload = self.client._native_document(envelope)
        legacy = self.client.BrokerLaneSnapshot(
            name="selected",
            generation=28,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "legacy-idle.sock",
            transport="dispatcher",
            protocol_version=self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        response = {
            "protocol_version": self.client.PROTOCOL_VERSION,
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
            self.client, "_capture_broker_lanes", return_value=((legacy,), None)
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge", return_value=response
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=True
        ) as wait_for_idle:
            result = self.client._launch_broker(
                resolution=resolution,
                payload=payload,
                timeout_ms=30_000,
                envelope=envelope,
            )

        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        wait_for_idle.assert_called_once_with(legacy.label, deadline=mock.ANY)

    def test_legacy_dispatcher_idle_proof_reuses_absolute_broker_deadline(
        self,
    ) -> None:
        self._fixture()
        envelope = self._envelope(
            route="gemini", action="advisory", request_id="legacy-idle-deadline-1"
        )
        payload = self.client._native_document(envelope)
        legacy = self.client.BrokerLaneSnapshot(
            name="selected",
            generation=28,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "legacy-idle-deadline.sock",
            transport="dispatcher",
            protocol_version=self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        response = {
            "protocol_version": self.client.PROTOCOL_VERSION,
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
            self.client, "_capture_broker_lanes", return_value=((legacy,), None)
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge", return_value=response
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=True
        ) as wait_for_idle, mock.patch.object(
            self.client.time, "monotonic", return_value=100.0
        ):
            result = self.client._launch_broker(
                resolution=resolution,
                payload=payload,
                timeout_ms=30_000,
                envelope=envelope,
            )

        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        wait_for_idle.assert_called_once_with(legacy.label, deadline=130.0)

    def test_legacy_dispatcher_response_fails_closed_when_idle_is_unproven(
        self,
    ) -> None:
        self._fixture()
        envelope = self._envelope(
            route="grok", action="architecture", request_id="legacy-idle-2"
        )
        payload = self.client._native_document(envelope)
        legacy = self.client.BrokerLaneSnapshot(
            name="selected",
            generation=28,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "legacy-idle.sock",
            transport="dispatcher",
            protocol_version=self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        response = {
            "protocol_version": self.client.PROTOCOL_VERSION,
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
            self.client, "_capture_broker_lanes", return_value=((legacy,), None)
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge", return_value=response
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=False
        ) as wait_for_idle, mock.patch.object(
            self.client.time, "monotonic", return_value=100.0
        ):
            result = self.client._launch_broker(
                resolution=resolution,
                payload=payload,
                timeout_ms=30_000,
                envelope=envelope,
            )

        self.assertEqual(result.status, self.client.RuntimeStatus.TEARDOWN_ERROR)
        self.assertEqual(
            result.error, "legacy provider dispatcher did not return idle"
        )
        wait_for_idle.assert_called_once_with(legacy.label, deadline=130.0)

    def test_legacy_dispatcher_accepted_failure_requires_idle_before_return(
        self,
    ) -> None:
        self._fixture()
        envelope = self._envelope(
            route="composer", action="codegen", request_id="legacy-idle-3"
        )
        payload = self.client._native_document(envelope)
        legacy = self.client.BrokerLaneSnapshot(
            name="selected",
            generation=28,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label=(
                "com.agent-collab.provider-dispatcher."
                + self.client._dispatcher_lane_token("c" * 64, "d" * 64)
            ),
            socket_path=self.root / "legacy-idle.sock",
            transport="dispatcher",
            protocol_version=self.client.LEGACY_DISPATCHER_PROTOCOL_VERSION,
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
        )
        resolution = self.client.RuntimeResolution(
            self.client.RuntimeStatus.OK,
            path=self.root / "runtime",
            manifest_digest="f" * 64,
            artifact_digest="e" * 64,
        )
        timeout = self.client.RuntimeResult(
            self.client.RuntimeStatus.TIMEOUT,
            error="native runtime timed out",
        )
        accepted = self.client._DispatcherPostRequestError(
            "accepted request deadline expired",
            result=timeout,
        )
        with mock.patch.object(
            self.client, "_capture_broker_lanes", return_value=((legacy,), None)
        ), mock.patch.object(
            self.client, "_invoke_dispatcher_bridge", side_effect=accepted
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=False
        ) as wait_for_idle, mock.patch.object(
            self.client.time, "monotonic", return_value=100.0
        ):
            result = self.client._launch_broker(
                resolution=resolution,
                payload=payload,
                timeout_ms=30_000,
                envelope=envelope,
            )

        self.assertEqual(result.status, self.client.RuntimeStatus.TEARDOWN_ERROR)
        self.assertEqual(
            result.error, "legacy provider dispatcher did not return idle"
        )
        wait_for_idle.assert_called_once_with(legacy.label, deadline=130.0)

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
                    "protocol_version": 2,
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
            anchor=self.client.RuntimeContractAnchor("2.0.0", 2),
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
                        "protocol_version": 2,
                        "request_id": envelope.request_id,
                        "status": status,
                        "error": "provider broker request was rejected",
                    },
                    envelope,
                    self.client.RuntimeContractAnchor("2.0.0", 2),
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
        self._fixture(body=body, schema_version=2)
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client,
            "_committed_legacy_package_role",
            return_value=("selected", "broker", None),
        ), patches[0], patches[1], patches[2], patches[3], patches[4]:
            installed = self.client.install_broker()
        self.assertEqual(installed.status, self.client.RuntimeStatus.OK, installed.error)
        state = json.loads((root / "state.json").read_text(encoding="utf-8"))
        selector = {
            "schema_version": 1,
            "generation": 1,
            "selected_lane": "blue",
            "blue": {
                "artifact_sha256": state["artifact_sha256"],
                "manifest_sha256": state["manifest_sha256"],
            },
            "green": None,
        }
        (root / self.client.BROKER_SELECTOR_FILENAME).write_bytes(
            self.client._selector_bytes(selector)
        )
        (root / self.client.BROKER_SELECTOR_FILENAME).chmod(0o600)
        return (
            (root / "state.json").read_bytes(),
            (root / "broker.plist").read_bytes(),
            state,
        )

    def _install_protocol_v1_blue(
        self, root: Path, *, body: str
    ) -> tuple[bytes, bytes, dict]:
        self._fixture(
            body=body,
            schema_version=2,
            runtime_protocol_version=1,
        )
        patches = self._broker_lifecycle_patches(root)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client,
            "_committed_legacy_package_role",
            return_value=("lifecycle", "broker", None),
        ), patches[0], patches[1], patches[2], patches[3], patches[4]:
            resolution = self.client.resolve_runtime()
            self.assertEqual(
                resolution.status, self.client.RuntimeStatus.OK, resolution.error
            )
            self.assertIsNone(resolution.anchor)
            installed_root = self.client._ensure_broker_layout()
            _bundle, runtime, _manifest, anchor = self.client._publish_broker_version(
                installed_root,
                resolution=resolution,
                role="lifecycle",
                transport="broker",
                dispatcher_protocol_version=None,
            )
            self.assertIsNone(anchor)
            plist_raw = self.client._plist_bytes(
                self.client._broker_plist_document(
                    runtime_path=runtime,
                    socket_path=root / self.client.BROKER_SOCKET_FILENAME,
                    tmpdir=root / "tmp",
                    home=Path(self.client._operator_home()),
                    uid=os.getuid(),
                )
            )
            state = self.client._record_for(
                root=root,
                artifact_digest=resolution.artifact_digest,
                manifest_digest=resolution.manifest_digest,
                plist_digest=hashlib.sha256(plist_raw).hexdigest(),
                previous=None,
                runtime_protocol_version=1,
            )
            self.client._write_private_atomic(
                root / "broker.plist", plist_raw, mode=0o600
            )
            self.client._write_private_atomic(
                root / "state.json", self.client._state_bytes(state), mode=0o600
            )
            self.assertTrue(self.client._bootstrap_broker(root / "broker.plist"))
        return (
            (root / "state.json").read_bytes(),
            (root / "broker.plist").read_bytes(),
            state,
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

    def _install_modern_selected(self, root: Path, *, body: str):
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
            installed = self.client.install_broker()
        self.assertEqual(installed.status, self.client.RuntimeStatus.OK, installed.error)
        return json.loads(
            (root / self.client.BROKER_SELECTOR_V2_FILENAME).read_text(
                encoding="utf-8"
            )
        )

    def _install_legacy_dispatcher1_without_blue(self, root: Path):
        self._fixture(schema_version=2, runtime_protocol_version=2)
        ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK, result={"ready": True}
        )
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client,
            "_committed_legacy_package_role",
            return_value=("selected", "dispatcher", 1),
        ), mock.patch.object(
            self.client,
            "_bootstrap_broker",
            side_effect=self._dispatcher_bootstrap(root),
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=ping
        ):
            resolution = self.client.resolve_runtime()
            self.assertEqual(resolution.status, self.client.RuntimeStatus.OK)
            installed_root = self.client._ensure_broker_layout()
            self.client._publish_broker_version(
                installed_root,
                resolution=resolution,
                role="selected",
                transport="dispatcher",
                dispatcher_protocol_version=1,
            )
            lane = self.client._dispatcher_lane_snapshot(
                root,
                artifact_digest=resolution.artifact_digest,
                manifest_digest=resolution.manifest_digest,
                generation=4,
                name="selected",
                protocol_version=1,
                anchor=resolution.anchor,
            )
            self.client._provision_dispatcher_lane(root, lane)
        reference = {
            "artifact_sha256": lane.artifact_digest,
            "manifest_sha256": lane.manifest_digest,
        }
        selector = {
            "schema_version": 1,
            "generation": 4,
            "selected_lane": "green",
            "blue": dict(reference),
            "green": dict(reference),
        }
        (root / self.client.BROKER_SELECTOR_FILENAME).write_bytes(
            self.client._selector_bytes(selector)
        )
        (root / self.client.BROKER_SELECTOR_FILENAME).chmod(0o600)
        return selector, lane

    def _install_v1_selected_green_with_lifecycle_blue(self, root: Path):
        _state_raw, _plist_raw, blue = self._install_protocol_v1_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        self._fixture(
            body="#!/bin/sh\nexit 7\n",
            schema_version=2,
            runtime_protocol_version=2,
        )
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
            "_committed_legacy_package_role",
            return_value=("selected", "dispatcher", 1),
        ), mock.patch.object(
            self.client,
            "_bootstrap_broker",
            side_effect=self._dispatcher_bootstrap(root),
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=ping
        ):
            resolution = self.client.resolve_runtime()
            self.assertEqual(resolution.status, self.client.RuntimeStatus.OK)
            installed_root = self.client._ensure_broker_layout()
            self.client._publish_broker_version(
                installed_root,
                resolution=resolution,
                role="selected",
                transport="dispatcher",
                dispatcher_protocol_version=1,
            )
            lane = self.client._dispatcher_lane_snapshot(
                root,
                artifact_digest=resolution.artifact_digest,
                manifest_digest=resolution.manifest_digest,
                generation=28,
                name="selected",
                protocol_version=1,
                anchor=resolution.anchor,
            )
            self.client._provision_dispatcher_lane(root, lane)
        selector = {
            "schema_version": 1,
            "generation": 28,
            "selected_lane": "green",
            "blue": {
                "artifact_sha256": blue["artifact_sha256"],
                "manifest_sha256": blue["manifest_sha256"],
            },
            "green": {
                "artifact_sha256": lane.artifact_digest,
                "manifest_sha256": lane.manifest_digest,
            },
        }
        (root / self.client.BROKER_SELECTOR_FILENAME).write_bytes(
            self.client._selector_bytes(selector)
        )
        (root / self.client.BROKER_SELECTOR_FILENAME).chmod(0o600)
        return selector, lane

    def _commit_staged_dispatcher(self, root: Path):
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
        self.assertEqual(
            committed.status, self.client.RuntimeStatus.OK, committed.error
        )
        return committed

    def test_protocol_v2_lifecycle_accepts_exact_v1_blue_only_for_lifecycle(
        self,
    ) -> None:
        root = self.root / "broker-state"
        _state_raw, _plist_raw, blue = self._install_protocol_v1_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        selector = {
            "schema_version": 1,
            "generation": 4,
            "selected_lane": "blue",
            "blue": {
                "artifact_sha256": blue["artifact_sha256"],
                "manifest_sha256": blue["manifest_sha256"],
            },
            "green": None,
        }
        (root / "selector.json").write_text(
            json.dumps(selector, sort_keys=True, separators=(",", ":")),
            encoding="ascii",
        )
        (root / "selector.json").chmod(0o600)

        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ):
            lifecycle = self.client._load_lifecycle_blue_lane(root)
            with self.assertRaisesRegex(ValueError, "contract mismatch|not migratable"):
                self.client._read_broker_selector_view(root)

        self.assertIsNotNone(lifecycle)
        self.assertEqual(lifecycle.transport, "broker")
        self.assertEqual(lifecycle.protocol_version, 1)
        self.assertIsNone(lifecycle.anchor)

    def test_broker_status_accepts_live_v1_selected_green_projection(self) -> None:
        root = self.root / "broker-state"
        _selector, lane = self._install_v1_selected_green_with_lifecycle_blue(root)
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
            self.client, "invoke_dispatcher_ping", return_value=ping
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=True
        ):
            result = self.client.broker_status()

        self.assertEqual(result.status, self.client.RuntimeStatus.OK, result.error)
        self.assertTrue(result.result["active"])
        self.assertTrue(result.result["dispatcher_ready"])
        self.assertFalse(result.result["rollback_available"])
        self.assertEqual(
            result.result["selected"]["artifact_sha256"], lane.artifact_digest
        )

    def test_broker_status_rejects_selectorless_live_legacy_broker(self) -> None:
        root = self.root / "broker-state"
        self._install_legacy_blue(root, body="#!/bin/sh\nexit 0\n")
        (root / self.client.BROKER_SELECTOR_FILENAME).unlink()

        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_broker_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "_broker_ping", return_value=True
        ) as broker_ping:
            result = self.client.broker_status()

        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        self.assertTrue(result.result["installed"])
        self.assertFalse(result.result["active"])
        self.assertFalse(result.result["dispatcher_ready"])
        self.assertEqual(result.error, "provider broker selector is unavailable")
        broker_ping.assert_not_called()

    def test_broker_status_requires_stable_selected_dispatcher_ping(self) -> None:
        root = self.root / "broker-state"
        self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        unavailable = self.client.RuntimeResult(
            self.client.RuntimeStatus.UNAVAILABLE,
            error="provider dispatcher ping is unavailable",
        )
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=unavailable
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=True
        ):
            result = self.client.broker_status()

        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        self.assertFalse(result.result["active"])
        self.assertFalse(result.result["dispatcher_ready"])

    def test_broker_status_requires_dispatcher_to_return_idle(self) -> None:
        root = self.root / "broker-state"
        self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
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
            self.client, "invoke_dispatcher_ping", return_value=ping
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=False
        ) as wait_for_idle:
            result = self.client.broker_status()

        self.assertEqual(result.status, self.client.RuntimeStatus.UNAVAILABLE)
        self.assertFalse(result.result["active"])
        self.assertFalse(result.result["dispatcher_ready"])
        self.assertTrue(result.result["persistent_process"])
        wait_for_idle.assert_called_once()

    def test_broker_status_rejects_invalid_retained_lane(self) -> None:
        root = self.root / "broker-state"
        selector = self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        selector["retained"] = dict(selector["selected"])
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ):
            selected_lane = self.client._load_selector_v2_lane(
                root, selector["selected"], role="selected"
            )
        ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK,
            result={"ready": True},
            provenance={"operation": "dispatcher_ping"},
        )
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_read_broker_selector_view", return_value=selector
        ), mock.patch.object(
            self.client,
            "_load_selector_v2_lane",
            side_effect=(selected_lane, ValueError("retained lane is invalid")),
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=ping
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=True
        ):
            result = self.client.broker_status()

        self.assertEqual(result.status, self.client.RuntimeStatus.INTEGRITY_ERROR)
        self.assertEqual(result.error, "provider broker status could not be proven")

    def test_broker_status_does_not_advertise_unloaded_retained_job(self) -> None:
        root = self.root / "broker-state"
        selector = self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        selector["retained"] = dict(selector["selected"])
        selected = self.client.BrokerLaneSnapshot(
            name="selected",
            generation=29,
            artifact_digest="c" * 64,
            manifest_digest="d" * 64,
            label="com.agent-collab.provider-dispatcher.selected",
            socket_path=root / "selected.sock",
        )
        retained = replace(
            selected,
            name="retained",
            generation=28,
            label="com.agent-collab.provider-dispatcher.retained",
            socket_path=root / "retained.sock",
        )
        ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK,
            result={"ready": True},
            provenance={"operation": "dispatcher_ping"},
        )
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_read_broker_selector_view", return_value=selector
        ), mock.patch.object(
            self.client,
            "_load_selector_v2_lane",
            side_effect=(selected, retained),
        ), mock.patch.object(
            self.client, "_job_loaded", side_effect=(True, False)
        ) as job_loaded, mock.patch.object(
            self.client, "_exact_mode", return_value=object()
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=ping
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=True
        ):
            result = self.client.broker_status()

        self.assertEqual(result.status, self.client.RuntimeStatus.OK, result.error)
        self.assertTrue(result.result["active"])
        self.assertTrue(result.result["dispatcher_ready"])
        self.assertFalse(result.result["rollback_available"])
        self.assertEqual(
            job_loaded.call_args_list,
            [mock.call(selected.label), mock.call(retained.label)],
        )

    def test_v1_green_derivation_accepts_already_drained_blue_plane(self) -> None:
        root = self.root / "broker-state"
        selector_v1, lane = self._install_legacy_dispatcher1_without_blue(root)
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ):
            derived = self.client._read_broker_selector_view(root)

        self.assertEqual(derived["selected"]["transport"], "dispatcher")
        self.assertEqual(derived["selected"]["protocol_version"], 1)
        self.assertEqual(derived["selected"]["artifact_sha256"], lane.artifact_digest)
        self.assertIsNone(derived["lifecycle"])
        self.assertEqual(
            derived["selector_v1_sha256"],
            hashlib.sha256(
                (root / self.client.BROKER_SELECTOR_FILENAME).read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(selector_v1["selected_lane"], "green")

    def test_stage_dispatcher_rejects_runtime_v1_as_selected_routing_state(
        self,
    ) -> None:
        root = self.root / "broker-state"
        blue_state_raw, blue_plist_raw, blue = self._install_protocol_v1_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        selector = {
            "schema_version": 1,
            "generation": 4,
            "selected_lane": "blue",
            "blue": {
                "artifact_sha256": blue["artifact_sha256"],
                "manifest_sha256": blue["manifest_sha256"],
            },
            "green": None,
        }
        (root / "selector.json").write_bytes(
            self.client._selector_bytes(selector)
        )
        (root / "selector.json").chmod(0o600)
        self._fixture(body="#!/bin/sh\nexit 7\n")
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_bootout_broker", return_value=True
        ) as bootout, mock.patch.object(
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

        self.assertEqual(staged.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertEqual((root / "state.json").read_bytes(), blue_state_raw)
        self.assertEqual((root / "broker.plist").read_bytes(), blue_plist_raw)
        selector = json.loads((root / "selector.json").read_text(encoding="utf-8"))
        self.assertEqual(selector["selected_lane"], "blue")
        self.assertEqual(selector["blue"], {
            "artifact_sha256": blue["artifact_sha256"],
            "manifest_sha256": blue["manifest_sha256"],
        })
        self.assertIsNone(selector["green"])
        self.assertFalse((root / "selector-v2.json").exists())
        bootout.assert_not_called()

    def test_lifecycle_bridge_rejects_every_unlisted_protocol_version(self) -> None:
        self._fixture()
        manifest = json.loads(
            (self.root / "runtime-manifest.json").read_text(encoding="utf-8")
        )
        for forbidden in (0, 3, True, 1.0):
            with self.subTest(forbidden=forbidden):
                entry, _error = self.client._manifest_entry(
                    manifest, runtime_protocol_version=forbidden
                )
                self.assertIsNone(entry)
                with self.assertRaises(ValueError):
                    self.client._record_for(
                        root=self.root,
                        artifact_digest="a" * 64,
                        manifest_digest="b" * 64,
                        plist_digest="c" * 64,
                        previous=None,
                        runtime_protocol_version=forbidden,
                    )

    def test_lifecycle_bridge_validates_previous_record_at_its_own_protocol(self) -> None:
        root = self.root / "broker-state"
        _state_raw, _plist_raw, blue = self._install_protocol_v1_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        candidate = self.client._record_for(
            root=root,
            artifact_digest="d" * 64,
            manifest_digest="e" * 64,
            plist_digest="f" * 64,
            previous=blue,
            runtime_protocol_version=2,
        )

        self.assertTrue(
            self.client._broker_record_valid(
                candidate,
                root,
                allow_previous=True,
                runtime_protocol_version=2,
            )
        )

        invalid_previous = dict(blue)
        invalid_previous["runtime_protocol_version"] = 3
        candidate["previous"] = invalid_previous
        self.assertFalse(
            self.client._broker_record_valid(
                candidate,
                root,
                allow_previous=True,
                runtime_protocol_version=2,
            )
        )

    def test_lifecycle_loader_derives_v1_protocol_from_published_manifest(
        self,
    ) -> None:
        root = self.root / "broker-state"
        blue_state_raw, _blue_plist_raw, blue = self._install_protocol_v1_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        corrupted = dict(blue)
        corrupted["runtime_protocol_version"] = 2
        (root / "state.json").write_bytes(self.client._state_bytes(corrupted))
        (root / "state.json").chmod(0o600)

        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ):
            with self.assertRaisesRegex(ValueError, "contract mismatch"):
                self.client._load_lifecycle_blue_lane(root)
            (root / "state.json").write_bytes(blue_state_raw)
            (root / "state.json").chmod(0o600)
            lifecycle = self.client._load_lifecycle_blue_lane(root)

        self.assertEqual(lifecycle.protocol_version, 1)
        self.assertIsNone(lifecycle.anchor)

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
        self.assertIsNone(selector["green"])
        selector_v2 = json.loads(
            (root / "selector-v2.json").read_text(encoding="utf-8")
        )
        self.assertEqual(selector_v2["candidate"], staged.result["candidate"])
        self.assertEqual(selector_v2["selected"]["transport"], "broker")
        token = self.client._dispatcher_lane_token(
            selector_v2["candidate"]["artifact_sha256"],
            selector_v2["candidate"]["manifest_sha256"],
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
            before = json.loads((root / "selector-v2.json").read_text(encoding="utf-8"))
            committed = self.client.commit_dispatcher_selector()
        self.assertEqual(committed.status, self.client.RuntimeStatus.OK, committed.error)
        after = json.loads((root / "selector-v2.json").read_text(encoding="utf-8"))
        self.assertEqual(after["generation"], before["generation"] + 1)
        self.assertEqual(after["selected"], before["candidate"])
        self.assertEqual(after["retained"], before["selected"])
        self.assertIsNone(after["candidate"])
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
            before = (root / "selector-v2.json").read_bytes()
            original = self.client._write_private_atomic

            def fail_selector(path, content, *, mode):
                if Path(path).name == self.client.BROKER_SELECTOR_V2_FILENAME:
                    raise OSError("fixture selector write denied")
                return original(path, content, mode=mode)

            with mock.patch.object(
                self.client, "_write_private_atomic", side_effect=fail_selector
            ):
                failed = self.client.commit_dispatcher_selector()
        self.assertEqual(failed.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertEqual((root / "selector-v2.json").read_bytes(), before)

    def test_abort_candidate_removes_only_green_and_keeps_blue_byte_identical(self) -> None:
        root = self.root / "broker-state"
        blue_state_raw, blue_plist_raw, _blue = self._install_legacy_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        staged = self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        selector_before = json.loads(
            (root / "selector-v2.json").read_text(encoding="utf-8")
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
            (root / "selector-v2.json").read_text(encoding="utf-8")
        )
        self.assertEqual(selector_after["generation"], selector_before["generation"] + 1)
        self.assertEqual(selector_after["selected"], selector_before["selected"])
        self.assertEqual(selector_after["retained"], selector_before["retained"])
        self.assertIsNone(selector_after["candidate"])
        token = self.client._dispatcher_lane_token(
            staged.result["candidate"]["artifact_sha256"],
            staged.result["candidate"]["manifest_sha256"],
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
        fixtures = (
            (b"{}\n", blue_plist_raw),
            (blue_state_raw, b"not-a-plist"),
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

    def test_recover_blue_second_write_failure_preserves_rollback_bytes(self) -> None:
        root = self.root / "broker-state"
        _state_raw, _plist_raw, blue = self._install_legacy_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        previous = self.client._record_for(
            root=root,
            artifact_digest="d" * 64,
            manifest_digest="e" * 64,
            plist_digest="f" * 64,
            previous=None,
            runtime_protocol_version=2,
        )
        blue_with_previous = dict(blue)
        blue_with_previous["previous"] = previous
        (root / "state.json").write_bytes(
            self.client._state_bytes(blue_with_previous)
        )
        (root / "state.json").chmod(0o600)
        state_before = (root / "state.json").read_bytes()
        plist_before = (root / "broker.plist").read_bytes()
        write_count = 0
        original_write = self.client._write_private_atomic

        def fail_second_write(path, content, *, mode):
            nonlocal write_count
            write_count += 1
            if write_count == 2:
                raise OSError("fixture broker plist write failed")
            return original_write(path, content, mode=mode)

        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "_bootout_broker", return_value=True
        ) as bootout, mock.patch.object(
            self.client, "_write_private_atomic", side_effect=fail_second_write
        ):
            recovered = self.client.recover_last_committed_control_plane()

        self.assertEqual(recovered.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertEqual((root / "state.json").read_bytes(), state_before)
        self.assertEqual((root / "broker.plist").read_bytes(), plist_before)
        bootout.assert_not_called()
        self.assertEqual(
            json.loads((root / "state.json").read_text(encoding="utf-8"))[
                "previous"
            ],
            previous,
        )

    def test_recover_failure_boots_out_only_job_started_by_recovery(self) -> None:
        root = self.root / "broker-state"
        state_before, plist_before, _blue = self._install_legacy_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        original_read_state = self.client._read_current_broker_state
        read_count = 0

        def fail_recovery_readback(*args, **kwargs):
            nonlocal read_count
            read_count += 1
            if read_count == 2:
                raise RuntimeError("fixture post-bootstrap readback failed")
            return original_read_state(*args, **kwargs)

        loaded = iter((False, True, False))
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", side_effect=lambda _label: next(loaded)
        ), mock.patch.object(
            self.client, "_bootstrap_broker", return_value=True
        ) as bootstrap, mock.patch.object(
            self.client, "_bootout_broker", return_value=True
        ) as bootout, mock.patch.object(
            self.client,
            "_read_current_broker_state",
            side_effect=fail_recovery_readback,
        ):
            recovered = self.client.recover_last_committed_control_plane()

        self.assertEqual(recovered.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertEqual((root / "state.json").read_bytes(), state_before)
        self.assertEqual((root / "broker.plist").read_bytes(), plist_before)
        bootstrap.assert_called_once_with(root / "broker.plist")
        bootout.assert_called_once_with(root / "broker.plist")

    def test_recover_partial_bootstrap_is_detected_and_booted_out(self) -> None:
        root = self.root / "broker-state"
        state_before, plist_before, _blue = self._install_legacy_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        loaded = iter((False, True, False))

        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", side_effect=lambda _label: next(loaded)
        ), mock.patch.object(
            self.client,
            "_bootstrap_broker",
            side_effect=RuntimeError("fixture partial bootstrap"),
        ) as bootstrap, mock.patch.object(
            self.client, "_bootout_broker", return_value=True
        ) as bootout:
            recovered = self.client.recover_last_committed_control_plane()

        self.assertEqual(recovered.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertEqual((root / "state.json").read_bytes(), state_before)
        self.assertEqual((root / "broker.plist").read_bytes(), plist_before)
        bootstrap.assert_called_once_with(root / "broker.plist")
        bootout.assert_called_once_with(root / "broker.plist")

    def test_recover_blue_success_preserves_valid_previous_record(self) -> None:
        root = self.root / "broker-state"
        _state_raw, _plist_raw, blue = self._install_legacy_blue(
            root, body="#!/bin/sh\nexit 0\n"
        )
        previous = self.client._record_for(
            root=root,
            artifact_digest="d" * 64,
            manifest_digest="e" * 64,
            plist_digest="f" * 64,
            previous=None,
            runtime_protocol_version=2,
        )
        blue_with_previous = dict(blue)
        blue_with_previous["previous"] = previous
        (root / "state.json").write_bytes(
            self.client._state_bytes(blue_with_previous)
        )
        (root / "state.json").chmod(0o600)

        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ):
            recovered = self.client.recover_last_committed_control_plane()

        self.assertEqual(recovered.status, self.client.RuntimeStatus.OK)
        self.assertEqual(
            json.loads((root / "state.json").read_text(encoding="utf-8"))[
                "previous"
            ],
            previous,
        )

    def test_recover_dispatcher_second_write_failure_preserves_exact_bytes(self) -> None:
        root = self.root / "broker-state"
        selector = self._install_modern_selected(
            root, body="#!/bin/sh\nexit 0\n"
        )
        selected = selector["selected"]
        lane = self.client._dispatcher_lane_snapshot(
            root,
            artifact_digest=selected["artifact_sha256"],
            manifest_digest=selected["manifest_sha256"],
            generation=selected["lane_generation"],
            name="selected",
            protocol_version=selected["protocol_version"],
        )
        state_path = self.client._dispatcher_mutable_path(root, lane, "json")
        plist_path = self.client._dispatcher_mutable_path(root, lane, "plist")
        state_document = json.loads(state_path.read_text(encoding="utf-8"))
        state_path.write_text(
            json.dumps(state_document, sort_keys=True, indent=2) + "\n",
            encoding="ascii",
        )
        state_path.chmod(0o600)
        state_before = state_path.read_bytes()
        plist_before = plist_path.read_bytes()
        write_count = 0
        original_write = self.client._write_private_atomic

        def fail_second_write(path, content, *, mode):
            nonlocal write_count
            write_count += 1
            if write_count == 2:
                raise OSError("fixture dispatcher plist write failed")
            return original_write(path, content, mode=mode)

        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "_write_private_atomic", side_effect=fail_second_write
        ):
            recovered = self.client.recover_last_committed_control_plane()

        self.assertEqual(recovered.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(plist_path.read_bytes(), plist_before)

    def test_drain_retiring_clears_retained_and_projection_only_after_idle(self) -> None:
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
        self.assertEqual(drained.result["selected"]["transport"], "dispatcher")
        self.assertTrue(drained.result["retained_drained"])
        self.assertTrue(drained.result["projection_retired"])
        bootout_call.assert_called_once_with(root / "broker.plist")
        self.assertFalse((root / "state.json").exists())
        self.assertFalse((root / "broker.plist").exists())
        self.assertFalse((root / self.client.BROKER_SOCKET_FILENAME).exists())
        self.assertFalse((root / "selector.json").exists())
        selector = json.loads(
            (root / "selector-v2.json").read_text(encoding="utf-8")
        )
        self.assertIsNone(selector["retained"])
        self.assertIsNone(selector["selector_v1_sha256"])

    def test_drain_failure_after_projection_unlink_restores_both_selectors(self) -> None:
        root = self.root / "broker-state"
        self._install_legacy_blue(root, body="#!/bin/sh\nexit 0\n")
        self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        self._commit_staged_dispatcher(root)
        v1_raw = (root / "selector.json").read_bytes()
        v2_raw = (root / "selector-v2.json").read_bytes()
        selected = json.loads(v2_raw)["selected"]
        token = self.client._dispatcher_lane_token(
            selected["artifact_sha256"], selected["manifest_sha256"]
        )
        selected_plist = root / f"provider-dispatcher-{token}.plist"
        selected_plist_raw = selected_plist.read_bytes()
        ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK, result={"ready": True}
        )
        original_unlink = self.client._unlink_private_durable
        injected = {"done": False}

        def unlink(path):
            original_unlink(path)
            if path == root / "selector.json" and not injected["done"]:
                injected["done"] = True
                raise RuntimeError("injected after projection unlink")

        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "_observe_job_quiescent", return_value=True
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=ping
        ), mock.patch.object(
            self.client, "_unlink_private_durable", side_effect=unlink
        ):
            result = self.client.drain_retiring_dispatcher()

        self.assertEqual(result.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertEqual((root / "selector.json").read_bytes(), v1_raw)
        self.assertEqual((root / "selector-v2.json").read_bytes(), v2_raw)
        self.assertEqual(selected_plist.read_bytes(), selected_plist_raw)

    def test_fresh_schema3_install_bootstraps_selected_dispatcher2_without_legacy_plane(self) -> None:
        self._fixture()
        root = self.root / "broker-state"
        expected_artifact = json.loads(
            (self.root / "runtime-manifest.json").read_text(encoding="utf-8")
        )["artifacts"][0]["sha256"]
        ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK, result={"ready": True}
        )
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_bootstrap_broker", side_effect=self._dispatcher_bootstrap(root)
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=True
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=ping
        ):
            result = self.client.install_broker()
        self.assertEqual(result.status, self.client.RuntimeStatus.OK, result.error)
        self.assertTrue(result.result["fresh_bootstrap"])
        self.assertFalse(result.result["persistent_process"])
        selector = json.loads((root / "selector-v2.json").read_text(encoding="utf-8"))
        self.assertIsNone(selector["selector_v1_sha256"])
        self.assertIsNone(selector["lifecycle"])
        self.assertEqual(selector["selected"]["transport"], "dispatcher")
        self.assertEqual(selector["selected"]["protocol_version"], 2)
        token = self.client._dispatcher_lane_token(
            selector["selected"]["artifact_sha256"],
            selector["selected"]["manifest_sha256"],
        )
        state = json.loads(
            (root / f"provider-dispatcher-{token}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(state["artifact_sha256"], expected_artifact)
        plist_path = root / f"provider-dispatcher-{token}.plist"
        self.assertEqual(stat.S_IMODE(plist_path.stat().st_mode), 0o600)
        version = root / "versions" / f"{expected_artifact}-{state['manifest_sha256']}"
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
        plist = plistlib.loads(plist_path.read_bytes())
        self.assertEqual(plist["Label"], f"com.agent-collab.provider-dispatcher.{token}")
        self.assertNotIn("KeepAlive", plist)
        self.assertNotIn("RunAtLoad", plist)

    def test_fresh_schema3_install_failure_restores_empty_selector_and_lane(self) -> None:
        self._fixture()
        root = self.root / "broker-state"
        manifest = json.loads(
            (self.root / "runtime-manifest.json").read_text(encoding="utf-8")
        )
        token = self.client._dispatcher_lane_token(
            manifest["artifacts"][0]["sha256"],
            hashlib.sha256(
                (self.root / "runtime-manifest.json").read_bytes()
            ).hexdigest(),
        )
        failed_ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.PROVIDER_ERROR,
            error="injected ping failure",
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
            self.client, "_bootout_broker", return_value=True
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=failed_ping
        ):
            result = self.client.install_broker()

        self.assertEqual(result.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertTrue(result.result["restored_previous"])
        self.assertFalse((root / "selector-v2.json").exists())
        for suffix in ("json", "plist", "sock"):
            self.assertFalse((root / f"provider-dispatcher-{token}.{suffix}").exists())

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

    def test_selector_v2_rollback_swaps_selected_and_retained_lanes(self) -> None:
        root = self.root / "broker-state"
        initial = self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        committed = self._commit_staged_dispatcher(root)
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
            rolled_back = self.client.rollback_broker()

        self.assertEqual(rolled_back.status, self.client.RuntimeStatus.OK, rolled_back.error)
        selector = json.loads((root / "selector-v2.json").read_text(encoding="utf-8"))
        self.assertEqual(selector["selected"], initial["selected"])
        self.assertEqual(selector["retained"], committed.result["selected"])
        self.assertEqual(selector["generation"], committed.result["generation"] + 1)

    def test_selector_v2_rollback_readback_failure_restores_prior_bytes(self) -> None:
        root = self.root / "broker-state"
        self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        self._commit_staged_dispatcher(root)
        selector_raw = (root / "selector-v2.json").read_bytes()
        selected = json.loads(selector_raw)["selected"]
        token = self.client._dispatcher_lane_token(
            selected["artifact_sha256"], selected["manifest_sha256"]
        )
        selected_plist = root / f"provider-dispatcher-{token}.plist"
        selected_plist_raw = selected_plist.read_bytes()
        ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK, result={"ready": True}
        )
        original_read = self.client._read_broker_selector_v2
        reads = {"count": 0}

        def read(root_path):
            reads["count"] += 1
            if reads["count"] == 2:
                raise RuntimeError("injected rollback readback failure")
            return original_read(root_path)

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
        ), mock.patch.object(
            self.client, "_read_broker_selector_v2", side_effect=read
        ):
            result = self.client.rollback_broker()

        self.assertEqual(result.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertTrue(result.result["restored_previous"])
        self.assertEqual((root / "selector-v2.json").read_bytes(), selector_raw)
        self.assertEqual(selected_plist.read_bytes(), selected_plist_raw)

    def test_new_cycle_requires_retained_lane_drain_before_stage_or_commit(self) -> None:
        root = self.root / "broker-state"
        self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        self._commit_staged_dispatcher(root)
        committed_raw = (root / "selector-v2.json").read_bytes()

        self._fixture(body="#!/bin/sh\nexit 9\n")
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ):
            staged = self.client.stage_dispatcher()
        self.assertEqual(staged.status, self.client.RuntimeStatus.UNAVAILABLE)
        self.assertEqual((root / "selector-v2.json").read_bytes(), committed_raw)

        selector = json.loads(committed_raw)
        selector["candidate"] = {
            "artifact_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
            "transport": "dispatcher",
            "protocol_version": 2,
            "lane_generation": max(
                selector["selected"]["lane_generation"],
                selector["retained"]["lane_generation"],
            )
            + 1,
        }
        candidate_raw = self.client._selector_v2_bytes(selector)
        (root / "selector-v2.json").write_bytes(candidate_raw)
        (root / "selector-v2.json").chmod(0o600)
        with mock.patch.object(self.client, "_broker_root", return_value=root):
            committed = self.client.commit_dispatcher_selector()
        self.assertEqual(committed.status, self.client.RuntimeStatus.UNAVAILABLE)
        self.assertEqual((root / "selector-v2.json").read_bytes(), candidate_raw)

    def test_abort_of_initial_v1_stage_allows_new_digest_without_rewriting_v1(self) -> None:
        root = self.root / "broker-state"
        self._install_legacy_blue(root, body="#!/bin/sh\nexit 0\n")
        first = self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        selector_v1_raw = (root / "selector.json").read_bytes()
        first_candidate = dict(first.result["candidate"])
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_bootout_broker", return_value=True
        ):
            aborted = self.client.abort_dispatcher_candidate()
        self.assertEqual(aborted.status, self.client.RuntimeStatus.OK, aborted.error)
        after_abort = json.loads((root / "selector-v2.json").read_bytes())
        self.assertIsNone(after_abort["candidate"])
        self.assertIsNotNone(after_abort["selector_v1_sha256"])

        second = self._stage_green(root, body="#!/bin/sh\nexit 9\n")
        after_restage = json.loads((root / "selector-v2.json").read_bytes())
        self.assertEqual((root / "selector.json").read_bytes(), selector_v1_raw)
        self.assertEqual(after_restage["selected"], after_abort["selected"])
        self.assertEqual(after_restage["candidate"], second.result["candidate"])
        self.assertNotEqual(after_restage["candidate"], first_candidate)

    def test_modern_commit_drain_then_next_daily_stage_is_live(self) -> None:
        root = self.root / "broker-state"
        self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        committed = self._commit_staged_dispatcher(root)
        selected = dict(committed.result["selected"])
        retained = dict(committed.result["retained"])
        selected_token = self.client._dispatcher_lane_token(
            selected["artifact_sha256"], selected["manifest_sha256"]
        )
        retained_token = self.client._dispatcher_lane_token(
            retained["artifact_sha256"], retained["manifest_sha256"]
        )
        ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK, result={"ready": True}
        )

        def job_loaded(label):
            return label.endswith(selected_token) and not label.endswith(retained_token)

        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", side_effect=job_loaded
        ), mock.patch.object(
            self.client, "_observe_job_quiescent", return_value=True
        ), mock.patch.object(
            self.client, "_bootout_broker", return_value=True
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=ping
        ):
            drained = self.client.drain_retiring_dispatcher()
        self.assertEqual(drained.status, self.client.RuntimeStatus.OK, drained.error)
        drained_selector = json.loads((root / "selector-v2.json").read_bytes())
        self.assertEqual(drained_selector["selected"], selected)
        self.assertIsNone(drained_selector["retained"])
        self.assertIsNone(drained_selector["selector_v1_sha256"])

        staged = self._stage_green(root, body="#!/bin/sh\nexit 9\n")
        next_selector = json.loads((root / "selector-v2.json").read_bytes())
        self.assertEqual(next_selector["selected"], selected)
        self.assertEqual(next_selector["candidate"], staged.result["candidate"])

    def test_idempotent_stage_failure_preserves_existing_candidate_bytes(self) -> None:
        root = self.root / "broker-state"
        self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        selector_raw = (root / "selector-v2.json").read_bytes()
        candidate = json.loads(selector_raw)["candidate"]
        token = self.client._dispatcher_lane_token(
            candidate["artifact_sha256"], candidate["manifest_sha256"]
        )
        mutable = {
            suffix: (root / f"provider-dispatcher-{token}.{suffix}").read_bytes()
            for suffix in ("json", "plist")
        }
        failed_ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.PROVIDER_ERROR, error="injected ping failure"
        )
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=failed_ping
        ):
            result = self.client.stage_dispatcher()

        self.assertEqual(result.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertEqual((root / "selector-v2.json").read_bytes(), selector_raw)
        for suffix, raw in mutable.items():
            self.assertEqual(
                (root / f"provider-dispatcher-{token}.{suffix}").read_bytes(), raw
            )

    def test_stage_failure_cannot_restore_v2_over_newer_projection_drain(self) -> None:
        root = self.root / "broker-state"
        self._install_legacy_blue(root, body="#!/bin/sh\nexit 0\n")
        self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_bootout_broker", return_value=True
        ):
            self.assertEqual(
                self.client.abort_dispatcher_candidate().status,
                self.client.RuntimeStatus.OK,
            )
        baseline = json.loads((root / "selector-v2.json").read_bytes())
        self.assertIsNotNone(baseline["selector_v1_sha256"])
        newer = {
            **baseline,
            "generation": baseline["generation"] + 1,
            "selector_v1_sha256": None,
            "lifecycle": None,
        }
        newer_raw = self.client._selector_v2_bytes(newer)

        class InterleavingLock:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, *_exc):
                (root / "selector.json").unlink()
                (root / "selector-v2.json").write_bytes(newer_raw)
                (root / "selector-v2.json").chmod(0o600)
                return False

        self._fixture(body="#!/bin/sh\nexit 9\n")
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_broker_control_lock", return_value=InterleavingLock()
        ), mock.patch.object(
            self.client,
            "_publish_broker_version",
            side_effect=RuntimeError("injected stage failure"),
        ):
            result = self.client.stage_dispatcher()

        self.assertEqual(result.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertTrue(result.result["restored_previous"])
        self.assertFalse((root / "selector.json").exists())
        self.assertEqual((root / "selector-v2.json").read_bytes(), newer_raw)
        with mock.patch.object(self.client, "_broker_root", return_value=root):
            self.assertEqual(self.client._read_broker_selector_view(root), newer)

    def test_commit_failure_cannot_clobber_newer_abort_transition(self) -> None:
        root = self.root / "broker-state"
        self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        baseline = json.loads((root / "selector-v2.json").read_bytes())
        newer = {
            **baseline,
            "generation": baseline["generation"] + 1,
            "candidate": None,
        }
        newer_raw = self.client._selector_v2_bytes(newer)

        class InterleavingLock:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, *_exc):
                (root / "selector-v2.json").write_bytes(newer_raw)
                (root / "selector-v2.json").chmod(0o600)
                return False

        original_read = self.client._read_broker_selector_v2
        reads = {"count": 0}

        def read(root_path):
            reads["count"] += 1
            if reads["count"] == 2:
                raise RuntimeError("injected commit readback failure")
            return original_read(root_path)

        ping = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK, result={"ready": True}
        )
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_broker_control_lock", return_value=InterleavingLock()
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ), mock.patch.object(
            self.client, "_wait_for_job_idle", return_value=True
        ), mock.patch.object(
            self.client, "invoke_dispatcher_ping", return_value=ping
        ), mock.patch.object(
            self.client, "_read_broker_selector_v2", side_effect=read
        ):
            result = self.client.commit_dispatcher_selector()

        self.assertEqual(result.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertTrue(result.result["restored_previous"])
        self.assertEqual((root / "selector-v2.json").read_bytes(), newer_raw)

    def test_abort_failure_cannot_clobber_newer_commit_transition(self) -> None:
        root = self.root / "broker-state"
        self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        baseline = json.loads((root / "selector-v2.json").read_bytes())
        newer = {
            **baseline,
            "generation": baseline["generation"] + 1,
            "selected": baseline["candidate"],
            "retained": baseline["selected"],
            "candidate": None,
        }
        newer_raw = self.client._selector_v2_bytes(newer)

        class InterleavingLock:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, *_exc):
                (root / "selector-v2.json").write_bytes(newer_raw)
                (root / "selector-v2.json").chmod(0o600)
                return False

        original_read = self.client._read_broker_selector_v2
        reads = {"count": 0}

        def read(root_path):
            reads["count"] += 1
            if reads["count"] == 2:
                raise RuntimeError("injected abort readback failure")
            return original_read(root_path)

        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_broker_control_lock", return_value=InterleavingLock()
        ), mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(
            self.client, "_read_broker_selector_v2", side_effect=read
        ):
            result = self.client.abort_dispatcher_candidate()

        self.assertEqual(result.status, self.client.RuntimeStatus.PROVIDER_ERROR)
        self.assertTrue(result.result["restored_previous"])
        self.assertEqual((root / "selector-v2.json").read_bytes(), newer_raw)

    def test_noop_schema3_install_preserves_selected_selector_bytes(self) -> None:
        root = self.root / "broker-state"
        self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        prior = (root / "selector-v2.json").read_bytes()
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(self.client, "_job_loaded", return_value=True):
            repeated = self.client.install_broker()

        self.assertEqual(repeated.status, self.client.RuntimeStatus.OK, repeated.error)
        self.assertFalse(repeated.result["fresh_bootstrap"])
        self.assertEqual((root / "selector-v2.json").read_bytes(), prior)

    def test_same_artifact_with_new_manifest_requires_staged_update(self) -> None:
        root = self.root / "broker-state"
        self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        prior = (root / "selector-v2.json").read_bytes()
        manifest_path = self.root / "runtime-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(self.client, "_job_loaded", return_value=True):
            updated = self.client.install_broker()

        self.assertEqual(updated.status, self.client.RuntimeStatus.CONFIG_ERROR)
        self.assertEqual((root / "selector-v2.json").read_bytes(), prior)
        self.assertEqual(len(tuple((root / "versions").iterdir())), 1)

    def test_unverified_selected_version_blocks_noop_install(self) -> None:
        root = self.root / "broker-state"
        selector = self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        prior = (root / "selector-v2.json").read_bytes()
        selected = selector["selected"]
        version = root / "versions" / (
            f"{selected['artifact_sha256']}-{selected['manifest_sha256']}"
        )
        (version / "runtime-manifest.json").chmod(0o600)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ):
            updated = self.client.install_broker()

        self.assertEqual(updated.status, self.client.RuntimeStatus.INTEGRITY_ERROR)
        self.assertEqual((root / "selector-v2.json").read_bytes(), prior)

    def test_uninstall_removes_mutable_state_but_retains_versions(self) -> None:
        root = self.root / "broker-state"
        selector = self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        token = self.client._dispatcher_lane_token(
            selector["selected"]["artifact_sha256"],
            selector["selected"]["manifest_sha256"],
        )
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "_broker_root", return_value=root), mock.patch.object(
            self.client, "_observe_job_quiescent", return_value=True
        ), mock.patch.object(
            self.client, "_bootout_broker", return_value=True
        ), mock.patch.object(self.client, "_job_loaded", return_value=False):
            result = self.client.uninstall_broker()
        self.assertEqual(result.status, self.client.RuntimeStatus.OK, result.error)
        self.assertTrue(result.result["versions_retained"])
        self.assertTrue(any((root / "versions").iterdir()))
        self.assertFalse((root / "selector-v2.json").exists())
        for suffix in ("json", "plist", "sock"):
            self.assertFalse((root / f"provider-dispatcher-{token}.{suffix}").exists())

    def test_foreign_or_malformed_dispatcher_plist_blocks_noop_install(self) -> None:
        root = self.root / "broker-state"
        selector = self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        token = self.client._dispatcher_lane_token(
            selector["selected"]["artifact_sha256"],
            selector["selected"]["manifest_sha256"],
        )
        (root / f"provider-dispatcher-{token}.plist").chmod(0o644)
        with mock.patch.object(
            self.client, "_verify_macos_signature", return_value=(True, "")
        ), mock.patch.object(self.client, "PLUGIN_ROOT", self.root), mock.patch.object(
            self.client, "_broker_root", return_value=root
        ):
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

    def test_launchctl_absolute_deadline_bounds_collection_and_preflight(
        self,
    ) -> None:
        process = mock.Mock(returncode=0)
        arguments = ["print", f"gui/{os.getuid()}/{self.client.BROKER_LABEL}"]
        with mock.patch.object(
            self.client.subprocess, "Popen", return_value=process
        ) as popen, mock.patch.object(
            self.client,
            "_collect_bounded_output",
            return_value=(b"state = not running\n", b"", None),
        ) as collect, mock.patch.object(
            self.client.time, "monotonic", side_effect=(100.0, 100.25)
        ):
            result = self.client._launchctl(arguments, deadline=101.0)

        self.assertEqual(result.returncode, 0)
        collect.assert_called_once_with(process, timeout_ms=750.0)
        popen.assert_called_once()

        with mock.patch.object(
            self.client.subprocess, "Popen"
        ) as expired_popen, mock.patch.object(
            self.client.time, "monotonic", return_value=101.0
        ):
            with self.assertRaises(RuntimeError):
                self.client._launchctl(arguments, deadline=101.0)
        expired_popen.assert_not_called()

    def test_job_loaded_forwards_deadline_to_launchctl(self) -> None:
        # The retained-lane availability probe on the request-dispatch path must
        # be bounded by the caller deadline, not launchctl's independent 20s
        # default, so a small-timeout request cannot block ~20s before dispatch.
        with mock.patch.object(
            self.client,
            "_launchctl",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as lc:
            self.assertTrue(
                self.client._job_loaded(self.client.BROKER_LABEL, deadline=123.0)
            )
        self.assertEqual(lc.call_args.kwargs.get("deadline"), 123.0)

    def test_job_loaded_default_deadline_is_none(self) -> None:
        # Lifecycle/status callers (no request timeout) keep the default bound.
        with mock.patch.object(
            self.client,
            "_launchctl",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as lc:
            self.client._job_loaded(self.client.BROKER_LABEL)
        self.assertIsNone(lc.call_args.kwargs.get("deadline"))

    def test_capture_broker_lanes_bounds_retained_probe_by_deadline(self) -> None:
        # _capture_broker_lanes threads the request deadline into the retained
        # lane's _job_loaded probe.
        resolution = mock.Mock(
            spec=self.client.RuntimeResolution,
            artifact_digest="a" * 64,
            manifest_digest="b" * 64,
        )
        selected = mock.Mock(label="com.agent-collab.provider-broker")
        retained = mock.Mock(
            label="com.agent-collab.provider-dispatcher." + "c" * 32
        )
        with mock.patch.object(
            self.client, "_broker_root", return_value=self.root
        ), mock.patch.object(
            self.client,
            "_read_broker_selector_view",
            return_value={"selected": {"x": 1}, "retained": {"y": 2}},
        ), mock.patch.object(
            self.client,
            "_load_selector_v2_lane",
            side_effect=[selected, retained],
        ), mock.patch.object(
            self.client, "_job_loaded", return_value=True
        ) as jl:
            self.client._capture_broker_lanes(resolution, deadline=456.0)
        # The retained-lane probe received the deadline.
        self.assertTrue(
            any(c.kwargs.get("deadline") == 456.0 for c in jl.call_args_list)
        )

    def test_wait_for_job_idle_propagates_deadline_and_caps_sleep(self) -> None:
        label = self.client.BROKER_LABEL
        with mock.patch.object(
            self.client.time,
            "monotonic",
            side_effect=(100.0, 100.04, 100.05),
        ), mock.patch.object(
            self.client, "_job_process_idle", return_value=False
        ) as idle, mock.patch.object(
            self.client.time, "sleep"
        ) as sleep:
            result = self.client._wait_for_job_idle(label, deadline=100.05)

        self.assertFalse(result)
        idle.assert_called_once_with(label, deadline=100.05)
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 0.01)

        with mock.patch.object(
            self.client.time, "monotonic", return_value=100.0
        ), mock.patch.object(
            self.client,
            "_job_process_idle",
            side_effect=RuntimeError("launchctl deadline expired"),
        ) as failed_idle:
            self.assertFalse(
                self.client._wait_for_job_idle(label, deadline=101.0)
            )
        failed_idle.assert_called_once_with(label, deadline=101.0)

    def test_wait_for_job_idle_fails_closed_on_probe_spawn_errors(self) -> None:
        # An accepted-request idle probe can fail with OSError (launchctl spawn
        # failure) or subprocess.SubprocessError; these must be treated as a
        # failed idle proof (return False -> TEARDOWN_ERROR at the accepted
        # boundary), not escape and become PROTOCOL_ERROR.
        label = self.client.BROKER_LABEL
        for exc in (
            OSError("launchctl could not be spawned"),
            self.client.subprocess.SubprocessError("launchctl crashed"),
        ):
            with self.subTest(exc=type(exc).__name__):
                with mock.patch.object(
                    self.client.time, "monotonic", return_value=100.0
                ), mock.patch.object(
                    self.client, "_operator_home", return_value=str(self.root)
                ), mock.patch.object(
                    self.client, "_job_process_idle", side_effect=exc
                ):
                    self.assertFalse(
                        self.client._wait_for_job_idle(label, deadline=101.0)
                    )

    def test_wait_for_job_idle_fails_closed_when_operator_home_unavailable(self) -> None:
        # Operator-home-unavailable is an environmental condition, pre-checked
        # OUT of the probe loop: fail closed to not-idle without ever invoking
        # the probe.
        label = self.client.BROKER_LABEL
        with mock.patch.object(
            self.client.time, "monotonic", return_value=100.0
        ), mock.patch.object(
            self.client, "_operator_home", return_value=None
        ), mock.patch.object(
            self.client, "_job_process_idle"
        ) as probe:
            self.assertFalse(
                self.client._wait_for_job_idle(label, deadline=101.0)
            )
        probe.assert_not_called()

    def test_wait_for_job_idle_fails_closed_on_home_failure_inside_loop(self) -> None:
        # _launchctl re-resolves operator-home on every call, so a transient
        # getpwuid failure AFTER the entry pre-check passed makes an in-loop
        # probe raise ValueError("operator home is unavailable"). That
        # environmental failure must fail closed (not escape as PROTOCOL_ERROR).
        label = self.client.BROKER_LABEL
        with mock.patch.object(
            self.client.time, "monotonic", return_value=100.0
        ), mock.patch.object(
            self.client, "_operator_home", return_value=str(self.root)
        ), mock.patch.object(
            self.client,
            "_job_process_idle",
            side_effect=self.client._OperatorHomeUnavailable(
                "operator home is unavailable"
            ),
        ):
            self.assertFalse(
                self.client._wait_for_job_idle(label, deadline=101.0)
            )

    def test_launchctl_raises_typed_operator_home_unavailable(self) -> None:
        # _launchctl raises the typed subclass (not a bare ValueError) so the
        # idle loop can distinguish this environmental case race-free.
        with mock.patch.object(self.client, "_operator_home", return_value=None):
            with self.assertRaises(self.client._OperatorHomeUnavailable):
                self.client._launchctl(["print", "gui/0/x"])
        # It remains a ValueError subclass for backward compatibility.
        self.assertTrue(
            issubclass(self.client._OperatorHomeUnavailable, ValueError)
        )

    def test_wait_for_job_idle_reraises_a_genuine_code_bug_value_error(self) -> None:
        # A ValueError that is NOT the environmental operator-home case (home
        # still resolves) is a code bug and must propagate, not be masked as a
        # failed idle proof.
        label = self.client.BROKER_LABEL
        with mock.patch.object(
            self.client.time, "monotonic", return_value=100.0
        ), mock.patch.object(
            self.client, "_operator_home", return_value=str(self.root)
        ), mock.patch.object(
            self.client,
            "_job_process_idle",
            side_effect=ValueError("provider job label is invalid"),
        ):
            with self.assertRaises(ValueError):
                self.client._wait_for_job_idle(label, deadline=101.0)

    def test_wait_for_job_idle_rejects_invalid_label_before_probe(self) -> None:
        # Label validation is hoisted to entry: an invalid label is a caller
        # bug that must raise, not be swallowed by the fail-closed loop.
        with mock.patch.object(
            self.client, "_operator_home", return_value=str(self.root)
        ), mock.patch.object(
            self.client, "_job_process_idle"
        ) as probe:
            with self.assertRaises(ValueError):
                self.client._wait_for_job_idle("not-a-valid-label", deadline=101.0)
        probe.assert_not_called()

    def test_lifecycle_entrypoints_map_launchctl_runtime_errors_to_typed_failures(self) -> None:
        root = self.root / "broker-state"
        self._install_modern_selected(root, body="#!/bin/sh\nexit 0\n")
        self._stage_green(root, body="#!/bin/sh\nexit 7\n")
        self._commit_staged_dispatcher(root)
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_job_loaded", side_effect=RuntimeError("timeout")
        ):
            status = self.client.broker_status()
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_read_broker_selector_v2", side_effect=RuntimeError("timeout")
        ):
            rolled_back = self.client.rollback_broker()
        with mock.patch.object(
            self.client, "_broker_root", return_value=root
        ), mock.patch.object(
            self.client, "_observe_job_quiescent", side_effect=RuntimeError("timeout")
        ):
            uninstalled = self.client.uninstall_broker()

        for result in (status, rolled_back, uninstalled):
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
        self.assertEqual(result.result["argv"], ["invoke", "--protocol", "2"])
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
    "protocol_version": 2,
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
    "protocol_version": 2,
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
                # `--check-notarization` MUST be combined with the requirement so
                # activation runs the online Apple notary lookup and therefore
                # verifies on a clean host (a freshly-installed plugin checkout has
                # no stapled ticket and no local trust state). Empirically
                # fail-closed on macos-15.7.7 (offline -> rc 3), so it does not
                # "fail open": rc 0 requires a positive online confirmation.
                if timestamp.startswith("Timestamp=Jul"):
                    self.assertTrue(
                        any(
                            "--test-requirement" in cmd
                            and "=notarized" in cmd
                            and "--check-notarization" in cmd
                            for cmd in observed
                        ),
                        "the =notarized requirement and --check-notarization must "
                        "be in the SAME codesign command (online notary lookup)",
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
            row_config={"task_class": "standard_codegen", "effort": "medium"},
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
                    row_config={
                        "task_class": "standard_codegen",
                        "effort": "medium",
                    },
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
    "protocol_version": 2,
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
    "protocol_version": 2,
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
            (
                "composer",
                "codegen",
                {"task_class": "standard_codegen", "effort": "medium"},
                "xai/grok-composer-2.5-fast",
                "xai",
            ),
        )
        for route, action, row, wrong_model, family in cases:
            with self.subTest(route=route, action=action):
                self._fixture(
                    body=f"""#!/usr/bin/env python3
import json, sys
request = json.loads(sys.stdin.readline())
print(json.dumps({{
    "protocol_version": 2,
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

    def test_protocol_v1_manifest_and_response_fail_closed(self) -> None:
        self._fixture()
        manifest_path = self.root / "runtime-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["protocol_version"] = 1
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
            resolution = self.client.resolve_runtime()
        self.assertEqual(resolution.status, self.client.RuntimeStatus.MANIFEST_INVALID)

        self._fixture()
        envelope = self._envelope()
        stale = json.dumps(
            {
                "protocol_version": 1,
                "request_id": envelope.request_id,
                "status": "provider_error",
                "error": "stale runtime",
            }
        ).encode("utf-8")
        parsed = self.client._parse_response(stale, envelope, 0)
        self.assertEqual(parsed.status, self.client.RuntimeStatus.PROTOCOL_ERROR)

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
    "protocol_version": 2,
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

    def test_terminate_and_reap_is_deadline_bounded(self) -> None:
        # A child that never exits must NOT block the two fixed 5s waits past
        # the caller deadline: with an already-expired deadline the call does
        # one non-blocking poll and returns False promptly (teardown unproven).
        client = self.client

        class _NeverExits:
            pid = 999999

            def __init__(self) -> None:
                self.wait_calls = 0

            def poll(self):
                return None

            def wait(self, timeout=None):
                self.wait_calls += 1
                raise subprocess.TimeoutExpired(cmd="x", timeout=timeout)

            def kill(self):
                pass

        stub = _NeverExits()
        with mock.patch.object(client.os, "killpg") as killpg:
            reaped = client._terminate_and_reap(stub, deadline=time.monotonic())
        self.assertFalse(reaped)
        # An already-expired deadline must NOT make a blocking wait(timeout>0)
        # call (the old two fixed 5s waits); a non-blocking poll pass instead.
        self.assertEqual(stub.wait_calls, 0)
        killpg.assert_called_once()
        args = killpg.call_args.args
        self.assertEqual(args[0], stub.pid)
        self.assertEqual(args[1], signal.SIGKILL)

    def test_terminate_and_reap_returns_false_on_leader_only_fallback(self) -> None:
        # killpg failing with a non-ESRCH OSError means the whole-group kill is
        # unproven; killing+reaping only the leader must return False so the
        # caller types TEARDOWN_ERROR, never a false "teardown proven".
        client = self.client

        class _LeaderReaps:
            pid = 999998

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        stub = _LeaderReaps()
        with mock.patch.object(
            client.os, "killpg", side_effect=PermissionError("cannot signal group")
        ):
            reaped = client._terminate_and_reap(stub, deadline=time.monotonic() + 5)
        self.assertFalse(reaped)

    def test_terminate_and_reap_treats_group_gone_as_success(self) -> None:
        # killpg raising ProcessLookupError (ESRCH) means the group already
        # exited; reaping the (already-gone) leader is a proven teardown.
        client = self.client

        class _AlreadyGone:
            pid = 999997

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        stub = _AlreadyGone()
        with mock.patch.object(
            client.os, "killpg", side_effect=ProcessLookupError("no such group")
        ):
            reaped = client._terminate_and_reap(stub, deadline=time.monotonic() + 5)
        self.assertTrue(reaped)

    def test_collect_bounded_output_teardown_respects_caller_deadline(self) -> None:
        # A real child holding its pipes open past a short timeout must be torn
        # down without the collection running ~10s past timeout_ms.
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            started = time.monotonic()
            out, err, result = self.client._collect_bounded_output(
                process, timeout_ms=200
            )
            elapsed = time.monotonic() - started
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        self.assertIsNotNone(result)
        self.assertEqual(result.status, self.client.RuntimeStatus.TIMEOUT)
        self.assertLess(elapsed, 3.0)  # bounded, not 200ms + 2x5s

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

    def test_hardlinked_runtime_is_rejected(self) -> None:
        # The source floor still requires nlink == 1: a hardlinked entrypoint is
        # rejected. (A group-writable runtime is now ADMITTED under trust-the-
        # checkout — see test_resolve_runtime_admits_group_writable_member — so only
        # the hardlink guard remains here.)
        binary = self._fixture()
        binary.parent.chmod(0o700)
        hardlink = binary.with_name("hardlink")
        os.link(binary, hardlink)
        binary.parent.chmod(0o500)
        try:
            with mock.patch.object(self.client, "PLUGIN_ROOT", self.root):
                result = self.client.resolve_runtime()
            self.assertEqual(result.status, self.client.RuntimeStatus.PATH_INVALID)
        finally:
            binary.parent.chmod(0o700)
            hardlink.unlink()
            binary.parent.chmod(0o500)

    def test_native_protocol_uses_exact_route_action_fields(self) -> None:
        self._fixture()
        expected_row_fields = {
            ("gemini", "advisory"): {"model", "effort"},
            ("gemini", "long_context"): {"model", "effort", "documents"},
            ("codex", "advisory"): {"model", "effort", "mode"},
            ("opencode", "plan"): {"model", "cwd"},
            ("opencode", "build"): {"model", "cwd"},
            ("grok", "architecture"): {"mode", "task_class", "effort"},
            ("grok", "governance"): {"mode", "task_class", "effort"},
            ("grok", "huge_context"): {"documents", "task_class", "effort"},
            ("composer", "codegen"): {"task_class", "effort"},
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

    def test_grok_routes_share_protocol_v2_and_one_fixed_author_model(self) -> None:
        self._fixture()
        self.assertEqual(self.client.PROTOCOL_VERSION, 2)
        self.assertEqual(
            self.client.FIXED_AUTHOR_MODELS,
            {"grok": "xai/grok-4.5", "composer": "xai/grok-4.5"},
        )

        cases = (
            ("grok", "architecture", "architecture", "high"),
            ("grok", "huge_context", "huge_context", "medium"),
            ("composer", "codegen", "standard_codegen", "medium"),
        )
        for route, action, task_class, effort in cases:
            with self.subTest(route=route, action=action):
                envelope = self._envelope(route=route, action=action)
                document = json.loads(self.client._native_document(envelope))
                self.assertEqual(document["protocol_version"], 2)
                self.assertEqual(document["task_class"], task_class)
                self.assertEqual(document["effort"], effort)
                self.assertNotIn("model", document)

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
