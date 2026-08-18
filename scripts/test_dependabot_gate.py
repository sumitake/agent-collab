#!/usr/bin/env python3
"""Unit tests for scripts/dependabot_gate.py.

Fixtures are derived from REAL observed payloads (peer-review requirement,
Codex concern 1 — 2026-08-17): the clean-result issue comment on workspace
PR #2733 (comment 5305468863) and the findings review on PR #2715
(review 4942058190).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dependabot_gate import check_commits, classify_signal  # noqa: E402

CODEX = "chatgpt-codex-connector[bot]"
HEAD = "0587e23fd8aa00112233445566778899aabbccdd"

# Real shape: clean result is an ISSUE COMMENT with a short reviewed-commit sha.
CLEAN_COMMENT = {
    "id": 5305468863,
    "user": {"login": CODEX},
    "body": (
        "Codex Review: Didn't find any major issues. More of your lovely PRs "
        "please.\n\n**Reviewed commit:** `0587e23fd8`\n\n<details>...</details>"
    ),
}

# Real shape: findings arrive as a REVIEW bound to a full commit_id with
# P-badge markers in the body.
FINDINGS_REVIEW = {
    "id": 4942058190,
    "user": {"login": CODEX},
    "state": "COMMENTED",
    "commit_id": HEAD,
    "body": (
        "\n### \U0001f4a1 Codex Review\n\nhttps://github.com/x/y/blob/f62047a5/"
        "scripts/manage.py#L917\n**<sub><sub>![P1 Badge](https://img.shields.io/"
        "badge/P1-orange?style=flat)</sub></sub>  Accept the prior released "
        "runtime during sanitization**\n\nWhen this workspace bumps..."
    ),
}


def _commit(author="dependabot[bot]", committer="web-flow", verified=True, sha="a" * 40):
    return {
        "sha": sha,
        "author": {"login": author} if author is not None else None,
        "committer": {"login": committer} if committer is not None else None,
        "commit": {"verification": {"verified": verified}},
    }


class TestCheckCommits(unittest.TestCase):
    def test_authentic_dependabot_commit_passes(self):
        self.assertEqual(check_commits([_commit()]), [])

    def test_spoofed_author_login_alone_is_not_enough(self):
        # author.login is derived from the commit-header email and is
        # spoofable; committer + signature must also match.
        self.assertTrue(check_commits([_commit(committer="sumitake")]))
        self.assertTrue(check_commits([_commit(verified=False)]))

    def test_foreign_author_fails(self):
        self.assertTrue(check_commits([_commit(author="sumitake")]))

    def test_null_author_fails_closed(self):
        self.assertTrue(check_commits([_commit(author=None)]))

    def test_any_bad_commit_among_good_ones_fails(self):
        self.assertTrue(check_commits([_commit(), _commit(author="mallory")]))


class TestClassifySignal(unittest.TestCase):
    def test_real_clean_comment_at_head_is_clean(self):
        verdict, _ = classify_signal(HEAD, [CLEAN_COMMENT], [])
        self.assertEqual(verdict, "clean")

    def test_clean_comment_for_other_head_is_absent(self):
        verdict, _ = classify_signal("f" * 40, [CLEAN_COMMENT], [])
        self.assertEqual(verdict, "absent")

    def test_real_findings_review_at_head_is_findings(self):
        verdict, _ = classify_signal(HEAD, [], [FINDINGS_REVIEW])
        self.assertEqual(verdict, "findings")

    def test_findings_review_for_other_head_is_ignored(self):
        stale = dict(FINDINGS_REVIEW, commit_id="e" * 40)
        verdict, _ = classify_signal(HEAD, [], [stale])
        self.assertEqual(verdict, "absent")

    def test_head_bound_findings_beat_head_bound_clean(self):
        # Fail-closed precedence: findings win even when a clean comment for
        # the same head also exists.
        verdict, _ = classify_signal(HEAD, [CLEAN_COMMENT], [FINDINGS_REVIEW])
        self.assertEqual(verdict, "findings")

    def test_unrecognized_head_bound_shape_fails_closed(self):
        odd = {
            "id": 1,
            "user": {"login": CODEX},
            "commit_id": HEAD,
            "body": "Something new the bot never said before.",
        }
        verdict, _ = classify_signal(HEAD, [], [odd])
        self.assertEqual(verdict, "findings")

    def test_non_codex_actors_cannot_mint_a_clean_signal(self):
        forged = dict(CLEAN_COMMENT, user={"login": "sumitake"})
        verdict, _ = classify_signal(HEAD, [forged], [])
        self.assertEqual(verdict, "absent")

    def test_no_responses_is_absent(self):
        verdict, _ = classify_signal(HEAD, [], [])
        self.assertEqual(verdict, "absent")




class TestTrustBoundary(unittest.TestCase):
    """Pin the base-controlled trust boundary (peer review Codex r2):
    the merge-blocking Dependabot gate must never execute PR-controlled code.
    """

    REPO = Path(__file__).resolve().parents[1]

    @classmethod
    def setUpClass(cls) -> None:
        cls.gate_wf = (cls.REPO / ".github" / "workflows" / "dependabot-gate.yml").read_text(
            encoding="utf-8"
        )
        cls.trace_wf = (cls.REPO / ".github" / "workflows" / "compliance-trace.yml").read_text(
            encoding="utf-8"
        )

    def test_gate_workflow_is_base_controlled(self):
        self.assertIn("pull_request_target", self.gate_wf)
        self.assertNotIn("\n  pull_request:\n", self.gate_wf)
        self.assertIn("ref: main", self.gate_wf, "checkout must pin the trusted base ref")

    def test_gate_workflow_runs_the_gate_scripts(self):
        self.assertIn("scripts/dependabot_gate.py commits", self.gate_wf)
        self.assertIn("scripts/dependabot_gate.py signal", self.gate_wf)

    def test_pr_controlled_trace_workflow_never_runs_the_gate(self):
        self.assertNotIn(
            "dependabot_gate.py", self.trace_wf,
            "compliance-trace.yml runs PR-controlled code and must not "
            "execute the merge-blocking Dependabot gate",
        )


if __name__ == "__main__":
    unittest.main()
