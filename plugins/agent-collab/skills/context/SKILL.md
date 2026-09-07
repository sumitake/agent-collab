---
name: context
version: 7.0.3
defaults:
  quality_profile: frontier
  effort_class: maximum

description: Use when the user says "summarize these documents," "extract this corpus," "compare these sources," "map this repository," "trace this codebase," "audit these logs," or "/agent-collab:context." Also offer this when a bounded document set or repository must be read completely for grounded synthesis without mutation or governance authority.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Set `explicit_target` only when the operator names a provider. Choose quality and effort for the workload; include context/output token estimates when known. Read the current manifest digest and actual cwd device/inode; do not copy example values. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not live availability or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.

# Source-grounded context

Use the public `context` capability for read-only summarization, extraction,
comparison, synthesis, dependency/control-flow tracing, repository inventory,
log or transcript audit, and anomaly or gap identification. It is not a
governance verdict even when the prompt says “review” or “audit.”

## Choose exactly one source mode

- **Documents:** provide bounded UTF-8 `documents` objects containing only
  `label` and `content`. Select `context.documents.extract` for mechanical
  structured extraction or `context.documents.reason` for multi-source
  synthesis and reasoning.
- **Repository:** provide the canonical `repo_root` and exact
  `expected_repo_head`. Select
  `context.repository.extract` for inventory or tracing, or
  `context.repository.reason` for architectural or multi-hop synthesis.

Reject prompt-only requests, hybrid documents-plus-repository requests,
document paths/globs/file handles, unextracted binary input, and source escapes.
Repository mode runs from the sealed repository root; document mode runs from
an empty request-private document root.

## Request and result contract

Resolve the plugin root from this loaded file, read the routing schema in
`<plugin-root>/README.md`, and submit one work unit to
`python3 "<plugin-root>/coordinator.py"`. Use an `explicit_target` only when
the user named one; never construct a provider transport action.
Use `quality_profile="economical"` with `effort_class="minimal"` for mechanical
extraction, and raise these closed provider-neutral fields only when the task
actually requires more synthesis depth. Never name a model or provider member.

One accepted request launches one provider process and fresh session. Provider-
internal tool rounds or model calls may exceed one. There is no automatic whole-request replay after any model call and no malformed-output retry.
Preserve typed failures.

Preserve every bounded returned content frame or recovered partial. Interpret
the raw text with ordinary reasoning, then spot-check load-bearing claims
against the caller-owned document or exact repository source. Missing or
conflicting diagnostics do not hide content and do not create authority.

This capability is advisory and read-only. It never edits files, applies a
patch, creates governance evidence, or authorizes a provider command outside
the co-packaged runtime.
