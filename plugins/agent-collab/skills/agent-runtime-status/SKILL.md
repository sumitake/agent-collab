---
name: agent-runtime-status
version: 7.0.3
defaults:
  quality_profile: frontier
  effort_class: maximum

description: Use when the user says "agent runtime status," "check agent runtimes," "list agent versions," "is a reviewer available," or "/agent-collab:agent-runtime-status." Also offer this after a direct runtime request returns unavailable or before a multi-agent workflow whose action-scoped readiness has not been checked this session.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Set `explicit_target` only when the operator names a provider. Choose quality and effort for the workload; include context/output token estimates when known. Read the current manifest digest and actual cwd device/inode; do not copy example values. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not live availability or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.

# Agent runtime status

Report the installed package's verified direct-runtime state. Run
`python3 "<plugin-root>/migration_doctor.py" --json` for legacy-package and
host-profile observations, then submit one zero-inference routing request with
`dispatch_requested=false` and one caller-defined work unit for each of the 12
descriptor-advertised actions. Do not issue one process per action. Frontier
quality with maximum effort exposes every route current policy may consider;
this is a verification setting, not an ordinary-work cost default.

This planning-only request proves descriptor eligibility, not executable
presence, authentication, quota, or live provider health. Report those as
unverified unless separate native evidence establishes them. Report logical agent, provider
surface, lineage, shared pool, and observed executable/model/catalog identity
only when the runtime returns them diagnostically. Never compare those observed
values to a fixed version or model string.

Preserve the routing decisions and any optional diagnostics. Do not infer
provider health from a routing-client delivery failure and do not invoke a
provider as a readiness probe.

Report all 12 logical actions and the actual returned route decisions. Do not
claim a complete eligible-agent set or carrier inventory when the result does
not enumerate it. A client, manifest, local permission, or protocol error is
not evidence that the provider is unavailable or needs authentication.
