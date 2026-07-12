#!/usr/bin/env python3
"""Unit tests for the pure functions in check_pr_compliance.py.

Directive-#6 pre-self-merge gate logic tested independently of any network /
gh calls: parse_trace_block, cross_check_ok, cross_check_valid_for_tier,
_parse_tier, parse_codeowners, path_is_operator_reserved, reserved_paths, and
compute_verdict.

The checker and its workflow-inline parser are the two local implementations of
the public contract in `docs/public-governance.md`; this suite prevents their
shared parsing and decision behavior from drifting.

Run: python scripts/test_check_pr_compliance.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_pr_compliance as cpc  # noqa: E402

TRACE_START = cpc.TRACE_START
TRACE_END = cpc.TRACE_END
REQUIRED_KEYS = cpc.REQUIRED_KEYS


def _make_body(**overrides):
    """Return a PR body containing a well-formed compliance-trace block.

    Defaults produce a block that is VALID under the tier-aware cross_check
    content validation (governance-gap fix 2026-06-01): tier defaults to "2"
    and cross_check to "PROCEED" (a recognized, converged verdict), so a
    no-override _make_body() is genuinely well-formed. Every other REQUIRED_KEY
    defaults to "yes". Pass key=value to override a value, or key=None to omit
    the key entirely (simulates a missing key).
    """
    defaults = {k: "yes" for k in REQUIRED_KEYS}
    defaults["tier"] = "2"
    defaults["cross_check"] = "PROCEED"
    defaults["contributor_rights"] = "OWNER-AUTHORED"
    defaults.update(overrides)
    lines = [TRACE_START]
    for k, v in defaults.items():
        if v is not None:
            lines.append(f"{k}: {v}")
    lines.append(TRACE_END)
    return "\n".join(lines)


def _valid_kv():
    """key->value dict for a content-valid trace block (tier 2 + PROCEED), used
    by the few tests that assemble the inner block manually rather than via
    _make_body. Keeps them valid under the tier-aware content check so they keep
    exercising what they were written to exercise (stray prose, extra keys,
    HTML-comment skipping)."""
    kv = {k: "yes" for k in REQUIRED_KEYS}
    kv["tier"] = "2"
    kv["cross_check"] = "PROCEED"
    kv["contributor_rights"] = "OWNER-AUTHORED"
    return kv


# ---------------------------------------------------------------------------
# parse_trace_block
# ---------------------------------------------------------------------------

class TestParseTraceBlock(unittest.TestCase):

    # --- well-formed block ---

    def test_well_formed_all_required_keys(self):
        data, errors = cpc.parse_trace_block(_make_body())
        self.assertEqual(errors, [])
        for key in REQUIRED_KEYS:
            self.assertIn(key, data)

    def test_returns_correct_values(self):
        data, errors = cpc.parse_trace_block(
            _make_body(author="claude", cross_check="PROCEED")
        )
        self.assertEqual(errors, [])
        self.assertEqual(data["author"], "claude")
        self.assertEqual(data["cross_check"], "PROCEED")

    # --- missing / mis-ordered markers ---

    def test_missing_start_marker(self):
        body = "no start here\n" + TRACE_END
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(data, {})
        self.assertTrue(any("start marker" in e for e in errors))

    def test_missing_end_marker(self):
        body = TRACE_START + "\nauthor: me\n"
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(data, {})
        self.assertTrue(any("end marker" in e for e in errors))

    def test_missing_both_markers(self):
        data, errors = cpc.parse_trace_block("just prose")
        self.assertEqual(data, {})
        self.assertTrue(any("missing start marker" in e for e in errors))

    def test_end_before_start(self):
        body = TRACE_END + "\n" + TRACE_START
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(data, {})
        self.assertIn("end marker appears before start marker", errors[0])

    # --- None body ---

    def test_none_body(self):
        data, errors = cpc.parse_trace_block(None)
        self.assertEqual(data, {})
        self.assertGreater(len(errors), 0)

    # --- missing / empty required key ---

    def test_missing_required_key(self):
        body = _make_body(author=None)
        _, errors = cpc.parse_trace_block(body)
        self.assertTrue(any("author" in e and "missing" in e for e in errors))

    def test_empty_required_key(self):
        body = _make_body(cross_check="")
        _, errors = cpc.parse_trace_block(body)
        self.assertTrue(any("cross_check" in e and "empty" in e for e in errors))

    # --- rfind picks the last (canonical) block ---

    def test_rfind_picks_last_block(self):
        """A PR body that mentions the marker strings as prose references
        before the canonical block at the bottom: rfind must select the bottom
        (last) block and not the prose reference."""
        prose = (
            "This PR documents the trace format. Opening marker: "
            + TRACE_START
            + " closing: "
            + TRACE_END
            + "\n"
        )
        canonical = _make_body(author="canonical_author")
        data, errors = cpc.parse_trace_block(prose + canonical)
        self.assertEqual(errors, [])
        self.assertEqual(data["author"], "canonical_author")

    # --- tolerance of stray content and extra keys ---

    def test_stray_prose_without_colon_tolerated(self):
        inner = "\n".join(f"{k}: {v}" for k, v in _valid_kv().items())
        inner += "\nThis line has no colon and is stray prose"
        body = TRACE_START + "\n" + inner + "\n" + TRACE_END
        _, errors = cpc.parse_trace_block(body)
        self.assertEqual(errors, [])

    def test_extra_keys_beyond_required_tolerated(self):
        inner = "\n".join(f"{k}: {v}" for k, v in _valid_kv().items())
        inner += "\nextra_future_key: extra_value"
        body = TRACE_START + "\n" + inner + "\n" + TRACE_END
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(errors, [])
        self.assertIn("extra_future_key", data)

    def test_html_comment_lines_inside_block_skipped(self):
        inner = "\n".join(f"{k}: {v}" for k, v in _valid_kv().items())
        inner += "\n<!-- internal note -->"
        body = TRACE_START + "\n" + inner + "\n" + TRACE_END
        _, errors = cpc.parse_trace_block(body)
        self.assertEqual(errors, [])

    # --- tier as a REQUIRED_KEY (Phase 4c-1, 2026-05-25) ----------------------

    def test_tier_in_required_keys(self):
        self.assertIn("tier", REQUIRED_KEYS)

    def test_missing_tier_key_is_required(self):
        """Without `tier`, the classifier can't gate on under-declaration, so the
        key is required. Mirrors the workspace gate."""
        body = _make_body(tier=None)
        _, errors = cpc.parse_trace_block(body)
        self.assertTrue(any("tier" in e and "missing" in e for e in errors),
                        f"expected a missing-tier error; got {errors}")

    def test_missing_contributor_rights_is_rejected(self):
        _, errors = cpc.parse_trace_block(
            _make_body(contributor_rights=None)
        )
        self.assertTrue(
            any("contributor_rights" in error for error in errors),
            errors,
        )

    def test_owner_authored_contributor_rights_is_valid(self):
        _, errors = cpc.parse_trace_block(
            _make_body(contributor_rights="OWNER-AUTHORED")
        )
        self.assertEqual(errors, [])

    def test_unknown_contributor_rights_state_is_rejected(self):
        _, errors = cpc.parse_trace_block(
            _make_body(contributor_rights="DCO-SIGNED")
        )
        self.assertTrue(
            any("contributor_rights" in error for error in errors),
            errors,
        )

    def test_operator_confirmed_contributor_rights_is_valid(self):
        _, errors = cpc.parse_trace_block(
            _make_body(contributor_rights="OPERATOR-CONFIRMED")
        )
        self.assertEqual(errors, [])

    # --- tier-aware cross_check CONTENT (governance-gap fix 2026-06-01, #481) --

    def test_tier3_na_cross_check_makes_block_invalid(self):
        """#481 regression guard at the parse layer: a Tier-3 block whose
        cross_check is 'N/A' is now an INVALID trace (the CI validate-trace gate
        and the pre-push hook both block on parse_trace_block errors)."""
        body = _make_body(tier="3", cross_check="N/A")
        _, errors = cpc.parse_trace_block(body)
        self.assertTrue(any("Tier 2/3" in e for e in errors),
                        f"expected a tier-validity error; got {errors}")

    def test_tier1_na_cross_check_is_valid(self):
        """A Tier-1 block with cross_check 'N/A' stays valid (the exemption)."""
        body = _make_body(tier="1", cross_check="N/A")
        _, errors = cpc.parse_trace_block(body)
        self.assertEqual(errors, [])

    def test_tier3_proceed_cross_check_is_valid(self):
        body = _make_body(tier="3")  # cross_check defaults to PROCEED
        _, errors = cpc.parse_trace_block(body)
        self.assertEqual(errors, [])

    def test_tier3_quota_blocked_cross_check_is_valid(self):
        """A paused Tier-3 PR (quota-failover exhausted) records a valid trace,
        even though it is not merge-eligible."""
        body = _make_body(tier="3",
                          cross_check="BLOCKED — quota exhausted (event: 7)")
        _, errors = cpc.parse_trace_block(body)
        self.assertEqual(errors, [])

    def test_tier3_garbage_cross_check_invalid(self):
        body = _make_body(tier="3", cross_check="we discussed it offline")
        _, errors = cpc.parse_trace_block(body)
        self.assertTrue(any("not valid for tier 3" in e for e in errors),
                        f"expected a tier-validity error; got {errors}")

    def test_duplicate_key_rejected(self):
        body = (f"{cpc.TRACE_START}\n"
                f"author: Claude\n"
                f"standing_directives: D6\n"
                f"tier: 3\n"
                f"tier: 1\n"
                f"cross_check: PROCEED\n"
                f"post_condition: ci-green\n"
                f"mcp_coverage_gap: NONE\n"
                f"contributor_rights: OWNER-AUTHORED\n"
                f"operator_reserved: no\n"
                f"{cpc.TRACE_END}")
        data, errors = cpc.parse_trace_block(body)
        self.assertTrue(any("duplicate key 'tier'" in e for e in errors))

    def test_duplicate_key_case_variant_rejected(self):
        body = (f"{cpc.TRACE_START}\n"
                f"author: Claude\n"
                f"standing_directives: D6\n"
                f"Tier: 3\n"
                f"tier: 1\n"
                f"cross_check: PROCEED\n"
                f"post_condition: ci-green\n"
                f"mcp_coverage_gap: NONE\n"
                f"contributor_rights: OWNER-AUTHORED\n"
                f"operator_reserved: no\n"
                f"{cpc.TRACE_END}")
        data, errors = cpc.parse_trace_block(body)
        self.assertTrue(any("duplicate key 'tier'" in e for e in errors))

    def test_duplicate_key_keeps_first_value(self):
        body = (f"{cpc.TRACE_START}\n"
                f"author: Claude\n"
                f"standing_directives: D6\n"
                f"tier: 3\n"
                f"tier: 1\n"
                f"cross_check: PROCEED\n"
                f"post_condition: ci-green\n"
                f"mcp_coverage_gap: NONE\n"
                f"contributor_rights: OWNER-AUTHORED\n"
                f"operator_reserved: no\n"
                f"{cpc.TRACE_END}")
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(data.get("tier"), "3")


def _block(tier: str, cross_check: str) -> str:
    return (f"{cpc.TRACE_START}\n"
            f"author: Claude\n"
            f"standing_directives: D6\n"
            f"tier: {tier}\n"
            f"cross_check: {cross_check}\n"
            f"post_condition: ci-green\n"
            f"mcp_coverage_gap: NONE\n"
            f"contributor_rights: OWNER-AUTHORED\n"
            f"operator_reserved: no\n"
            f"{cpc.TRACE_END}")


class TestMultiBlockLaunderGuard(unittest.TestCase):

    def test_two_complete_blocks_rejected(self):
        body = ("## Summary\n\nchange.\n\n"
                + _block("3", "round 2 PROCEED") + "\n\n"
                + _block("1", "N/A"))
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(data, {})
        self.assertTrue(any("block" in e.lower() for e in errors))

    def test_second_block_concealed_in_details_rejected(self):
        body = (f"{_block('3', 'round 2 PROCEED')}\n\n"
                f"<details>\n<summary>internal</summary>\n\n"
                f"{_block('1', 'N/A')}\n\n</details>\n")
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(data, {})
        self.assertTrue(any("block" in e.lower() for e in errors))

    def test_unclosed_visible_start_plus_hidden_block_rejected(self):
        body = (f"{cpc.TRACE_START}\ntier: 3\ncross_check: PROCEED\n\n"
                f"<details>\n{_block('1', 'N/A')}\n</details>\n")
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(data, {})
        self.assertTrue(errors)

    def test_single_line_double_block_rejected(self):
        body = (f"{cpc.TRACE_START}tier: 1{cpc.TRACE_END} "
                f"{cpc.TRACE_START}tier: 3{cpc.TRACE_END}")
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(data, {})
        self.assertTrue(errors)

    def test_single_line_block_after_visible_rejected(self):
        body = (f"{_block('3', 'round 2 PROCEED')}\n\n"
                f"<details>\n{cpc.TRACE_START}tier: 1{cpc.TRACE_END}\n</details>\n")
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(data, {})
        self.assertTrue(errors)

    def test_lone_single_line_block_rejected(self):
        body = f"{cpc.TRACE_START}tier: 2 cross_check: PROCEED{cpc.TRACE_END}"
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(data, {})
        self.assertTrue(errors)

    def test_prefixed_marker_hidden_block_ignored_not_laundered(self):
        visible = _block("3", "round 2 PROCEED")
        hidden = (f"<details>{cpc.TRACE_START}tier: 1 cross_check: N/A"
                  f"{cpc.TRACE_END}</details>")
        body = f"{visible}\n\n{hidden}\n"
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(errors, [])
        self.assertEqual(data["tier"], "3")
        self.assertIn("PROCEED", data["cross_check"])

    def test_prose_backtick_mention_plus_real_block_parses(self):
        body = (f"This documents the `{cpc.TRACE_START} ... {cpc.TRACE_END}` "
                f"markers inline; not a real block.\n\n" + _block("2", "round 1 PROCEED"))
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(errors, [])
        self.assertEqual(data["tier"], "2")
        self.assertIn("PROCEED", data["cross_check"])

    def test_bare_midline_decoy_is_a_documented_residual(self):
        decoy = f"Compliance trace: {cpc.TRACE_START} tier: 3 {cpc.TRACE_END}"
        body = f"{decoy}\n\n{_block('1', 'N/A')}\n"
        data, errors = cpc.parse_trace_block(body)
        self.assertEqual(data.get("tier"), "1")


class TestTraceBlockSpan(unittest.TestCase):

    def test_good_block_returns_correct_span(self):
        body = "Some prefix\n" + _block("3", "round 2 PROCEED") + "\nSome suffix"
        start_idx = body.find(cpc.TRACE_START)
        end_idx = body.find(cpc.TRACE_END)
        span = cpc.trace_block_span(body)
        self.assertEqual(span, (start_idx, end_idx))

    def test_multiple_blocks_returns_none(self):
        body = _block("3", "PROCEED") + "\n" + _block("1", "N/A")
        self.assertIsNone(cpc.trace_block_span(body))

    def test_missing_start_returns_none(self):
        body = "tier: 1\n" + cpc.TRACE_END
        self.assertIsNone(cpc.trace_block_span(body))

    def test_missing_end_returns_none(self):
        body = cpc.TRACE_START + "\ntier: 1\n"
        self.assertIsNone(cpc.trace_block_span(body))

    def test_reversed_markers_returns_none(self):
        body = cpc.TRACE_END + "\n" + cpc.TRACE_START
        self.assertIsNone(cpc.trace_block_span(body))

    def test_none_body_returns_none(self):
        self.assertIsNone(cpc.trace_block_span(None))


# ---------------------------------------------------------------------------
# cross_check_ok  (C3 merge-eligibility)
# ---------------------------------------------------------------------------

class TestCrossCheckOk(unittest.TestCase):

    # --- converged PROCEED ---------------------------------------------------

    def test_proceed_exact(self):
        ok, _ = cpc.cross_check_ok("PROCEED")
        self.assertTrue(ok)

    def test_proceed_case_insensitive(self):
        ok, _ = cpc.cross_check_ok("Gemini returned proceed on this change")
        self.assertTrue(ok)

    def test_proceed_mixed_case(self):
        ok, _ = cpc.cross_check_ok("Proceed -- details follow")
        self.assertTrue(ok)

    def test_proceed_with_modifications_passes(self):
        """The hyphenated converged verdict must still pass (word boundary lands
        at the hyphen)."""
        ok, _ = cpc.cross_check_ok(
            "Gemini round 2 PROCEED-WITH-MODIFICATIONS H — all integrated")
        self.assertTrue(ok)

    def test_proceed_after_one_round_still_passes(self):
        """'proceed after one round' is converged-after-a-round, not a negated
        'proceed only after' condition."""
        ok, _ = cpc.cross_check_ok("converged; proceed after one round")
        self.assertTrue(ok)

    # --- tier-gated N/A exemption (governance-gap fix 2026-06-01, PR #481) -----

    def test_na_leading_tier1(self):
        ok, detail = cpc.cross_check_ok("N/A", tier="1")
        self.assertTrue(ok)
        self.assertIn("N/A", detail)

    def test_na_with_explanation_tier1(self):
        ok, _ = cpc.cross_check_ok(
            "N/A -- trivial doc fix, workflow exempt", tier="1")
        self.assertTrue(ok)

    def test_na_lowercase_tier1(self):
        ok, _ = cpc.cross_check_ok("n/a", tier="1")
        self.assertTrue(ok)

    def test_na_tier2_not_merge_eligible(self):
        ok, detail = cpc.cross_check_ok("N/A - exempt", tier="2")
        self.assertFalse(ok)
        self.assertIn("Tier 2/3", detail)

    def test_na_tier3_not_eligible_pr481_regression(self):
        """THE regression guard: a Tier-3 PR with cross_check 'N/A' must NOT be
        merge-eligible. This is exactly how PR #481 self-merged with no
        cross-check before this fix."""
        ok, detail = cpc.cross_check_ok("N/A", tier="3")
        self.assertFalse(ok)
        self.assertIn("3", detail)

    def test_na_no_tier_is_strict_not_eligible(self):
        """An undeclared/unparseable tier is fail-safe strict: N/A is rejected."""
        ok, _ = cpc.cross_check_ok("N/A - exempt")
        self.assertFalse(ok)

    def test_na_unparseable_tier_not_eligible(self):
        ok, _ = cpc.cross_check_ok("N/A", tier="banana")
        self.assertFalse(ok)

    def test_proceed_tier3_still_eligible(self):
        ok, _ = cpc.cross_check_ok("round 2 PROCEED, all integrated", tier="3")
        self.assertTrue(ok)

    def test_proceed_tier_int_arg(self):
        # tier may be passed as an int, not just a string.
        ok, _ = cpc.cross_check_ok("PROCEED", tier=3)
        self.assertTrue(ok)

    # --- deny-token / negated-proceed gate (2026-05-28 substring-bypass fix) --

    def test_reconsider_with_proceed_substring_fails(self):
        """The core bug: a RECONSIDER verdict whose prose contains 'proceed'
        must FAIL. Pre-fix, the bare substring test passed it through."""
        ok, detail = cpc.cross_check_ok(
            "VERDICT: RECONSIDER — do not proceed without fixing X")
        self.assertFalse(ok)
        self.assertIn("non-converged", detail)

    def test_reconsider_alone_fails(self):
        ok, _ = cpc.cross_check_ok("Gemini round 1 RECONSIDER")
        self.assertFalse(ok)

    def test_reconsider_mixed_case_fails(self):
        ok, _ = cpc.cross_check_ok("gemini said Reconsider, proceed only after")
        self.assertFalse(ok)

    def test_request_changes_fails(self):
        ok, _ = cpc.cross_check_ok("peer review VERDICT: REQUEST_CHANGES")
        self.assertFalse(ok)

    def test_request_changes_hyphen_fails(self):
        ok, _ = cpc.cross_check_ok("Antigravity: REQUEST-CHANGES, 2 concerns")
        self.assertFalse(ok)

    def test_needs_discussion_fails(self):
        ok, _ = cpc.cross_check_ok("NEEDS_DISCUSSION — escalate to operator")
        self.assertFalse(ok)

    def test_negated_proceed_without_deny_token_fails(self):
        """A withheld approval that doesn't use a deny token still fails."""
        ok, detail = cpc.cross_check_ok(
            "Do not proceed until the migration is validated")
        self.assertFalse(ok)
        self.assertIn("non-converged", detail)

    def test_proceed_only_after_condition_fails(self):
        ok, _ = cpc.cross_check_ok("PROCEED only after the flag is added")
        self.assertFalse(ok)

    # --- multi-round: the LAST verdict is operative --------------------------

    def test_multiround_reconsider_then_proceed_passes(self):
        """A multi-round trace that names an early RECONSIDER but converges to
        PROCEED is converged — the LAST verdict wins."""
        ok, _ = cpc.cross_check_ok(
            "round 1 RECONSIDER (2 concerns); round 2 PROCEED, both integrated")
        self.assertTrue(ok)

    def test_proceed_then_reconsider_fails(self):
        """Inverse ordering: if the operative (last) verdict is RECONSIDER, the
        earlier PROCEED does not rescue it."""
        ok, _ = cpc.cross_check_ok(
            "round 1 PROCEED; round 2 RECONSIDER after new concern surfaced")
        self.assertFalse(ok)

    # --- BLOCKED pause sentinels (auth-expiry + quota-failover) ---------------

    def test_blocked_auth_expired_fails(self):
        """auth-expiry contract: a BLOCKED cross-check pauses the PR."""
        ok, detail = cpc.cross_check_ok("BLOCKED — agy auth expired (event: 12)")
        self.assertFalse(ok)
        self.assertIn("auth", detail.lower())

    def test_blocked_quota_exhausted_paused(self):
        ok, detail = cpc.cross_check_ok(
            "BLOCKED — quota exhausted (event: 7)", tier="3")
        self.assertFalse(ok)
        self.assertIn("quota", detail.lower())
        self.assertIn("paused", detail.lower())

    def test_proceed_mentioning_blocked_quota_is_eligible(self):
        """Anchored sentinel: a converged verdict that merely MENTIONS the words
        'blocked'/'quota' must NOT be misclassified as a pause."""
        ok, _ = cpc.cross_check_ok("PROCEED — not blocked by any quota", tier="3")
        self.assertTrue(ok)

    def test_multiround_blocked_auth_then_proceed_is_eligible(self):
        """A leading non-BLOCKED value with a later PROCEED converges; the
        earlier 'BLOCKED auth' is not the operative (leading) token."""
        ok, _ = cpc.cross_check_ok(
            "round 1 BLOCKED auth; round 2 re-ran, PROCEED", tier="3")
        self.assertTrue(ok)

    # --- in-flight tokens (Phase 4 audit O10) --------------------------------

    def test_in_flight_pending(self):
        ok, detail = cpc.cross_check_ok("PENDING peer review from Antigravity")
        self.assertTrue(ok)
        self.assertIn("in-flight", detail)
        self.assertIn("PENDING", detail)

    def test_in_flight_awaiting(self):
        ok, _ = cpc.cross_check_ok("Awaiting cross-agent peer review verdict")
        self.assertTrue(ok)

    def test_in_flight_in_progress(self):
        ok, _ = cpc.cross_check_ok("Gemini round 1 IN PROGRESS")
        self.assertTrue(ok)

    def test_in_flight_in_progress_hyphenated(self):
        ok, _ = cpc.cross_check_ok("Cross-check IN-PROGRESS round 2")
        self.assertTrue(ok)

    def test_in_flight_peer_review_open(self):
        ok, _ = cpc.cross_check_ok("PEER_REVIEW_OPEN; pushed collaborative commit")
        self.assertTrue(ok)

    def test_in_flight_deferred_as_equivalent(self):
        ok, _ = cpc.cross_check_ok("deferred-as-equivalent — 5 validation passes")
        self.assertTrue(ok)

    def test_in_flight_case_insensitive(self):
        ok, _ = cpc.cross_check_ok("pending review (lowercase test)")
        self.assertTrue(ok)

    def test_pending_tier3_still_eligible_o10(self):
        """Phase-4-audit-O10 collaborative-push allowance is preserved: an
        in-flight token stays merge-eligible even at Tier 3. The governance-gap
        fix targets the N/A exemption only."""
        ok, _ = cpc.cross_check_ok("PENDING peer review", tier="3")
        self.assertTrue(ok)

    # --- empty / unrecognized -------------------------------------------------

    def test_empty_string(self):
        ok, detail = cpc.cross_check_ok("")
        self.assertFalse(ok)
        self.assertIn("empty", detail)

    def test_whitespace_only(self):
        ok, detail = cpc.cross_check_ok("   ")
        self.assertFalse(ok)
        self.assertIn("empty", detail)

    def test_none_treated_as_empty(self):
        ok, _ = cpc.cross_check_ok(None)
        self.assertFalse(ok)

    def test_unrecognized_verdict(self):
        ok, _ = cpc.cross_check_ok("Gemini raised concerns; still discussing")
        self.assertFalse(ok)

    def test_na_not_at_start_does_not_pass(self):
        # "N/A" must BEGIN the value to count as an exemption. Fixture avoids
        # in-flight tokens (PENDING/AWAITING/etc.) which would pass independently.
        ok, _ = cpc.cross_check_ok("verdict may be N/A later, gemini failed")
        self.assertFalse(ok)


