"""Direct-runtime archive source contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from tests.test_direct_runtime_public_contract import _wire_descriptor


ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "build_plugin_archive.py"
    spec = importlib.util.spec_from_file_location("direct_archive", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PluginArchiveTests(unittest.TestCase):
    def test_development_plugin_members_are_rejected_before_packaging(self) -> None:
        archive = _load()
        with tempfile.TemporaryDirectory() as raw:
            plugin = Path(raw)
            for name in (
                "_dev_route_evidence.py",
                "development-provenance.json",
            ):
                member = plugin / name
                member.write_text("private", encoding="utf-8")
                with self.subTest(name=name), self.assertRaisesRegex(
                    ValueError, "development-only"
                ):
                    archive._require_no_development_members(plugin)
                member.unlink()

    def test_policy_manifest_uses_the_single_top_level_descriptor(self) -> None:
        archive = _load()
        descriptor, digest = _wire_descriptor()
        manifest = {
            "schema_version": 4,
            "protocol_version": 4,
            "contract_version": 4,
            "wire_contract": descriptor,
            "wire_contract_sha256": digest,
            "channel": "production",
            "artifacts": [],
        }
        self.assertEqual(archive._parse_manifest(json.dumps(manifest).encode()), manifest)
        self.assertNotIn("runtime_setup.py", archive.REQUIRED_ROOTS)
        self.assertNotIn("execute-output-contract-v1.json", archive.REQUIRED_ROOTS)

    def test_manifest_parser_rejects_duplicate_keys_and_runtime_oversize(self) -> None:
        archive = _load()
        descriptor, digest = _wire_descriptor()
        manifest = {
            "schema_version": 4,
            "protocol_version": 4,
            "contract_version": 4,
            "wire_contract": descriptor,
            "wire_contract_sha256": digest,
            "channel": "production",
            "artifacts": [],
        }
        encoded = json.dumps(manifest, separators=(",", ":")).encode()
        duplicate = b'{"schema_version":4,' + encoded[1:]
        with self.assertRaises(ValueError):
            archive._parse_manifest(duplicate)
        oversized = b" " * (archive.runtime_bundle.MAX_MANIFEST_BYTES + 1) + encoded
        with self.assertRaises(ValueError):
            archive._parse_manifest(oversized)


if __name__ == "__main__":
    unittest.main()
