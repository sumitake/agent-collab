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
_LIFECYCLE_COMMANDS = {
    "install-broker": "install_broker",
    "broker-status": "broker_status",
    "rollback-broker": "rollback_broker",
    "uninstall-broker": "uninstall_broker",
}
_MUTATING_LIFECYCLE_COMMANDS = frozenset(
    {"install-broker", "rollback-broker", "uninstall-broker"}
)


def _emit(payload: dict[str, object]) -> None:
    sys.stdout.write(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {*_COMMANDS, *_LIFECYCLE_COMMANDS}:
        _emit(
            {
                "status": runtime_client.RuntimeStatus.CONFIG_ERROR.value,
                "error": (
                    "expected exactly one of: status, prepare, login-grok, "
                    "install-broker, broker-status, rollback-broker, uninstall-broker"
                ),
            }
        )
        return 2
    if args[0] in _MUTATING_LIFECYCLE_COMMANDS and (
        blocked := runtime_client._broker_lifecycle_seatbelt_block()
    ) is not None:
        result = blocked
    elif args[0] in _LIFECYCLE_COMMANDS:
        result = getattr(runtime_client, _LIFECYCLE_COMMANDS[args[0]])()
    else:
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
