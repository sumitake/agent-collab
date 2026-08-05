#!/usr/bin/env python3
"""Wrapper-level tests for .githooks/pre-commit (worktree root resolution).

The wrapper is exercised as bash against copies of the hook with stub
`python3` and `git` executables on PATH, so the tests assert which tree the
consistency check is resolved against without running the real check.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_SRC = REPO_ROOT / ".githooks" / "pre-commit"


class PreCommitWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".githooks").mkdir()
        (self.root / "scripts").mkdir()
        self.hook = self.root / ".githooks" / "pre-commit"
        self.hook.write_text(HOOK_SRC.read_text())
        self.hook.chmod(self.hook.stat().st_mode | stat.S_IXUSR)
        self.log = self.root / "calls.log"
        self.bin = self.root / "stubbin"
        self.bin.mkdir()
        self._write_stub(
            "python3",
            '#!/bin/bash\necho "python3 $*" >> "$STUB_LOG"\n'
            'exit "${FAIL_CONSISTENCY:-0}"\n',
        )
        self._write_stub(
            "git",
            "#!/bin/bash\n"
            'case "$*" in\n'
            '  *"rev-parse --show-toplevel"*)\n'
            '    if [ -n "${GIT_TOPLEVEL_FAIL:-}" ]; then exit 1; fi\n'
            '    echo "$PWD";;\n'
            "  *) exit 0;;\n"
            "esac\n",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_stub(self, name: str, body: str) -> None:
        p = self.bin / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _run(
        self, hook: Path | None = None, **env_over: str
    ) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["PATH"] = f"{self.bin}:{env['PATH']}"
        env["STUB_LOG"] = str(self.log)
        env.update(env_over)
        # git runs hooks with the working directory at the worktree top; the
        # wrapper's root resolution (rev-parse, pwd fallback) depends on it.
        return subprocess.run(
            ["bash", str(hook or self.hook)],
            capture_output=True,
            text=True,
            env=env,
            cwd=self.root,
            check=False,
        )

    def _calls(self) -> list[str]:
        if not self.log.exists():
            return []
        return [line for line in self.log.read_text().splitlines() if line]

    def test_check_runs_against_invoking_worktree_not_hook_location(self) -> None:
        # core.hooksPath can point into a DIFFERENT checkout (the primary);
        # a copy of the hook living outside the invoking worktree must still
        # resolve the consistency check against the worktree root (the
        # hook's cwd), not against its own file location — the 2026-08-05
        # false "NOTICE drifted" FAIL came from exactly that mismatch.
        elsewhere = self.root / "elsewhere" / ".githooks"
        elsewhere.mkdir(parents=True)
        foreign_hook = elsewhere / "pre-commit"
        foreign_hook.write_text(HOOK_SRC.read_text())
        foreign_hook.chmod(foreign_hook.stat().st_mode | stat.S_IXUSR)
        res = self._run(hook=foreign_hook)
        self.assertEqual(res.returncode, 0, res.stderr)
        calls = self._calls()
        self.assertEqual(len(calls), 1)
        self.assertIn(
            str(self.root / "scripts" / "check_release_consistency.py"), calls[0]
        )
        self.assertNotIn("elsewhere", calls[0])

    def test_rev_parse_failure_blocks_the_commit(self) -> None:
        # Fail closed: without a proven worktree root the wrapper must not run
        # anything (a cwd fallback would execute whatever tree cwd names).
        res = self._run(GIT_TOPLEVEL_FAIL="1")
        self.assertEqual(res.returncode, 1)
        self.assertIn("cannot resolve the invoking worktree root", res.stderr)
        self.assertEqual(len(self._calls()), 0)

    def test_consistency_failure_blocks_the_commit(self) -> None:
        res = self._run(FAIL_CONSISTENCY="1")
        self.assertEqual(res.returncode, 1)


class PreCommitWorktreeIntegrationTest(unittest.TestCase):
    """Real-git end-to-end: a linked worktree commit must run the WORKTREE's
    consistency check even though core.hooksPath is an absolute path into the
    primary checkout (the 2026-08-05 false-FAIL topology)."""

    def test_linked_worktree_commit_validates_worktree_tree(self) -> None:
        env = dict(os.environ)
        for var in (
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_PREFIX",
            "GIT_OBJECT_DIRECTORY",
            "GIT_COMMON_DIR",
        ):
            env.pop(var, None)

        def git(*args: str, cwd: Path) -> None:
            subprocess.run(
                ["git", *args], cwd=cwd, env=env, check=True, capture_output=True
            )

        with tempfile.TemporaryDirectory() as td:
            base = Path(td).resolve()
            primary = base / "primary"
            primary.mkdir()
            git("init", "-b", "main", cwd=primary)
            git("config", "user.name", "t", cwd=primary)
            git("config", "user.email", "t@example.invalid", cwd=primary)
            git("config", "commit.gpgsign", "false", cwd=primary)

            marker_log = base / "marker.log"
            env["MARKER_LOG"] = str(marker_log)
            (primary / "scripts").mkdir()
            (primary / "scripts" / "check_release_consistency.py").write_text(
                "import os, pathlib\n"
                "pathlib.Path(os.environ['MARKER_LOG']).write_text(\n"
                "    str(pathlib.Path(__file__).resolve()))\n"
            )
            (primary / ".githooks").mkdir()
            hook = primary / ".githooks" / "pre-commit"
            hook.write_text(HOOK_SRC.read_text())
            hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
            git("add", "-A", cwd=primary)
            git("commit", "-m", "init", cwd=primary)
            # Absolute hooksPath into the primary checkout, as in production.
            git("config", "core.hooksPath", str(primary / ".githooks"), cwd=primary)

            wt = base / "wt"
            git("worktree", "add", str(wt), "-b", "feature", cwd=primary)
            (wt / "file.txt").write_text("x\n")
            git("add", "file.txt", cwd=wt)
            git("commit", "-m", "wt commit", cwd=wt)

            logged = marker_log.read_text()
            self.assertEqual(
                logged, str((wt / "scripts" / "check_release_consistency.py").resolve())
            )


if __name__ == "__main__":
    unittest.main()
