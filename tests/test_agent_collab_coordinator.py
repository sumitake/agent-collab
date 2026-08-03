"""Public semantic coordinator contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

from tests.test_direct_runtime_public_contract import _wire_descriptor


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SemanticCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = _load("coordinator_test_client", PLUGIN / "runtime_client.py")
        cls.coordinator = _load("semantic_coordinator", PLUGIN / "coordinator.py")
        descriptor, digest = _wire_descriptor()
        cls.wire = cls.client.validate_wire_descriptor(
            descriptor, expected_sha256=digest
        )

    def test_repository_request_adds_canonical_repo_source_and_wire_hash(self) -> None:
        request = {
            "request_id": "review-1",
            "logical_action": "review.repository",
            "target_agent": None,
            "author_lineage": "openai",
            "timeout_ms": 5000,
            "prompt": "Review the current repository.",
            "repo_root": str(ROOT),
        }
        native = self.coordinator.validate_request(request, self.wire)
        self.assertEqual(native["wire_contract_sha256"], self.wire.sha256)
        self.assertEqual(
            native["source"], {"mode": "repository", "repo_root": str(ROOT)}
        )
        self.assertNotIn("route", native)
        self.assertNotIn("action", native)

    def test_old_public_route_action_request_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "closed"):
            self.coordinator.validate_request(
                {
                    "request_id": "old-1",
                    "route": "grok",
                    "action": "architecture",
                    "timeout_ms": 5000,
                    "prompt": "old wire",
                },
                self.wire,
            )

    def test_repository_action_requires_repo_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "repo_root"):
            self.coordinator.validate_request(
                {
                    "request_id": "review-2",
                    "logical_action": "review.repository",
                    "target_agent": None,
                    "author_lineage": None,
                    "timeout_ms": 5000,
                    "prompt": "Review.",
                },
                self.wire,
            )

    def test_one_accepted_request_invokes_runtime_once_without_replay(self) -> None:
        calls: list[object] = []
        fake_client = types.SimpleNamespace(
            RuntimeStatus=self.client.RuntimeStatus,
            runtime_contract_snapshot=lambda: (self.wire, "a" * 64, ""),
            invoke=lambda *, envelope: calls.append(envelope)
            or self.client.RuntimeResult(self.client.RuntimeStatus.UNAVAILABLE, error="busy"),
        )
        request = {
            "request_id": "context-1",
            "logical_action": "context.documents.extract",
            "target_agent": None,
            "author_lineage": None,
            "timeout_ms": 5000,
            "prompt": "Extract facts.",
            "documents": [{"label": "a", "content": "one"}],
        }
        with mock.patch.object(self.coordinator, "_load_runtime", return_value=fake_client):
            response, code = self.coordinator.process(request)
        self.assertEqual(code, 0)
        self.assertEqual(response["status"], "unavailable")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
