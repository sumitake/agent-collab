#!/usr/bin/env python3
"""Verify the closed public project-estimation maintenance payload.

This is deliberately stdlib-only.  The release gate validates the small JSON
Schema subset used by the six public contracts, then proves the receipt's
closed inventory and content hashes against the files actually packaged.
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any


PLUGIN = "agent-collab"
PUBLIC_ESTIMATION_MEMBERS: tuple[Path, ...] = tuple(
    Path("project-estimation-data") / name
    for name in (
        "estimate-request.schema.json",
        "estimate-result.schema.json",
        "aggregate-prior.schema.json",
        "pricing-snapshot.schema.json",
        "quota-snapshot.schema.json",
        "maintenance-receipt.schema.json",
        "maintenance-receipt.json",
    )
)
_SCHEMA_MEMBERS = tuple(path for path in PUBLIC_ESTIMATION_MEMBERS if path.name.endswith(".schema.json"))
_MAX_BYTES = 1_048_576


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def _read_bounded(path: Path) -> bytes:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError(f"not a regular file: {path.name}")
    if info.st_size > _MAX_BYTES:
        raise ValueError(f"file exceeds public bound: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"cannot open public file: {path.name}") from exc
    try:
        pinned = os.fstat(descriptor)
        if (
            stat.S_ISLNK(pinned.st_mode)
            or not stat.S_ISREG(pinned.st_mode)
            or pinned.st_dev != info.st_dev
            or pinned.st_ino != info.st_ino
            or pinned.st_size != info.st_size
            or pinned.st_size > _MAX_BYTES
        ):
            raise ValueError(f"public file changed during admission: {path.name}")
        payload = bytearray()
        remaining = pinned.st_size
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                raise ValueError(f"public file truncated during admission: {path.name}")
            payload.extend(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError(f"public file grew during admission: {path.name}")
        return bytes(payload)
    except OSError as exc:
        raise ValueError(f"cannot read public file: {path.name}") from exc
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for offset in range(0, len(payload := _read_bounded(path)), 65536):
        chunk = payload[offset : offset + 65536]
        digest.update(chunk)
    return digest.hexdigest()


def _date(value: object, *, field: str) -> _datetime.date:
    if type(value) is not str:
        raise ValueError(f"{field} must be an ISO date")
    try:
        return _datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def _type_matches(value: object, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "boolean": type(value) is bool,
        "null": value is None,
    }.get(expected, True)


def _validate_schema(value: object, schema: dict[str, Any], *, root_schema: dict[str, Any], field: str = "document") -> None:
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                _validate_schema(value, option, root_schema=root_schema, field=field)
                return
            except ValueError as exc:
                failures.append(str(exc))
        raise ValueError(f"{field} does not match any allowed shape")
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise ValueError(f"{field} has an unsupported schema reference")
        _validate_schema(value, root_schema["$defs"][ref.rsplit("/", 1)[1]], root_schema=root_schema, field=field)
        return
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{field} has an invalid constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{field} has an invalid value")
    if "type" in schema and not _type_matches(value, schema["type"]):
        raise ValueError(f"{field} has an invalid type")
    if "format" in schema and schema["format"] == "date":
        _date(value, field=field)
    if "pattern" in schema and (type(value) is not str or re.fullmatch(schema["pattern"], value) is None):
        raise ValueError(f"{field} has an invalid format")
    if type(value) is int:
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{field} is below its minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{field} exceeds its maximum")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 10**9):
            raise ValueError(f"{field} has an invalid length")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            raise ValueError(f"{field} contains duplicate items")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_schema(item, schema["items"], root_schema=root_schema, field=f"{field}[{index}]")
    if isinstance(value, dict):
        if len(value) < schema.get("minProperties", 0) or len(value) > schema.get("maxProperties", 10**9):
            raise ValueError(f"{field} has an invalid property count")
        required = set(schema.get("required", ()))
        missing = sorted(required - set(value))
        if missing:
            raise ValueError(f"{field} is missing {missing[0]}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ValueError(f"{field} has unknown field {unknown[0]}")
        for name, item in value.items():
            child_schema = properties.get(name, schema.get("additionalProperties"))
            if isinstance(child_schema, dict):
                _validate_schema(item, child_schema, root_schema=root_schema, field=f"{field}.{name}")


def _data_root(root: Path) -> Path:
    return root / "plugins" / PLUGIN / "project-estimation-data"


def verify_maintenance(root: Path, *, expected_version: str, today: _datetime.date | None = None) -> tuple[bool, list[str]]:
    """Return ``(ok, diagnostics)`` for the exact public maintenance set."""
    today = today or _datetime.date.today()
    errors: list[str] = []
    data = _data_root(root)
    try:
        current = root
        for component in ("plugins", PLUGIN, "project-estimation-data"):
            current = current / component
            component_info = current.lstat()
            if stat.S_ISLNK(component_info.st_mode):
                raise ValueError(f"project-estimation path component is a symlink: {component}")
        info = data.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("project-estimation data root is not a directory")
        entries = list(data.iterdir())
        actual = {entry.name for entry in entries}
        expected = {path.name for path in PUBLIC_ESTIMATION_MEMBERS}
        if actual != expected:
            errors.append(f"project-estimation maintenance inventory mismatch: expected {sorted(expected)}, got {sorted(actual)}")
        for entry in entries:
            if entry.name.lower().find("raw") >= 0 or entry.name.lower().find("private") >= 0 or entry.is_symlink():
                errors.append(f"project-estimation maintenance contains forbidden member {entry.name}")
        schemas: dict[str, dict[str, Any]] = {}
        for relative in _SCHEMA_MEMBERS:
            path = data / relative.name
            try:
                raw = _read_bounded(path)
                schema = json.loads(raw)
                if not isinstance(schema, dict) or schema.get("type") != "object" or schema.get("additionalProperties") is not False:
                    raise ValueError("schema must be a closed object")
                schemas[relative.name] = schema
            except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
                errors.append(f"project-estimation maintenance schema {relative.name} invalid: {exc}")
        receipt_path = data / "maintenance-receipt.json"
        receipt_raw = _read_bounded(receipt_path)
        receipt = json.loads(receipt_raw)
        receipt_schema = schemas.get("maintenance-receipt.schema.json")
        if receipt_schema is None:
            raise ValueError("maintenance receipt schema is unavailable")
        _validate_schema(receipt, receipt_schema, root_schema=receipt_schema)
        if receipt.get("version") != expected_version:
            errors.append(f"maintenance receipt version is {receipt.get('version')!r}, expected {expected_version!r}")
        expected_schema_names = sorted(path.name for path in _SCHEMA_MEMBERS)
        inventory = receipt.get("inventory")
        admitted = receipt.get("admitted_sha256")
        if inventory != expected_schema_names or not isinstance(admitted, dict) or set(admitted) != set(expected_schema_names):
            errors.append("maintenance receipt inventory is not the closed public schema set")
        else:
            for name in expected_schema_names:
                digest = _sha256(data / name)
                if admitted.get(name) != digest:
                    errors.append(f"maintenance receipt hash mismatch for {name}")
        receipt_core = dict(receipt)
        declared_receipt_hash = receipt_core.pop("receipt_sha256", None)
        if declared_receipt_hash != hashlib.sha256(_canonical(receipt_core)).hexdigest():
            errors.append("maintenance receipt hash does not match its canonical contents")
        generated = _date(receipt.get("generated_date"), field="generated_date")
        cutoff = _date(receipt.get("source_cutoff_date"), field="source_cutoff_date")
        if cutoff > generated or generated > today:
            errors.append("maintenance receipt dates are outside the release window")
        if (today - generated).days > 60:
            errors.append("calibration evidence is older than the 60-day policy")
        for kind, outcome_key, date_key in (("pricing", "pricing_outcome", "pricing_original_last_good_date"), ("quota", "quota_outcome", "quota_original_last_good_date")):
            observed = receipt.get(date_key)
            if observed is None:
                observed_date = generated
            else:
                observed_date = _date(observed, field=date_key)
            if (today - observed_date).days > 90:
                allowed_expired = receipt.get(outcome_key) == ("unpriced" if kind == "pricing" else "unknown")
                if not allowed_expired:
                    errors.append(f"{kind} evidence is older than the 90-day policy")
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"project-estimation maintenance verification failed: {exc}")
    return not errors, [f"FAIL  {error}" for error in errors] if errors else ["PASS  project-estimation maintenance receipt and closed inventory"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="verify public project-estimation maintenance evidence")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args(argv)
    ok, lines = verify_maintenance(args.root, expected_version=args.expected_version)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
