#!/usr/bin/env python3
"""Wrapper-level tests for .githooks/pre-push (the test gate + compliance chain).

The wrapper is exercised as bash against a temp copy of the hook with stub
`python3` and `git` executables on PATH, so the tests assert the wrapper's
control flow (which suites ran, in what order, what blocked) without running
the real suites.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_SRC = REPO_ROOT / ".githooks" / "pre-push"


class PrePushWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".githooks").mkdir()
        (self.root / "scripts").mkdir()
        (self.root / "tests").mkdir()
        self.hook = self.root / ".githooks" / "pre-push"
        self.hook.write_text(HOOK_SRC.read_text())
        self.hook.chmod(self.hook.stat().st_mode | stat.S_IXUSR)
        (self.root / "scripts" / "hook-pre-push.py").write_text("# stub\n")
        self.log = self.root / "calls.log"
        self.bin = self.root / "stubbin"
        self.bin.mkdir()
        self._write_stub(
            "python3",
            '#!/bin/bash\necho "python3 $* GIT_DIR=${GIT_DIR-unset}" >> "$STUB_LOG"\n'
            'case "$*" in\n'
            '  *"-s tests"*) exit "${FAIL_TESTS_SUITE:-0}";;\n'
            '  *"-s scripts"*) exit "${FAIL_SCRIPTS_SUITE:-0}";;\n'
            "  *) exit 0;;\n"
            "esac\n",
        )
        self._write_stub(
            "git",
            '#!/bin/bash\nif [ -n "${GIT_FAIL:-}" ]; then exit 1; fi\n'
            'echo "${GIT_BRANCH:-feature-x}"\n',
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_stub(self, name: str, body: str) -> None:
        p = self.bin / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _run(self, **env_over: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.pop("AGENT_COLLAB_PREPUSH_TESTS", None)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["STUB_LOG"] = str(self.log)
        env.update(env_over)
        return subprocess.run(
            ["bash", str(self.hook)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def _calls(self) -> list[str]:
        if not self.log.exists():
            return []
        return [line for line in self.log.read_text().splitlines() if line]

    def test_both_suites_run_in_order_then_compliance(self) -> None:
        res = self._run()
        self.assertEqual(res.returncode, 0, res.stderr)
        calls = self._calls()
        self.assertEqual(len(calls), 3)
        self.assertIn("-s tests", calls[0])
        self.assertIn("-s scripts", calls[1])
        self.assertIn("hook-pre-push.py", calls[2])

    def test_first_suite_failure_blocks_before_compliance(self) -> None:
        res = self._run(FAIL_TESTS_SUITE="1")
        self.assertEqual(res.returncode, 1)
        self.assertIn("tests/ suite failed", res.stderr)
        self.assertEqual(len(self._calls()), 1)

    def test_second_suite_failure_blocks_before_compliance(self) -> None:
        res = self._run(FAIL_SCRIPTS_SUITE="1")
        self.assertEqual(res.returncode, 1)
        self.assertIn("scripts/ suite failed", res.stderr)
        self.assertEqual(len(self._calls()), 2)

    def test_exact_opt_out_skips_tests_but_runs_compliance(self) -> None:
        res = self._run(AGENT_COLLAB_PREPUSH_TESTS="0")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("SKIPPED", res.stderr)
        calls = self._calls()
        self.assertEqual(len(calls), 1)
        self.assertIn("hook-pre-push.py", calls[0])

    def test_non_exact_opt_out_values_still_run_tests(self) -> None:
        for value in ("", "false", "no", "1"):
            self.log.unlink(missing_ok=True)
            res = self._run(AGENT_COLLAB_PREPUSH_TESTS=value)
            self.assertEqual(res.returncode, 0, (value, res.stderr))
            self.assertEqual(len(self._calls()), 3, value)

    def test_main_branch_skips_tests_but_runs_compliance(self) -> None:
        res = self._run(GIT_BRANCH="main")
        self.assertEqual(res.returncode, 0, res.stderr)
        calls = self._calls()
        self.assertEqual(len(calls), 1)
        self.assertIn("hook-pre-push.py", calls[0])

    def test_branch_detection_failure_runs_tests(self) -> None:
        res = self._run(GIT_FAIL="1")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(len(self._calls()), 3)

    def test_suite_subshells_are_sanitized_of_hook_git_env(self) -> None:
        res = self._run(GIT_DIR="/some/repo/.git/worktrees/x")
        self.assertEqual(res.returncode, 0, res.stderr)
        calls = self._calls()
        self.assertEqual(len(calls), 3)
        self.assertIn("GIT_DIR=unset", calls[0])
        self.assertIn("GIT_DIR=unset", calls[1])
        # the exec'd compliance checker keeps the hook environment
        self.assertIn("GIT_DIR=/some/repo/.git/worktrees/x", calls[2])


if __name__ == "__main__":
    unittest.main()
