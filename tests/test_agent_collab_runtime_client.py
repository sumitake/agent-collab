"""Direct process client tests."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests.test_direct_runtime_public_contract import _wire_descriptor


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
        cls.wire = cls.client.validate_wire_descriptor(
            descriptor, expected_sha256=digest
        )

    def _envelope(self, timeout_ms: int) -> dict[str, object]:
        return {
            "wire_contract_sha256": self.wire.sha256,
            "request_id": "direct-1",
            "logical_action": "architecture.conceptual",
            "target_agent": None,
            "author_lineage": None,
            "timeout_ms": timeout_ms,
            "prompt": "Think.",
            "source": {"mode": "conceptual_prompt"},
        }

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


if __name__ == "__main__":
    unittest.main()
