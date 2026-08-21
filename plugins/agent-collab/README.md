# agent-collab 6

`agent-collab` is one collaboration package with a closed semantic request
boundary and one co-packaged native runtime. Public callers choose a logical
action and source; they never choose a provider route, transport action, model,
binary, socket, lane, or lifecycle command.

Current: **6.2.0** (source only; not tagged, released, installed, or activated)

Version 6.2.0 adds the public `project-estimation` skill. It provides
read-only-by-default, structured estimates for agent-led work and a compact
design/plan checkpoint; it does not alter provider routing or the co-packaged
native runtime. Its source is implemented, but the initial governed empirical
promotion failed: no production aggregate, pricing/quota snapshot, or
maintenance receipt exists in this branch. Release verification therefore
fails closed. v6.2.0 is not tagged, published, installed, activated, or
observed as loaded.

General users should start with the public
[architecture handbook](../../docs/architecture/README.md) and
[lifecycle guide](../../docs/architecture/lifecycle-and-operations.md). This
file is the low-level package and coordinator reference.

## Coordinator request

Send one JSON object on stdin to:

```text
python3 "<plugin-root>/coordinator.py"
```

Every request contains exactly these common fields:

```json
{
  "request_id": "review-123",
  "logical_action": "review.repository",
  "quality_profile": "frontier",
  "effort_class": "maximum",
  "target_agent": null,
  "timeout_ms": 120000,
  "prompt": "Review the requested change.",
  "repo_root": "/absolute/canonical/repository"
}
```

- `request_id` is 1–128 characters from `A-Z`, `a-z`, `0-9`, `.`, `_`, `:`,
  and `-`.
- `logical_action` is one of the 12 actions below.
- `quality_profile` is `economical`, `standard`, or `frontier`.
- `effort_class` is `minimal`, `standard`, or `maximum`.
  These fields express desired quality and depth; they never name a model.
- `target_agent` is `null` unless the user explicitly named an agent. It is a
  logical agent name, not a provider or model selector.
- The coordinator observes the current host family and adds `author_lineage`
  internally. A caller-supplied lineage is rejected.
- `timeout_ms` is 1–600000 (the enforced outer deadline the coordinator applies
  to the native process). A value over the cap is rejected with an actionable
  `timeout_ms_over_cap` error naming the `max`, not silently clamped.
- `prompt` is non-empty UTF-8, bounded to 1 MiB.
- Every repository action adds exactly one canonical absolute `repo_root`.
- Document-context actions replace `repo_root` with `documents`, an array of
  1–64 closed `{ "label", "content" }` objects whose total content is at most
  32 MiB.
- `architecture.conceptual` has neither repository nor document source.

The public actions are:

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

Old `route`, `action`, `row`, provider, model, native-effort,
development-shadow, and artifact-proof request fields are rejected. There is
no alias or translator.

Runtime status uses one separate closed request. It has no prompt or source and
returns every logical action in one zero-inference snapshot:

```json
{"operation":"readiness","request_id":"runtime-status-1","quality_profile":"frontier","effort_class":"maximum","timeout_ms":120000}
```

## Direct runtime boundary

The workspace build emits one schema-4 manifest with a positive-integer wire schema
revision, runtime protocol 4, native contract 4, and provider runtime `4.0.6`. The
wire revision records compatible descriptor evolution; runtime protocol 4 remains the
executable compatibility boundary. The manifest carries one
top-level closed `wire_contract` and its canonical `wire_contract_sha256`.
That descriptor is the only source for:

- the 12 logical actions;
- the 13 source-collapsed provider transport actions;
- the 17 currently valid action/source pairs;
- semantic request and typed response schemas;
- the four artifacts (`review_findings`, `governance_verdict`, `context_text`,
  and `private_patch`);
- the provider-neutral execution receipt;
- zero-inference readiness; and
- bounded diagnostics.

Artifact entries contain bundle membership and signing identity only. They do
not mirror action membership.

For each accepted request the public client:

