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
- [ ] Version metadata is bumped when behavior or distributed content changes.

## Verification

List the exact deterministic tests, schema/generation checks, secret scan, and public-export gates run for this change.

- [ ] `python3 scripts/build_skills.py --check`
- [ ] `python3 scripts/build_marketplace.py --check`
- [ ] `python3 scripts/build-changelog.py --check`
- [ ] `python3 -m unittest discover -s tests -t . -v`
- [ ] `python3 -m unittest discover -s scripts -p 'test_*.py' -v`
- [ ] `python3 scripts/check_release_consistency.py`
- [ ] `python3 scripts/secret_scan.py`
- [ ] `python3 scripts/check-public-export-safety.py --active-tree --history`
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
