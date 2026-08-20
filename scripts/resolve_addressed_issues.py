#!/usr/bin/env python3
"""Close GitHub issues addressed by a release — the feedback-loop closeout.

A session that hits an ``agent-collab`` plugin error files a GitHub issue on
this repo (workspace ``AGENTS.md`` § Learning loop rule). This script closes the
loop at the other end: when a release ships the fix, the issue is closed with
version evidence, so filed → fixed → shipped → closed is a complete cycle.

Linkage is EXPLICIT and honest. A changelog fragment that fixes issue N carries
an own-line marker::

    Addressed: #125
    Addressed: #130, #131          # multiple on one line is fine

The marker is deliberately NOT GitHub's ``Fixes #125`` closing keyword, so the
fix merging to ``main`` never auto-closes the issue prematurely — closure
happens only when the signed build actually ships. At release time this script
diffs ``CHANGELOG.md`` + ``changelog.d/`` between the previous release tag and
this one, extracts issue numbers from ADDED ``Addressed:`` lines, and for each
OPEN issue on this repo posts a version-stamped comment, applies the
``resolved-in-release`` label, and closes it.

Fail-safe by construction:
  * Explicit markers only — never text/similarity matching.
  * Only OPEN issues on THIS repo are touched; pull requests are skipped.
  * Idempotent: already-closed or missing issues are skipped.
  * Every per-issue action is best-effort and NON-FATAL. The release has already
    shipped; this bookkeeping must never fail the build or block later issues.
  * Bounded: a hard cap on issues acted on per run guards a pathological diff.
  * ``--dry-run`` prints the exact plan and touches nothing.

Auth: uses the ``gh`` CLI; in CI set ``GH_TOKEN`` to a token with
``issues: write`` (the release job grants it job-scoped).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# The empty-tree object: diff base when there is no previous tag (first release).
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# Files whose ADDED lines are scanned for markers. The marker may live in a
# changelog fragment (pre-compilation) or the compiled CHANGELOG section
# (post-compilation); diffing both across the tag window catches it either way.
# changelog.d/README.md is EXCLUDED: it documents the marker with example
# `Addressed: #N` lines that must never be read as real closures (Grok review,
# HIGH — a README example would otherwise close that issue on the next release).
# Excluded from the scan: the fragment README (carries example markers) and the
# archived/ dir (already-released fragments moved there at release time; their
# markers already reached CHANGELOG.md in the release that shipped them). The
# compiled CHANGELOG.md always carries a fix's marker, so excluding these loses
# nothing while removing two false-closure sources.
_SCAN_EXCLUDES = ("changelog.d/README.md", "changelog.d/archived/")


def scan_pathspec() -> list[str]:
    """Git pathspec: scanned files minus the excluded non-fragment paths."""

    spec = ["CHANGELOG.md", "changelog.d/"]
    spec.extend(f":(exclude){path}" for path in _SCAN_EXCLUDES)
    return spec


def select_actionable(numbers: list[int]) -> list[int]:
    """Fail-safe cap: refuse to act on a runaway marker set (testable)."""

    if len(numbers) > _MAX_ISSUES_PER_RUN:
        return []
    return numbers

# An own-line marker, optionally bulleted: ``Addressed: #1, #2``. Case-insensitive
# on the keyword; issue refs are extracted from the remainder of the line only,
# so a ``#123`` elsewhere in prose is never mistaken for a resolution.
_MARKER_RE = re.compile(r"^\s*(?:[-*]\s*)?Addressed:\s*(?P<refs>.+)$", re.IGNORECASE)
_ISSUE_REF_RE = re.compile(r"#(\d+)\b")

# Guard against a pathological or hand-crafted diff closing a flood of issues.
_MAX_ISSUES_PER_RUN = 100

_RESOLVED_LABEL = "resolved-in-release"
_RESOLVED_LABEL_COLOR = "0e8a16"
_RESOLVED_LABEL_DESC = "Closed automatically because a release shipped the fix"


class ResolveError(RuntimeError):
    """A setup-level failure (bad args, git unavailable) — distinct from the
    per-issue best-effort failures which are swallowed and logged."""


# Per-call wall-clock bound: a hung gh/git call must not run to the job
# deadline and fail an already-published release. TimeoutExpired propagates to
# the caller, which classifies it as a per-issue (non-fatal) or setup failure.
_CALL_TIMEOUT_SECONDS = 60


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, check=check,
        timeout=_CALL_TIMEOUT_SECONDS,
    )


def extract_addressed_issue_numbers(diff_text: str) -> list[int]:
    """Return sorted-unique issue numbers from ADDED ``Addressed:`` lines.

    Pure function (no I/O) so the risky parsing is deterministically testable.
    Only unified-diff ADDED lines (``+`` prefix, excluding the ``+++`` file
    header) are considered, so a marker merely present in the base — or in a
    REMOVED line — never triggers a closure.
    """

    numbers: list[int] = []
    seen: set[int] = set()
    for raw in diff_text.splitlines():
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        line = raw[1:]
        match = _MARKER_RE.match(line)
        if match is None:
            continue
        for ref in _ISSUE_REF_RE.findall(match.group("refs")):
            n = int(ref)
            if n > 0 and n not in seen:
                seen.add(n)
                numbers.append(n)
    return sorted(numbers)


def _previous_tag(repo_root: Path, tag: str) -> str:
    """The nearest annotated/reachable tag before ``tag``, or the empty tree."""

    result = _run(
        ["git", "-C", str(repo_root), "describe", "--tags", "--abbrev=0", f"{tag}^"],
        check=False,
    )
    prev = result.stdout.strip()
    return prev if result.returncode == 0 and prev else _EMPTY_TREE


def _diff_since(repo_root: Path, base: str, target: str) -> str:
    result = _run(
        [
            "git", "-C", str(repo_root), "diff", "--unified=0",
            f"{base}..{target}", "--", *scan_pathspec(),
        ],
        check=False,
    )
    if result.returncode != 0:
        raise ResolveError(f"git diff {base}..{target} failed: {result.stderr.strip()}")
    return result.stdout


def _issue_state(repo: str, number: int) -> str | None:
    """'open' / 'closed' for an issue, or None for a PR or a missing number."""

    try:
        result = _run(
            ["gh", "api", f"repos/{repo}/issues/{number}",
             "--jq", '(if .pull_request then "pr" else .state end)'],
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    state = result.stdout.strip()
    return state if state in ("open", "closed") else None


def _ensure_label(repo: str) -> None:
    # --force creates or updates; a failure here is non-fatal (the label may
    # already exist and adding it below will still work).
    _run(
        ["gh", "label", "create", _RESOLVED_LABEL, "--repo", repo,
         "--color", _RESOLVED_LABEL_COLOR, "--description", _RESOLVED_LABEL_DESC,
         "--force"],
        check=False,
    )


def _close_issue(repo: str, number: int, tag: str, release_url: str) -> None:
    where = f" ({release_url})" if release_url else ""
    body = (
        f"Resolved in release **{tag}**{where}. Closed automatically by the "
        f"release feedback-loop closeout. Reopen if this build does not in fact "
        f"resolve it."
    )
    _run(["gh", "issue", "comment", str(number), "--repo", repo, "--body", body])
    _run(["gh", "issue", "edit", str(number), "--repo", repo,
          "--add-label", _RESOLVED_LABEL], check=False)
    _run(["gh", "issue", "close", str(number), "--repo", repo,
          "--reason", "completed"])


def resolve(
    repo: str,
    tag: str,
    *,
    repo_root: Path,
    release_url: str = "",
    target_rev: str | None = None,
    dry_run: bool = False,
) -> int:
    """Close every open issue explicitly addressed since the previous tag.

    Returns the count of issues closed (or that WOULD be closed in dry-run).
    """

    target = target_rev or tag
    base = _previous_tag(repo_root, tag)
    diff = _diff_since(repo_root, base, target)
    numbers = extract_addressed_issue_numbers(diff)
    if not numbers:
        print(f"resolve-addressed: no Addressed: markers in {base}..{target}")
        return 0
    actionable = select_actionable(numbers)
    if not actionable:
        # Fail-safe: refuse a runaway rather than close a flood of issues.
        print(
            f"resolve-addressed: {len(numbers)} markers exceed the per-run cap "
            f"of {_MAX_ISSUES_PER_RUN}; refusing to act. Investigate the diff.",
            file=sys.stderr,
        )
        return 0

    label_ensured = False
    closed = 0
    for number in actionable:
        try:
            state = _issue_state(repo, number)
            if state is None:
                print(f"resolve-addressed: #{number} is a PR or missing — skipped")
                continue
            if state == "closed":
                print(f"resolve-addressed: #{number} already closed — skipped")
                continue
            if dry_run:
                print(f"resolve-addressed: [dry-run] would close #{number} for {tag}")
                closed += 1
                continue
            if not label_ensured:
                _ensure_label(repo)
                label_ensured = True
            _close_issue(repo, number, tag, release_url)
        except Exception as exc:  # noqa: BLE001 — per-issue best-effort, never fatal
            print(
                f"resolve-addressed: #{number} failed ({exc}); continuing — "
                f"the release is unaffected.",
                file=sys.stderr,
            )
            continue
        print(f"resolve-addressed: closed #{number} (resolved in {tag})")
        closed += 1
    return closed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/name of THIS repo")
    parser.add_argument("--tag", required=True, help="release tag, e.g. v6.1.2")
    parser.add_argument("--release-url", default="", help="URL cited as evidence")
    parser.add_argument(
        "--target-rev",
        default=None,
        help="rev to diff to (default: --tag). Use HEAD to preview before tagging.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if _run(["git", "rev-parse", "--is-inside-work-tree"], check=False).returncode != 0:
        raise ResolveError("not inside a git work tree")
    repo_root = Path(
        _run(["git", "rev-parse", "--show-toplevel"]).stdout.strip()
    )
    resolve(
        args.repo,
        args.tag,
        repo_root=repo_root,
        release_url=args.release_url,
        target_rev=args.target_rev,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ResolveError as exc:
        print(f"resolve-addressed: {exc}", file=sys.stderr)
        raise SystemExit(1)
