# agent-collab

`agent-collab` publishes one collaboration plugin for Claude Code, Codex, and
compatible hosts. Version 6 keeps the closed semantic coordinator and
co-packaged direct native runtime while adding provider-neutral quality and
effort profiles, current-portfolio routing, and truthful advisory degradation.

This public repository distributes **agent-collab** (v6.0.1). The
**v6.0.1 release** corrects provider-free readiness projection while preserving
the v6 runtime, routing, and wire identities. The
**[v6.0.1 release](https://github.com/sumitake/agent-collab/releases/tag/v6.0.1)**
is the governed publication target for the signed runtime, archive, checksum,
SPDX evidence, and installation proof described below.

The human-first [architecture handbook](docs/architecture/README.md) explains
the system boundaries and lifecycle. This README and that handbook were
reconciled against the exact published artifact during the mandatory final
release documentation closeout; the package reference below remains the
machine-operational contract. The dated
[status and evidence snapshot](docs/architecture/status-and-evidence.md)
keeps repository, tag, release, installation, and readiness claims separate.

## What's new - v6.0.1

- Provider-free runtime status now projects the public request into the exact
  closed v6 readiness profile accepted by the co-packaged runtime.
- Requests now carry closed provider-neutral `quality_profile` and
  `effort_class` fields while provider-local adapters resolve current
  executable capabilities without model or version pins.
- Clean substantive results without sufficient native source evidence return
  first-class ungrounded advisories instead of fabricated authority or generic
  protocol failures.
- Codex private-patch code generation expands the internal projection to 13
  transport actions and 17 action/source pairs while the public semantic
  surface remains provider-neutral.
- Provider teardown, cleanup, and route-local degradation are bounded without
  replay, fallback after possible inference, or a background broker.
- Promotion uses a fixed three-call mechanical canary; exhaustive live semantic
  matrices are no longer activation or publication authority.
- The 4.7 engineering-process pack remains available as three self-executed
  skills: `decision-map`, `prototype`, and `architecture-review`.
- The current `code-review` skill retains its spec-fidelity axis and
  evidence-bound Fowler smell baseline; `Spec` and `Smell` findings remain
  separate from defect severity and merge-blocking aggregation.
- `orchestrate` and `teamwork` retain conditional tracer-bullet and
  expand–contract guidance for product-feature decomposition without adding a
  provider route or generic orchestration layer.

## What ships

- Source skill specifications in `skill-specs/` and generated skills in
  `plugins/agent-collab/skills/`.
- Pinned source and license provenance for MIT-derived skill material in
  `docs/third-party-skill-provenance.md`.
- A closed semantic coordinator at `plugins/agent-collab/coordinator.py`.
- A direct bounded process client at `plugins/agent-collab/runtime_client.py`.
- Provider-neutral host observations and migration reporting.
- One schema-4 runtime manifest contract and public archive/release/export
  safety gates.
- A final signed native standalone bundle only when produced by the separate
  private build/sign workflow.

No provider executor source, provider invocation recipe, model pin,
compatibility package, downloader, post-install hook, broker, socket, lane,
launchd job, lifecycle setup command, or raw provider wire is public.

## Install

```text
codex plugin marketplace add sumitake/agent-collab
codex plugin add agent-collab@agent-collab
```

## Semantic actions

Public requests select one of 11 logical actions:

```text
architecture.conceptual
architecture.repository
codegen.repository
context.documents.extract
context.documents.reason
context.repository.extract
context.repository.reason
frontend_codegen.repository
frontend_review.repository
governance.repository
review.repository
```

Repository actions require a canonical absolute `repo_root`. Document context
uses bounded inline documents. Conceptual architecture uses prompt-only source.
The runtime's workspace-generated wire descriptor derives the internal 13
transport actions and 17 action/source pairs. Those projections are diagnostic
contract data, not a second public request surface.

See `plugins/agent-collab/README.md` for the exact coordinator and runtime
contract.

## Source and generated files

- Edit `skill-specs/<name>.md`.
- Generate with `python3 scripts/build_skills.py`.
- Check with `python3 scripts/build_skills.py --check`.
- Generate marketplace metadata with `python3 scripts/build_marketplace.py`.
- Check it with `python3 scripts/build_marketplace.py --check`.

`context` is the sole source-grounded corpus/repository skill. No parallel
size-branded source or generated skill surface is supported.

## Runtime trust boundary

The canonical workspace build owns the final binary and generated manifest.
The public source expects:

- manifest schema 4;
- runtime protocol 4;
- native manifest contract 4;
- provider runtime version `4.0.0`;
- one top-level closed `wire_contract` plus canonical
  `wire_contract_sha256`; and
- no action-membership mirror in artifact entries.

The public client verifies fixed plugin-relative path, exact membership and
digests, Mach-O architecture/minimum macOS, hardened Developer ID identity,
team, and secure timestamp. Online notarization verification remains a release
gate. One accepted request launches one process group with bounded streams,
deadline, TERM/KILL/reap, and no hidden replay.

## Migration status

Run the provider-free doctor:

```text
python3 plugins/agent-collab/migration_doctor.py --json
```

It inventories retired packages, reports host and descriptor state, and does
not invoke a provider or mutate the host. No daemon installation or runtime
setup step exists.

## Validation

```text
python3 scripts/build_skills.py --check
python3 scripts/build_marketplace.py --check
python3 scripts/build-changelog.py --check
python3 -m unittest discover -s tests -t . -v
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/check_release_consistency.py
python3 scripts/check-public-export-safety.py --active-tree
python3 scripts/secret_scan.py
git diff --check
```

Archive/release validation additionally requires the canonical final signed
runtime artifact and generated manifest. Public source work must not rebuild,
sign, notarize, or hand-edit either artifact.

## Contribution and release governance

Read `AGENTS.md` and `docs/public-governance.md`. User-visible changes use a
unique `changelog.d/` fragment; do not commit generated `CHANGELOG.md`.
Pull requests must include the repository compliance trace and the required
independent review for their tier.

The clean-public-repository invariant applies to the active tree, reachable
history, and release archive. If executor source, credentials, private paths,
or suspect native bytes appear, stop publication and follow `SECURITY.md`.

Public CI uses distinct GitHub-hosted runners, pins every external action to a
full commit SHA, runs CodeQL and Gitleaks, enables secret scanning, and uses
Dependabot for dependency update review.

After every other release task finishes, complete the
[documentation closeout](docs/architecture/repository-and-release.md#final-documentation-closeout).
The v6.0.1 closeout is recorded in the
[status and evidence snapshot](docs/architecture/status-and-evidence.md). Each
future closeout must likewise align the architecture handbook, this README,
and generated changelog evidence with the exact release without exposing
private executor recipes.

## License

The public repository and distributed package use the unmodified
[PolyForm Strict License 1.0.0](LICENSE), except that the derived portions of
`decision-map`, `prototype`, and `architecture-review`, plus the adapted
spec-fidelity and smell-baseline portions of `code-review`, and the adapted
decomposition guidance in `orchestrate` and `teamwork`, remain MIT-licensed
and carry the full MIT notice in each generated skill. Their pinned upstream
and per-file provenance is recorded in
[docs/third-party-skill-provenance.md](docs/third-party-skill-provenance.md).
Commercial use of the PolyForm-licensed material requires separate, explicit
written approval administered by Osumi Consulting LLC. See [NOTICE](NOTICE) and
[COMMERCIAL-LICENSING.md](COMMERCIAL-LICENSING.md) for the ownership and
approval boundary.
