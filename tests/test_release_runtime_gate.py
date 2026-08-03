"""Direct runtime release-gate contract."""

import importlib.util
from pathlib import Path
import sys
import unittest


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


if __name__ == "__main__":
    unittest.main()
