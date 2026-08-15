---
name: migration-doctor
version: 6.0.4
description: Use when the user says "migration doctor," "check old collaboration plugins," "verify agent-collab migration," or "/agent-collab:migration-doctor." Also offer this after installing or updating agent-collab, when direct runtime invocation is blocked, or when a retired package may still be active.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host, validates the semantic request, and verifies the co-packaged native manifest and wire descriptor. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. `provider_error` and `teardown_error` are attempt-local diagnostics: they invalidate only that request's artifact and evidence. They must not quarantine a route, exclude it from later selection, or establish route or provider unavailability. The caller must not automatically replay the failed request; a later caller-authorized request is a new attempt whose eligibility is recomputed from fresh readiness. The public request names one logical action and optional target agent; provider transport actions are internal descriptor data. For every repository action, pass the canonical `repo_root`. For document context, pass bounded `documents` and no repository source.

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
