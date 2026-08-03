"""Direct-runtime public export contract."""

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicExportSafetyTests(unittest.TestCase):
    def test_export_gate_uses_the_shared_manifest_validator(self) -> None:
        path = ROOT / "scripts" / "check-public-export-safety.py"
        spec = importlib.util.spec_from_file_location("direct_export", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.runtime_client.validate_manifest_document))
        self.assertFalse(hasattr(module, "REQUIRED_RUNTIME_CONTRACTS"))


if __name__ == "__main__":
    unittest.main()
