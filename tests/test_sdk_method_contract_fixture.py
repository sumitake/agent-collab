"""Keep the independent-review example grounded in executable SDK behavior."""

import importlib.util
import json
from pathlib import Path
import unittest
from uuid import UUID


FIXTURE = Path(__file__).parent / "fixtures" / "sdk-method-contracts"


def load_fixture(name):
    spec = importlib.util.spec_from_file_location(
        "sdk_method_contract_fixture_" + name, FIXTURE / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SdkMethodContractFixtureTests(unittest.TestCase):
    def setUp(self):
        self.client = load_fixture("sdk").Secrets()

    def test_string_read_caller_serializes_actual_read_arguments(self):
        first, second = load_fixture("case_a").read_secrets(self.client)
        self.assertEqual(
            json.loads(first),
            {"operation": "get", "arguments": {
                "id": "54fbb187-3626-4832-b581-2f6fc85cc518"
            }},
        )
        self.assertEqual(
            json.loads(second),
            {"operation": "list", "arguments": {
                "organizationId": "2b96f0ed-8c6c-45bd-832c-b88fcc4eae07"
            }},
        )

    def test_uuid_read_caller_fails_in_the_real_json_serializer(self):
        with self.assertRaises(TypeError):
            load_fixture("case_b").read_secrets(self.client)
        with self.assertRaises(TypeError):
            self.client.list(UUID("2b96f0ed-8c6c-45bd-832c-b88fcc4eae07"))

    def test_create_converts_uuid_in_its_own_method(self):
        self.assertEqual(
            json.loads(self.client.create(
                UUID("54fbb187-3626-4832-b581-2f6fc85cc518")
            )),
            {"operation": "create", "arguments": {
                "id": "54fbb18736264832b5812f6fc85cc518"
            }},
        )
        with self.assertRaises(AttributeError):
            self.client.create("54fbb187-3626-4832-b581-2f6fc85cc518")


if __name__ == "__main__":
    unittest.main()
