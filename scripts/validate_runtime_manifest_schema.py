#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["jsonschema==4.25.1"]
# ///
"""Validate the committed runtime manifest with its Draft 2020-12 schema."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "plugins/agent-collab/runtime-manifest.json"
DEFAULT_SCHEMA = ROOT / "plugins/agent-collab/runtime-manifest.schema.json"
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_REPORTED_ERRORS = 20
BOOTSTRAP_TIMEOUT_SECONDS = 180
_BOOTSTRAP_MARKER = "AGENT_COLLAB_SCHEMA_VALIDATOR_BOOTSTRAPPED"


class SchemaValidationError(ValueError):
    """The local schema gate cannot produce a positive validation result."""


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SchemaValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_document(path: Path, *, label: str) -> Any:
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise SchemaValidationError(f"{label} is not a regular file")
        if info.st_size > MAX_DOCUMENT_BYTES:
            raise SchemaValidationError(f"{label} exceeds the validation size limit")
        raw = path.read_bytes()
        if len(raw) != info.st_size:
            raise SchemaValidationError(f"{label} changed while being read")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_closed_object)
    except SchemaValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SchemaValidationError(f"{label} is unreadable") from exc


def _load_draft_validator():
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise SchemaValidationError("Draft 2020-12 validator dependency is unavailable") from exc
    return Draft202012Validator


def _error_path(error: Any) -> str:
    parts = [str(part) for part in getattr(error, "absolute_path", ())]
    return "$" if not parts else "$." + ".".join(parts)


def _validate(schema: Any, manifest: Any, validator_type: Any) -> list[str]:
    if not isinstance(schema, dict) or schema.get("$schema") != DRAFT_2020_12:
        raise SchemaValidationError("runtime manifest schema is not Draft 2020-12")
    try:
        validator_type.check_schema(schema)
        errors = sorted(
            validator_type(schema).iter_errors(manifest),
            key=lambda error: (_error_path(error), str(error.message)),
        )
    except SchemaValidationError:
        raise
    except Exception as exc:
        raise SchemaValidationError("runtime manifest schema validation failed") from exc
    return [f"{_error_path(error)}: {error.message}" for error in errors]


def _bootstrap(argv: list[str]) -> int:
    uv = shutil.which("uv")
    if uv is None:
        print(
            "FAIL: Draft 2020-12 validator dependency is unavailable; "
            "install uv or jsonschema==4.25.1",
            file=sys.stderr,
        )
        return 2
    environment = os.environ.copy()
    environment[_BOOTSTRAP_MARKER] = "1"
    try:
        with tempfile.TemporaryDirectory(
            prefix="agent-collab-schema-validator-"
        ) as cache:
            result = subprocess.run(
                [
                    uv,
                    "run",
                    "--cache-dir",
                    cache,
                    "--script",
                    str(Path(__file__).resolve()),
                    *argv,
                ],
                env=environment,
                timeout=BOOTSTRAP_TIMEOUT_SECONDS,
                check=False,
            )
    except (OSError, subprocess.SubprocessError):
        print("FAIL: Draft 2020-12 validator bootstrap failed", file=sys.stderr)
        return 2
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(arguments)
    try:
        validator_type = _load_draft_validator()
    except SchemaValidationError as exc:
        if os.environ.get(_BOOTSTRAP_MARKER) != "1":
            return _bootstrap(arguments)
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    try:
        schema = _load_document(args.schema, label="runtime manifest schema")
        manifest = _load_document(args.manifest, label="runtime manifest")
        errors = _validate(schema, manifest, validator_type)
        if not errors:
            if not isinstance(manifest, dict):
                raise SchemaValidationError("runtime manifest root is not an object")
            negative_control = dict(manifest)
            negative_control["schema_version"] = -1
            if not _validate(schema, negative_control, validator_type):
                raise SchemaValidationError(
                    "Draft 2020-12 validator accepted the negative control"
                )
    except SchemaValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if errors:
        for message in errors[:MAX_REPORTED_ERRORS]:
            print(f"FAIL: {message}", file=sys.stderr)
        if len(errors) > MAX_REPORTED_ERRORS:
            print(
                f"FAIL: {len(errors) - MAX_REPORTED_ERRORS} additional schema errors omitted",
                file=sys.stderr,
            )
        return 1
    print("PASS: runtime manifest matches Draft 2020-12 release schema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
