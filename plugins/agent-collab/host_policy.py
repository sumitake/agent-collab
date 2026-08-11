#!/usr/bin/env python3
"""Provider-neutral host identity observations for the semantic coordinator.

Routing, authority, source modes, and agent eligibility live exclusively in
the validated workspace-generated wire descriptor consumed by the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Mapping


_FAMILIES = frozenset({"anthropic", "google", "moonshot", "openai", "xai", "zhipu", "unknown"})
_PRIMARY_FAMILIES = {
    "claude": "anthropic",
    "codex": "openai",
    "antigravity": "google",
    "zcode": "unknown",
}
_PRIMARY_RUNTIMES = {
    "claude": "claude-code",
    "codex": "codex",
    "antigravity": "antigravity",
    "zcode": "opencode",
}
_SESSION_RE = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")


@dataclass(frozen=True)
class HostProfile:
    primary_id: str
    primary_family: str
    active_model: str
    host_runtime: str
    session_identifier: str
    explicit: bool
    governance_ready: bool = False
    identity_conflict: bool = False


def _clean(value: object, *, limit: int = 4096) -> str:
    if type(value) is not str:
        return ""
    candidate = value.strip()
    if not candidate or len(candidate.encode("utf-8")) > limit or "\x00" in candidate:
        return ""
    return candidate


def _observed_session(*names: str) -> tuple[str, bool]:
    """Return the first host session observation and whether aliases conflict."""

    values = [
        value
        for name in names
        if (value := _clean(os.environ.get(name), limit=256))
    ]
    if not values:
        return "", False
    return values[0], len(set(values)) > 1


def _explicit_profile(config: Mapping[str, str]) -> HostProfile:
    allowed = {
        "primary_id",
        "primary_family",
        "active_model",
        "host_runtime",
        "session_identifier",
    }
    if set(config) != allowed:
        raise ValueError("explicit host profile is not closed")
    primary_id = _clean(config.get("primary_id"), limit=64)
    family = _clean(config.get("primary_family"), limit=64).lower()
    runtime = _clean(config.get("host_runtime"), limit=128)
    model = _clean(config.get("active_model"))
    session = _clean(config.get("session_identifier"), limit=256)
    if (
        not primary_id
        or family not in _FAMILIES
        or not runtime
        or not session
        or _SESSION_RE.fullmatch(session) is None
    ):
        raise ValueError("explicit host profile is invalid")
    return HostProfile(
        primary_id,
        family,
        model,
        runtime,
        session,
        True,
        governance_ready=family != "unknown",
    )


def resolve_profile(explicit_config: Mapping[str, str] | None = None) -> HostProfile:
    """Observe only host identity; never infer a provider route or model pin."""

    if explicit_config is not None:
        if not isinstance(explicit_config, Mapping):
            raise ValueError("explicit host profile is invalid")
        return _explicit_profile(explicit_config)

    candidates: list[tuple[str, str, str, bool]] = []
    host_observations = (
        (
            "codex",
            ("CODEX_THREAD_ID", "CODEX_SESSION_ID"),
            ("CODEX_ACTIVE_MODEL", "CODEX_MODEL"),
        ),
        (
            "claude",
            ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID"),
            ("CLAUDE_CODE_MODEL", "CLAUDE_MODEL"),
        ),
        (
            "antigravity",
            ("ANTIGRAVITY_SESSION_ID",),
            ("ANTIGRAVITY_ACTIVE_MODEL", "ANTIGRAVITY_MODEL"),
        ),
        (
            "zcode",
            ("ZCODE_SESSION_ID", "OPENCODE_SESSION_ID"),
            ("OPENCODE_ACTIVE_MODEL", "OPENCODE_MODEL"),
        ),
    )
    for primary_id, session_names, model_names in host_observations:
        session, conflict = _observed_session(*session_names)
        if session:
            model = next(
                (
                    value
                    for name in model_names
                    if (value := _clean(os.environ.get(name)))
                ),
                "",
            )
            candidates.append((primary_id, session, model, conflict))
    if len(candidates) != 1:
        return HostProfile(
            "unknown",
            "unknown",
            "",
            "unknown",
            "unknown",
            False,
            identity_conflict=len(candidates) > 1,
        )
    primary_id, session, model, identity_conflict = candidates[0]
    model = _clean(model)
    family = _PRIMARY_FAMILIES[primary_id]
    return HostProfile(
        primary_id,
        family,
        model,
        _PRIMARY_RUNTIMES[primary_id],
        session,
        False,
        governance_ready=family != "unknown" and not identity_conflict,
        identity_conflict=identity_conflict,
    )


if __name__ == "__main__":
    raise SystemExit("host_policy.py is a library")
