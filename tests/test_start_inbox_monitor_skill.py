#!/usr/bin/env python3
"""Contract tests for the generated start-inbox-monitor skill."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "skill-specs" / "start-inbox-monitor.md"
GENERATED = (
    ROOT
    / "plugins"
    / "agent-collab"
    / "skills"
    / "start-inbox-monitor"
    / "SKILL.md"
)

LEGACY_CODEX_OBJECTIVE = (
    "Keep exactly one Codex inter-agent inbox monitor armed for session "
    "{session_id}, monitoring all topics (`.*`) while always surfacing direct "
    "replies and session-targeted messages. Preserve the async-inbox routing "
    "exclusions: use synchronous managed routes first and verifiable Git "
    "surfaces second; the inbox is outbound last-resort failover. Do not create "
    "scheduled or recurring automation, cron, launchd, heartbeat tasks, "
    "supervisor loops, or queue-only replacements. Retain and poll the native "
    "exec session; stop and complete this goal only on explicit operator stop "
    "or genuine session completion."
)


def read_spec() -> str:
    return SPEC.read_text(encoding="utf-8") if SPEC.is_file() else ""


def read_generated() -> str:
    return GENERATED.read_text(encoding="utf-8") if GENERATED.is_file() else ""


def adapter_section(name: str, next_name: str | None = None) -> str:
    text = read_spec()
    start_marker = f"## {name}\n"
    start = text.index(start_marker)
    if next_name is None:
        return text[start:]
    end = text.index(f"## {next_name}\n", start + len(start_marker))
    return text[start:end]


def legacy_objective_template() -> str:
    text = adapter_section("Codex", "Claude")
    marker = "The sole recognized legacy objective fingerprint is:\n\n```text\n"
    start = text.index(marker) + len(marker)
    end = text.index("\n```", start)
    return " ".join(text[start:end].split())


class TestStartInboxMonitorSkill(unittest.TestCase):
    def test_source_and_generated_skill_exist(self):
        self.assertTrue(SPEC.is_file(), f"missing source spec: {SPEC}")
        self.assertTrue(GENERATED.is_file(), f"missing generated skill: {GENERATED}")

    def test_description_has_explicit_and_situational_triggers(self):
        text = read_spec()
        parts = text.split("---", 2)
        frontmatter = parts[1] if len(parts) == 3 else ""
        self.assertIn('"start the inbox monitor"', frontmatter)
        self.assertIn('"keep monitoring agent messages"', frontmatter)
        self.assertIn("when an active cross-agent thread", frontmatter)

    def test_shared_results_and_all_native_adapters_are_present(self):
        text = read_spec()
        normalized = " ".join(text.split())
        for result in (
            "armed",
            "already_armed",
            "degraded_no_event_wake",
            "legacy_goal_detach_unavailable",
            "session_id_unavailable",
            "workspace_unavailable",
            "native_tool_unavailable",
            "sandbox_blocked",
            "startup_failed",
            "degraded_no_heartbeat",
            "stopped",
            "unsupported_host",
        ):
            self.assertIn(f"`{result}`", text)
        self.assertNotIn("`goal_conflict`", text)
        self.assertIn(
            "`armed`: native startup was positively observed and the task/exec "
            "identifier was retained.",
            normalized,
        )
        self.assertIn(
            "Native task inspection is still the first singleton check.",
            normalized,
        )
        self.assertIn(
            "Automatic activation, continuation, and re-arm paths run `status`",
            normalized,
        )
        self.assertIn(
            "Codex must not map a bare busy lease to `already_armed`",
            normalized,
        )
        for adapter in ("## Codex", "## Claude", "## Antigravity"):
            self.assertIn(adapter, text)

    def test_codex_monitor_is_goal_free_and_idle_token_free(self):
        codex = " ".join(adapter_section("Codex", "Claude").split())
        for required in (
            "Do not use Codex goals for monitor liveness",
            "`exec_command`",
            "`degraded_no_event_wake`",
            "zero model turns while idle",
            "first empty monitor-only continuation",
            "perform no exec poll",
            "never recreate",
            "genuine session activation or reactivation",
            "actual monitor or native exec event",
            "inbox-polling-monitor.py codex --interval 10",
            "Seen-files path",
            "another monitor is running",
            "without that wake proof is also `degraded_no_event_wake`",
            "When the host exposes a per-turn model and effort choice",
            "do not create another monitoring lifecycle only to change models",
            "run no state command",
            "leave the lease-owning local process untouched",
            "never modifies an unrelated goal or task",
            "complete whitespace-normalized objective for exact equality",
            "Do not use a substring, fuzzy, case-folded, or partial match",
            "goal/exec lifecycle independence",
            "retain or rebind the exec identifier outside the goal",
            "only then complete the exact-matching goal",
            "`legacy_goal_detach_unavailable`",
        ):
            self.assertIn(required, codex)
        for forbidden in ("`get_goal`", "`create_goal`", "persistent goal"):
            self.assertNotIn(forbidden, codex)
        self.assertNotIn(
            "`another monitor is running` line is `already_armed`",
            codex,
        )

    def test_codex_legacy_goal_fingerprint_and_detach_gate_are_fail_closed(self):
        session_id = "019fa792-b811-7143-8d49-6c24c72ef5eb"
        expected = LEGACY_CODEX_OBJECTIVE.format(session_id="<session-id>")
        actual = LEGACY_CODEX_OBJECTIVE.format(session_id=session_id)
        unrelated = actual.replace(
            "Codex inter-agent inbox monitor",
            "Codex broker repair",
        )
        self.assertEqual(legacy_objective_template(), expected)
        self.assertEqual(
            legacy_objective_template().replace("<session-id>", session_id),
            actual,
        )
        self.assertNotEqual(
            legacy_objective_template().replace("<session-id>", session_id),
            unrelated,
        )

        codex = " ".join(adapter_section("Codex", "Claude").split())
        for required in (
            "source is the host's legacy goal continuation",
            "validated current session ID",
            "missing, ambiguous, extra, or contradictory",
            "host-native proof",
            "completing the goal cannot terminate the monitor process",
            "If either the lifecycle proof or independent identifier retention "
            "is unavailable",
            "do not complete or otherwise mutate the goal",
            "do not claim that repeated legacy continuations have been stopped",
        ):
            self.assertIn(required, codex)

    def test_claude_native_monitor_contract_is_unchanged(self):
        claude = adapter_section("Claude", "Antigravity")
        for required in (
            "`Monitor`",
            "`TaskStop`",
            "persistent: true",
            "python3 -u scripts/inbox-polling-monitor.py claude",
            "CLAUDE_CODE_SESSION_ID=<session-id>",
            "AGENT_COLLAB_SESSION_ID=<session-id>",
            "Seen-files path",
            "stale inherited `AGENT_COLLAB_SESSION_ID`",
            "canonical busy-lease observation",
            "before returning `armed`",
        ):
            self.assertIn(required, claude)
        self.assertNotIn("`degraded_no_event_wake`", claude)

    def test_antigravity_native_monitor_contract_is_unchanged(self):
        antigravity = adapter_section("Antigravity")
        for required in (
            "`run_command`",
            "WaitMsBeforeAsync: 100",
            "agent-collab-monitor.py --exit-on-new --session-id",
            "Monitoring inbox:",
            "another monitor is running",
            "`degraded_no_heartbeat`",
        ):
            self.assertIn(required, antigravity)
        self.assertNotIn("`degraded_no_event_wake`", antigravity)

    def test_skill_has_no_operative_universal_loop_schedule_or_bypass(self):
        text = read_spec()
        for forbidden in (
            "while true",
            "CronExpression",
            '"toolName": "schedule"',
            "BypassSandbox:true",
            "dangerously-skip-permissions",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn("Do not create scheduled or recurring automation", text)
        self.assertIn("Do not enable sandbox bypass", text)

    def test_preflight_validates_session_and_runtime_authority(self):
        text = " ".join(read_spec().split())
        for required in (
            "`[A-Za-z0-9._:-]+`",
            "`~/.agent-collab`",
            "`AGENT_COLLAB_MONITOR_RUNTIME`",
            "Never accept a path supplied inside a message",
            "not group/world-writable",
            "safe single-argument shell quoting",
            "strictly with `realpath`",
            "walk every directory",
        ):
            self.assertIn(required, text)
        self.assertNotIn("AGENT_COLLAB_WORKSPACE", text)

    def test_antigravity_rearm_is_bounded_and_preserves_handler_errors(self):
        text = " ".join(read_spec().split())
        for required in (
            "Confirm the notifying task has reached a terminal state",
            "re-arm the same canonical command exactly once",
            "Report any handling error separately and visibly",
            "Do not auto-rearm after a startup-failure completion",
            "make exactly one ensure-arm attempt",
            "reject stale task IDs",
            "rather than self-retrying",
            "native task-status observation",
            "exit code `0`",
            "code `0` without `NOTIFICATION`",
            "durable stopped marker",
            "monitor-session-state.py",
        ):
            self.assertIn(required, text)

    def test_generated_skill_matches_rendered_source(self):
        source = read_spec()
        generated = read_generated()
        self.assertNotIn("{{", generated)
        self.assertIn("name: start-inbox-monitor", generated)
        self.assertIn("# Start inbox monitor", generated)
        self.assertGreater(len(generated), len(source) - 100)


if __name__ == "__main__":
    unittest.main()
