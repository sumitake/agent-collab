---
name: migration-doctor
version: {{ skill_version }}
description: Use when the user says "migration doctor," "check old collaboration plugins," "verify agent-collab migration," or "/agent-collab:migration-doctor." Also offer this after installing or updating agent-collab, when direct runtime invocation is blocked, or when a retired package may still be active.
---

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
