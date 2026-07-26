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

    def test_activation_manifest_ships_route_and_policy_only_has_no_runtime(
        self,
    ) -> None:
        """Activation ships the route; policy-only source carries no runtime.

        Until v4.4.1 the client and schema accepted ``codex/governance`` while
        the signed runtime deliberately did not advertise it, and this test
        pinned that gap. An activation bundle built from the current workspace
        source closure must advertise the real read-only contract. Between
        activation cuts, the public source may instead be canonical
        policy-only state: an empty manifest and no runtime directory. In both
        states the public client keeps the route accepted-but-not-required so
        older installed artifacts remain valid.
        """
        self.assertNotIn(CONTRACT, self.client.REQUIRED_CONTRACTS)
        artifacts = self.manifest["artifacts"]
        if artifacts:
            advertised = {
                (row["route"], row["action"])
                for row in artifacts[0]["contracts"]
            }
            self.assertIn(CONTRACT, advertised)
            self.assertTrue(self.client.REQUIRED_CONTRACTS <= advertised)
        else:
            self.assertFalse((PLUGIN / "runtime").exists())

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

        # Any committed activation manifest satisfies the required baseline in
        # full. A policy-only source manifest has no runtime to judge ready.
        artifacts = self.manifest["artifacts"]
        if artifacts:
            advertised = {
                (row["route"], row["action"])
                for row in artifacts[0]["contracts"]
            }
            self.assertEqual(
                set(self.client.REQUIRED_CONTRACTS).difference(advertised),
                set(),
            )
        else:
            self.assertFalse((PLUGIN / "runtime").exists())

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


class ReleaseGateRequiresCodexGovernanceTests(unittest.TestCase):
    """v4.4.1 requires codex/governance at the RELEASE gates, not optionally.

    Release gates validate what this repository is about to publish, so the
    route is REQUIRED there: a later cut that silently omits it must fail
    rather than quietly regress a governance capability (Tier 3 review
    condition). The public client keeps it OPTIONAL because it validates
    whatever is already installed, including older field artifacts. These
    tests exercise a real call site, not just the constants, so a future
    partial edit to any of the three copies fails here.
    """

    GATES = (
        "verify_runtime_release",
        "build_plugin_archive",
        "check-public-export-safety",
    )

    @staticmethod
    def _load(name):
        alias = "_gate_" + name.replace("-", "_")
        spec = importlib.util.spec_from_file_location(
            alias, ROOT / "scripts" / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        # register before exec: @dataclass resolves sys.modules[__module__]
        sys.modules[alias] = module
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _required(module):
        return getattr(
            module, "REQUIRED_CONTRACTS", None
        ) or module.REQUIRED_RUNTIME_CONTRACTS

    def test_all_three_gate_copies_require_the_route(self) -> None:
        for name in self.GATES:
            with self.subTest(gate=name):
                required = self._required(self._load(name))
                self.assertIn(CONTRACT, required)
                self.assertEqual(len(required), 11)

    def test_gate_copies_agree_exactly(self) -> None:
        """Three hand-maintained copies must not drift apart."""
        sets = {name: self._required(self._load(name)) for name in self.GATES}
        reference = sets[self.GATES[0]]
        for name, value in sets.items():
            with self.subTest(gate=name):
                self.assertEqual(set(value), set(reference))

    def test_client_keeps_the_route_optional(self) -> None:
        """The client posture is deliberately the opposite of the gates'."""
        client = _load_runtime_client()
        self.assertIn(CONTRACT, client.SUPPORTED_CONTRACTS)
        self.assertIn(CONTRACT, client.OPTIONAL_CONTRACTS)
        self.assertNotIn(CONTRACT, client.REQUIRED_CONTRACTS)


if __name__ == "__main__":
    unittest.main()
