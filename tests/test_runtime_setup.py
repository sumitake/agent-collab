"""Closed public CLI for signed runtime management."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"
CLIENT_PATH = PLUGIN / "runtime_client.py"
SETUP_PATH = PLUGIN / "runtime_setup.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class RuntimeSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = _load("runtime_client", CLIENT_PATH)
        cls.setup = _load("agent_collab_runtime_setup", SETUP_PATH)

    def test_each_public_command_maps_to_one_closed_management_action(self) -> None:
        mapping = {
            "status": "status",
            "prepare": "prepare",
            "login-grok": "grok_login",
        }
        for command, action in mapping.items():
            with self.subTest(command=command):
                result = self.client.RuntimeResult(
                    self.client.RuntimeStatus.OK,
                    result={"management_action": action},
                )
                output = io.StringIO()
                with mock.patch.object(
                    self.setup.runtime_client,
                    "manage_runtime",
                    return_value=result,
                ) as managed, contextlib.redirect_stdout(output):
                    exit_code = self.setup.main([command])
                self.assertEqual(exit_code, 0)
                payload = json.loads(output.getvalue())
                self.assertEqual(payload["status"], "ok")
                self.assertEqual(payload["result"]["management_action"], action)
                self.assertEqual(managed.call_args.kwargs["action"], action)
                self.assertRegex(
                    managed.call_args.kwargs["request_id"],
                    r"^setup-[0-9a-f]{32}$",
                )

    def test_each_broker_command_maps_to_one_closed_lifecycle_action(self) -> None:
        mapping = {
            "install-broker": "install_broker",
            "broker-status": "broker_status",
            "rollback-broker": "rollback_broker",
            "uninstall-broker": "uninstall_broker",
            "stage-dispatcher": "stage_dispatcher",
            "dispatcher-status": "dispatcher_status",
            "commit-selector": "commit_dispatcher_selector",
            "abort-candidate": "abort_dispatcher_candidate",
            "recover-last-committed-control-plane": "recover_last_committed_control_plane",
            "drain-retiring": "drain_retiring_dispatcher",
        }
        for command, function_name in mapping.items():
            with self.subTest(command=command):
                result = self.client.RuntimeResult(
                    self.client.RuntimeStatus.OK,
                    result={"operation": command},
                )
                output = io.StringIO()
                with mock.patch.object(
                    self.setup.runtime_client,
                    function_name,
                    return_value=result,
                ) as lifecycle, mock.patch.object(
                    self.setup.runtime_client, "manage_runtime"
                ) as managed, mock.patch.dict(
                    os.environ, {}, clear=True
                ), mock.patch.object(
                    self.setup.runtime_client,
                    "_sandbox_denies_broker_lifecycle",
                    return_value=False,
                ), contextlib.redirect_stdout(output):
                    exit_code = self.setup.main([command])
                self.assertEqual(exit_code, 0)
                self.assertEqual(json.loads(output.getvalue())["status"], "ok")
                lifecycle.assert_called_once_with()
                managed.assert_not_called()

    def test_codex_seatbelt_rejects_mutating_lifecycle_before_dispatch(self) -> None:
        mutating = (
            ("install-broker", "install_broker"),
            ("rollback-broker", "rollback_broker"),
            ("uninstall-broker", "uninstall_broker"),
            ("stage-dispatcher", "stage_dispatcher"),
            ("commit-selector", "commit_dispatcher_selector"),
            ("abort-candidate", "abort_dispatcher_candidate"),
            (
                "recover-last-committed-control-plane",
                "recover_last_committed_control_plane",
            ),
            ("drain-retiring", "drain_retiring_dispatcher"),
        )
        for command, function_name in mutating:
            with self.subTest(command=command):
                output = io.StringIO()
                with mock.patch.dict(
                    os.environ, {"CODEX_SANDBOX": "seatbelt"}, clear=True
                ), mock.patch.object(
                    self.setup.runtime_client, function_name
                ) as lifecycle, mock.patch.object(
                    self.setup.runtime_client, "broker_status"
                ) as status, mock.patch.object(
                    self.setup.runtime_client, "manage_runtime"
                ) as managed, contextlib.redirect_stdout(output):
                    exit_code = self.setup.main([command])
                self.assertEqual(exit_code, 1)
                self.assertEqual(
                    json.loads(output.getvalue()),
                    {
                        "status": "host_blocked",
                        "error": "broker lifecycle is unavailable from the Codex seatbelt",
                    },
                )
                lifecycle.assert_not_called()
                status.assert_not_called()
                managed.assert_not_called()

    def test_dispatcher_probes_are_closed_non_lifecycle_commands(self) -> None:
        cases = (
            (
                ["dispatcher-ping"],
                "invoke_dispatcher_ping",
                {"timeout_ms": 30_000},
            ),
            (
                ["dispatcher-lock-probe", "--provider", "grok", "--timeout-ms", "750"],
                "invoke_dispatcher_lock_probe",
                {"provider": "grok", "timeout_ms": 750},
            ),
        )
        for argv, function_name, expected_kwargs in cases:
            with self.subTest(argv=argv):
                output = io.StringIO()
                result = self.client.RuntimeResult(
                    self.client.RuntimeStatus.OK,
                    result={"ready": True},
                )
                with mock.patch.object(
                    self.setup.runtime_client, function_name, return_value=result
                ) as probe, mock.patch.object(
                    self.setup.runtime_client, "_broker_lifecycle_seatbelt_block"
                ) as seatbelt, contextlib.redirect_stdout(output):
                    exit_code = self.setup.main(list(argv))
                self.assertEqual(exit_code, 0)
                self.assertEqual(json.loads(output.getvalue())["status"], "ok")
                probe.assert_called_once_with(**expected_kwargs)
                seatbelt.assert_not_called()

    def test_kernel_sandbox_guard_rejects_setup_after_marker_removal(self) -> None:
        output = io.StringIO()
        with mock.patch.dict(
            os.environ, {}, clear=True
        ), mock.patch.object(
            self.setup.runtime_client,
            "_sandbox_denies_broker_lifecycle",
            return_value=True,
        ), mock.patch.object(
            self.setup.runtime_client, "install_broker"
        ) as lifecycle, contextlib.redirect_stdout(output):
            exit_code = self.setup.main(["install-broker"])
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "host_blocked")
        lifecycle.assert_not_called()

    def test_codex_seatbelt_keeps_read_only_broker_status_available(self) -> None:
        result = self.client.RuntimeResult(
            self.client.RuntimeStatus.OK,
            result={"installed": True, "active": True},
        )
        output = io.StringIO()
        with mock.patch.dict(
            os.environ, {"CODEX_SANDBOX": "seatbelt"}, clear=True
        ), mock.patch.object(
            self.setup.runtime_client, "broker_status", return_value=result
        ) as status, mock.patch.object(
            self.setup.runtime_client, "install_broker"
        ) as install, contextlib.redirect_stdout(output):
            exit_code = self.setup.main(["broker-status"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "ok")
        status.assert_called_once_with()
        install.assert_not_called()

    def test_cli_rejects_raw_provider_model_path_and_option_surfaces(self) -> None:
        invalid = (
            [],
            ["status", "extra"],
            ["--provider", "grok"],
            ["--model", "xai/grok-4.5"],
            ["--path", "/tmp/runtime"],
            ["--env", "KEY=VALUE"],
            ["login"],
            ["install-broker", "--path", "/tmp/runtime"],
            ["broker-status", "--socket", "/tmp/provider.sock"],
        )
        for argv in invalid:
            with self.subTest(argv=argv):
                output = io.StringIO()
                with mock.patch.object(
                    self.setup.runtime_client, "manage_runtime"
                ) as managed, mock.patch.object(
                    self.setup.runtime_client, "install_broker"
                ) as install, contextlib.redirect_stdout(output):
                    exit_code = self.setup.main(list(argv))
                self.assertEqual(exit_code, 2)
                self.assertEqual(json.loads(output.getvalue())["status"], "config_error")
                managed.assert_not_called()
                install.assert_not_called()

    def test_typed_management_failure_returns_nonzero_without_extra_fields(self) -> None:
        result = self.client.RuntimeResult(
            self.client.RuntimeStatus.AUTH_ERROR,
            error="managed Grok authentication is unavailable",
        )
        output = io.StringIO()
        with mock.patch.object(
            self.setup.runtime_client,
            "manage_runtime",
            return_value=result,
        ), contextlib.redirect_stdout(output):
            exit_code = self.setup.main(["login-grok"])
        self.assertEqual(exit_code, 1)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "status": "auth_error",
                "error": "managed Grok authentication is unavailable",
            },
        )


if __name__ == "__main__":
    unittest.main()
