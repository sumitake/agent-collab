"""The public package consumes one provider-neutral execution receipt schema."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

from tests.test_direct_runtime_public_contract import _wire_descriptor


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "plugins" / "agent-collab" / "runtime_client.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ExecutionReceiptContractTests(unittest.TestCase):
    def test_receipt_schema_is_carried_only_by_the_validated_descriptor(self) -> None:
        spec = importlib.util.spec_from_file_location("receipt_client", CLIENT)
        assert spec is not None and spec.loader is not None
        client = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = client
        spec.loader.exec_module(client)
        descriptor, digest = _wire_descriptor()
        snapshot = client.validate_wire_descriptor(descriptor, expected_sha256=digest)
        self.assertIs(snapshot.execution_receipt, descriptor["execution_receipt"])
        self.assertFalse((CLIENT.parent / "execute-output-contract-v1.json").exists())

    def test_validator_enforces_receipt_prefix_binding_and_custom_bounds(self) -> None:
        module = _load("receipt_validator_runtime_client", CLIENT)
        schema = {
            "type": "object",
            "additionalProperties": False,
            "x-maxCanonicalUtf8Bytes": 256,
            "required": ["selection", "paths"],
            "properties": {
                "selection": {
                    "type": "array",
                    "minItems": 2,
                    "prefixItems": [
                        {},
                        {
                            "type": "object",
                            "required": ["logical_action"],
                            "properties": {
                                "logical_action": {"const": "review.repository"}
                            },
                        },
                    ],
                },
                "paths": {
                    "type": "array",
                    "x-maxTotalUtf8Bytes": 8,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "x-maxUtf8ComponentBytes": 4,
                    },
                },
            },
        }
        accepted = {
            "selection": [{}, {"logical_action": "review.repository"}],
            "paths": ["a/b", "c"],
        }
        module._validate_schema(accepted, schema)
        with self.assertRaises(ValueError):
            module._validate_schema(
                {**accepted, "selection": [{}, {"logical_action": "other"}]},
                schema,
            )
        with self.assertRaises(ValueError):
            module._validate_schema({**accepted, "paths": ["abcde"]}, schema)


if __name__ == "__main__":
    unittest.main()
