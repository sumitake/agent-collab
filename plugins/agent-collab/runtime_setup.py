#!/usr/bin/env python3
"""Closed operator entrypoint for the signed agent-collab runtime."""

from __future__ import annotations

import json
import sys
import uuid

import runtime_client


_COMMANDS = {
    "status": ("status", 60_000),
    "prepare": ("prepare", 60_000),
    "login-grok": ("grok_login", 600_000),
}


def _emit(payload: dict[str, object]) -> None:
    sys.stdout.write(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in _COMMANDS:
        _emit(
            {
                "status": runtime_client.RuntimeStatus.CONFIG_ERROR.value,
                "error": "expected exactly one of: status, prepare, login-grok",
            }
        )
        return 2
    action, timeout_ms = _COMMANDS[args[0]]
    result = runtime_client.manage_runtime(
        action=action,
        request_id=f"setup-{uuid.uuid4().hex}",
        timeout_ms=timeout_ms,
    )
    payload: dict[str, object] = {"status": result.status.value}
    if result.result is not None:
        payload["result"] = dict(result.result)
    if result.error:
        payload["error"] = result.error
    _emit(payload)
    return 0 if result.status is runtime_client.RuntimeStatus.OK else 1


if __name__ == "__main__":
    raise SystemExit(main())
