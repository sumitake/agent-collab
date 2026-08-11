"""Direct runtime release-gate contract."""

import importlib.util
import json
from pathlib import Path
import sys
import unittest

from tests.test_direct_runtime_public_contract import _wire_descriptor


ROOT = Path(__file__).resolve().parents[1]


class ReleaseRuntimeGateTests(unittest.TestCase):
    def test_release_gate_uses_shared_schema4_validator_and_notarization_gate(self) -> None:
        path = ROOT / "scripts" / "verify_runtime_release.py"
        spec = importlib.util.spec_from_file_location("direct_release_gate", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.runtime_client.validate_manifest_document))
        self.assertFalse(hasattr(module, "REQUIRED_CONTRACTS"))
        self.assertIn("--check-notarization", path.read_text(encoding="utf-8"))

    def test_release_manifest_loader_rejects_duplicate_keys(self) -> None:
        import tempfile

        path = ROOT / "scripts" / "verify_runtime_release.py"
        spec = importlib.util.spec_from_file_location("strict_release_gate", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
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
        encoded = json.dumps(manifest, separators=(",", ":"))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / module.MANIFEST_REL
            target.parent.mkdir(parents=True)
            target.write_text('{"schema_version":4,' + encoded[1:], encoding="utf-8")
            data, _path, errors = module._manifest(root)
        self.assertIsNone(data)
        self.assertEqual(errors, ["runtime manifest is unreadable"])


if __name__ == "__main__":
    unittest.main()