1. Reads the fixed plugin-relative manifest without following links.
2. Validates the descriptor hash and derives all projections from it.
3. Selects the artifact matching the host (macOS arm64 or macOS x86_64) and
   verifies exact bundle membership, file digests, thin single-architecture
   Mach-O identity, minimum macOS, hardened Developer ID signature, team, and
   secure timestamp.
   Notarization is verified by the release gate, not by an online Apple lookup
   on each invocation.
4. Rechecks entrypoint identity immediately before spawning.
5. Starts the fixed entrypoint as a new process group with bounded stdin,
   stdout, and stderr.
6. Applies the shared deadline and explicitly sends TERM, then KILL if needed,
   and reaps the group.
7. Validates the exact success, ungrounded advisory, or failure response
   against the descriptor.

The verified bundle identity is cached only in the current Python process and
is invalidated when the manifest or entrypoint identity changes. There is no
daemon, broker root, Unix socket, launchd plist, installed copy, selector,
lane, setup command, fallback transport, or automatic whole-request replay.

## Results and authority

Coordinator results preserve a valid typed runtime status independently of the
native process's shell exit convention. Malformed coordinator input still exits
as a CLI failure. The closed runtime statuses
are `ok`, `advisory`, `invalid_request`, `unavailable`, `auth_error`, `quota_error`,
`capability_error`, `protocol_error`, `provider_error`, `output_limit`,
`timeout`, `cancelled`, and route-local `teardown_error`.

`provider_error` and `teardown_error` are attempt-local diagnostics. They
invalidate only that request's artifact and evidence; they do not establish
route or provider unavailability and must never quarantine or suppress the
route for a later request. They also do not authorize an automatic replay: a
later caller-authorized request is a distinct attempt whose route eligibility
is recomputed from fresh readiness.

Every non-usable response also carries two additive fields so a caller cannot
misread it and need not re-derive the request:

- `disposition` classifies the outcome into one closed set:
  `fix_request` (adjust the request: shape, target, action, effort, or size),
  `retry` (attempt-local or transient; a fresh request may succeed), `inspect`
  (overloaded; inspect the specific diagnostic before deciding), or
  `unavailable` (the only "route down" class). By construction `provider_error`,
  `teardown_error`, and `protocol_error` are never `unavailable`.
- `recovery` is a short human hint for that disposition.

A rejected request (`status: invalid_request`) additionally carries a specific
`error_code` (e.g. `timeout_ms_over_cap`, `unknown_logical_action`,
`quality_profile_invalid`, `request_not_closed`) and a bounded `detail` object
naming the offending field, its constraint, and the admitted values or the
required source, so the caller can correct it in place. Echoed values in
`detail` are ASCII-printable, length-bounded, and list-bounded, so a rejection
never reflects unbounded or raw untrusted input back to the caller. The only
in-place normalization is coercing an empty `target_agent` to `null` (recorded
in a `normalized` field); nothing that changes cost, depth, or a security
decision is rewritten.

A success contains the descriptor-defined artifact, runtime-owned evidence,
one provider-neutral execution receipt, and bounded diagnostics. Observed
agent/provider/model/executable/catalog/bundle identity is diagnostic only; it
does not create authority and is not a second receipt. There are no
provider-specific governance proofs and no self-hashed caller assertion.

An `advisory` result is safe substantive text from a clean attempt that lacked
sufficient native source evidence. It is explicitly ungrounded, carries no
artifact or receipt, and cannot authorize governance, merge, or source claims.
Route-local capability drift and unavailability retain fixed runtime-owned
assistance without retrying or substituting a provider after possible model
access.

One accepted request selects and launches one provider process and fresh
session. Provider-internal tool rounds may exceed one. After a model call, the
whole request is never replayed against another provider. An explicit
ineligible target fails typed rather than being silently replaced.

## Context skill

`context` is the sole source-grounded synthesis and extraction surface. It
supports exactly one source mode:

- `context.documents.extract`, `context.documents.intent`, or
  `context.documents.reason` with bounded inline documents; or
- `context.repository.extract` or `context.repository.reason` with one
  canonical repository root.

It is read-only and cannot create governance authority or apply changes.

## Status and migration

Run:

```text
python3 "<plugin-root>/migration_doctor.py" --json
```

