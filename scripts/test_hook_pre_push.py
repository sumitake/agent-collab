#!/usr/bin/env python3
"""Unit tests for scripts/hook-pre-push.py's tier-aware C3 wiring.

Regression coverage for the bug where the pre-push hook called
`cross_check_ok(trace.get("cross_check", ""))` WITHOUT the declared tier, so
every tier read as None -> fail-safe strict and a legitimate Tier-1 'N/A'
cross_check was wrongly rejected ("tier is undeclared/unparseable"), blocking
valid pure-documentation pushes locally. The fix threads `tier=trace.get("tier")`
into the call, matching the authoritative check_pr_compliance.py C3 and the CI
validate-trace gate.

These tests drive the hook's `main()` end-to-end with `run_cmd` monkeypatched,
so they exercise the real call site (not just cross_check_ok in isolation). The
assertions key on the return-code contract (0 = allow push, 1 = block), not on
printed strings, so they stay robust to message wording changes.

Run: python scripts/test_hook_pre_push.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import check_pr_compliance as cpc  # noqa: E402


def _load_hook():
    """Import the hyphenated hook-pre-push.py module by file path."""
    hook_path = SCRIPTS_DIR / "hook-pre-push.py"
    spec = importlib.util.spec_from_file_location("hook_pre_push", hook_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _make_body(**overrides):
    """PR body with a well-formed compliance-trace block (all REQUIRED_KEYS).

    Every key must be present and non-empty or C2 (parse_trace_block) blocks the
    push before C3 is reached, so the trace here is well-formed by construction;
    the tests then vary only `tier` and `cross_check`. Defaults: tier 2 +
    PROCEED (a converged verdict). Pass key=value to override.
    """
    values = {k: "yes" for k in cpc.REQUIRED_KEYS}
    values["tier"] = "2"
    values["cross_check"] = "PROCEED"
    values["contributor_rights"] = "OWNER-AUTHORED"
    values.update(overrides)
    lines = [cpc.TRACE_START]
    lines.extend(f"{k}: {v}" for k, v in values.items())
    lines.append(cpc.TRACE_END)
    return "\n".join(lines)


def _fake_run_cmd(body, branch="dev/claude/prepush-tier-fix-test", pr_state="OPEN"):
    """Build a run_cmd stand-in that answers the hook's two subprocess calls:
    `git symbolic-ref --short HEAD` (branch) and `gh pr view --json ...` (PR JSON).
    Any other command returns a benign success so the seam stays permissive.
    """

    def _runner(args, cwd=None):
        if args[:2] == ["git", "symbolic-ref"]:
            return subprocess.CompletedProcess(args, 0, stdout=branch + "\n", stderr="")
        if args[:3] == ["gh", "pr", "view"]:
            payload = json.dumps({"body": body, "state": pr_state, "number": 999})
            return subprocess.CompletedProcess(args, 0, stdout=payload, stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    return _runner


def _run_main(body, **kwargs):
    """Run the hook's main() against a canned PR body; return (rc, output)."""
    buf = io.StringIO()
    with mock.patch.object(hook, "run_cmd", _fake_run_cmd(body, **kwargs)):
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = hook.main()
    return rc, buf.getvalue()


class TestPrePushTierAwareC3(unittest.TestCase):
    """The pre-push hook must agree with the authoritative gates on the
    tier-gated N/A exemption."""

    def test_tier1_na_allows_push(self):
        """Tier-1 'N/A' is the legitimate pure-docs exemption -> push allowed.

        This is the regression guard: on the pre-fix code (tier not threaded)
        the N/A read as fail-safe strict and main() returned 1.
        """
        rc, out = _run_main(_make_body(tier="1", cross_check="N/A"))
        self.assertEqual(rc, 0, f"Tier-1 N/A should pass the pre-push hook; got rc={rc}\n{out}")

    def test_tier2_na_blocks_push(self):
        """Tier-2 'N/A' is an illegitimate exemption claim -> push blocked."""
        rc, out = _run_main(_make_body(tier="2", cross_check="N/A"))
        self.assertEqual(rc, 1, f"Tier-2 N/A should block the pre-push hook; got rc={rc}\n{out}")

    def test_tier3_na_blocks_push(self):
        """Tier-3 'N/A' is an illegitimate exemption claim -> push blocked."""
        rc, out = _run_main(_make_body(tier="3", cross_check="N/A"))
        self.assertEqual(rc, 1, f"Tier-3 N/A should block the pre-push hook; got rc={rc}\n{out}")

    def test_tier2_proceed_allows_push(self):
        """Positive control: a real converged verdict passes at any tier."""
        rc, out = _run_main(_make_body(tier="2", cross_check="PROCEED"))
        self.assertEqual(rc, 0, f"Tier-2 PROCEED should pass the pre-push hook; got rc={rc}\n{out}")

    def test_tier3_proceed_allows_push(self):
        """A real converged verdict is tier-independent: Tier-3 PROCEED passes."""
        rc, out = _run_main(_make_body(tier="3", cross_check="PROCEED"))
        self.assertEqual(rc, 0, f"Tier-3 PROCEED should pass the pre-push hook; got rc={rc}\n{out}")

    def test_reconsider_blocks_at_tier1(self):
        """The tier only gates the N/A exemption: a non-converged verdict is
        blocked even at Tier 1 (deny logic is tier-independent)."""
        rc, out = _run_main(_make_body(tier="1", cross_check="RECONSIDER"))
        self.assertEqual(rc, 1, f"Tier-1 RECONSIDER should block the pre-push hook; got rc={rc}\n{out}")

    def test_matches_check_pr_compliance_c3(self):
        """Cross-check the wiring directly: the hook must reach the same C3
        eligibility decision as check_pr_compliance.cross_check_ok(tier=...)
        for each tier/verdict pair the hook can see."""
        for tier, verdict in [("1", "N/A"), ("2", "N/A"), ("3", "N/A"),
                              ("2", "PROCEED"), ("1", "RECONSIDER")]:
            with self.subTest(tier=tier, verdict=verdict):
                authoritative_ok, _ = cpc.cross_check_ok(verdict, tier=tier)
                rc, out = _run_main(_make_body(tier=tier, cross_check=verdict))
                self.assertEqual(
                    rc == 0, authoritative_ok,
                    f"hook (rc={rc}) disagrees with cross_check_ok(tier={tier})"
                    f"={authoritative_ok} for {verdict!r}\n{out}")

    def test_non_open_pr_skips_check(self):
        """A closed/merged PR is not gated (matches the hook's skip path)."""
        rc, out = _run_main(_make_body(tier="2", cross_check="N/A"), pr_state="MERGED")
        self.assertEqual(rc, 0, f"non-open PR should skip the check; got rc={rc}\n{out}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