# ---------------------------------------------------------------------------
# _parse_tier
# ---------------------------------------------------------------------------

class TestParseTier(unittest.TestCase):

    def test_bare_int_string(self):
        self.assertEqual(cpc._parse_tier("2"), 2)

    def test_tier_word_prefix(self):
        self.assertEqual(cpc._parse_tier("tier 3"), 3)

    def test_trailing_parenthetical(self):
        self.assertEqual(cpc._parse_tier("3 (security)"), 3)

    def test_leading_whitespace_stripped(self):
        self.assertEqual(cpc._parse_tier("  2  "), 2)

    def test_int_arg(self):
        self.assertEqual(cpc._parse_tier(3), 3)

    def test_out_of_range_int(self):
        self.assertIsNone(cpc._parse_tier(4))

    def test_none(self):
        self.assertIsNone(cpc._parse_tier(None))

    def test_unparseable(self):
        self.assertIsNone(cpc._parse_tier("banana"))


# ---------------------------------------------------------------------------
# cross_check_valid_for_tier  (trace-VALIDITY / process-honesty)
# ---------------------------------------------------------------------------

class TestCrossCheckValidForTier(unittest.TestCase):
    """The trace-VALIDITY check (CI validate-trace gate + pre-push hook).
    Distinct from cross_check_ok's merge-eligibility: a non-converged verdict is
    VALID FORM here but not merge-eligible there."""

    # --- Tier 1 is exempt -----------------------------------------------------

    def test_tier1_na_valid(self):
        ok, _ = cpc.cross_check_valid_for_tier("N/A - docs only", "1")
        self.assertTrue(ok)

    def test_tier1_any_nonempty_valid(self):
        ok, _ = cpc.cross_check_valid_for_tier("anything goes at tier 1", "1")
        self.assertTrue(ok)

    # --- Tier 2/3 reject the absence markers (THE fix) ------------------------

    def test_tier3_na_rejected(self):
        ok, reason = cpc.cross_check_valid_for_tier("N/A", "3")
        self.assertFalse(ok)
        self.assertIn("Tier 2/3", reason)

    def test_tier2_na_rejected(self):
        ok, _ = cpc.cross_check_valid_for_tier("N/A - skip", "2")
        self.assertFalse(ok)

    def test_tier3_none_rejected(self):
        ok, _ = cpc.cross_check_valid_for_tier("none", "3")
        self.assertFalse(ok)

    def test_tier3_empty_rejected(self):
        ok, reason = cpc.cross_check_valid_for_tier("", "3")
        self.assertFalse(ok)
        self.assertIn("empty", reason)

    def test_tier3_garbage_rejected(self):
        ok, _ = cpc.cross_check_valid_for_tier("we talked about it", "3")
        self.assertFalse(ok)

    # --- Tier 2/3 accept any RECOGNIZED state (verdict / in-flight / pause) ----

    def test_tier3_proceed_valid(self):
        ok, _ = cpc.cross_check_valid_for_tier("round 2 PROCEED", "3")
        self.assertTrue(ok)

    def test_tier3_proceed_with_modifications_valid(self):
        ok, _ = cpc.cross_check_valid_for_tier(
            "PROCEED-WITH-MODIFICATIONS, all integrated", "3")
        self.assertTrue(ok)

    def test_tier3_approve_valid(self):
        ok, _ = cpc.cross_check_valid_for_tier("peer review: APPROVE H", "3")
        self.assertTrue(ok)

    def test_tier3_reconsider_is_valid_form_but_not_converged(self):
        """A non-converged verdict is VALID FORM (an honest mid-cycle trace must
        not turn CI red) — even though cross_check_ok rejects it for merge."""
        ok, _ = cpc.cross_check_valid_for_tier("VERDICT: RECONSIDER", "3")
        self.assertTrue(ok)
        merge_ok, _ = cpc.cross_check_ok("VERDICT: RECONSIDER", tier="3")
        self.assertFalse(merge_ok)

    def test_tier3_request_changes_valid_form(self):
        ok, _ = cpc.cross_check_valid_for_tier("REQUEST_CHANGES, 2 concerns", "3")
        self.assertTrue(ok)

    def test_tier3_failover_valid_form(self):
        ok, _ = cpc.cross_check_valid_for_tier(
            "FAILOVER (Antigravity unresponsive 65m): Grok APPROVE + Gemini PROCEED",
            "3")
        self.assertTrue(ok)

    def test_tier3_inflight_pending_valid(self):
        ok, _ = cpc.cross_check_valid_for_tier("PENDING peer review", "3")
        self.assertTrue(ok)

    def test_tier3_inflight_deferred_as_equivalent_valid(self):
        ok, _ = cpc.cross_check_valid_for_tier("DEFERRED-AS-EQUIVALENT", "3")
        self.assertTrue(ok)

    def test_tier3_auth_blocked_valid(self):
        ok, reason = cpc.cross_check_valid_for_tier(
            "BLOCKED — auth expired (event: 12)", "3")
        self.assertTrue(ok)
        self.assertIn("pause sentinel", reason)

    def test_tier3_quota_blocked_valid(self):
        ok, reason = cpc.cross_check_valid_for_tier(
            "BLOCKED — quota exhausted (event: 7)", "3")
        self.assertTrue(ok)
        self.assertIn("pause sentinel", reason)

    # --- pause sentinel must be anchored (round-1 Mod 1) ----------------------

    def test_unanchored_blocked_quota_without_verdict_rejected(self):
        """A value that merely contains 'blocked'/'quota' mid-string, with NO
        recognized verdict, is NOT a valid pause sentinel (anchored startswith)
        and is rejected at Tier 3."""
        ok, _ = cpc.cross_check_valid_for_tier(
            "see notes; nothing is blocked and quota is fine", "3")
        self.assertFalse(ok)

    # --- unparseable tier is fail-safe strict ---------------------------------

    def test_unparseable_tier_strict_na_rejected(self):
        ok, _ = cpc.cross_check_valid_for_tier("N/A", "tier-unknown")
        self.assertFalse(ok)

    def test_unparseable_tier_strict_proceed_accepted(self):
        ok, _ = cpc.cross_check_valid_for_tier("PROCEED", "tier-unknown")
        self.assertTrue(ok)


