#!/usr/bin/env python3
"""Dependabot auto-merge gate — required-context enforcement (2026-08-17).

Two subcommands, both HARD-FAIL (exit 1) unless their condition positively
holds; any API/network error raises and fails the step (never passes on a
failed read). stdlib-only: the self-hosted runner images carry no gh CLI.

``commits``  Every commit on the PR must be authentically Dependabot's:
             commit author ``dependabot[bot]`` AND committer ``web-flow`` AND
             GitHub signature verification ``verified``. ``author.login`` alone
             is spoofable via the commit-header email (peer review 2026-08-17,
             Codex concern 2); a forged commit cannot carry GitHub's own
             web-flow signature.

``signal``   A Codex review response bound to the CURRENT head must exist and
             be clean. Clean results arrive as issue comments containing
             "Didn't find any major issues" plus ``**Reviewed commit:**
             `<short-sha>```; findings arrive as reviews (``commit_id``) whose
             bodies carry ``![Pn Badge]`` markers. Head binding is mandatory
             (Codex concern 3); findings or any unrecognized/unbound response
             shape fail closed (Codex concern 1) — the PR then takes the
             manual review path.

Env: GH_TOKEN (or GITHUB_TOKEN), REPO, PR_NUMBER, HEAD_SHA.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

CODEX_LOGIN = "chatgpt-codex-connector[bot]"
CLEAN_MARKER = "Didn't find any major issues"
BADGE_RE = re.compile(r"!\[P\d Badge\]")
REVIEWED_COMMIT_RE = re.compile(r"\*\*Reviewed commit:\*\*\s*`([0-9a-f]{7,40})`")


def _next_link(link_header: str):
    for part in link_header.split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue
        if section.startswith("<") and ">" in section:
            return section[1 : section.index(">")]
    return None


def _get_paginated(path: str):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("::error::no GH_TOKEN/GITHUB_TOKEN — failing closed")
        sys.exit(1)
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    url = f"{api}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
        "User-Agent": "dependabot-gate",
    }
    items = []
    while url:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            items.extend(json.load(resp))
            url = _next_link(resp.headers.get("Link", ""))
    return items


def check_commits(commits) -> list[str]:
    """Return violation strings; empty means every commit is *shaped* like a
    genuine Dependabot commit (author dependabot[bot] + committer web-flow +
    verified signature with reason=valid).

    KNOWN, OPERATOR-ACCEPTED RESIDUAL (2026-08-17): this is NOT robust
    provenance against an actor with WRITE ACCESS to the repo. GitHub signs
    commits it creates via the contents/git-data API with its own web-flow key
    (verified=true, reason=valid) for ANY caller, and author/committer are
    caller-selectable metadata (empirically: the #2762 merge commit is
    web-flow-signed + verified + valid with a non-Dependabot author). So a
    write-capable actor can create a web-flow-signed commit with
    author=dependabot[bot] and arbitrary content and pass every predicate here
    without holding any key. The commit-content/signature approach therefore
    cannot prove Dependabot ORIGIN against a write-capable actor (Codex
    connector P1, escalated + operator-accepted 2026-08-17).

    Why this is accepted rather than closed: the authoritative backstop is the
    HEAD-BOUND Codex clean-signal in classify_signal() — any injected commit
    changes the PR head, invalidating the clean signal, so the content needs a
    FRESH Codex review of that exact commit (the same review bar any PR faces).
    The residual privilege an insider gains is skipping the agent-body
    governance gates (trace/tier/phase1), not skipping review. Under the shared
    identity model (write-capable agents already exist) the operator accepted
    this tradeoff over reintroducing actor-restriction complexity. This function
    is thus a cheap shape/sanity filter layered UNDER the Codex review, not a
    standalone provenance proof.
    """
    bad = []
    for c in commits:
        sha = (c.get("sha") or "?")[:10]
        author = ((c.get("author") or {}).get("login")) or ""
        committer = ((c.get("committer") or {}).get("login")) or ""
        verification = (c.get("commit") or {}).get("verification") or {}
        verified = bool(verification.get("verified"))
        reason = verification.get("reason")
        if author != "dependabot[bot]":
            bad.append(f"{sha} author={author or 'NULL'}")
        elif committer != "web-flow":
            bad.append(f"{sha} committer={committer or 'NULL'}")
        elif not verified or reason != "valid":
            bad.append(f"{sha} signature-not-valid(verified={verified},reason={reason})")
    return bad


def classify_signal(head_sha: str, comments, reviews) -> tuple[str, str]:
    """Return (verdict, detail): verdict in {clean, findings, absent}.

    Precedence is fail-closed: ANY head-bound findings response wins over a
    clean one; an unrecognized head-bound shape counts as findings (never
    clean); responses that cannot be bound to the current head are ignored.
    """
    head_bound_clean = None
    for r in reviews:
        if ((r.get("user") or {}).get("login")) != CODEX_LOGIN:
            continue
        if (r.get("commit_id") or "") != head_sha:
            continue
        body = r.get("body") or ""
        if BADGE_RE.search(body) or CLEAN_MARKER not in body:
            return "findings", f"review {r.get('id')} at head has findings/unknown shape"
        head_bound_clean = f"review {r.get('id')}"
    for c in comments:
        if ((c.get("user") or {}).get("login")) != CODEX_LOGIN:
            continue
        body = c.get("body") or ""
        m = REVIEWED_COMMIT_RE.search(body)
        if not m or not head_sha.startswith(m.group(1)):
            continue
        if BADGE_RE.search(body) or CLEAN_MARKER not in body:
            return "findings", f"comment {c.get('id')} at head has findings/unknown shape"
        head_bound_clean = f"comment {c.get('id')}"
    if head_bound_clean:
        return "clean", head_bound_clean
    return "absent", "no Codex response bound to the current head"


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    repo = os.environ["REPO"]
    pr = os.environ["PR_NUMBER"]
    if mode == "commits":
        commits = _get_paginated(f"/repos/{repo}/pulls/{pr}/commits?per_page=100")
        if not commits:
            # Fail closed: an empty commit list must never satisfy the
            # authenticity gate (Grok trust-model review, concern 9).
            print("::error::PR reported zero commits — failing closed")
            return 1
        bad = check_commits(commits)
        if bad:
            print(
                "::error::non-authentic commit(s) on a dependabot[bot] PR: "
                + "; ".join(bad)
            )
            return 1
        print(f"all {len(commits)} commit(s) authentically Dependabot-authored")
        return 0
    if mode == "signal":
        head = os.environ["HEAD_SHA"]
        comments = _get_paginated(f"/repos/{repo}/issues/{pr}/comments?per_page=100")
        reviews = _get_paginated(f"/repos/{repo}/pulls/{pr}/reviews?per_page=100")
        verdict, detail = classify_signal(head, comments, reviews)
        if verdict == "clean":
            print(f"head-bound clean Codex signal: {detail}")
            return 0
        print(
            f"::error::no clean head-bound Codex signal ({verdict}: {detail}) — "
            "merge stays blocked; manual review path applies"
        )
        return 1
    print("::error::usage: dependabot_gate.py commits|signal")
    return 2


if __name__ == "__main__":
    sys.exit(main())
