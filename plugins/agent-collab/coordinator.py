#!/usr/bin/env python3
"""Bounded routing-only CLI for the co-packaged native runtime.

The caller supplies the complete routing request. This shim adds no semantic
schema, provider command, retry, fallback, receipt, verdict, or output parser;
it only preserves the library result as one JSON response on stdout.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parent
MAX_INPUT_BYTES = 48 * 1024 * 1024


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate request key")
        value[key] = item
    return value


def _reject_nonfinite(_value: str) -> None:
    raise ValueError("request contains a non-finite number")


def _load_client() -> ModuleType:
    path = PLUGIN_ROOT / "runtime_client.py"
    spec = importlib.util.spec_from_file_location("agent_collab_runtime_client", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("runtime client is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_request() -> object:
    if sys.stdin.isatty():
        raise ValueError("tty input is unsupported")
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if not raw:
        raise ValueError("request is empty")
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("request exceeds input bound")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("request is not one JSON value") from exc


def _response(result: object) -> dict[str, object]:
    if not is_dataclass(result):
        raise RuntimeError("runtime client returned an invalid result")
    value = asdict(result)
    status = value.get("status")
    value["status"] = getattr(status, "value", status)
    return value


def _write(value: object) -> None:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def main() -> int:
    try:
        request = _read_request()
        if type(request) is not dict:
            raise ValueError("request root must be an object")
        _write(_response(_load_client().invoke(envelope=request)))
        return 0
    except ValueError as exc:
        _write({"status": "invalid_request", "result": [], "error": str(exc)})
        return 2
    except Exception:
        _write({
            "status": "unavailable",
            "result": [],
            "error": "routing client failed before a result was available",
        })
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
