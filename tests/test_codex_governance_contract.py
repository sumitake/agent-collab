"""Contract-boundary tests for the Codex governance route."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"
CONTRACT = ("codex", "governance")


def _load_runtime_client():
    name = "codex_governance_runtime_client"
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN / "runtime_client.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CodexGovernanceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = _load_runtime_client()
        cls.schema = json.loads(
            (PLUGIN / "runtime-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        cls.manifest = json.loads(
            (PLUGIN / "runtime-manifest.json").read_text(encoding="utf-8")
        )

    def test_client_and_schema_accept_dev_codex_governance_contract(self) -> None:
        schema_rows = self.schema["properties"]["artifacts"]["items"][
            "properties"
        ]["contracts"]["items"]["oneOf"]
        schema_contracts = {
            (
                row["properties"]["route"]["const"],
                row["properties"]["action"]["const"],
            )
            for row in schema_rows
        }

        self.assertIn(CONTRACT, self.client.SUPPORTED_CONTRACTS)
        self.assertIn(CONTRACT, schema_contracts)
        self.assertEqual(
            self.client._contracts(
                [{"route": CONTRACT[0], "action": CONTRACT[1]}]
            ),
            frozenset({CONTRACT}),
        )

    def test_signed_public_manifest_does_not_claim_unshipped_route(self) -> None:
        advertised = {
            (row["route"], row["action"])
            for row in self.manifest["artifacts"][0]["contracts"]
        }
        self.assertNotIn(CONTRACT, advertised)


if __name__ == "__main__":
    unittest.main()
