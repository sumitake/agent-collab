---
name: intent-check
version: 7.0.6
defaults:
  quality_profile: standard
  effort_class: standard

description: Verify that the active primary's interpretation matches the operator's request before consequential planning or execution. Use when the user says "intent check," "confirm what I asked," "check for scope drift," or "/agent-collab:intent-check." Also offer this proactively when a major request has multiple constraints whose omission would materially change the result.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Set `explicit_target` only when the operator names a provider. Choose quality and effort for the workload; include context/output token estimates when known. Read the current manifest digest and actual cwd device/inode; do not copy example values. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not live availability or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.

# Intent check - independent interpretation comparison

Freeze two artifacts: the operator's original request and the active primary's
plain-language interpretation. Do not include an implementation plan; this
step checks understanding, not design quality.

Resolve the **plugin root** from this loaded file and invoke only
`python3 "<plugin-root>/coordinator.py"` with one normally untargeted
`context.documents.intent` work unit. Put the verbatim operator request and
plain-language primary interpretation in its bounded opaque payload. Use a
provider-free planning request to inspect known family evidence before dispatch;
set `explicit_target` only when the operator names a provider. The caller does
not construct an agent/action pair or invent primary/author exclusion fields.
Record the active-primary and interpretation-author families from session and
artifact evidence. Before dispatch, establish that the proposed reviewer has a
known family distinct from both; a planned route name alone does not prove it.

## Workflow

1. Quote the original request exactly, preserving negations and scope limits.
2. Write the interpretation as objective, in-scope work, out-of-scope work,
   constraints, success criteria, and stop conditions.
3. Put the two frozen documents in the payload and ask the reviewer to compare
   missed constraints, added scope, ambiguities, and a recommended interpretation.
   Do not add unsupported identity or family-exclusion fields.
4. Dispatch as independent governance only after the caller has established a
   known-distinct eligible reviewer. If that cannot be established, explain the
   missing lineage or selection evidence without dispatching a claimed
   independent review. After the response, verify its observed reviewer family
   differs from both recorded families and that it addresses the frozen
   documents. If family or source evidence is missing, retain the response as
   advisory and do not claim an independent intent check. Preserve the complete
   raw response; do not require a verdict line or alternate envelope.
5. Adjudicate the returned text as match, drift, or ambiguity. On a match,
   proceed. On drift, revise the interpretation and recheck only when a new
   request is separately justified. On ambiguity, ask the operator only the
   load-bearing question. Preserve and reason over the full raw route result;
   never replay it for formatting.

Never reconstruct a raw provider command, choose an explicit target unless the
operator names its provider, invoke Claude synchronously, or turn a route-local
typed failure into a claim that global governance is unavailable.
