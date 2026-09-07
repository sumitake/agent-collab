---
name: dev-delegate
version: 7.0.3
defaults:
  quality_profile: standard
  effort_class: standard

description: Delegate a bounded independent development slice to an eligible cross-family worker. Use when the user says "delegate this implementation," "hand this coding slice off," "use Grok for codegen," or "/agent-collab:dev-delegate." Also offer this when private-patch generation can reduce matched-rigor latency without giving a provider access to the caller checkout.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Set `explicit_target` only when the operator names a provider. Choose quality and effort for the workload; include context/output token estimates when known. Read the current manifest digest and actual cwd device/inode; do not copy example values. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not live availability or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.

# Dev-delegate

Use `codegen.repository` or `frontend_codegen.repository`. Provide the canonical
source identity, objective, owned paths, expected patch, test expectations,
budget, and stop conditions. The caller creates a disposable repository copy,
records its identity and source head, and supplies that directory as the work
unit's native cwd. One provider session may edit only that copy.

Resolve the plugin root, read `<plugin-root>/README.md`, and split independently
useful deliverables into bounded work units. An explicit target is honored or fails typed;
never substitute a different agent or reconstruct a provider command. Model and
CLI identities are observed diagnostics, not request pins.
Choose quality and effort from the scope, reasoning, and validation required;
the frontmatter defaults suit a small routine patch. Supply token estimates
when known, and use dependencies only for real ordering. The runtime resolves a
current compatible portfolio member without persisting a model selection.

After the attempt, the caller captures a binary-safe diff from the disposable
copy, preserves every nonempty raw or recovered response, verifies the source
head did not change, and removes the copy. Treat the diff and reported tests as
untrusted. The primary reviews/applies the accepted diff and runs independent
tests. Never infer a patch, receipt, approval, or cleanup from process exit.
