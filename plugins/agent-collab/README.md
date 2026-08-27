# agent-collab 6

`agent-collab` is one collaboration package with a closed semantic request
boundary and one co-packaged native runtime. Public callers choose a logical
action and source; they never choose a provider route, transport action, model,
binary, socket, lane, or lifecycle command.

Current repository source: **6.3.0**

Current published release: **6.2.4**
([`v6.2.4`](https://github.com/sumitake/agent-collab/releases/tag/v6.2.4));
the exact package members and provider-free runtime readiness were verified on
Claude, Codex, Antigravity, and Grok.

Version 6.3.0 adds private allowlist-only capture of typed terminal
coordinator failures after the response is written and flushed. It excludes prompts,
source paths/content, commands, raw provider streams, provider prose,
artifacts, credentials, and environment data. Capture failure cannot change
the response, provider authority, or no-replay contract; external filing is a
separately governed workspace operation. Invocation selectors are included
only after admission through the closed coordinator wire contract; rejected
raw request values are omitted. A private capture lock waits under a fixed
deadline and serializes capacity checks with publication across concurrent
coordinator processes, preserving ordinary concurrent evidence and the 10,000
unresolved-event hard bound. The workspace filer uses that same lock for local
state transitions but releases it before GitHub operations, and newly created
outbox directories are parent-fsynced before publication returns. Malformed request identifiers that cannot encode
as UTF-8 omit their optional digest without suppressing the failure event.
Plugin identity and request diagnostics are closed as well: the public plugin
version, runtime-manifest digest, recognized request-field names, unknown-field
count, and allowlisted validation difference may be retained, but no request
value or unknown field name is copied.
Version 6.2.4 adds a managed native Claude route through the
official structured CLI for `context.documents.intent` only. It returns
read-only document intent, is cost-last after eligible Gemini and Grok routes,
and does not make Claude eligible for review, governance, repository, or
code-generation actions. Host-owned asynchronous coordination remains a
separate surface. The signed descriptor retains 12 public logical actions and
now derives 15 transport actions and 19 valid action/source pairs across five
native carrier families. The released archive and all four installed roots were
verified byte-for-byte; readiness is provider-free and does not imply future
provider authentication or availability.

Version 6.2.3 adds bounded correction for uniquely identifiable one-edit
spelling errors in closed invocation tokens and ships signed provider runtime
`4.2.1` with provider-neutral CLI currency, effort, output, Gemini repository,
and Grok cancellation reliability repairs. It never corrects open prose,
aliases, or ambiguous values, and it never replays a provider request. Version
6.2.2 added a pinned clean-runner bootstrap for the mandatory runtime
manifest-schema gate and published the bounded TTY request framing,
conservative invocation recovery, and signed provider runtime `4.2.0` that had
been prepared for 6.2.1. Runtime 4.2.0 recovers an
eligible distinct route within the original invocation, publishes exact
schema-7 recovery criteria, hardens grounded carrier-output interpretation,
and adds per-class readiness diagnostics across Codex, Gemini/agy, Grok, and
OpenCode. It never replays a provider request. Version 6.2.0 advanced the
co-packaged native runtime to `4.1.0` (a governance-pool widening) and added the
public `project-estimation` skill. The
skill provides read-only-by-default, structured estimates for agent-led work and
a compact design/plan checkpoint; the skill itself does not alter provider
routing. A governed schema-2 `empirical-v3` bootstrap aggregate and its
schema-3 receipt are admitted for descriptive enhancement-duration estimates.
Greenfield and unpublished token, wait, rework, quota-delay, and cash metrics
remain typed unavailable; bootstrap confidence is never high.

General users should start with the public
[architecture handbook](../../docs/architecture/README.md) and
[lifecycle guide](../../docs/architecture/lifecycle-and-operations.md). This
file is the low-level package and coordinator reference.

## Skills

The package ships these 53 generated skills. Their `SKILL.md` files are the
authoritative invocation contracts; the
[capability map](../../docs/architecture/capabilities-and-workflows.md) groups
them by user outcome.

```text
agent-readiness              agent-runtime-status       ai-writing-auditor
architect                    architecture-review        autonomy-readiness
brainstorm                    chain                      chain-configurator
code-review                  compose-skills             context
data-engineer                debate                     decision-map
delegate                     dev-delegate               elixir-engineer
eval-engineer                go-engineer                 governance-review
hallucination-investigator   incident-responder         intent-check
knowledge-compile            kubernetes-specialist      learning-loop
llm-architect                logic-check                 merge-resolve
migration-doctor             mlops-engineer              orchestrate
postgres-engineer            project-estimation         project-knowledge
prompt-regression-tester     prototype                   qa-verify
red-team                     route                       rust-engineer
second-opinion               simulate-user               sql-engineer
sre-engineer                 start-inbox-monitor         teamwork
terraform-engineer           ui-to-code                  untrusted-audit
visual-review                worker
```

## Coordinator request

Send one JSON object on stdin to:

```text
python3 "<plugin-root>/coordinator.py"
```

For a noninteractive pipe or file, close stdin after the object; the exact body
is EOF-delimited. On a TTY, terminate the single object with a newline within
the bounded 120-second frame window; the coordinator responds without waiting
for the terminal to close. An automated PTY owner must wait until the slave has
entered noncanonical mode before transmitting, because bytes sent before the
Python process starts are still governed by the platform's canonical line
buffer. In either mode, only one object is consumed and one accepted request
starts at most one runtime attempt. Official skill and release invocations use
closed noninteractive stdin and have no PTY startup race.

The canonical request contains exactly these common fields:

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

For caller compatibility, legacy field names `action` and `route`, the closed
native `source` object, `operation: "invoke"`, missing/empty target, and ASCII
whitespace/case around an admitted token are normalized and reported in
`normalized`. A spelling error in an invocation-only closed token is corrected
only when exactly one canonical value is one substitution, insertion, deletion,
or adjacent transposition away. Zero or multiple matches remain typed
rejections before provider launch. Prompts, documents, paths, evidence,
provider/model/product aliases, transport actions, authority, and arbitrary
prose are never inferred or rewritten.

Runtime status uses one separate closed request. It has no prompt or source and
returns every logical action in one zero-inference snapshot:

```json
{"operation":"readiness","request_id":"runtime-status-1","quality_profile":"frontier","effort_class":"maximum","timeout_ms":120000}
```

## Direct runtime boundary

The workspace build emits one schema-4 manifest with wire schema 7, runtime
protocol 4, native contract 4, and provider runtime `4.2.1`. Schema 7 publishes
logical agents, model lineages, action-compatible targets, and effort floors;
request-bound occupied lineages and evidence anchors remain closed and
runtime-adjudicated. The wire revision records compatible descriptor evolution;
runtime protocol 4 remains the executable compatibility boundary. The manifest carries one
top-level closed `wire_contract` and its canonical `wire_contract_sha256`.
That descriptor is the only source for:

- the 12 logical actions;
- the 15 source-collapsed provider transport actions;
- the 19 currently valid action/source pairs;
- semantic request and typed response schemas;
- the four artifacts (`review_findings`, `governance_verdict`, `context_text`,
  and `private_patch`);
- the provider-neutral execution receipt;
- zero-inference readiness; and
- bounded diagnostics.

Artifact entries contain bundle membership and signing identity only. They do
not mirror action membership.

The released runtime 4.2.1 build adds the action-scoped Claude edge while
preserving protocol 4 and the closed authority model. It refreshes supported
CLI currency at build time and applies the same grounded-output tolerance
across all five native carrier families. Codex uses provider-default effort
when its native interface has no exact advertised tier. Gemini repository reads
use the permission-capable route, and Grok uses the supervised ACP route;
cancelled attempts remain retryable and never quarantine the route. Untargeted
selection may move to the next eligible distinct route before provider
execution, inside the same invocation; there is no provider replay, fallback
invocation, or authority substitution.

Claude uses the official structured CLI only for document-intent requests. The
route is read-only, source-bound to documents, and cost-last after Gemini and
Grok. It does not satisfy review, governance, repository, or code-generation
contracts and is therefore never selected for those actions.

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
never reflects unbounded or raw untrusted input back to the caller. Every
accepted compatibility normalization is recorded in `normalized`; nothing that
changes cost, depth, family, authority, or a security decision is rewritten.

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
12/15/19 counts. Active retired packages block direct routing; cache-only
residue is reported separately. Runtime readiness launches the installed
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

The public schemas and one exact, receipt-declared bootstrap handoff are in
`project-estimation-data/`. The handoff is production maintenance evidence but
is explicitly descriptive, not promoted calibration. Full semantics and
examples are in the [project-estimation architecture](../../docs/architecture/project-estimation.md).

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
