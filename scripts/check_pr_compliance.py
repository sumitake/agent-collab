#!/usr/bin/env python3
"""Pre-self-merge compliance check for an agent-authored pull request.

The public governance contract in AGENTS.md lets an AI agent
merge its own PR ONCE four preconditions hold:
  1. the Project Decision Workflow positively converged (an independent
     Gemini cross-check returned PROCEED);
  2. required CI is green;
  3. the change is recorded -- the cross-check verdict is quoted in the PR;
  4. the change is not operator-reserved (touches no file governed by an
     operator-only CODEOWNERS rule, e.g. docs/global-claude-md-canonical.md).
The operator retains final say.

This tool is what an agent runs locally BEFORE clicking merge. It mechanically
checks the FORM and PRESENCE of the directive-#6 evidence -- it does NOT and
cannot verify the SUBSTANCE (that the PROCEED was genuine, that re-consultation
fired on a material plan change). Directive #6's anti-self-dealing clause
governs substance at the judgment layer; this tool is the form check beneath it.

  python3 scripts/check_pr_compliance.py <pr-number> --repo <owner/repo>

Four checks:
  C1  CI green             -- every reported check is pass/skipping
  C2  trace block present  -- a well-formed compliance-trace block in the body,
                             AND its cross_check value is valid for the declared
                             tier (Tier 2/3 may not record a bare 'N/A')
  C3  cross-check recorded -- the trace's cross_check value is merge-eligible: a
                             converged PROCEED, or an 'N/A' exemption only at
                             Tier 1 (a paused BLOCKED sentinel is valid but not
                             merge-eligible)
  C4  operator-reserved    -- no changed file falls under a *specific*
                             operator-only CODEOWNERS rule (the repo-wide
                             `*`/`**` catch-all is the default owner, not a
                             reservation, and is excluded)

Verdict:
  MERGE-ELIGIBLE   C1+C2+C3 pass and C4 is not reserved
  NEEDS-OPERATOR   C4 is reserved (overrides -- the operator must merge)
  BLOCKED          otherwise

Exit: 0 = MERGE-ELIGIBLE, 1 = anything else.

Stdlib-only by design (runs on a bare macOS python3 with no pip install); the
only external dependency is the `gh` CLI, used through thin wrappers so the
parsing/decision logic stays pure and unit-testable.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import fnmatch
import json
import re
import subprocess
import sys
import unicodedata

# --- the compliance-trace block contract ------------------------------------
#
# KEEP IN SYNC: the next three constants are inlined into this repository's
# `.github/workflows/compliance-trace.yml`. The public prose contract lives in
# `docs/public-governance.md`. Change both local implementations together so
# CI and the pre-merge check cannot disagree.

TRACE_START = "<!-- compliance-trace:start -->"
TRACE_END = "<!-- compliance-trace:end -->"
REQUIRED_KEYS = (
    "author",
    "standing_directives",
    "tier",  # Phase 4c-1 (2026-05-25): formal Tier 1/2/3 declaration required.
             # Mirror in .github/workflows/compliance-trace.yml. Without this,
             # the classifier (scripts/classify_pr_tier.py) couldn't gate on
             # under-declaration; agents could omit the key to bypass.
    "cross_check",
    "post_condition",
    "mcp_coverage_gap",
    "operator_reserved",
)

# CI conclusions that count as "not blocking a merge".
_CI_OK = frozenset({"pass", "skipping"})

# CODEOWNERS owner list that marks a rule operator-only.
_OPERATOR_ONLY_OWNERS = ("@sumitake",)

# CODEOWNERS repo-wide catch-all patterns. A catch-all names the DEFAULT
# owner, not an operator *reservation* -- every repo has one, and with a
# single-identity CODEOWNERS (`* @sumitake`) treating it as a reservation
# would flag every file in the repo. Only a more-specific operator-only rule
# reserves a path (directive #6 precondition 4). C4 excludes these.
_CATCHALL_PATTERNS = frozenset({"*", "**"})

# CODEOWNERS filenames GitHub recognises, in the order it searches them.
_CODEOWNERS_PATHS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")


# --- pure helper: locate THE one line-anchored compliance-trace block --------

def _anchored_block_span(body: str):
    """Locate the single LINE-ANCHORED compliance-trace block in `body`.

    Returns (span, error):
      span  -- (start_off, end_off) byte offsets of the block's TRACE_START and
               TRACE_END markers, or None when there is no usable single block.
      error -- a human-readable diagnostic, or None when `span` is set.

    A marker is *line-anchored* -- a real block boundary, not a prose reference --
    when its line, stripped of surrounding whitespace, STARTS WITH the marker. A
    mid-line or backtick-wrapped mention (e.g. the PR template's own quoted example
    `<!-- compliance-trace:start --> ... <!-- compliance-trace:end -->`) is NOT a
    boundary, so it is ignored. EVERY own-line marker is counted, which is what
    closes the laundering vector this guards (Grok D2 review of PR #760, deferred
    there): a body with TWO complete blocks -- the human reads the first (visible),
    while `body.rfind` made the SECOND (e.g. concealed in a collapsed <details>
    after it) the operative parsed trace, feeding different key/values to the gate
    than a reviewer reads.

      - exactly one anchored start-line AND one anchored end-line, start before end,
        neither line carrying a second marker  -> that span is the block.
      - >=2 anchored starts, >=2 anchored ends, OR any anchored line bearing a second
        marker substring (a single-line multi-block shape)  -> rejected as
        multiple/stray blocks. This covers the operator's ">=2 complete blocks"
        case AND the unclosed-visible-start + single-line-double evasions a naive
        complete-pair counter would miss (Gemini round-2 cross-check).
      - 0 starts -> missing start (short-circuits even if 0 ends); 0 ends after seeing a start -> missing end; end before start -> reversed.

    KNOWN RESIDUAL (operator-scoped): a BARE, non-backtick mid-line marker sequence
    renders visible to a human yet is non-anchored, so a single hidden own-line block
    plus a visible bare-mid-line decoy is not caught here. Closing it needs inline-
    code-span-aware rendering to tell a backtick-wrapped mention (legit -- the PR
    template relies on it) from a bare one (decoy) -- a larger, separate hardening
    with its own bypass surface, out of this guard's "tolerate prose/backtick
    mentions" scope. A tier / peer-review downgrade laundered that way is still
    caught by classify_pr_tier (changed-files tier challenge) + check_pr_phase1_
    extension (Tier-3 peer review). (Gemini round-2/3 cross-check; Grok D2 review.)
    """
    starts: list[int] = []
    ends: list[int] = []
    stray = False
    pos = 0
    for raw in body.splitlines(keepends=True):
        stripped = raw.strip()
        off = pos + (len(raw) - len(raw.lstrip()))
        pos += len(raw)
        is_start = stripped.startswith(TRACE_START)
        is_end = stripped.startswith(TRACE_END)
        if not (is_start or is_end):
            continue
        # A second marker substring on ONE anchored line is a single-line
        # multi-block shape ("<!-- ..start -->k<!-- ..end --><!-- ..start -->..");
        # treat it as a stray/extra marker so it can't smuggle a hidden pair.
        if stripped.count(TRACE_START) + stripped.count(TRACE_END) > 1:
            stray = True
        (starts if is_start else ends).append(off)
    if stray or len(starts) > 1 or len(ends) > 1:
        return None, (
            "multiple compliance-trace blocks (or stray markers) found -- exactly "
            "one block is allowed; a concealed second block or stray marker can "
            "launder different key/values past this gate than a reviewer reads in "
            "the first")
    if not starts:
        return None, f"missing start marker '{TRACE_START}'"
    if not ends:
        return None, f"missing end marker '{TRACE_END}'"
    if ends[0] < starts[0]:
        return None, "end marker appears before start marker"
    return (starts[0], ends[0]), None


def trace_block_span(body):
    """Public single-source-of-truth for "where is the one compliance-trace block".

    Returns the (start_off, end_off) byte offsets of the single LINE-ANCHORED
    block, or None when the body has no usable single block (0 blocks, OR the
    >=2 / stray-marker multi-block laundering shape). Callers that only need the
    block's LOCATION -- to slice it out, or scan inside it -- use this instead of
    a private `rfind` copy, so they cannot drift from parse_trace_block's
    selection (the PR-#760 multi-block guard). For full key parsing use
    parse_trace_block. Fail-closed: a malformed/multi-block body yields None, so a
    caller never honors a declaration concealed in a second/stray block.
    """
    if body is None:
        return None
    span, _err = _anchored_block_span(body)
    return span


# --- pure function (a): parse the trace block from a PR body string ----------

def parse_trace_block(body: str):
    """Parse the compliance-trace block out of a PR body.

    Returns (data, errors):
      data   -- dict of key->value for every well-formed `key: value` line
                between the markers (empty dict if the block is unusable).
      errors -- list of human-readable problems; empty list == well-formed.

    A block is well-formed when: exactly one line-anchored start/end marker pair
    is present (start before end) -- a second complete block (or a stray marker)
    is rejected as a laundering vector (see _anchored_block_span) -- and every
    REQUIRED_KEYS key appears with a non-empty value.
    """
    errors: list[str] = []
    if body is None:
        return {}, ["PR body is empty -- no compliance-trace block"]

    # Select the block from LINE-ANCHORED markers (a marker line whose strip()
    # STARTS WITH the marker), not raw rfind. rfind honored a marker substring
    # ANYWHERE -- including a prefixed/mid-line one a human reads as prose -- and
    # picked the LAST, so a concealed second block (e.g. in a collapsed <details>
    # after the visible one) became the operative trace while a reviewer read the
    # first: the PR-#760 laundering vector. _anchored_block_span counts every
    # own-line marker, rejecting >=2 blocks (or a stray marker) and always parsing
    # the single line-anchored block; a mid-line / backtick mention stays ignored.
    span, span_error = _anchored_block_span(body)
    if span_error:
        return {}, [span_error]
    start, end = span

    inner = body[start + len(TRACE_START):end]
    data: dict[str, str] = {}
    for line in inner.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("<!--") or raw.startswith("#") or ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        # Normalize the key: drop every whitespace (Z*) and control/format (C*) character
        # -- including zero-width U+200B / U+FEFF / NBSP -- and lowercase, so visually-
        # identical decoy keys ('Tier', a zero-width-injected 'tier', 'tier ') ALL collapse
        # to one canonical key and cannot slip a duplicate past the guard below. Makes
        # REQUIRED_KEYS matching case/format-robust; legit keys are [a-z0-9_]+ and survive
        # unchanged. Every consumer reads lowercase keys (REQUIRED_KEYS, cross_check_valid_
        # for_tier, the phase-1 trace.get(...) calls), so this is consumer-safe (Gemini
        # Step-2 cross-check concern 1 + Grok D2 concern 2).
        key = "".join(c for c in key if unicodedata.category(c)[0] not in ("C", "Z")).lower()
        value = value.strip()
        if key:
            # Duplicate-key guard (governance bypass fix, 2026-06-04): the parse is
            # last-wins, so a repeated key silently overrides its first (operative)
            # value -- e.g. `tier: 3` followed by `tier: 1` makes the operative tier 1,
            # letting a Tier-3 change launder a lower-tier exemption (an `N/A` cross_check)
            # past validate-trace while a human reviewer sees the first, higher line. A
            # well-formed compliance-trace block never repeats a key, so any duplicate is
            # rejected (discovered by the gate-attack corpus recon).
            if key in data:
                errors.append(
                    f"duplicate key '{key}' in compliance-trace block -- a repeated "
                    f"key silently overrides via last-wins; each key must appear at "
                    f"most once")
                # Keep the FIRST (operative, human-visible) value; do NOT last-wins
                # override, so a consumer that forgets to halt on `errors` still can't be
                # laundered to the lower value (defense-in-depth; Gemini Step-2 concern 2).
                continue
            data[key] = value

    for key in REQUIRED_KEYS:
        if key not in data:
            errors.append(f"missing required key '{key}'")
        elif not data[key]:
            errors.append(f"required key '{key}' has an empty value")

    # Tier-aware cross_check CONTENT validation (governance-gap fix 2026-06-01,
    # PR #481 post-mortem): a Tier-2/3 PR must record a real cross-check verdict
    # (or an in-flight / codified-pause state) — 'N/A' is only valid at Tier 1.
    # `cross_check_valid_for_tier` is defined below (forward reference, resolved
    # at call time). Only run it when both keys are populated so we don't
    # double-report a missing/empty key already flagged by the loop above.
    if data.get("tier") and data.get("cross_check"):
        cc_ok, cc_reason = cross_check_valid_for_tier(
            data["cross_check"], data["tier"])
        if not cc_ok:
            errors.append(cc_reason)
    return data, errors


# --- pure function (b): C3 verdict logic on a cross_check string -------------

# Phase 4 audit O10 (2026-05-25): in-flight cross-check states. When a
# cross-agent reviewer pushes a collaborative commit to the author's branch
# DURING peer review (before the verdict is integrated into the trace), the
# cross_check field may legitimately say "PENDING" / "IN PROGRESS" /
# "AWAITING-REVIEW". Such pushes shouldn't be blocked — the in-flight state
# is part of the convergence cycle. Per Antigravity Phase 4 audit msg
# 7dd113c5 finding B1: "Pre-push hook blocked our direct pushes because the
# cross_check field on GitHub was not yet a PROCEED. Bypassing via
# --no-verify was necessary."
#
# Recognized in-flight tokens (case-insensitive prefix or contains):
_IN_FLIGHT_TOKENS = ("PENDING", "AWAITING", "IN PROGRESS", "IN-PROGRESS",
                     "PEER_REVIEW_OPEN", "AWAITING-REVIEW", "DEFERRED-AS-EQUIVALENT")

# Explicit non-converged verdicts (the "deny" signal).
_DENY_TOKEN_RE = re.compile(
    r"\b(RECONSIDER|REQUEST[_\- ]CHANGES|NEEDS[_\- ]DISCUSSION)\b", re.IGNORECASE)

# A 'proceed' bound to a negation or an unmet condition is NOT an accept — it
# is itself a deny signal (e.g. "do not proceed", "proceed only after X").
_NEGATED_PROCEED_RE = re.compile(
    r"\b(?:DO\s+NOT|DOES\s+NOT|DO\s*N'?T|CAN\s*NOT|CANNOT|WILL\s+NOT|"
    r"SHOULD\s+NOT|NOT)\s+PROCEED\b"
    r"|\bPROCEED\s+ONLY\s+(?:AFTER|IF|WHEN|ONCE)\b", re.IGNORECASE)

# A bare, un-negated PROCEED (the "accept" signal). Covers
# PROCEED-WITH-MODIFICATIONS (word boundary lands at the hyphen).
_PROCEED_RE = re.compile(r"\bPROCEED\b", re.IGNORECASE)

# Any RECOGNIZED cross-check verdict token (converged OR not). Used by the
# tier-aware trace-VALIDITY check (cross_check_valid_for_tier) to decide whether
# a Tier-2/3 value ENGAGES the cross-check requirement vs DECLINES it ('N/A').
# This is deliberately broader than the accept/deny split above: RECONSIDER /
# REQUEST_CHANGES are non-converged but are still a real recorded verdict, so an
# honest mid-cycle trace must validate (CI must not go red on it). Whether the
# verdict is merge-eligible is cross_check_ok's separate, stricter question.
_RECOGNIZED_VERDICT_RE = re.compile(
    r"\b(PROCEED|APPROVE|RECONSIDER|REQUEST[_\- ]CHANGES|"
    r"NEEDS[_\- ]DISCUSSION|FAILOVER)\b", re.IGNORECASE)


def _parse_tier(tier_raw):
    """Extract the declared tier integer (1/2/3) from a raw `tier:` value.

    Mirrors `check_pr_phase1_extension.trace_declares_tier_3`'s regex so the two
    governance checkers read a `tier:` value identically. Accepts a raw string
    ("2", "tier 3", "3 (security)") or an int. Returns 1/2/3, or None when the
    value names no recognizable tier (an undeclared/unparseable tier is treated
    as None → fail-safe strict by every caller).
    """
    if tier_raw is None:
        return None
    if isinstance(tier_raw, int):
        return tier_raw if tier_raw in (1, 2, 3) else None
    m = re.match(r"^(?:tier\s+)?([123])\b", str(tier_raw).strip(), re.IGNORECASE)
    return int(m.group(1)) if m else None


def _is_pause_sentinel(value_upper: str) -> bool:
    """True if an already-upper-cased, stripped value is a codified pause/blocked
    sentinel: it must START WITH 'BLOCKED' and name a recognized pause reason
    ('AUTH' for the auth-expiry fallback contract, 'QUOTA' for the quota-failover
    fallback contract). Anchoring to `startswith` (per the round-1 cross-check) is
    load-bearing: an unanchored substring test would misclassify a converged
    verdict that merely mentions the words (e.g. "PROCEED — not blocked by quota",
    or "round 1 BLOCKED auth; round 2 PROCEED") as a pause and wrongly withhold a
    merge."""
    return value_upper.startswith("BLOCKED") and (
        "AUTH" in value_upper or "QUOTA" in value_upper)


def _last_deny_signal(value: str):
    """Return (pos, label) of the LAST deny signal (deny-token or negated
    proceed) in `value`, or (None, None) if there is none."""
    last_pos, last_label = None, None
    for m in _DENY_TOKEN_RE.finditer(value):
        if last_pos is None or m.start() > last_pos:
            last_pos, last_label = m.start(), m.group(1).upper()
    for m in _NEGATED_PROCEED_RE.finditer(value):
        if last_pos is None or m.start() > last_pos:
            last_pos, last_label = m.start(), "negated-proceed"
    return last_pos, last_label


def _last_accept_signal(value: str):
    """Return the position of the LAST bare PROCEED that is not part of a
    negated-proceed phrase, or None."""
    negated_spans = [m.span() for m in _NEGATED_PROCEED_RE.finditer(value)]
    last = None
    for m in _PROCEED_RE.finditer(value):
        if any(s <= m.start() < e for s, e in negated_spans):
            continue
        if last is None or m.start() > last:
            last = m.start()
    return last


def cross_check_ok(cross_check: str, tier=None):
    """Decide whether a `cross_check` trace value satisfies directive-#6 #3.

    Returns (ok, detail). `tier` is the raw `tier:` trace value (string or int);
    it gates the N/A exemption — see step 2.

    The load-bearing fix (2026-05-28): the verdict that appears LAST in the
    value is the operative one. This both closes the pre-fix bug (a bare
    `"proceed" in value` substring test passed "RECONSIDER — do not proceed")
    AND avoids the inverse false-reject (a legitimate multi-round trace such as
    "round 1 RECONSIDER → round 2 PROCEED" must still converge — a false
    reject would force a --no-verify bypass, the exact anti-pattern the
    in-flight tokens were added to prevent).

      1. FAIL on empty value.
      2. The 'N/A' exemption is tier-gated (governance-gap fix 2026-06-01,
         PR #481): PASS on an 'N/A' prefix ONLY at Tier 1 (docs/cosmetic — no
         cross-check required). On Tier 2/3, or an undeclared/unparseable tier
         (fail-safe strict), an 'N/A' is an illegitimate exemption claim → FAIL.
         Before this fix, 'N/A' passed at every tier — that is how Tier-3 PR
         #481 self-merged with no cross-check.
      3. FAIL on a BLOCKED-auth-expired OR BLOCKED-quota-exhausted value — the
         PR is correctly paused per the directive-#6 auth-expiry / quota-failover
         fallback contracts. Anchored to a leading 'BLOCKED' (see
         `_is_pause_sentinel`) so a converged verdict that merely mentions the
         words is not misclassified as a pause.
      4. Compare the LAST accept signal (a bare, un-negated PROCEED — covers
         PROCEED-WITH-MODIFICATIONS) against the LAST deny signal (RECONSIDER /
         REQUEST_CHANGES / NEEDS_DISCUSSION, or a negated proceed like
         "do not proceed" / "proceed only after X"):
           - accept present and later than any deny → PASS (converged).
           - otherwise, if a deny is present → FAIL (operative verdict
             non-converged).
      5. PASS on an in-flight token (PENDING / AWAITING / IN PROGRESS /
         PEER_REVIEW_OPEN / DEFERRED-AS-EQUIVALENT) — legitimately in-progress
         (Phase 4 audit O10; supports collaborative pushes during peer review
         without a --no-verify bypass).
      6. FAIL otherwise (unrecognised).
    """
    if not cross_check or not cross_check.strip():
        return False, "cross_check value is empty"
    value = cross_check.strip()
    value_upper = value.upper()
    tier_int = _parse_tier(tier)

    if value_upper.startswith("N/A"):
        if tier_int == 1:
            return True, "cross_check declares the change workflow-exempt (N/A; tier 1)"
        return False, (
            f"cross_check is 'N/A' but tier is "
            f"{tier_int if tier_int else 'undeclared/unparseable'} — Tier 2/3 "
            f"require a real cross-check verdict, not an N/A exemption "
            f"(governance-gap fix 2026-06-01)")

    # auth-expiry + quota-failover fallback contracts: a BLOCKED cross-check
    # pauses the PR (awaiting operator). Anchored to a leading 'BLOCKED'.
    if _is_pause_sentinel(value_upper):
        if "AUTH" in value_upper:
            reason, contract = "auth expired", "auth-expiry"
        else:
            reason, contract = "quota exhausted", "quota-failover"
        return False, (f"cross_check is BLOCKED ({reason}); PR correctly paused "
                       f"per the directive-#6 {contract} fallback contract")

    deny_pos, deny_label = _last_deny_signal(value)
    accept_pos = _last_accept_signal(value)

    if accept_pos is not None and (deny_pos is None or accept_pos > deny_pos):
        return True, "cross_check records a converged PROCEED verdict"
    if deny_pos is not None:
        return False, (f"cross_check's operative verdict is non-converged "
                       f"({deny_label}); directive-#6 self-merge gate not "
                       f"satisfied")

    # Phase 4 audit O10: accept in-flight states for collaborative pushes
    for token in _IN_FLIGHT_TOKENS:
        if token in value_upper:
            return True, (f"cross_check is in-flight ({token}); collaborative "
                          f"push allowed per Phase 4 audit O10")
    return False, ("cross_check records neither a PROCEED verdict, an "
                   "N/A exemption, nor an in-flight token (PENDING / "
                   "AWAITING / IN PROGRESS / PEER_REVIEW_OPEN / "
                   "DEFERRED-AS-EQUIVALENT)")


# --- pure function (b'): tier-aware trace-VALIDITY of a cross_check value -----

def cross_check_valid_for_tier(cross_check: str, tier_raw):
    """Is a `cross_check` trace value VALID FORM for the declared tier?

    This is the trace-VALIDITY (process-honesty) check the CI validate-trace gate
    and the pre-push hook enforce — distinct from `cross_check_ok`'s
    merge-ELIGIBILITY check. It answers "did this PR ENGAGE the cross-check its
    tier demands?", NOT "did the cross-check converge?". A non-converged verdict
    (RECONSIDER) is therefore VALID here but NOT merge-eligible there.

    Returns (ok, reason).

      - Tier 1 (docs/cosmetic): no cross-check required — any non-empty value is
        valid (the norm is 'N/A').
      - Tier 2 / Tier 3 / undeclared-or-unparseable tier (fail-safe strict): the
        value must record a recognized cross-check STATE — a verdict (PROCEED /
        APPROVE / RECONSIDER / REQUEST_CHANGES / NEEDS_DISCUSSION / FAILOVER), an
        in-flight token (PENDING / AWAITING / IN PROGRESS / PEER_REVIEW_OPEN /
        AWAITING-REVIEW / DEFERRED-AS-EQUIVALENT), or a codified pause sentinel (a
        leading 'BLOCKED' naming AUTH or QUOTA). A bare 'N/A' / 'none' / empty /
        unrecognized value is REJECTED: Tier 2/3 may not DECLINE the cross-check.

    Governance-gap fix (2026-06-01): before this check, a Tier-3 PR could merge
    with cross_check 'N/A' because the validate-trace gate only verified the key
    was present and non-empty (PR #481). This is the trace-CONTENT analogue of the
    gate exit-propagation fix in PR #475.

    KEEP IN SYNC: an equivalent inline implementation lives in
    `.github/workflows/compliance-trace.yml`. Change both together.
    """
    value = (cross_check or "").strip()
    if not value:
        return False, "cross_check value is empty"
    tier_int = _parse_tier(tier_raw)

    if tier_int == 1:
        return True, "tier 1 — cross-check not required (any non-empty value valid)"

    # Tier 2 / 3 / unknown → require a recognized cross-check state.
    value_upper = value.upper()
    if _RECOGNIZED_VERDICT_RE.search(value):
        return True, "cross_check records a recognized verdict"
    if any(token in value_upper for token in _IN_FLIGHT_TOKENS):
        return True, "cross_check records an in-flight cross-check state"
    if _is_pause_sentinel(value_upper):
        return True, "cross_check records a codified BLOCKED pause sentinel (auth/quota)"

    tier_label = f"tier {tier_int}" if tier_int else "an undeclared/unparseable tier"
    return False, (
        f"cross_check '{value[:40]}' is not valid for {tier_label}: Tier 2/3 "
        f"require a real cross-check verdict (PROCEED / PROCEED-WITH-MODIFICATIONS "
        f"/ APPROVE / ...), an in-flight state, or a codified BLOCKED pause "
        f"sentinel — 'N/A' / 'none' / empty is only valid at Tier 1")


# --- pure function (c): parse CODEOWNERS text into rules ---------------------

def parse_codeowners(text: str):
    """Parse CODEOWNERS text into an ordered list of (pattern, owners) rules.

    Comments (#...) and blank lines are skipped. Each rule is
    (pattern:str, owners:list[str]); file order is preserved because
    CODEOWNERS precedence is last-matching-rule-wins.
    """
    rules: list[tuple[str, list[str]]] = []
    if not text:
        return rules
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # An inline '#' starts a comment on an otherwise valid rule line.
        if "#" in line:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
        parts = line.split()
        if len(parts) < 2:
            continue  # a pattern with no owner is not an enforceable rule
        pattern, owners = parts[0], parts[1:]
        rules.append((pattern, owners))
    return rules


def _pattern_matches(pattern: str, path: str) -> bool:
    """gitignore-style match of a single CODEOWNERS pattern against a path.

    `path` is a repo-root-relative POSIX path with no leading slash.
    Supports: a leading '/' anchoring to the repo root; a trailing '/'
    matching a directory and everything under it; bare names matching at
    any depth; and fnmatch wildcards inside a segment.
    """
    path = path.lstrip("/")
    pat = pattern

    # A trailing-slash pattern matches the directory's whole subtree.
    dir_only = pat.endswith("/")
    if dir_only:
        pat = pat.rstrip("/")

    anchored = pat.startswith("/")
    if anchored:
        pat = pat.lstrip("/")

    if dir_only:
        # 'docs/' -> match 'docs/anything'; '/docs/' -> anchored the same way
        # (a directory pattern has no files of its own to match).
        if anchored:
            return path == pat or path.startswith(pat + "/")
        # Unanchored directory: the directory name may sit at any depth.
        if path == pat or path.startswith(pat + "/"):
            return True
        return any(
            seg == pat for seg in path.split("/")[:-1]
        ) and ("/" + pat + "/") in ("/" + path)

    if anchored:
        # Anchored file/glob pattern: match from the repo root only.
        if fnmatch.fnmatch(path, pat):
            return True
        # An anchored directory-name pattern (no trailing slash) also covers
        # everything beneath it, mirroring git's behaviour for '/dir'.
        return fnmatch.fnmatch(path, pat + "/*")

    # Unanchored pattern: match the full path, or any path segment, or the
    # subtree under a directory segment.
    if fnmatch.fnmatch(path, pat):
        return True
    if fnmatch.fnmatch(path, "*/" + pat):
        return True
    return fnmatch.fnmatch(path, pat + "/*") or fnmatch.fnmatch(path, "*/" + pat + "/*")


# --- pure function (d): match a path against rules -> operator-reserved bool -

def path_is_operator_reserved(path: str, rules):
    """Is `path`'s effective CODEOWNERS rule an operator-only reservation?

    Applies last-matching-rule-wins precedence, but EXCLUDING the repo-wide
    catch-all patterns (`*`, `**`): a catch-all names the default owner, not
    an operator reservation -- treating it as one would flag every file under
    a single-identity CODEOWNERS. A path is operator-reserved only when its
    last-matching *specific* (non-catch-all) rule is owned solely by the
    operator. A path whose only match is the catch-all -- or which matches no
    rule at all -- is not operator-reserved (returns False).
    """
    effective = None
    for pattern, owners in rules:
        if pattern in _CATCHALL_PATTERNS:
            continue  # the default-owner catch-all is never a reservation
        if _pattern_matches(pattern, path):
            effective = owners
    if effective is None:
        return False
    return tuple(effective) == _OPERATOR_ONLY_OWNERS


def reserved_paths(paths, rules):
    """Subset of `paths` whose effective CODEOWNERS rule is operator-only."""
    return [p for p in paths if path_is_operator_reserved(p, rules)]


# --- pure function (e): compute the overall verdict --------------------------

def compute_verdict(c1_ok: bool, c2_ok: bool, c3_ok: bool, c4_reserved: bool):
    """Fold the four check results into the directive-#6 verdict.

      NEEDS-OPERATOR  C4 reserved (overrides everything -- operator must merge)
      MERGE-ELIGIBLE  C1, C2, C3 all pass and C4 not reserved
      BLOCKED         otherwise
    """
    if c4_reserved:
        return "NEEDS-OPERATOR"
    if c1_ok and c2_ok and c3_ok:
        return "MERGE-ELIGIBLE"
    return "BLOCKED"


# --- thin gh-calling wrappers ------------------------------------------------

class GhError(RuntimeError):
    """A `gh` invocation failed in a way the caller should surface, not crash."""


def _run_gh(args, repo: str):
    """Run `gh <args>` and return stdout; raise GhError on failure.

    `gh` is not given --repo automatically -- each caller passes it in args
    where the subcommand supports it (so this stays a generic runner).
    """
    try:
        proc = subprocess.run(
            ["gh", *args],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError as exc:
        raise GhError("the 'gh' CLI is not installed or not on PATH") from exc
    except subprocess.SubprocessError as exc:
        raise GhError(f"'gh {' '.join(args)}' failed to run: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise GhError(f"'gh {' '.join(args)}' exited {proc.returncode}: {detail}")
    return proc.stdout


def check_ci(pr: str, repo: str):
    """C1 -- every reported CI check is pass/skipping.

    Returns (ok, detail). `gh pr checks` exits non-zero when a check has
    failed; that is a legitimate FAIL, not a tool error, so a non-zero exit
    is parsed rather than raised. A genuine "no checks at all" is a FAIL
    (directive #6 requires required CI to be GREEN, and absent != green).
    """
    try:
        proc = subprocess.run(
            ["gh", "pr", "checks", pr, "--repo", repo],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        return False, "the 'gh' CLI is not installed or not on PATH"
    except subprocess.SubprocessError as exc:
        return False, f"'gh pr checks' failed to run: {exc}"

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    combined = "\n".join(p for p in (out, err) if p)

    if "no checks reported" in combined.lower():
        return False, "no CI checks reported on this PR -- cannot confirm green"

    statuses: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        statuses.append(cols[1].strip().lower())

    if not statuses:
        if proc.returncode != 0:
            return False, f"'gh pr checks' exited {proc.returncode}: {err or out}"
        return False, "no CI checks reported on this PR -- cannot confirm green"

    bad = sorted({s for s in statuses if s not in _CI_OK})
    if bad:
        return False, (f"{len(bad)} non-green check state(s): {', '.join(bad)} "
                       f"(of {len(statuses)} check(s))")
    return True, f"all {len(statuses)} CI check(s) pass/skipping"


def fetch_pr_body(pr: str, repo: str):
    """Fetch the PR body text via `gh pr view`."""
    out = _run_gh(["pr", "view", pr, "--repo", repo, "--json", "body",
                   "--jq", ".body"], repo)
    return out.rstrip("\n")


def fetch_changed_files(pr: str, repo: str):
    """Fetch the PR's changed-file paths via `gh pr view`."""
    out = _run_gh(["pr", "view", pr, "--repo", repo, "--json", "files",
                   "--jq", ".files[].path"], repo)
    return [line.strip() for line in out.splitlines() if line.strip()]


def fetch_codeowners(repo: str, ref: str = "main"):
    """Fetch CODEOWNERS text from `ref`, trying each recognised location.

    Returns (text, source_path). text is None if no CODEOWNERS file exists
    at any recognised path on `ref`.
    """
    for path in _CODEOWNERS_PATHS:
        try:
            # The ref MUST be a query-string parameter: `gh api -f ref=main`
            # sends it as a form field, which promotes the request to a POST
            # and 404s. The Contents API needs `?ref=` on the URL.
            raw = _run_gh(
                ["api", f"repos/{repo}/contents/{path}?ref={ref}",
                 "--jq", ".content"],
                repo,
            ).strip()
        except GhError:
            continue  # 404 / not found at this path -- try the next
        if not raw:
            continue
        try:
            text = base64.b64decode(raw).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        return text, path
    return None, None


# --- orchestration -----------------------------------------------------------

def run(pr: str, repo: str):
    """Run all four checks and return (verdict, lines) for printing."""
    lines: list[str] = []
    lines.append("=" * 68)
    lines.append(f"PR compliance check (directive #6)  --  {repo} #{pr}")
    lines.append("=" * 68)

    # --- C1: CI green --------------------------------------------------------
    c1_ok, c1_detail = check_ci(pr, repo)
    lines.append(f"C1  CI green             [{'PASS' if c1_ok else 'FAIL'}]  {c1_detail}")

    # --- C2: trace block present & well-formed -------------------------------
    body = None
    body_error = None
    try:
        body = fetch_pr_body(pr, repo)
    except GhError as exc:
        body_error = str(exc)

    if body_error is not None:
        c2_ok = False
        trace = {}
        c2_detail = f"could not fetch PR body: {body_error}"
    else:
        trace, trace_errors = parse_trace_block(body)
        c2_ok = not trace_errors
        if c2_ok:
            c2_detail = (f"well-formed block: all {len(REQUIRED_KEYS)} required "
                         f"keys present and non-empty")
        else:
            c2_detail = "; ".join(trace_errors)
    lines.append(f"C2  trace block present  [{'PASS' if c2_ok else 'FAIL'}]  {c2_detail}")

    # --- C3: cross-check verdict recorded ------------------------------------
    if c2_ok and "cross_check" in trace:
        c3_ok, c3_detail = cross_check_ok(trace["cross_check"], tier=trace.get("tier"))
    elif body_error is not None:
        c3_ok, c3_detail = False, "cannot evaluate -- PR body unavailable"
    else:
        c3_ok, c3_detail = False, "cannot evaluate -- no well-formed trace block"
    lines.append(f"C3  cross-check recorded [{'PASS' if c3_ok else 'FAIL'}]  {c3_detail}")

    # --- C4: operator-reserved paths -----------------------------------------
    c4_reserved = False
    try:
        changed = fetch_changed_files(pr, repo)
        owners_text, owners_src = fetch_codeowners(repo, "main")
        if owners_text is None:
            c4_detail = ("no CODEOWNERS file on main -- no operator-reserved "
                         "paths possible")
        else:
            rules = parse_codeowners(owners_text)
            hits = reserved_paths(changed, rules)
            if hits:
                c4_reserved = True
                shown = ", ".join(hits[:5])
                more = "" if len(hits) <= 5 else f" (+{len(hits) - 5} more)"
                c4_detail = (f"{len(hits)} operator-reserved file(s) per "
                             f"{owners_src}: {shown}{more}")
            else:
                c4_detail = (f"none of {len(changed)} changed file(s) is "
                             f"operator-reserved (per {owners_src})")
    except GhError as exc:
        c4_detail = f"could not evaluate (treated as not reserved): {exc}"
    status = "RESERVED" if c4_reserved else "clear"
    lines.append(f"C4  operator-reserved    [{status}]  {c4_detail}")

    # --- verdict -------------------------------------------------------------
    verdict = compute_verdict(c1_ok, c2_ok, c3_ok, c4_reserved)
    lines.append("-" * 68)
    lines.append(f"VERDICT: {verdict}")
    if verdict == "MERGE-ELIGIBLE":
        lines.append("  C1+C2+C3 pass and no operator-reserved paths -- the "
                      "form checks for")
        lines.append("  agent self-merge under directive #6 are satisfied.")
    elif verdict == "NEEDS-OPERATOR":
        lines.append("  This PR changes an operator-reserved file (operator-only "
                      "CODEOWNERS")
        lines.append("  rule). Directive #6 precondition 4 fails -- the operator "
                      "must merge.")
    else:
        lines.append("  One or more of C1/C2/C3 did not pass -- not eligible for "
                      "agent self-merge.")

    # --- honest limitation ---------------------------------------------------
    lines.append("-" * 68)
    lines.append("LIMITATION: this trace verifies the FORM and PRESENCE of "
                 "directive-#6")
    lines.append("  compliance evidence -- NOT its SUBSTANCE. It does not and "
                 "cannot confirm")
    lines.append("  the cross-check's PROCEED was genuine, or that "
                 "re-consultation fired on")
    lines.append("  a material plan change. Directive #6's anti-self-dealing "
                 "clause governs")
    lines.append("  substance at the judgment layer; the operator retains final "
                 "say.")
    lines.append("  This verdict is a POINT-IN-TIME snapshot: PR state can change "
                 "before")
    lines.append("  merge, and branch protection re-checks required CI at merge "
                 "time.")
    lines.append("=" * 68)
    return verdict, lines


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Pre-self-merge compliance check for a PR (directive #6)")
    ap.add_argument("pr", help="pull request number")
    ap.add_argument("--repo", required=True, metavar="OWNER/REPO",
                    help="target repository, e.g. sumitake/agent-collab")
    args = ap.parse_args(argv)

    verdict, lines = run(str(args.pr), args.repo)
    print("\n".join(lines))
    return 0 if verdict == "MERGE-ELIGIBLE" else 1


if __name__ == "__main__":
    sys.exit(main())
