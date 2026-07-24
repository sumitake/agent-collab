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

    def test_optional_route_is_accepted_but_not_required_for_readiness(
        self,
    ) -> None:
        """An accepted-but-unadvertised route must not block the runtime.

        Readiness is judged against REQUIRED_CONTRACTS. Judging it against
        SUPPORTED_CONTRACTS instead makes ``migration_doctor._runtime_state()``
        report ``invalid: missing contracts codex/governance`` for the runtime
        this release actually ships, which drives ``provider_routing`` to
        BLOCKED even though only this one route is unavailable.
        """
        self.assertIn(CONTRACT, self.client.SUPPORTED_CONTRACTS)
        self.assertIn(CONTRACT, self.client.OPTIONAL_CONTRACTS)
        self.assertNotIn(CONTRACT, self.client.REQUIRED_CONTRACTS)

        # required and optional partition the acceptance set, so a route added
        # to SUPPORTED_CONTRACTS is required until deliberately marked optional.
        self.assertEqual(
            self.client.REQUIRED_CONTRACTS | self.client.OPTIONAL_CONTRACTS,
            self.client.SUPPORTED_CONTRACTS,
        )
        self.assertFalse(
            self.client.REQUIRED_CONTRACTS & self.client.OPTIONAL_CONTRACTS
        )

        # The shipped signed manifest satisfies the required baseline in full.
        advertised = {
            (row["route"], row["action"])
            for row in self.manifest["artifacts"][0]["contracts"]
        }
        self.assertEqual(
            set(self.client.REQUIRED_CONTRACTS).difference(advertised), set()
        )

    def test_doctor_readiness_uses_the_required_baseline(self) -> None:
        """Guard the call site itself, not just the constants."""
        source = (PLUGIN / "migration_doctor.py").read_text(encoding="utf-8")
        self.assertIn(
            "set(client.REQUIRED_CONTRACTS).difference(resolution.contracts)",
            source,
        )
        self.assertNotIn(
            "set(client.SUPPORTED_CONTRACTS).difference(resolution.contracts)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
