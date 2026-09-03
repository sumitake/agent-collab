---
name: worker
version: 7.0.2
description: Use when the operator says "delegate this implementation," "generate a private patch," "use Grok for codegen," or "use Moonshot for frontend work." Also offer this when a bounded non-governance task needs output-only code generation without access to the caller checkout.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on stdin. Before constructing it, read the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit for this skill's logical action, with a bounded opaque payload. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.

# Delegate bounded worker output

Use `codegen.repository` for ordinary code generation or
`frontend_codegen.repository` for frontend-affinity work. These are disposable-
repository editing actions, not read-only planning or governance.

The caller creates a disposable repository copy, records its source head and
filesystem identity, and supplies that directory as the work unit's native cwd.
Provide a bounded prompt and an explicit target only when requested. Never send
a model name, provider CLI version, provider transport action, tool list, or raw
command.
Send closed `quality_profile` and `effort_class` fields; use `standard` for
both unless the task justifies an economical or frontier profile.

The provider may inspect, edit, and test only the disposable copy. The caller
preserves every nonempty raw or recovered response, captures the binary-safe
diff, verifies the recorded source head, and removes the copy. Provider
formatting and optional diagnostics do not gate content recovery. The primary
reviews and applies accepted changes, runs independent tests, and owns commits,
PRs, merges, and deployment. Never infer a patch or cleanup from process exit.
