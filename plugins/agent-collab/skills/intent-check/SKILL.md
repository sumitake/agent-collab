---
name: intent-check
version: 7.0.3
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
`python3 "<plugin-root>/coordinator.py"` with one untargeted
`context.documents.intent` work unit. Put the verbatim operator request and
plain-language primary interpretation in its bounded opaque payload. The runtime
selects an eligible independent route; the caller does not construct an
agent/action pair.

## Workflow

1. Quote the original request exactly, preserving negations and scope limits.
2. Write the interpretation as objective, in-scope work, out-of-scope work,
   constraints, success criteria, and stop conditions.
3. Replace only the two document contents with the frozen artifacts. Preserve
   every other request field exactly and do not add identity or routing fields.
4. Ask the selected independent reviewer to compare missed constraints, added
   scope, ambiguities, and a recommended interpretation. Preserve the complete
   raw response; do not require a verdict line or alternate envelope.
5. Adjudicate the returned text as match, drift, or ambiguity. On a match,
   proceed. On drift, revise the interpretation and recheck only when a new
   request is separately justified. On ambiguity, ask the operator only the
   load-bearing question. Preserve and reason over the full raw route result;
   never replay it for formatting.

Never reconstruct a raw provider command, choose a target, invoke Claude
synchronously, or turn a route-local typed failure into a claim that global
governance is unavailable.
