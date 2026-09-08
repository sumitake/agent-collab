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
- This repository may receive only final signed native standalone bundles and
  their closed per-member/whole-bundle manifest metadata.
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

For a release containing `project-estimation`, first obtain the governed,
privacy-safe maintenance handoff. The public tree may admit only its declared
aggregate prior, pricing snapshot, quota snapshot, and version-bound receipt;
never substitute fixtures or raw evidence. Run
`scripts/verify_project_estimation_maintenance.py` directly when diagnosing the
gate. `scripts/check_release_consistency.py` and the remote release workflow
must both reject a missing, stale, mismatched, or privacy-unsafe handoff. See
[`docs/architecture/project-estimation.md`](docs/architecture/project-estimation.md).

Commit only a unique `changelog.d/` fragment for user-visible changes. The
generated `CHANGELOG.md` is compiled by the release flow.

After every other release task has completed, perform the
[final documentation closeout](docs/architecture/repository-and-release.md#final-documentation-closeout).
It aligns the public architecture handbook, root README, and generated
changelog evidence with the exact release before the release is declared
complete. Keep that public material human-first; low-level machine contracts
belong in the package reference, and private executor/control-plane recipes do
not belong in this repository.

## Repository governance

[`docs/public-governance.md`](docs/public-governance.md) is the local,
self-contained contribution and merge contract. The PR template defines the
required evidence block, `.github/workflows/compliance-trace.yml` validates its
form in CI, and `scripts/check_pr_compliance.py` is the authoritative local
pre-merge form check. No external or private repository is required to apply
these rules.

## Runtime policy

The coordinator is a routing-only shim. Its client validates the manifest,
request, and native bundle; the signed runtime selects descriptor-admitted
routes. Provider-free planning does not establish authentication or live
availability. Run the migration doctor as a separate host inventory step; do
not claim that the coordinator automatically runs a migration or identity
preflight. Host-owned asynchronous coordination is outside this routing wire.

The caller and skill/repository workflow verify the primary, artifact-author,
and reviewer lineages wherever independence is required. The current wire has
no dynamic primary/author-family exclusion fields; host observations and a
route decision cannot establish independent approval. Unknown-family output
can be advisory but cannot satisfy governance-grade independence. A policy-only
package has no admitted native artifact and returns typed unavailable for model
execution. It does not expose a separate async-runtime safe-mode service.

The native client accepts no path or member override, resolves only the
manifest-selected closed bundle beneath the plugin root, and rejects links,
aliases, traversal, and unknown members. A git-checkout source is admitted
under a permission FLOOR — owner
read+execute, no setuid/setgid/sticky — that tolerates the operator's umask
group/other bits, because the whole plugin checkout is ONE trust domain: the host
runs the plugin's Python control plane from that same checkout, so a peer who can
write it already owns the client and the mode is not the integrity boundary
there. Integrity is verified per-member (architecture/type/size/hash/signing)
plus whole-bundle identity. Offline Developer ID, hardened-runtime, and
secure-timestamp checks run before invocation; Apple notarization remains a
release gate. The environment is scrubbed and only the fixed direct-runtime
protocol is used.

## Clean public repository invariant

Every active path, reachable ref, and release archive must remain free of
provider executor source, raw provider invocation recipes, private absolute
paths, credentials, retired package trees, and unreviewed native artifacts.
Before publication or release, run both active-tree and history modes of
`scripts/check-public-export-safety.py`. History mode covers refs reachable in
the *local* clone, so a clone retaining pre-rewrite refs fails it even when the
canonical remote is clean; compare against a disposable full clone of the
canonical remote and record the snapshot checked. That comparison clears only
the recorded snapshot, never the failing clone, the publication candidate,
unfetched refs, or prior exposure. If contamination is suspected, stop
publication and follow `SECURITY.md`; never paste suspect material into a public
issue or pull request. See
[`docs/public-governance.md`](docs/public-governance.md) for the full rule.
