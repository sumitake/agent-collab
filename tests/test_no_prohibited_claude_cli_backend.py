"""Negative reachability guard for synchronous Claude and raw provider paths."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "agent-collab"
CLAUDE_ARGV = re.compile(r"[\"']claude[\"']\s*,\s*[\"']-p[\"']")


class TestNoRawProviderBackend(unittest.TestCase):
    def test_unified_skills_have_no_reachable_raw_provider_markers(self) -> None:
        forbidden = (
            "mcp__claude-cli",
            "ask-claude",
            "command -v codex",
            "opencode run -m",
            "grok --prompt-file",
        )
        offenders = []
        for path in (PLUGIN / "skills").rglob("SKILL.md"):
            text = path.read_text(encoding="utf-8")
            for marker in forbidden:
                if marker in text:
                    offenders.append(f"{path.relative_to(ROOT)}: {marker}")
            if CLAUDE_ARGV.search(text):
                offenders.append(f"{path.relative_to(ROOT)}: Claude argv")
        self.assertEqual(offenders, [])

    def test_plugin_has_no_provider_executor_source_or_mcp_server(self) -> None:
        self.assertFalse((PLUGIN / "backend").exists())
        self.assertFalse((PLUGIN / "mcp-server").exists())
        self.assertFalse(any(PLUGIN.rglob("codex_exec.py")))
        self.assertFalse(any(PLUGIN.rglob("opencode_exec.py")))
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "plugins/agent-collab"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        self.assertFalse(any(path.endswith(".pyc") for path in tracked))
        self.assertFalse(any("/__pycache__/" in f"/{path}/" for path in tracked))


if __name__ == "__main__":
    unittest.main()
