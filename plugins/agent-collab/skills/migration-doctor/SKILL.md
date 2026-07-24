---
name: migration-doctor
version: 4.3.3
description: Use when the user says "migration doctor," "check old collaboration plugins," "verify agent-collab migration," or "/agent-collab:migration-doctor." Also offer this proactively after installing or updating agent-collab, when provider routing is blocked, or when a retired package may still be selected from an installed plugin or cache.
---

# Migration doctor

Resolve the **plugin root** from this loaded file and run
`python3 "<plugin-root>/migration_doctor.py"`. The doctor and public
`coordinator.py` are co-packaged with the skills.
For any coordinator readiness request, first read the **Coordinator request
schema** in `<plugin-root>/README.md`.

For an activation release, use only the co-packaged managed setup surface:
`python3 "<plugin-root>/runtime_setup.py" status`, then `prepare`, and use
`login-grok` only when the status result reports that managed Grok
authentication is unavailable. The command accepts no provider, model, path,
environment, binary, tool, or raw argument overrides. Never invoke the native
runtime or a provider CLI directly.

## Workflow

Run the provider-free `migration_doctor.py` beside this skill's plugin root.
It reads local manifests, plugin directories, cache selections, Codex plugin
tables in `~/.codex/config.toml`, the runtime manifest, and current host-profile
evidence. It also verifies the canonical selected broker lane, immutable
artifact and manifest, launchd job, socket, and one closed liveness exchange.
That exchange never invokes a provider or returns provider output, and the
doctor never downloads an artifact.

Treat any installed or active legacy package as a hard routing conflict. Show
each observation's source host/state and the report's exact host-manager
install, verify, and uninstall actions. Cache-only residue is reported
separately. After cleanup, re-run the doctor before provider selection.
Treat `provider_routing=READY` as executable only when
`broker_runtime=ready`; manifest availability alone is not route readiness.

If the signed native artifact is absent, report native Gemini, Codex, OpenCode,
and Grok 4.5 routes, including `composer/codegen` compatibility, as typed
unavailable. An async inbox is eligible only
after a current host availability observation; the public coordinator reports
readiness only and never sends. Without that observation it is unavailable in
safe mode too. Never recommend reinstalling a retired package as a rollback.
