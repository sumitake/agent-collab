#!/usr/bin/env python3
"""Unit tests for scripts/dependabot_gate.py (deterministic no-AI gate).

Fixtures reflect REAL observed shapes: a genuine Dependabot commit (workspace
PR #2763 head b608be0d: author dependabot[bot], committer web-flow,
verification.reason=valid) and fetch-metadata's updated-dependencies-json
(objects with `dependencyName` + `updateType` like `version-update:semver-*`).
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dependabot_gate  # noqa: E402
from dependabot_gate import (  # noqa: E402
    check_commits,
    check_files,
    check_update_types,
)


def _commit(author="dependabot[bot]", committer="web-flow", verified=True,
            reason="valid", sha="a" * 40):
    return {
        "sha": sha,
        "author": {"login": author} if author is not None else None,
        "committer": {"login": committer} if committer is not None else None,
        "commit": {"verification": {"verified": verified, "reason": reason}},
    }


def _run_main(mode, **env):
    orig_argv = sys.argv
    orig_env = {k: os.environ.get(k) for k in env}
    orig_get = dependabot_gate._get_paginated
    try:
        sys.argv = ["dependabot_gate.py", mode]
        for k, v in env.items():
            if k == "_paginated":
                dependabot_gate._get_paginated = lambda path, _v=v: _v
            else:
                os.environ[k] = v
        return dependabot_gate.main()
    finally:
        sys.argv = orig_argv
        dependabot_gate._get_paginated = orig_get
        for k, v in orig_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestCheckCommits(unittest.TestCase):
    def test_authentic_dependabot_commit_passes(self):
        self.assertEqual(check_commits([_commit()]), [])

    def test_spoofed_author_login_alone_is_not_enough(self):
        self.assertTrue(check_commits([_commit(committer="sumitake")]))
        self.assertTrue(check_commits([_commit(verified=False)]))

    def test_valid_signer_reason_required(self):
        self.assertTrue(check_commits([_commit(reason="unverified")]))
        self.assertTrue(check_commits([_commit(reason=None)]))
        self.assertEqual(check_commits([_commit(reason="valid")]), [])

    def test_foreign_or_null_author_fails(self):
        self.assertTrue(check_commits([_commit(author="sumitake")]))
        self.assertTrue(check_commits([_commit(author=None)]))

    def test_any_bad_commit_among_good_ones_fails(self):
        self.assertTrue(check_commits([_commit(), _commit(author="mallory")]))

    def test_commits_mode_fails_closed_on_empty_list(self):
        self.assertEqual(
            _run_main("commits", REPO="o/r", PR_NUMBER="1", _paginated=[]), 1)


class TestCheckUpdateTypes(unittest.TestCase):
    def _dep(self, ut, name="actions/checkout"):
        return {"dependencyName": name, "updateType": ut}

    def test_patch_and_minor_pass(self):
        self.assertEqual(check_update_types(
            [self._dep("version-update:semver-patch"),
             self._dep("version-update:semver-minor")]), [])

    def test_any_major_in_group_fails(self):
        self.assertTrue(check_update_types(
            [self._dep("version-update:semver-patch"),
             self._dep("version-update:semver-major", "actions/setup-node")]))

    def test_missing_or_null_update_type_fails_closed(self):
        # fetch-metadata's scalar maxSemver() OMITS these; the per-entry check
        # must catch them (Grok concern 1).
        self.assertTrue(check_update_types([{"dependencyName": "x"}]))
        self.assertTrue(check_update_types([self._dep(None)]))

    def test_unknown_token_fails_closed(self):
        self.assertTrue(check_update_types([self._dep("version-update:semver-huge")]))

    def test_grouped_minor_plus_missing_still_fails(self):
        # The exact hole: a group whose scalar update-type reads 'minor' while
        # one entry has no updateType. Per-entry catches the missing one.
        self.assertTrue(check_update_types(
            [self._dep("version-update:semver-minor"), {"dependencyName": "y"}]))

    def test_update_type_mode_env_paths(self):
        patch = json.dumps([self._dep("version-update:semver-patch")])
        major = json.dumps([self._dep("version-update:semver-major")])
        self.assertEqual(_run_main("update-type", UPDATED_DEPENDENCIES_JSON=patch), 0)
        self.assertEqual(_run_main("update-type", UPDATED_DEPENDENCIES_JSON=major), 1)
        self.assertEqual(_run_main("update-type", UPDATED_DEPENDENCIES_JSON=""), 1)
        self.assertEqual(_run_main("update-type", UPDATED_DEPENDENCIES_JSON="not json"), 1)
        self.assertEqual(_run_main("update-type", UPDATED_DEPENDENCIES_JSON="[]"), 1)
        self.assertEqual(_run_main("update-type", UPDATED_DEPENDENCIES_JSON='{"a":1}'), 1)


class TestCheckFiles(unittest.TestCase):
    def _f(self, name, previous=None):
        d = {"filename": name}
        if previous:
            d["previous_filename"] = previous
        return d

    def test_workflow_and_action_paths_allowed(self):
        self.assertEqual(check_files(
            [self._f(".github/workflows/ci.yml"),
             self._f(".github/actions/build/action.yml")]), [])

    def test_path_outside_ecosystem_fails(self):
        self.assertTrue(check_files([self._f("README.md")]))
        self.assertTrue(check_files([self._f("src/app.py")]))

    def test_control_plane_workflow_is_held(self):
        # These ARE workflow files (pass the allowlist) but are the gate's own
        # control plane — a Dependabot bump of the fetch-metadata pin here must
        # go manual (Grok concern 2).
        self.assertTrue(check_files([self._f(".github/workflows/dependabot-gate.yml")]))
        self.assertTrue(check_files([self._f(".github/workflows/dependabot-automerge.yml")]))

    def test_control_plane_script_is_held(self):
        self.assertTrue(check_files([self._f("scripts/dependabot_gate.py")]))
        self.assertTrue(check_files([self._f("tests/test_dependabot_gate.py")]))

    def test_rename_from_disallowed_path_fails(self):
        self.assertTrue(check_files(
            [self._f(".github/workflows/ci.yml", previous="secrets.txt")]))

    def test_files_mode_paths(self):
        good = [self._f(".github/workflows/ci.yml")]
        bad = [self._f("README.md")]
        self.assertEqual(_run_main("files", REPO="o/r", PR_NUMBER="1", _paginated=good), 0)
        self.assertEqual(_run_main("files", REPO="o/r", PR_NUMBER="1", _paginated=bad), 1)
        self.assertEqual(_run_main("files", REPO="o/r", PR_NUMBER="1", _paginated=[]), 1)


class TestTrustBoundary(unittest.TestCase):
    """Pin the base-controlled trust boundary + that referenced gate paths
    exist (DOA-path guard, GLM peer review)."""

    REPO = Path(__file__).resolve().parents[1]

    @classmethod
    def setUpClass(cls):
        cls.gate = (cls.REPO / ".github" / "workflows" / "dependabot-gate.yml").read_text()

    def test_gate_is_base_controlled_single_event(self):
        self.assertIn("pull_request_target", self.gate)
        self.assertNotIn("\n  pull_request:\n", self.gate)
        self.assertIn("ref: main", self.gate)

    def test_gate_runs_the_three_deterministic_checks(self):
        for mode in ("commits", "files", "update-type"):
            self.assertIn(f"dependabot_gate.py {mode}", self.gate)
        # no Codex signal mode / no async review dependency (prose may still
        # reference the retired design in comments — check the invocation only).
        self.assertNotIn("dependabot_gate.py signal", self.gate)

    def test_fetch_metadata_is_sha_pinned(self):
        import re
        m = re.search(r"uses:\s*dependabot/fetch-metadata@([0-9a-f]{40})", self.gate)
        self.assertIsNotNone(m, "fetch-metadata must be pinned to a 40-hex SHA")

    def test_every_referenced_python_path_exists(self):
        import re
        for path in re.findall(r"python3 (\S+\.py)", self.gate):
            self.assertTrue((self.REPO / path).is_file(),
                            msg=f"gate references non-existent path: {path}")


if __name__ == "__main__":
    unittest.main()
