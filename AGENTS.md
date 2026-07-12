# agent-collab development guide

This repository publishes one package: `plugins/agent-collab`. Do not create a
host preset, provider-specific plugin, compatibility shim, downloader,
post-install hook, or provider executor source.

## Source boundaries

- `skill-specs/` is the editable source for generated collaboration skills.
- `plugins/agent-collab/skills/` is generated output.
- This repository is authoritative for public policy, governance, skills,
  client behavior, migration, and release-safety checks.
- Native runtime implementation and build/sign credentials stay in a separate
  private producer that contributors do not need to access.
- This repository may receive only final signed native artifacts and their
  size/hash/signature manifest metadata.
- Never place executor source, bytecode, private absolute paths, or retired
  package trees in the active source or release archive.

## Build and validation

```text
python3 scripts/build_skills.py
python3 scripts/build_marketplace.py
python3 -m unittest discover -s tests -t . -v
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/check_release_consistency.py
python3 scripts/check-public-export-safety.py --active-tree
git diff --check
```

Commit only a unique `changelog.d/` fragment for user-visible changes. The
generated `CHANGELOG.md` is compiled by the release flow.

## Repository governance

[`docs/public-governance.md`](docs/public-governance.md) is the local,
self-contained contribution and merge contract. The PR template defines the
required evidence block, `.github/workflows/compliance-trace.yml` validates its
form in CI, and `scripts/check_pr_compliance.py` is the authoritative local
pre-merge form check. No external or private repository is required to apply
these rules.

## Runtime policy

Provider routing must pass the provider-free startup preflight. Active legacy
package state blocks all provider routing. Unknown-family governance review
requires explicit configuration and fails closed; non-governance use carries an
independence warning. Policy-only safe mode preserves only validated async
inbox/coordination seams and returns typed unavailable for every model route.

The native client accepts no path override, resolves only the manifest-selected
artifact beneath the plugin root, rejects symlinks and traversal, verifies
platform/architecture/size/hash and macOS signing/notarization, scrubs the
environment, and uses only the fixed protocol.

## Clean public repository invariant

Every active path, reachable ref, and release archive must remain free of
provider executor source, raw provider invocation recipes, private absolute
paths, credentials, retired package trees, and unreviewed native artifacts.
Before publication or release, run both active-tree and history modes of
`scripts/check-public-export-safety.py`. If contamination is suspected, stop
publication and follow `SECURITY.md`; never paste suspect material into a public
issue or pull request.
