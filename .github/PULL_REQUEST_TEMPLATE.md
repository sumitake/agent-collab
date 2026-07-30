## Summary

Describe the user-visible outcome and why it belongs in the public policy/client repository.

## Boundary declaration

- [ ] No provider executor source, raw provider command, credential, private absolute path, retired package tree, downloader, or post-install hook is included.
- [ ] Native-runtime changes, if any, contain only a final signed artifact and reviewed public verification metadata; implementation and credentials remain private.
- [ ] The change does not create a host-specific preset or provider-specific plugin.

## Generated and release surfaces

- [ ] Skill specs and generated `SKILL.md` files are in parity.
- [ ] Claude and Codex marketplaces/manifests are in parity.
- [ ] A unique `changelog.d/` fragment is present for a user-visible change; generated `CHANGELOG.md` changes only in a release/bootstrap PR.
- [ ] Version metadata is bumped when behavior or distributed content changes. Every surface has to move together or `check_release_consistency.py` reports drift, so bump all seven:
  1. `plugins/agent-collab/.claude-plugin/plugin.json`
  2. `plugins/agent-collab/.codex-plugin/plugin.json`
  3. `.claude-plugin/marketplace.base.json` → then re-run `python3 scripts/build_marketplace.py`
  4. root `README.md` — the summary-table row **and** the `## What's new - vX.Y.Z` heading (two separate edits)
  5. `plugins/agent-collab/README.md` — `Current: **X.Y.Z**` **and** the "this same X.Y.Z package" line
  6. `scripts/skill-build-config.json` — the **nested** `skill_version` inside the package block, not a new top-level key → then re-run `python3 scripts/build_skills.py`, which rewrites every generated `SKILL.md`
  7. a `changelog.d/` fragment naming `agent-collab X.Y.Z`

  The generated `CHANGELOG.md` is **not** one of them — at PR time the version requirement is met by that fragment, so a content PR can bump without touching a release-only file. Run `python3 scripts/check_release_consistency.py` and the test suite; between them they name any surface you missed.

## Verification

List the exact deterministic tests, schema/generation checks, secret scan, and public-export gates run for this change.

- [ ] `python3 scripts/build_skills.py --check`
- [ ] `python3 scripts/build_marketplace.py --check`
- [ ] `python3 scripts/build-changelog.py --check`
- [ ] `python3 -m unittest discover -s tests -t . -v`
- [ ] `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
- [ ] `python3 scripts/check_release_consistency.py`
- [ ] `python3 scripts/secret_scan.py`
- [ ] `python3 scripts/check-public-export-safety.py --active-tree --history` (history
      mode covers refs reachable in the *local* clone; see the history-mode scope rule in
      `docs/public-governance.md` before treating a failure as public contamination)
- [ ] `git diff --check`

## Review and post-condition

State the change tier from `docs/public-governance.md`, the independent-family review outcome when required, and the post-merge verification.

## Compliance trace

<!-- compliance-trace:start -->
author: <agent or contributor>
standing_directives: <public boundaries and validation followed>
tier: <1 | 2 | 3>
cross_check: <verdict and reviewer family, in-flight state, or reasoned N/A for Tier 1>
post_condition: <post-merge/release verification>
mcp_coverage_gap: <NONE | FILED: public issue URL>
contributor_rights: <OWNER-AUTHORED | OPERATOR-CONFIRMED>
operator_reserved: <yes | no>
<!-- compliance-trace:end -->
