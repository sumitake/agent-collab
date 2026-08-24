#!/usr/bin/env python3
"""Tests for the repository-owned runtime-manifest schema gate."""

from __future__ import annotations

import builtins
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_runtime_manifest_schema.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_runtime_manifest_schema_tested", SCRIPT
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _PassingValidator:
    @staticmethod
    def check_schema(_schema):
        return None

    def __init__(self, _schema):
        pass

    def iter_errors(self, manifest):
        if manifest.get("schema_version") != -1:
            return ()

        class Error:
            absolute_path = ("schema_version",)
            message = "4 was expected"

        return (Error(),)


class RuntimeManifestSchemaValidationTests(unittest.TestCase):
    def test_incompatible_installed_jsonschema_bootstraps(self) -> None:
        module = _load_module()
        original_import = builtins.__import__

        def incompatible_jsonschema(name, *args, **kwargs):
            if name == "jsonschema":
                raise ImportError("cannot import name 'Draft202012Validator'")
            return original_import(name, *args, **kwargs)

        with (
            mock.patch("builtins.__import__", side_effect=incompatible_jsonschema),
            mock.patch.object(module, "_bootstrap", return_value=17) as bootstrap,
        ):
            self.assertEqual(module.main([]), 17)
        bootstrap.assert_called_once_with([])

    def test_duplicate_keys_fail_before_schema_validation(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "duplicate.json"
            path.write_text('{"schema_version":4,"schema_version":4}\n')
            with self.assertRaisesRegex(module.SchemaValidationError, "duplicate JSON key"):
                module._load_document(path, label="runtime manifest")

    def test_wrong_draft_is_rejected(self) -> None:
        module = _load_module()
        with self.assertRaisesRegex(
            module.SchemaValidationError, "not Draft 2020-12"
        ):
            module._validate(
                {"$schema": "http://json-schema.org/draft-07/schema#"},
                {},
                _PassingValidator,
            )

    def test_main_validates_the_repository_documents(self) -> None:
        module = _load_module()
        with mock.patch.object(
            module, "_load_draft_validator", return_value=_PassingValidator
        ):
            self.assertEqual(module.main([]), 0)

    def test_invalid_manifest_returns_failure(self) -> None:
        module = _load_module()
        schema = ROOT / "plugins/agent-collab/runtime-manifest.schema.json"
        with tempfile.TemporaryDirectory() as raw:
            manifest = Path(raw) / "invalid.json"
            manifest.write_text(json.dumps({"schema_version": 4}) + "\n")

            class Error:
                absolute_path = ("artifacts",)
                message = "'artifacts' is a required property"

            class FailingValidator(_PassingValidator):
                def iter_errors(self, _manifest):
                    return (Error(),)

            with mock.patch.object(
                module, "_load_draft_validator", return_value=FailingValidator
            ):
                self.assertEqual(
                    module.main(["--schema", str(schema), "--manifest", str(manifest)]),
                    1,
                )


if __name__ == "__main__":
    unittest.main()
