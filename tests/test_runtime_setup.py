"""Closed public CLI for signed runtime management."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
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

    def test_cli_rejects_raw_provider_model_path_and_option_surfaces(self) -> None:
        invalid = (
            [],
            ["status", "extra"],
            ["--provider", "grok"],
            ["--model", "xai/grok-4.5"],
            ["--path", "/tmp/runtime"],
            ["--env", "KEY=VALUE"],
            ["login"],
        )
        for argv in invalid:
            with self.subTest(argv=argv):
                output = io.StringIO()
                with mock.patch.object(
                    self.setup.runtime_client, "manage_runtime"
                ) as managed, contextlib.redirect_stdout(output):
                    exit_code = self.setup.main(list(argv))
                self.assertEqual(exit_code, 2)
                self.assertEqual(json.loads(output.getvalue())["status"], "config_error")
                managed.assert_not_called()

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
