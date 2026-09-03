---
name: route
version: 7.0.2
description: Use when the operator says "ask Codex," "target Gemini," "target Grok," "target Moonshot," "target Zhipu," or explicitly names a collaboration agent. Also offer this when a semantic action needs primary-family exclusion or a truthful typed availability decision.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on stdin. Before constructing it, read the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit for this skill's logical action, with a bounded opaque payload. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.

# Route a semantic collaboration request

Resolve the plugin root and read `<plugin-root>/README.md`. Submit one bounded
routing request to `python3 "<plugin-root>/coordinator.py"` using one work unit
whose `capability` is a descriptor-admitted logical action; never send a
provider route/action pair.

Every routing request names one `quality_profile` (`economical`, `standard`,
or `frontier`) and one `effort_class` (`minimal`, `standard`, or `maximum`).
These express desired quality and depth without selecting a model. The runtime
resolves a current compatible provider portfolio member and reports the
observed member and effective effort only as diagnostics.

The public actions are:

- `architecture.conceptual` and `architecture.repository`
- `review.repository` and `governance.repository`
- `codegen.repository` and `frontend_codegen.repository`
- `frontend_review.repository`
- `context.documents.extract`, `context.documents.reason`,
  `context.repository.extract`, and `context.repository.reason`

For repository actions, the caller runs the work unit in a caller-controlled
checkout or disposable copy and positively records and rechecks its source
identity. Document-context actions carry bounded document content in the opaque
payload. For code generation, the caller owns the disposable copy, captures the
binary-safe diff after the attempt, and verifies cleanup.

An explicit work-unit `explicit_target` is honored or fails typed; it is never silently
replaced. Automatic selection uses the runtime's compiled routing policy. One selected
provider attempt is not replayed after a model call. The skill contains no
provider command, model name, version gate, or transport membership table. A
route-local diagnostic never triggers a hidden provider fallback. Preserve
every nonempty raw or recovered content record and interpret it with ordinary
model reasoning; structured fields are optional diagnostics and do not gate
content availability.
