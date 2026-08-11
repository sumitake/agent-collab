"""Closed direct standalone-bundle primitives."""

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RuntimeBundleTests(unittest.TestCase):
    def test_bundle_contract_has_one_source_mode_and_no_broker_store(self) -> None:
        path = ROOT / "plugins" / "agent-collab" / "runtime_bundle.py"
        spec = importlib.util.spec_from_file_location("direct_bundle", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertTrue(module.source_mode_ok(0o755))
        self.assertFalse(module.source_mode_ok(0o4755))
        self.assertFalse(hasattr(module, "_broker_root_mode_ok"))


if __name__ == "__main__":
    unittest.main()
