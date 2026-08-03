"""Provider-free direct-runtime migration doctor tests."""

from __future__ import annotations

import importlib.util
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

    def test_report_has_no_broker_runtime_or_lifecycle_requirement(self) -> None:
        policy_module = _load("migration_test_policy", PLUGIN / "host_policy.py")
        fake_profile = policy_module.HostProfile(
            primary_id="codex",
            primary_family="openai",
            active_model="observed",
            host_runtime="codex",
            session_identifier="session-1",
            explicit=True,
            governance_ready=True,
            identity_conflict=False,
        )
        fake_policy = types.SimpleNamespace(resolve_profile=lambda _config: fake_profile)
        with tempfile.TemporaryDirectory() as raw_home, mock.patch.object(
            self.doctor, "_load_policy", return_value=fake_policy
        ), mock.patch.object(
            self.doctor,
            "_runtime_state",
            return_value=("available", "b" * 64, 11, 12, 16),
        ):
            report = self.doctor.build_report(home=Path(raw_home), explicit_config=None)
        self.assertEqual(report.provider_routing, "READY")
        self.assertEqual(report.logical_actions, 11)
        self.assertEqual(report.transport_actions, 12)
        self.assertEqual(report.action_source_pairs, 16)
        self.assertFalse(hasattr(report, "broker_runtime"))


if __name__ == "__main__":
    unittest.main()
