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

    def test_signed_public_manifest_now_ships_the_route_and_keeps_it_optional(
        self,
    ) -> None:
        """The route is shipped as of v4.4.1, and stays OPTIONAL, not required.

        Until v4.4.1 the client and schema accepted ``codex/governance`` while
        the signed runtime deliberately did not advertise it, and this test
        pinned that gap. The v4.4.1 runtime is built from a workspace source
        closure where the route is a real read-only contract, so it now
        advertises it. The invariant that still matters is the partition: the
        route must remain accepted-but-not-required, so a runtime that omits
        it continues to verify rather than being forced to claim it.
        """
        advertised = {
            (row["route"], row["action"])
            for row in self.manifest["artifacts"][0]["contracts"]
        }
        self.assertIn(CONTRACT, advertised)
        self.assertNotIn(CONTRACT, self.client.REQUIRED_CONTRACTS)
        self.assertTrue(self.client.REQUIRED_CONTRACTS <= advertised)

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


class ReleaseVerifierContractBoundsTests(unittest.TestCase):
    """The release verifiers accept the enumerated optional route only.

    All THREE copies are covered (verify_runtime_release, build_plugin_archive,
    check-public-export-safety) — the third was missed on the first pass and
    only CI's --active-tree run caught it.

    v4.4.1 replaced their exact-equality contract check with a bounded
    containment check (REQUIRED <= advertised <= REQUIRED | OPTIONAL). These
    tests pin that it is BOUNDED: an unenumerated extra route is still
    rejected, and the required baseline is still mandatory. Without this, the
    change would read as an open superset that tolerates any future route.
    """

    def _modules(self):
        root = Path(__file__).resolve().parent.parent
        loaded = []
        for name in (
            "verify_runtime_release",
            "build_plugin_archive",
            "check-public-export-safety",
        ):
            alias = "_bounds_" + name.replace("-", "_")
            spec = importlib.util.spec_from_file_location(
                alias, root / "scripts" / f"{name}.py"
            )
            module = importlib.util.module_from_spec(spec)
            # register before exec: @dataclass resolves sys.modules[__module__]
            sys.modules[alias] = module
            spec.loader.exec_module(module)
            loaded.append((name, module))
        return loaded

    @staticmethod
    def _sets(module):
        """The export-safety copy uses _RUNTIME_-suffixed names."""
        if hasattr(module, "REQUIRED_CONTRACTS"):
            return (
                module.REQUIRED_CONTRACTS,
                module.OPTIONAL_CONTRACTS,
                module.ACCEPTED_CONTRACTS,
            )
        return (
            module.REQUIRED_RUNTIME_CONTRACTS,
            module.OPTIONAL_RUNTIME_CONTRACTS,
            module.ACCEPTED_RUNTIME_CONTRACTS,
        )

    def test_optional_set_is_exactly_the_codex_governance_route(self) -> None:
        for name, module in self._modules():
            with self.subTest(module=name):
                required, optional, accepted = self._sets(module)
                self.assertEqual(optional, frozenset({("codex", "governance")}))
                self.assertEqual(accepted, required | optional)
                # optional must not overlap the mandatory baseline
                self.assertFalse(required & optional)

    def test_unenumerated_extra_route_is_not_accepted(self) -> None:
        rogue = ("attacker", "exfiltrate")
        for name, module in self._modules():
            with self.subTest(module=name):
                required, _, accepted = self._sets(module)
                self.assertFalse((required | {rogue}) <= accepted)

    def test_missing_required_route_is_not_accepted(self) -> None:
        for name, module in self._modules():
            with self.subTest(module=name):
                required, _, _ = self._sets(module)
                short = set(required)
                short.pop()
                self.assertFalse(required <= short)


if __name__ == "__main__":
    unittest.main()
