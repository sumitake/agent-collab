"""The public package consumes one provider-neutral execution receipt schema."""

from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import unittest

from tests.test_direct_runtime_public_contract import (
    _readiness_response,
    _wire_descriptor,
)


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

    def test_descriptor_rejects_unsupported_schema_keywords(self) -> None:
        module = _load("closed_keyword_runtime_client", CLIENT)
        descriptor, _digest = _wire_descriptor()
        descriptor["success_response"]["minProperties"] = 1
        raw = json.dumps(
            descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            module.validate_wire_descriptor(
                descriptor, expected_sha256=hashlib.sha256(raw).hexdigest()
            )

    def test_descriptor_rejects_non_schema_items_value(self) -> None:
        module = _load("closed_items_runtime_client", CLIENT)
        descriptor, _digest = _wire_descriptor()
        descriptor["success_response"] = {"type": "array", "items": False}
        raw = json.dumps(
            descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        with self.assertRaisesRegex(ValueError, "schema"):
            module.validate_wire_descriptor(
                descriptor, expected_sha256=hashlib.sha256(raw).hexdigest()
            )

    def test_descriptor_rejects_known_keywords_with_ignored_shapes(self) -> None:
        module = _load("closed_keyword_shapes_runtime_client", CLIENT)
        mutations = (
            lambda schema: schema.__setitem__("additionalProperties", {}),
            lambda schema: schema.__setitem__("required", "status"),
            lambda schema: schema.__setitem__("type", ["object", 7]),
            lambda schema: schema.__setitem__("minimum", "0"),
            lambda schema: schema.__setitem__("uniqueItems", False),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                descriptor, _digest = _wire_descriptor()
                mutate(descriptor["success_response"])
                raw = json.dumps(
                    descriptor,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
                with self.assertRaisesRegex(ValueError, "schema"):
                    module.validate_wire_descriptor(
                        descriptor,
                        expected_sha256=hashlib.sha256(raw).hexdigest(),
                    )

    def test_zero_inference_readiness_consumer_validates_complete_response(self) -> None:
        module = _load("readiness_consumer_runtime_client", CLIENT)
        descriptor, digest = _wire_descriptor()
        wire = module.validate_wire_descriptor(descriptor, expected_sha256=digest)
        value = _readiness_response(wire.sha256)
        self.assertEqual(
            module.validate_readiness_response(
                value,
                wire,
                request_id="runtime-status-1",
                author_lineage="openai",
            ),
            value,
        )
        replay = _readiness_response(wire.sha256, author_lineage="google")
        with self.assertRaises(ValueError):
            module.validate_readiness_response(
                replay,
                wire,
                request_id="runtime-status-1",
                author_lineage="openai",
            )
        value["result"]["actions"][0]["candidates"][0][
            "implementation_fingerprint"
        ] = "a" * 64
        with self.assertRaises(ValueError):
            module.validate_readiness_response(
                value,
                wire,
                request_id="runtime-status-1",
                author_lineage="openai",
            )


if __name__ == "__main__":
    unittest.main()
