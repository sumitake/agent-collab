---
name: route
version: 7.0.6
description: Use when the operator says "ask Codex," "target Gemini," "target Grok," "target Moonshot," "target Zhipu," or explicitly names a collaboration agent. Also offer this when a semantic action needs a provider-neutral plan or a truthful typed availability decision.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Honor an operator-named provider with `explicit_target`. For an authorized independent review or governance task without an operator-named provider, also use that field to bind the caller-verified distinct reviewer selected by the caller or designated by the workflow. Carry the same target into planning and live dispatch; verify returned native lineage before accepting independence. Otherwise use normal untargeted routing. Choose quality and effort for the workload; include context/output token estimates when known. Read the current manifest digest and actual cwd device/inode; do not copy example values. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not live availability or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.

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

Honor an operator-named provider with the work-unit `explicit_target`; it is
honored or fails typed and is never silently replaced. For an authorized
independent review or governance task without an operator-named provider, also
use `explicit_target` to bind the caller-verified distinct reviewer selected by
the caller or designated by the workflow. Carry the same target into planning
and live dispatch; untargeted planning does not bind a later live request.
Otherwise use normal economic routing. The caller may use provider-free planning
to inspect known family evidence before dispatch. A route, provider name, status, receipt,
or self-assertion alone does not prove lineage. One selected provider attempt is
not replayed after a model call. The skill contains no provider command, model
name, version gate, or transport membership table. A route-local diagnostic
never triggers a hidden provider fallback. Preserve every nonempty raw or
recovered content record and interpret it with ordinary model reasoning;
structured fields are optional diagnostics and do not gate content availability.
