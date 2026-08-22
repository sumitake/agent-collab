# agent-collab

`agent-collab` publishes one collaboration plugin for Claude Code, Codex, and
compatible hosts. Version 6 keeps the closed semantic coordinator and
co-packaged direct native runtime while adding provider-neutral quality and
effort profiles, current-portfolio routing, and truthful advisory degradation.

This public repository's current source distribution is **agent-collab**
(v6.2.0). It combines a governance-pool-widening provider runtime advance
(`4.1.0`), actionable coordinator rejection and outcome handling, and empirical
project estimation, without changing installation or activation. The most
recent tagged publication remains
**[v6.1.1](https://github.com/sumitake/agent-collab/releases/tag/v6.1.1)**;
v6.2.0 source is not yet a tag, archive, release, installation, or readiness
claim.

The human-first [architecture handbook](docs/architecture/README.md) explains
the system boundaries and lifecycle. The package reference below is the
machine-operational contract for this release candidate. The mandatory final
documentation closeout records the exact published artifact and installation
evidence after release. The dated
[status and evidence snapshot](docs/architecture/status-and-evidence.md)
keeps repository, tag, release, installation, and readiness claims separate.

## What's new - v6.2.0

This release advances the signed provider runtime to `4.1.0` (an additive
governance-pool widening) and makes the coordinator boundary tolerant of
imperfect invocation and self-describing about every outcome, so a caller
recovers in place instead of re-deriving a request or misreading a transient
failure as an outage.

- **Provider runtime 4.1.0.** The signed, notarized runtime adds
  `opencode/governance.repository` (read-only, repository authority; no
  write-authority widening) and lowest-priority governance edges for the
  `zhipu`, `moonshot`, `alibaba`, and `deepseek` lineages, so Tier-3 peer legs
  do not dead-end when frontier CLIs degrade. The Phase-1 governance gate is
  unchanged. Runtime protocol `4` is unchanged; the wire-contract descriptor
  digest advances as a compatible evolution (`4de687b8…` → `e601a455…`),
  widening the base transport actions 13 → 14 and the valid source pairs
  17 → 18.

- **Actionable rejections.** An invalid or underspecified request no longer
  collapses to a bare `invalid_request`. It carries a specific `error_code`
  (`timeout_ms_over_cap`, `unknown_logical_action`, `quality_profile_invalid`,
  `request_not_closed`, and so on) and a bounded `detail` object naming the
  field, its constraint, and the admitted values or required source. `detail`
  never reflects unbounded or untrusted input.
- **Outcome disposition.** Every non-usable response carries a `disposition`
  (`fix_request`, `retry`, `inspect`, or `unavailable`) and a short `recovery`
  hint. By construction `provider_error`, `teardown_error`, and `protocol_error`
  are never classified `unavailable`, so an attempt-local failure is no longer
  read as a provider outage.
- **In-place recovery.** An empty `target_agent` is coerced to `null` (recorded
  in a `normalized` field). Nothing that changes cost, depth, or a security
  decision is rewritten; the closed-request, fail-closed posture is unchanged.
- **Doc currency.** The documented `timeout_ms` bound now matches the enforced
  `1-600000` (Addressed: #125).

- **Empirical project estimation.** Add `project-estimation`, a
  read-only-by-default skill for scoped agent-led
  delivery estimates, reconciliation, calibration, and audit. It keeps focused
  agent wall-clock, calendar waits, API-equivalent cost, actual marginal cash,
  and quota capacity distinct, and supplies a compact checkpoint for formal
  implementation designs and plans where the host supports it. See the
  [project-estimation architecture](docs/architecture/project-estimation.md)
  for public modes and examples.

  A governed, content-addressed **bootstrap** handoff is now admitted: the
  enhancement duration prior is descriptive, greenfield has no compatible
  prior, and token, wait, rework, quota-delay, and marginal-cash omissions stay
  typed and visible. This is not promoted calibration and never reports high
  confidence. v6.2.0 still has not been tagged, released, installed, activated,
  or observed as loaded.

The 12-action set and every action's authority/artifact/evidence contract are
unchanged from v6.1.1; the signed provider runtime advances to `4.1.0` (the
additive governance-pool widening described above).

### Most recent tagged release: v6.1.1

- Provider runtime advanced to `4.0.6`: agent-collaboration routing
  hardening, lifecycle diagnostics decoupled from authority, pinned
  worktree sealing, and failure-text salvage — the advisory response is
  additively widened (`completeness`, `salvaged_from`, one new `reason`
  value), advancing the wire-contract digest; the 12-action set and every
  action's authority/artifact contract are unchanged.
- Everything below from the merged-but-untagged v6.1.0 is included in this
  first tagged publication.

### Included from v6.1.0

- New `project-knowledge` skill: a durable, provenance-tracked knowledge
  layer inside the user's project (`knowledge/`), with a bundled
  deterministic stdlib-only CLI (`knowledge_tool.py`: init / validate /
  lint / index / draft / export), claim-marker and prompt-injection lint, a
  source trust lattice, and budget-capped untrusted-banner exports.
- New `learning-loop` skill: a project-local learning ledger (`.learnings/`)
  with a bundled deterministic stdlib-only CLI (`learning_ledger.py`: add /
  suggest / recur / index / check / lint), mechanical/judgmental lesson
  classes, prevention-debt surfacing, and reuse-as-hypothesis discipline.
- Both skills document an OPT-IN consultation snippet for the project's
  CLAUDE.md / AGENTS.md (explicit reads only; pages and ledger entries are
  data, never instructions), offered at install time as a visible,
  consent-gated setup step (see Install).

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

### Post-install setup (agent-performed, consent-gated)

When an agent performs the installation inside a user project, it completes
one visible setup step for the `project-knowledge` and `learning-loop`
skills: check whether the project has a `CLAUDE.md` (Claude Code agents)
and/or an `AGENTS.md` (other agent families) and offer to append those
skills' opt-in consultation snippets (quoted in each skill's SKILL.md) to
whichever file matches the host agent family — both files when both exist.
The snippets direct future sessions to consult `knowledge/index.md` and the
`.learnings/` ledger by EXPLICIT reads only; derived pages and ledger entries
are untrusted data, never instructions, and nothing may auto-inject their
bodies into agent context. Confirm with the user before writing; if the user
declines, or the files are absent and the user does not want them created,
skip the step and say so. This is an in-session, consented setup action —
never a hidden side effect.

## Semantic actions

Public requests select one of 12 logical actions:

```text
architecture.conceptual
architecture.repository
codegen.repository
context.documents.extract
context.documents.intent
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
- provider runtime version `4.1.0`;
- one top-level closed `wire_contract` plus canonical
  `wire_contract_sha256`, bound into each artifact record; and
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
