"""Closed host-matrix selection for the co-packaged native runtime."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
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


class RuntimeHostMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = _load("runtime_host_matrix_client", PLUGIN / "runtime_client.py")
        cls.bundle = cls.client.runtime_bundle
        cls.base = json.loads(
            (PLUGIN / "runtime-manifest.json").read_text(encoding="utf-8")
        )

    def _matrix(self) -> dict[str, object]:
        # Synthesize the pending schema-12 candidate for selector-only tests;
        # the signed manifest remains the schema-11 source of truth.
        manifest = deepcopy(self.base)
        descriptor = manifest["wire_contract"]
        descriptor["schema_version"] = 12
        descriptor["logical_action_timeout_modes"] = {
            action: "total_deadline" for action in descriptor["logical_actions"]
        }
        encoded = json.dumps(
            descriptor, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
        manifest["wire_contract_sha256"] = hashlib.sha256(encoded).hexdigest()
        arm64 = manifest["artifacts"][0]
        arm64["provider_runtime_version"] = self.client.PROVIDER_RUNTIME_VERSION
        arm64["wire_contract_sha256"] = manifest["wire_contract_sha256"]
        x86_64 = deepcopy(arm64)
        x86_64["arch"] = "x86_64"
        x86_64["path"] = "runtime/darwin-x86_64/agent-collab-runtime.bundle"
        for record in x86_64["files"]:
            record["architecture"] = "x86_64"
        manifest["artifacts"] = [arm64, x86_64]
        return manifest

    def _parse(self, manifest: dict[str, object]):
        raw = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        return self.client.parse_manifest_bytes(raw, require_artifact=True)

    def test_each_supported_host_selects_one_row_with_the_same_wire_contract(self) -> None:
        artifacts, wire, _document = self._parse(self._matrix())

        cases = (
            ("Darwin", "arm64", "arm64"),
            ("darwin", "aarch64", "arm64"),
            ("DARWIN", "x86_64", "x86_64"),
        )
        for system, machine, expected in cases:
            with self.subTest(system=system, machine=machine):
                selected, status, error = self.client._select_artifact(
                    artifacts, system=system, machine=machine
                )
                self.assertEqual(status, self.client.RuntimeStatus.OK)
                self.assertEqual(error, "")
                self.assertEqual(selected["arch"], expected)
                self.assertEqual(selected["wire_contract_sha256"], wire.sha256)

    def test_absent_or_unsupported_host_rows_fail_closed(self) -> None:
        matrix = self._matrix()
        artifacts, _wire, _document = self._parse(matrix)
        cases = (
            (artifacts, "Linux", "x86_64", self.client.RuntimeStatus.PLATFORM_UNSUPPORTED),
            ((artifacts[0],), "Darwin", "x86_64", self.client.RuntimeStatus.PLATFORM_UNSUPPORTED),
            ((), "Darwin", "arm64", self.client.RuntimeStatus.UNAVAILABLE),
        )
        for rows, system, machine, expected in cases:
            with self.subTest(system=system, machine=machine, rows=len(rows)):
                selected, status, error = self.client._select_artifact(
                    rows, system=system, machine=machine
                )
                self.assertIsNone(selected)
                self.assertEqual(status, expected)
                self.assertTrue(error)

    def test_duplicate_host_row_is_rejected_before_selection(self) -> None:
        manifest = self._matrix()
        manifest["artifacts"] = [
            manifest["artifacts"][0],
            deepcopy(manifest["artifacts"][0]),
        ]
        with self.assertRaisesRegex(ValueError, "host row"):
            self._parse(manifest)

    def test_malformed_arch_alias_and_unsafe_path_are_rejected(self) -> None:
        mutations = (
            ("alias", lambda item: item.__setitem__("arch", "amd64")),
            ("non-string alias", lambda item: item.__setitem__("arch", [])),
            ("path", lambda item: item.__setitem__("path", "runtime/../unsafe")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                manifest = self._matrix()
                mutate(manifest["artifacts"][1])
                with self.assertRaisesRegex(ValueError, "artifact identity"):
                    self._parse(manifest)

    def test_mixed_artifact_wire_contracts_are_rejected(self) -> None:
        manifest = self._matrix()
        manifest["artifacts"][1]["wire_contract_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "wire contract"):
            self._parse(manifest)

    def test_wrong_arch_macho_is_rejected_against_the_selected_row(self) -> None:
        manifest = self._matrix()
        record = manifest["artifacts"][1]["files"][0]
        signing = manifest["artifacts"][1]["signing"]
        results = (
            SimpleNamespace(returncode=0, stdout="arm64\n", stderr=""),
            SimpleNamespace(
                returncode=0,
                stdout=(
                    "Load command 1\n"
                    "      cmd LC_BUILD_VERSION\n"
                    " platform macos\n"
                    "    minos 14.0\n"
                ),
                stderr="",
            ),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(
                returncode=0,
                stdout="",
                stderr=(
                    f"Authority={signing['identity']}\n"
                    f"TeamIdentifier={signing['team_id']}\n"
                    "flags=0x10000(runtime)\n"
                    "Timestamp=Aug 15, 2026 at 12:00:00\n"
                ),
            ),
        )
        with mock.patch.object(self.client.subprocess, "run", side_effect=results):
            with self.assertRaisesRegex(
                self.bundle.BundleContractError, "Mach-O identity"
            ):
                self.client._inspect_member(Path("/unused"), record, signing)

    def test_runtime_resolution_exposes_no_caller_host_override(self) -> None:
        with self.assertRaises(TypeError):
            self.client.resolve_runtime(system="darwin", machine="x86_64")


class RuntimeBundleArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = _load("runtime_host_matrix_bundle", PLUGIN / "runtime_bundle.py")
        manifest = json.loads(
            (PLUGIN / "runtime-manifest.json").read_text(encoding="utf-8")
        )
        cls.arm64_records = manifest["artifacts"][0]["files"]

    def test_existing_arm64_identity_remains_unchanged(self) -> None:
        manifest = json.loads(
            (PLUGIN / "runtime-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            self.bundle.compute_bundle_identity(self.arm64_records),
            manifest["artifacts"][0]["sha256"],
        )

    def test_x86_64_records_form_a_distinct_closed_identity(self) -> None:
        records = deepcopy(self.arm64_records)
        for record in records:
            record["architecture"] = "x86_64"
        validated = self.bundle.validate_file_records(records)
        self.assertEqual({row["architecture"] for row in validated}, {"x86_64"})
        self.assertNotEqual(
            self.bundle.compute_bundle_identity(records),
            self.bundle.compute_bundle_identity(self.arm64_records),
        )

    def test_mixed_architecture_members_fail_closed(self) -> None:
        records = deepcopy(self.arm64_records)
        records[-1]["architecture"] = "x86_64"
        with self.assertRaisesRegex(
            self.bundle.BundleContractError, "architectures are inconsistent"
        ):
            self.bundle.validate_file_records(records)


if __name__ == "__main__":
    unittest.main()
