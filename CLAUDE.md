# agent-collab-plugin development guide

This repository publishes one package: `plugins/agent-collab`. Do not create a
host preset, provider-specific plugin, compatibility shim, downloader,
post-install hook, or provider executor source.

## Source boundaries

- `skill-specs/` is the editable source for generated collaboration skills.
- `plugins/agent-collab/skills/` is generated output.
- The private workspace owns editable native runtime implementation.
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

## Public-release hard stop

Do not change visibility or publish from a clone whose reachable history still
contains retired packages or executor implementation. A public export must be a
clean-history repository that passes both active-tree and history modes of
`scripts/check-public-export-safety.py`. History rewriting, force-pushes, tag or
release deletion, and GitHub residual cleanup are primary/operator actions, not
part of ordinary plugin authoring.
