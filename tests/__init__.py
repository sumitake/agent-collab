# Marketplace-level test suite (cross-cutting checks that span both plugins).
# Per-plugin tests live under plugins/<name>/backend/tests/ or
# plugins/<name>/mcp-server/tests/.

import os

# Tests in this package spawn git in temporary directories. When the suite is
# run from a git hook (or any process where git has exported its environment),
# an inherited absolute GIT_DIR makes those temp-dir git calls target the REAL
# repository — observed 2026-08-03: a pre-push run set core.bare=true and a
# fixture user identity in the live .git/config (ledger
# plugin.tests.inherit.git.hook.env.mutate.real.repo). Scrub the per-repo
# pointers at package import so every runner is safe, not just the hook (the
# .githooks/pre-push wrapper independently sanitizes its suite subshells).
# GIT_CONFIG_GLOBAL/GIT_CONFIG_SYSTEM are deliberately left alone: tests that
# commit in temp repositories rely on the machine's global identity. A test
# that deliberately exercises poisoned-git-env behavior must set its variables
# AFTER this package import (e.g., in the test body or a subprocess env), as
# the scrub runs once at import time.
for _var in (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
):
    os.environ.pop(_var, None)
del _var
