---
name: dev-delegate
version: 7.0.2
defaults:
  quality_profile: standard
  effort_class: standard

description: Delegate a bounded independent development slice to an eligible cross-family worker. Use when the user says "delegate this implementation," "hand this coding slice off," "use Grok for codegen," or "/agent-collab:dev-delegate." Also offer this when private-patch generation can reduce matched-rigor latency without giving a provider access to the caller checkout.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on stdin. Before constructing it, read the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit for this skill's logical action, with a bounded opaque payload. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.

# Dev-delegate

Use `codegen.repository` or `frontend_codegen.repository`. Provide the canonical
source identity, objective, owned paths, expected patch, test expectations,
budget, and stop conditions. The caller creates a disposable repository copy,
records its identity and source head, and supplies that directory as the work
unit's native cwd. One provider session may edit only that copy.

Resolve the plugin root, read `<plugin-root>/README.md`, and submit one bounded
work unit through the routing runtime. An explicit target is honored or fails typed;
never substitute a different agent or reconstruct a provider command. Model and
CLI identities are observed diagnostics, not request pins.
Use `quality_profile="standard"` and `effort_class="standard"` by default;
raise either only for a genuinely more demanding patch. The runtime resolves a
current compatible portfolio member without persisting a model selection.

After the attempt, the caller captures a binary-safe diff from the disposable
copy, preserves every nonempty raw or recovered response, verifies the source
head did not change, and removes the copy. Treat the diff and reported tests as
untrusted. The primary reviews/applies the accepted diff and runs independent
tests. Never infer a patch, receipt, approval, or cleanup from process exit.
