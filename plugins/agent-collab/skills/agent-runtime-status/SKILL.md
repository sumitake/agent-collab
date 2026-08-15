---
name: agent-runtime-status
version: 6.0.3
defaults:
  quality_profile: frontier
  effort_class: maximum

description: Use when the user says "agent runtime status," "check agent runtimes," "list agent versions," "is a reviewer available," or "/agent-collab:agent-runtime-status." Also offer this after a direct runtime request returns unavailable or before a multi-agent workflow whose action-scoped readiness has not been checked this session.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON readiness request on stdin. Before constructing it, read the **Coordinator readiness request schema** in `<plugin-root>/README.md`; never invent fields. The public coordinator re-observes the active host, validates the zero-inference readiness request, and verifies the co-packaged native manifest and wire descriptor. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. This single call asks the runtime for the complete all-action readiness matrix and never invokes a model.

# Agent runtime status

Report the installed package's verified direct-runtime state. Run
`python3 "<plugin-root>/migration_doctor.py" --json` for legacy-package and host
profile observations, then submit zero-inference readiness requests through
`python3 "<plugin-root>/coordinator.py"` once for the complete action matrix:

```json coordinator-request
{"operation":"readiness","request_id":"runtime-status-1","quality_profile":"frontier","effort_class":"maximum","timeout_ms":120000}
```

The coordinator derives the author lineage from the current host. Do not add a
prompt, source, provider, action, target, model, or version field. Do not issue one request per action.
Frontier quality with maximum effort admits every route
whose own minimum is lower without guessing a per-action profile.

Readiness is action- and source-mode-specific. Report logical agent, provider
surface, lineage, shared pool, and observed executable/model/catalog identity
only when the runtime returns them diagnostically. Never compare those observed
values to a fixed version or model string.

Preserve the runtime's typed status (`ok`, `unavailable`, `auth_error`,
`quota_error`, `protocol_error`, `capability_error`, `timeout`, `cancelled`,
`output_limit`, or `provider_error`). Do not infer provider health from a
coordinator delivery failure and do not invoke a provider as a readiness probe.

Report all 12 logical actions, their eligible agent set, and readiness source.
The 13 provider transport actions and source-qualified pairs are diagnostics
derived from the co-packaged wire descriptor, not a second public routing
surface. Claude remains host-owned asynchronous coordination and is never
invented as a headless provider route.