# ---------------------------------------------------------------------------
# parse_codeowners + path_is_operator_reserved + reserved_paths
# ---------------------------------------------------------------------------

class TestParseCodeowners(unittest.TestCase):

    def test_empty_text_returns_empty(self):
        self.assertEqual(cpc.parse_codeowners(""), [])

    def test_none_text_returns_empty(self):
        self.assertEqual(cpc.parse_codeowners(None), [])

    def test_comments_and_blanks_skipped(self):
        rules = cpc.parse_codeowners("# Comment\n\n* @sumitake\n")
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0][0], "*")

    def test_inline_comment_stripped(self):
        rules = cpc.parse_codeowners("/docs/foo.md @sumitake # my note\n")
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0][0], "/docs/foo.md")
        self.assertEqual(rules[0][1], ["@sumitake"])

    def test_preserves_order(self):
        rules = cpc.parse_codeowners("* @sumitake\n/docs/foo.md @other\n")
        self.assertEqual(rules[0][0], "*")
        self.assertEqual(rules[1][0], "/docs/foo.md")

    def test_pattern_without_owner_skipped(self):
        rules = cpc.parse_codeowners("/lonely/pattern\n* @sumitake\n")
        self.assertEqual(len(rules), 1)


class TestPathIsOperatorReserved(unittest.TestCase):

    def test_catchall_star_does_not_reserve(self):
        """The repo-wide * @sumitake catch-all must NOT mark any path reserved
        (C4 _CATCHALL_PATTERNS exclusion)."""
        rules = cpc.parse_codeowners("* @sumitake\n")
        self.assertFalse(cpc.path_is_operator_reserved("README.md", rules))
        self.assertFalse(
            cpc.path_is_operator_reserved("scripts/check_pr_compliance.py", rules)
        )

    def test_catchall_doublestar_does_not_reserve(self):
        rules = cpc.parse_codeowners("** @sumitake\n")
        self.assertFalse(cpc.path_is_operator_reserved("any/file.py", rules))

    def test_specific_rule_reserves_path(self):
        rules = cpc.parse_codeowners("* @sumitake\n/docs/foo.md @sumitake\n")
        self.assertTrue(cpc.path_is_operator_reserved("docs/foo.md", rules))

    def test_unmatched_path_not_reserved(self):
        rules = cpc.parse_codeowners("/docs/foo.md @sumitake\n")
        self.assertFalse(cpc.path_is_operator_reserved("scripts/bar.py", rules))

    def test_no_rules_not_reserved(self):
        self.assertFalse(cpc.path_is_operator_reserved("README.md", []))

    def test_multi_owner_rule_not_reserved(self):
        """A rule with @sumitake plus another owner is NOT operator-only."""
        rules = cpc.parse_codeowners("/docs/foo.md @sumitake @other-reviewer\n")
        self.assertFalse(cpc.path_is_operator_reserved("docs/foo.md", rules))

    def test_last_matching_rule_wins_non_reserved(self):
        """A later specific non-reserved rule overrides an earlier reserved rule.

        /docs/ gives @sumitake (reserved), but /docs/foo.md @other appears
        later in the file and wins — last-matching-rule-wins means not reserved.
        Uses two specific rules (not a catch-all) to actually exercise precedence.
        """
        rules = cpc.parse_codeowners("/docs/ @sumitake\n/docs/foo.md @other\n")
        self.assertFalse(cpc.path_is_operator_reserved("docs/foo.md", rules))

    def test_last_matching_rule_wins_reserved(self):
        """A later @sumitake-only rule overrides an earlier @other rule."""
        rules = cpc.parse_codeowners("/docs/ @other\n/docs/foo.md @sumitake\n")
        self.assertTrue(cpc.path_is_operator_reserved("docs/foo.md", rules))


