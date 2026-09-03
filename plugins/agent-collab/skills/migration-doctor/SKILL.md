---
name: migration-doctor
version: 7.0.2
description: Use when the user says "migration doctor," "check old collaboration plugins," "verify agent-collab migration," or "/agent-collab:migration-doctor." Also offer this after installing or updating agent-collab, when direct runtime invocation is blocked, or when a retired package may still be active.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on stdin. Before constructing it, read the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit for this skill's logical action, with a bounded opaque payload. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.

# Migration doctor

Run `python3 "<plugin-root>/migration_doctor.py" --json`. The provider-free
doctor inventories retired packages, conflicting selections, host-profile
evidence, and the co-packaged runtime manifest. It never launches a provider,
downloads an artifact, installs a daemon, or mutates runtime state.

Treat an active retired package as a migration conflict. Report cache-only
residue separately and give exact host-manager cleanup commands only when the
doctor returns them. Re-run after cleanup.

Runtime readiness requires a verified manifest, closed wire descriptor/hash,
and eligible action-scoped readiness. No socket, plist, installed runtime copy,
or lifecycle selector is required. If the signed runtime is absent or mixed
with a different wire unit, report truthful typed unavailable; never recommend
reinstalling a retired provider package as rollback.
