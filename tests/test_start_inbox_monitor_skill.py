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


def read_spec() -> str:
    return SPEC.read_text(encoding="utf-8") if SPEC.is_file() else ""


def read_generated() -> str:
    return GENERATED.read_text(encoding="utf-8") if GENERATED.is_file() else ""


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
        for result in (
            "armed",
            "already_armed",
            "goal_conflict",
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
        for adapter in ("## Codex", "## Claude", "## Antigravity"):
            self.assertIn(adapter, text)

    def test_native_tool_and_command_contracts_are_exact(self):
        text = read_spec()
        for required in (
            "`get_goal`/`create_goal`",
            "`exec_command`",
            "persistent goal",
            "inbox-polling-monitor.py codex --interval 10",
            "`Monitor`",
            "`TaskStop`",
            "persistent: true",
            "python3 -u scripts/inbox-polling-monitor.py claude",
            "CLAUDE_CODE_SESSION_ID=<session-id>",
            "AGENT_COLLAB_SESSION_ID=<session-id>",
            "Seen-files path",
            "stale inherited `AGENT_COLLAB_SESSION_ID`",
            "`run_command`",
            "WaitMsBeforeAsync: 100",
            "agent-collab-monitor.py --exit-on-new --session-id",
            "Monitoring inbox:",
            "another monitor is running",
        ):
            self.assertIn(required, text)

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
