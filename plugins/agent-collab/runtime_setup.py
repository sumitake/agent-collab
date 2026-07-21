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
    "stage-dispatcher": "stage_dispatcher",
    "dispatcher-status": "dispatcher_status",
    "commit-selector": "commit_dispatcher_selector",
    "abort-candidate": "abort_dispatcher_candidate",
    "recover-last-committed-control-plane": "recover_last_committed_control_plane",
    "drain-retiring": "drain_retiring_dispatcher",
}
_MUTATING_LIFECYCLE_COMMANDS = frozenset(
    {
        "install-broker",
        "rollback-broker",
        "uninstall-broker",
        "stage-dispatcher",
        "commit-selector",
        "abort-candidate",
        "recover-last-committed-control-plane",
        "drain-retiring",
    }
)


def _emit(payload: dict[str, object]) -> None:
    sys.stdout.write(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    probe: tuple[str, dict[str, object]] | None = None
    if args == ["dispatcher-ping"]:
        probe = ("invoke_dispatcher_ping", {"timeout_ms": 30_000})
    elif len(args) == 5 and args[0] == "dispatcher-lock-probe":
        if args[1] == "--provider" and args[3] == "--timeout-ms":
            try:
                timeout_ms = int(args[4])
            except ValueError:
                timeout_ms = -1
            if args[2] in {"gemini", "grok", "opencode"} and 1 <= timeout_ms <= 600_000:
                probe = (
                    "invoke_dispatcher_lock_probe",
                    {"provider": args[2], "timeout_ms": timeout_ms},
                )
    ordinary = len(args) == 1 and args[0] in {*_COMMANDS, *_LIFECYCLE_COMMANDS}
    if not ordinary and probe is None:
        _emit(
            {
                "status": runtime_client.RuntimeStatus.CONFIG_ERROR.value,
                "error": (
                    "expected exactly one of: status, prepare, login-grok, "
                    "install-broker, broker-status, rollback-broker, uninstall-broker, "
                    "stage-dispatcher, dispatcher-status, commit-selector, "
                    "abort-candidate, recover-last-committed-control-plane, "
                    "drain-retiring, dispatcher-ping, or a closed dispatcher-lock-probe"
                ),
            }
        )
        return 2
    if probe is not None:
        function_name, kwargs = probe
        result = getattr(runtime_client, function_name)(**kwargs)
    elif args[0] in _MUTATING_LIFECYCLE_COMMANDS and (
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
