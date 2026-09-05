---
name: worker
version: 7.0.3
description: Use when the operator says "delegate this implementation," "generate a private patch," "use Grok for codegen," or "use Moonshot for frontend work." Also offer this when a bounded non-governance task needs output-only code generation without access to the caller checkout.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Set `explicit_target` only when the operator names a provider. Choose quality and effort for the workload; include context/output token estimates when known. Read the current manifest digest and actual cwd device/inode; do not copy example values. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not live availability or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.

# Delegate bounded worker output

Use `codegen.repository` for ordinary code generation or
`frontend_codegen.repository` for frontend-affinity work. These are disposable-
repository editing actions, not read-only planning or governance.

The caller creates a disposable repository copy, records its source head and
filesystem identity, and supplies that directory as the work unit's native cwd.
Provide a bounded prompt and an explicit target only when requested. Never send
a model name, provider CLI version, provider transport action, tool list, or raw
command.
Send closed `quality_profile` and `effort_class` fields chosen for the workload.
Split independently useful deliverables into bounded work units, use dependencies
only for real ordering, and supply context/output token estimates when known.
Standard suits routine work; demanding implementation and validation need a
corresponding quality and effort choice.

The provider may inspect, edit, and test only the disposable copy. The caller
preserves every nonempty raw or recovered response, captures the binary-safe
diff, verifies the recorded source head, and removes the copy. Provider
formatting and optional diagnostics do not gate content recovery. The primary
reviews and applies accepted changes, runs independent tests, and owns commits,
PRs, merges, and deployment. Never infer a patch or cleanup from process exit.
