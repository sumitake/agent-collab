#!/usr/bin/env python3
"""Regression test for the tests-package git-env scrub (see tests/__init__.py).

Inherited per-repo git pointers (an absolute GIT_DIR exported by a git hook)
made temp-dir git calls in this suite mutate the real repository config.
The package __init__ scrubs them at import; this test pins that property.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

SCRUBBED = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class GitEnvHardeningTests(unittest.TestCase):
    def test_scrubbed_variables_are_absent_after_package_import(self) -> None:
        # By the time any test in this package runs, tests/__init__.py has
        # imported and the pointers must be gone regardless of the runner.
        for var in SCRUBBED:
            self.assertNotIn(var, os.environ, var)

    def test_import_scrubs_a_freshly_poisoned_environment(self) -> None:
        # Run a child interpreter with every pointer poisoned; importing the
        # tests package must remove them all.
        env = dict(os.environ)
        for var in SCRUBBED:
            env[var] = "/nonexistent/poison"
        code = (
            "import os, sys; sys.path.insert(0, sys.argv[1]); import tests; "
            "leaked = [v for v in sys.argv[2:] if v in os.environ]; "
            "print(','.join(leaked) or 'CLEAN')"
        )
        res = subprocess.run(
            [sys.executable, "-c", code, str(REPO_ROOT), *SCRUBBED],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "CLEAN")


if __name__ == "__main__":
    unittest.main()
