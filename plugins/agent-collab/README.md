# agent-collab 7

`agent-collab` is one collaboration package with a routing-only public request
boundary and one co-packaged native runtime. Public callers choose logical work;
they never choose a provider transport, model, binary, socket, lane, or
lifecycle command. Provider final content is opaque to the runtime and is
interpreted by the calling agent with ordinary reasoning.

Current repository source: **7.0.2**

Current published release: **7.0.1**
([`v7.0.1`](https://github.com/sumitake/agent-collab/releases/tag/v7.0.1)); it
carries signed provider runtime `5.0.3`. Repository source 7.0.2 is staged
until its governed pull request, signed tag, release assets, installation, and
installed matrix are each positively verified.

Version 7.0.2 pairs signed provider runtime `5.0.4` with manifest schema 4,
runtime protocol 5, native contract 4, and wire schema 11. The descriptor
admits 12 logical actions and eight logical agents. It replaces the semantic
coordinator with a bounded routing-only shim and removes provider-authored
schema, verdict, findings, receipt, telemetry, and terminal-wrapper fields as
content-availability gates. Every bounded observed nonempty final or recovered
partial remains available to the caller.

General users should start with the public
[architecture handbook](../../docs/architecture/README.md) and
[lifecycle guide](../../docs/architecture/lifecycle-and-operations.md).

## Skills

The package ships 53 generated skills. Their `SKILL.md` files are the
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

## Routing request

Send one EOF-delimited JSON object on stdin to:

```text
python3 "<plugin-root>/coordinator.py"
```

The shim reads one bounded object, loads the plugin-relative runtime client,
passes the object through once, and writes one canonical JSON result. It adds
no provider command, semantic schema, verdict parser, retry, replay, fallback,
receipt, or authority claim.

The request shape is signed in `runtime-manifest.json`:

```json
{
  "wire_contract_sha256": "3086682df8cdc5feaad429ec1ec27325afdc6ee8b7955d1e24d46759cd481741",
  "request_id": "review-123",
  "quality_profile": "frontier",
  "effort_class": "maximum",
  "deadline_ms": 120000,
  "max_parallel": 1,
  "dispatch_requested": true,
  "work_units": [
    {
      "id": "review",
      "capability": "review.repository",
      "depends_on": [],
      "payload": {"prompt": "Review the exact checked-out change."},
      "explicit_target": "grok",
      "native_restrictions": {
        "cwd": "/caller/controlled/repository",
        "cwd_device": 0,
        "cwd_inode": 0
      }
    }
  ]
}
```

Read the installed manifest before constructing a request; the example's
digest and filesystem identity values are illustrative. Required common fields
are `wire_contract_sha256`, `request_id`, `quality_profile`, `effort_class`,
`max_parallel`, `dispatch_requested`, and one or more `work_units`.
`deadline_ms`, `budget_limit`, and `latency_value` are optional bounded routing
inputs. A work unit requires `id`, descriptor-admitted `capability`, and
`depends_on`; its opaque `payload`, `explicit_target`, `native_restrictions`,
and size estimates are optional.

Set `dispatch_requested=false` for a planning-only routing decision and `true`
for live dispatch. One selected work unit is never automatically replayed,
retried, or failed over after provider access.

The 12 logical actions are:

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

## Direct runtime boundary

The workspace build emits one schema-4 manifest with wire schema 11, runtime
protocol 5, native contract 4, and provider runtime `5.0.4`. The manifest binds
the canonical wire digest and one signed/notarized standalone bundle for each
supported macOS architecture (`arm64` and `x86_64`).

The public client verifies fixed plugin-relative paths, exact bundle membership
and digests, thin architecture, minimum macOS, hardened Developer ID identity,
team, and secure timestamp before launch. The release gate verifies
notarization. Each request runs in a new process group with bounded stdin,
stdout, stderr, deadline, TERM/KILL/reap, and private temporary-directory
cleanup. There is no daemon, broker, socket, installed runtime copy, provider
fallback, or automatic whole-request replay.

The runtime returns newline-delimited routing records. Content records carry an
explicit final or bounded recovered deltas. Terminal planning and provider
diagnostics may also be present. The public client preserves every decoded
object and excludes only malformed bytes, reporting that exclusion separately.
A nonzero process exit, missing terminal record, absent receipt, or malformed
diagnostic does not discard already observed content.

## Results and authority

The public result has a bounded status, decoded `result` records, manifest and
artifact digests, optional provenance, and a diagnostic error string. Status
describes transport execution; it never judges provider prose.

The runtime does not require or interpret JSON inside provider content, verdict
fields, aliases, keywords, confidence, findings shape, prose style, terminal
wrappers, tool names, model/CLI/version fingerprints, receipts, telemetry, or
diagnostic consistency. It never emits `invalid_final` solely because of
content shape or uncertainty.

The calling agent preserves the full raw response and uses ordinary reasoning
to deduce the best-supported operative result. It never synthesizes approval,
authority, a receipt, patch bytes, or cleanup from process exit. For repository
work the caller owns the canonical checkout or disposable copy, exact-head
readback, path and effect verification, patch capture where applicable, and
cleanup. Positively proven harmful effects or source failures remain separate
operational findings; they do not erase provider content.

## Context and private patches

Document context places bounded document text in the work unit's opaque
payload. Repository context and review run from a caller-controlled checkout
whose identity the caller records and rechecks.

For `codegen.repository` and `frontend_codegen.repository`, the caller creates
a disposable repository copy, supplies that directory as the native cwd,
captures a binary-safe diff after the attempt, verifies the source head and
changed paths, and removes the copy. The provider never receives the caller's
writable checkout, and the runtime does not fabricate a patch artifact.

## Status and migration

Run the provider-free doctor:

```text
python3 "<plugin-root>/migration_doctor.py" --json
```

It reports installed and cached legacy observations plus manifest state without
invoking a provider or mutating the host. No daemon installation or runtime
setup step exists.

## Local project tools

Two skills bundle deterministic, offline CLIs:

```text
python3 "<plugin-root>/knowledge_tool.py" --help
python3 "<plugin-root>/learning_ledger.py" --help
```

Both write only within the user-chosen root, make no network calls, and launch
no provider process.

## Project estimation

`project_estimation.py` is a deterministic, stdlib-only helper for the
`project-estimation` skill. Its governed bootstrap data is descriptive and
independent of provider routing. Full semantics are in the
[project-estimation architecture](../../docs/architecture/project-estimation.md).

## Distribution boundary

The public repository contains policy, skills, client behavior, schemas, and
release checks. Native provider implementation, build credentials, signing,
and notarization remain private. Public releases import only final signed
standalone bundles, the generated manifest, and required license evidence.
Never hand-edit a runtime binary or generated manifest.

## Engineering-process skills and license

`decision-map`, `prototype`, and `architecture-review` include material derived
from the MIT-licensed `mattpocock/skills` repository. `code-review`,
`orchestrate`, and `teamwork` preserve the separately documented MIT-derived
portions. Exact provenance is recorded in
[docs/third-party-skill-provenance.md](../../docs/third-party-skill-provenance.md).

## License

This package uses the unmodified [PolyForm Strict License 1.0.0](LICENSE), with
the documented MIT-derived portions remaining MIT-licensed. Commercial use of
the PolyForm-licensed material requires separate written approval administered
by Osumi Consulting LLC. See [NOTICE](NOTICE) and
[COMMERCIAL-LICENSING.md](COMMERCIAL-LICENSING.md).