The doctor is provider-free. It reports active/installed/cached legacy package
observations, host identity, manifest/descriptor state, and descriptor-derived
12/13/17 counts. Active retired packages block direct routing; cache-only
residue is reported separately. Runtime readiness launches this same 6.2.0
package's signed one-shot runtime, performs no model inference, and may use one
bounded catalog metadata process for each OpenCode lineage.

## Local project tools

Two skills bundle deterministic, stdlib-only CLIs that run offline inside
the user's project and never touch the coordinator or the native runtime:

```text
python3 "<plugin-root>/knowledge_tool.py" --help
python3 "<plugin-root>/learning_ledger.py" --help
```

`knowledge_tool.py` (the `project-knowledge` skill) maintains a
provenance-tracked `knowledge/` page layer; `learning_ledger.py` (the
`learning-loop` skill) maintains a `.learnings/` lesson ledger. Both write
only within the user-chosen `--root`, make no network calls, and launch no
provider process.

## Project estimation

`project_estimation.py` is a deterministic, stdlib-only helper for the
`project-estimation` skill. It consumes strict request, aggregate-prior,
pricing, and quota JSON documents and has no provider or network dependency:

```text
python3 "<plugin-root>/project_estimation.py" estimate --request REQUEST.json --prior PRIOR.json --pricing PRICING.json --quota QUOTA.json
python3 "<plugin-root>/project_estimation.py" reconcile --prior-result ESTIMATE.json --actual VERIFIED-ACTUAL.json --pricing PRICING.json
```

The estimate headline reports focused agent wall-clock, calendar elapsed and
waits, and current API-equivalent token cost. Actual marginal cash and quota
capacity remain detailed, separate, non-additive views. Pricing output includes
state and the last successful official retrieval date; stale evidence keeps
that historical date rather than claiming a fresh retrieval.

Ordinary runs write canonical JSON to stdout. `--out` requires explicit
persistence consent in the validated request or actual document. The skill is
also auto-invocable for formal implementation designs and plans on supported
hosts; `architect`, `orchestrate`, and `teamwork` compose the checkpoint
explicitly. Unsupported hosts use explicit invocation without claiming a
lifecycle hook.

The public schemas are in `project-estimation-data/`. Production aggregate,
pricing, quota, and receipt files are intentionally absent until a governed,
privacy-safe handoff passes release verification. Full semantics and examples
are in the [project-estimation architecture](../../docs/architecture/project-estimation.md).

## Distribution boundary

The public repository contains policy, skills, client behavior, schemas, and
release checks. Native provider implementation, build credentials, signing,
and notarization remain private. Public releases may import only the final
signed standalone bundle, closed generated manifest, and required license
evidence. Never hand-edit the runtime binary or generated manifest.

## Engineering-process skills and license

`decision-map`, `prototype`, and `architecture-review` are self-executed by the
active primary and add no coordinator or provider route. They contain material
derived from the MIT-licensed
[mattpocock/skills](https://github.com/mattpocock/skills) repository at pinned
commit `2ab95809`; those portions remain MIT-licensed and each generated
`SKILL.md` carries the full MIT notice. The pinned upstream and per-file map is
recorded in
[docs/third-party-skill-provenance.md](../../docs/third-party-skill-provenance.md).

`code-review` also preserves its spec-fidelity axis and subordinate,
evidence-bound Fowler smell baseline. Those adapted portions remain
MIT-licensed; the rest of the skill remains package-original. `Spec` and
`Smell` findings are reported separately from defect severity and do not
automatically enter merge-blocking aggregation.

`orchestrate` and `teamwork` retain conditional tracer-bullet and
expand–contract decomposition guidance. Those adapted portions likewise remain
MIT-licensed; they do not introduce a new provider route or orchestration
engine.

## License

This package uses the unmodified [PolyForm Strict License 1.0.0](LICENSE), with
the MIT-derived skill portions described above remaining MIT-licensed.
Commercial use of the PolyForm-licensed material requires separate, explicit
written approval administered by Osumi Consulting LLC. See [NOTICE](NOTICE) and
[COMMERCIAL-LICENSING.md](COMMERCIAL-LICENSING.md) for the ownership and
approval boundary.
