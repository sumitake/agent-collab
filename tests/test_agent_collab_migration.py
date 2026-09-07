"""Provider-free direct-runtime migration doctor tests."""

from __future__ import annotations

import contextlib
import io
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class DirectMigrationDoctorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.doctor = _load("direct_migration_doctor", PLUGIN / "migration_doctor.py")
        cls.client = _load("migration_test_runtime_client", PLUGIN / "runtime_client.py")
        policy_module = _load("migration_test_policy", PLUGIN / "host_policy.py")
        cls.profile = policy_module.HostProfile(
            primary_id="codex",
            primary_family="openai",
            active_model="observed",
            host_runtime="codex",
            session_identifier="session-1",
            explicit=True,
            governance_ready=True,
            identity_conflict=False,
        )

    @classmethod
    def _wire(cls):
        return cls.client.WireDescriptorSnapshot(
            sha256="b" * 64,
            logical_actions=frozenset({"review.repository"}),
            logical_action_timeout_modes={"review.repository": "admitted_progress_inactivity"},
            routing_source_sha256="c" * 64,
            logical_agents=frozenset({"codex"}),
            routing_request={"type": "routing_request"},
            content_frame={"type": "content"},
            terminal_planning_record={"type": "terminal"},
        )

    def _client_with_resolution(self, resolution):
        return types.SimpleNamespace(
            RuntimeStatus=self.client.RuntimeStatus,
            resolve_runtime=lambda: resolution,
        )

    def test_runtime_state_uses_current_wire_snapshot_shape(self) -> None:
        cases = (
            (
                "available",
                types.SimpleNamespace(
                    status=self.client.RuntimeStatus.OK,
                    wire=self._wire(),
                    error=None,
                ),
                ("available", "b" * 64, 1),
            ),
            (
                "unavailable",
                types.SimpleNamespace(
                    status=self.client.RuntimeStatus.UNAVAILABLE,
                    wire=self._wire(),
                    error="notarization unavailable",
                ),
                ("typed unavailable: notarization unavailable", "b" * 64, 1),
            ),
            (
                "missing wire",
                types.SimpleNamespace(
                    status=self.client.RuntimeStatus.OK,
                    wire=None,
                    error=None,
                ),
                ("invalid: wire descriptor absent", "", 0),
            ),
        )
        for label, resolution, expected in cases:
            with self.subTest(label=label), mock.patch.object(
                self.doctor,
                "_load_runtime_client",
                return_value=self._client_with_resolution(resolution),
            ):
                self.assertEqual(self.doctor._runtime_state(), expected)

    def test_report_json_and_text_use_logical_actions_only(self) -> None:
        resolution = types.SimpleNamespace(
            status=self.client.RuntimeStatus.OK,
            wire=self._wire(),
            error=None,
        )
        fake_policy = types.SimpleNamespace(resolve_profile=lambda _config: self.profile)
        with tempfile.TemporaryDirectory() as raw_home, mock.patch.object(
            self.doctor, "_load_policy", return_value=fake_policy
        ), mock.patch.object(
            self.doctor,
            "_load_runtime_client",
            return_value=self._client_with_resolution(resolution),
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    self.doctor.main(["--home", raw_home, "--json"]),
                    0,
                )
            report_json = json.loads(output.getvalue())

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(self.doctor.main(["--home", raw_home]), 0)
            report_text = output.getvalue()

        self.assertEqual(report_json["provider_routing"], "READY")
        self.assertEqual(report_json["logical_actions"], 1)
        self.assertEqual(report_json["wire_contract_sha256"], "b" * 64)
        self.assertIn("ACTIONS: logical=1", report_text)
        self.assertNotIn("transport=", report_text)
        self.assertNotIn("source-qualified=", report_text)


if __name__ == "__main__":
    unittest.main()
