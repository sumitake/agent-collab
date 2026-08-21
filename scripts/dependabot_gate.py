#!/usr/bin/env python3
"""Dependabot auto-merge gate — required-context enforcement (deterministic,
no-AI design 2026-08-19).

Three subcommands, each HARD-FAILS (exit 1) unless its condition positively
holds; any API/network error raises and fails the step (never passes on a
failed read). stdlib-only.

``commits``       Every commit on the PR must be authentically Dependabot's:
                  author ``dependabot[bot]`` AND committer ``web-flow`` AND
                  signature verification ``reason == valid``. Empty commit list
                  fails closed. (Shape/sanity filter — see the residual note in
                  check_commits.)

``files``         Every changed path must be within the github-actions
                  ecosystem allowlist (``.github/workflows/`` or
                  ``.github/actions/``); empty file list fails closed; and a PR
                  touching the gate's own CONTROL PLANE (dependabot-gate.yml /
                  dependabot-automerge.yml / this script / its test) is HELD for
                  manual review — the oracle must not auto-update itself.

``update-type``   Reads ``UPDATED_DEPENDENCIES_JSON`` (dependabot/fetch-metadata's
                  ``updated-dependencies-json`` output) and requires a non-empty
                  list where EVERY entry's ``updateType`` is patch or minor.
                  fetch-metadata's scalar ``update-type`` uses ``maxSemver()``,
                  which OMITS unknown/missing tokens instead of promoting them —
                  so a grouped PR with a missing/unknown type plus a minor reads
                  as "minor" and would hide the unknown entry. Checking every
                  entry here closes that fail-open (Grok design review 2026-08-19,
                  concern 1). Majors are held for manual review.

Env: GH_TOKEN (or GITHUB_TOKEN), REPO, PR_NUMBER  [commits, files];
     UPDATED_DEPENDENCIES_JSON  [update-type].
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

ALLOWED_UPDATE_TYPES = {
    "version-update:semver-patch",
    "version-update:semver-minor",
}
# github-actions-ecosystem Dependabot PRs only rewrite workflow/action pins.
ALLOWED_PATH_PREFIXES = (".github/workflows/", ".github/actions/")
# Files that ARE workflows/actions (so pass the allowlist) but are the gate's
# own control plane: a Dependabot bump of the fetch-metadata pin inside these
# must go manual. Non-workflow entries here are redundant with the allowlist
# but kept explicit for defence in depth.
CONTROL_PLANE_PATHS = {
    ".github/workflows/dependabot-gate.yml",
    ".github/workflows/dependabot-automerge.yml",
    "scripts/dependabot_gate.py",
    "scripts/test_dependabot_gate.py",
    "tests/test_dependabot_gate.py",
}


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

    KNOWN, OPERATOR-ACCEPTED RESIDUAL: this is a shape/sanity filter, NOT robust
    provenance against an actor with WRITE ACCESS. GitHub signs API-created
    commits with its own web-flow key (verified/valid) for any caller, and
    author/committer are caller-selectable, so a write-capable actor could forge
    a commit that passes here. The no-AI design (2026-08-19) removed the former
    head-bound Codex review backstop; the limits now are (a) this all-commit
    filter, (b) the `files` path allowlist + control-plane hold, and (c) the
    `update-type` patch/minor gate — all deterministic, plus required CI. The
    `update-type` value is Dependabot's own first-commit YAML trailer, NOT the
    diff, so it assumes honest Dependabot metadata; it is not a second
    provenance proof (Grok design review 2026-08-19, concern 2).
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


def check_files(files) -> list[str]:
    """Return violation strings; empty means every changed path is an allowed
    github-actions-ecosystem path AND none touches the gate's control plane.
    """
    bad = []
    for f in files:
        for path in (f.get("filename"), f.get("previous_filename")):
            if not path:
                continue
            if path in CONTROL_PLANE_PATHS:
                bad.append(f"{path} (control-plane — held for manual review)")
            elif not path.startswith(ALLOWED_PATH_PREFIXES):
                bad.append(f"{path} (outside the github-actions ecosystem allowlist)")
    return bad


def check_update_types(deps) -> list[str]:
    """Return violation strings; empty means every dependency update is
    patch or minor. `deps` is fetch-metadata's updated-dependencies-json.
    """
    bad = []
    for d in deps:
        name = (d or {}).get("dependencyName") or "?"
        update_type = (d or {}).get("updateType")
        if update_type not in ALLOWED_UPDATE_TYPES:
            bad.append(f"{name} update-type={update_type!r}")
    return bad


def _repo_pr():
    return os.environ["REPO"], os.environ["PR_NUMBER"]


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "commits":
        repo, pr = _repo_pr()
        commits = _get_paginated(f"/repos/{repo}/pulls/{pr}/commits?per_page=100")
        if not commits:
            print("::error::PR reported zero commits — failing closed")
            return 1
        bad = check_commits(commits)
        if bad:
            print("::error::non-authentic commit(s) on a dependabot[bot] PR: "
                  + "; ".join(bad))
            return 1
        print(f"all {len(commits)} commit(s) authentically Dependabot-shaped")
        return 0

    if mode == "files":
        repo, pr = _repo_pr()
        files = _get_paginated(f"/repos/{repo}/pulls/{pr}/files?per_page=100")
        if not files:
            print("::error::PR reported zero changed files — failing closed")
            return 1
        bad = check_files(files)
        if bad:
            print("::error::disallowed/held path(s) on a dependabot[bot] PR: "
                  + "; ".join(bad))
            return 1
        print(f"all {len(files)} changed file(s) within the github-actions "
              "allowlist; no control-plane touch")
        return 0

    if mode == "update-type":
        raw = os.environ.get("UPDATED_DEPENDENCIES_JSON", "")
        if not raw.strip():
            print("::error::UPDATED_DEPENDENCIES_JSON empty/missing "
                  "(fetch-metadata output absent) — failing closed")
            return 1
        try:
            deps = json.loads(raw)
        except (ValueError, TypeError) as exc:
            print(f"::error::updated-dependencies-json not parseable ({exc}) — "
                  "failing closed")
            return 1
        if not isinstance(deps, list) or not deps:
            print("::error::updated-dependencies-json is not a non-empty list — "
                  "failing closed")
            return 1
        bad = check_update_types(deps)
        if bad:
            print("::error::update(s) not in {patch, minor} — held for manual "
                  "review: " + "; ".join(bad))
            return 1
        print(f"all {len(deps)} dependency update(s) are patch/minor")
        return 0

    print("::error::usage: dependabot_gate.py commits|files|update-type")
    return 2


if __name__ == "__main__":
    sys.exit(main())