class TestReservedPaths(unittest.TestCase):

    def test_filters_operator_reserved(self):
        rules = cpc.parse_codeowners(
            "* @sumitake\n/docs/global-claude-md-canonical.md @sumitake\n"
        )
        paths = [
            "scripts/test_check_pr_compliance.py",
            "docs/global-claude-md-canonical.md",
            "CHANGELOG.md",
        ]
        result = cpc.reserved_paths(paths, rules)
        self.assertEqual(result, ["docs/global-claude-md-canonical.md"])

    def test_empty_paths_returns_empty(self):
        rules = cpc.parse_codeowners("* @sumitake\n")
        self.assertEqual(cpc.reserved_paths([], rules), [])

    def test_catchall_only_reserves_nothing(self):
        rules = cpc.parse_codeowners("* @sumitake\n")
        result = cpc.reserved_paths(["scripts/foo.py", "README.md"], rules)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# compute_verdict — full truth table
# ---------------------------------------------------------------------------

class TestComputeVerdict(unittest.TestCase):

    def test_merge_eligible_all_pass(self):
        self.assertEqual(
            cpc.compute_verdict(True, True, True, False), "MERGE-ELIGIBLE"
        )

    def test_needs_operator_c4_overrides_all_pass(self):
        self.assertEqual(
            cpc.compute_verdict(True, True, True, True), "NEEDS-OPERATOR"
        )

    def test_needs_operator_c4_overrides_c1_fail(self):
        self.assertEqual(
            cpc.compute_verdict(False, True, True, True), "NEEDS-OPERATOR"
        )

    def test_needs_operator_c4_overrides_all_fail(self):
        self.assertEqual(
            cpc.compute_verdict(False, False, False, True), "NEEDS-OPERATOR"
        )

    def test_blocked_c1_fail(self):
        self.assertEqual(
            cpc.compute_verdict(False, True, True, False), "BLOCKED"
        )

    def test_blocked_c2_fail(self):
        self.assertEqual(
            cpc.compute_verdict(True, False, True, False), "BLOCKED"
        )

    def test_blocked_c3_fail(self):
        self.assertEqual(
            cpc.compute_verdict(True, True, False, False), "BLOCKED"
        )

    def test_blocked_all_fail(self):
        self.assertEqual(
            cpc.compute_verdict(False, False, False, False), "BLOCKED"
        )


if __name__ == "__main__":
    unittest.main()
