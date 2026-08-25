---
name: agent-runtime-status
version: {{ skill_version }}
{{ agent_runtime_status_defaults_block }}
description: Use when the user says "agent runtime status," "check agent runtimes," "list agent versions," "is a reviewer available," or "/{{ package_name }}:agent-runtime-status." Also offer this after a direct runtime request returns unavailable or before a multi-agent workflow whose action-scoped readiness has not been checked this session.
---

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
The 15 provider transport actions and 19 source-qualified pairs are diagnostics
derived from the co-packaged wire descriptor, not a second public routing
surface. Claude is reported as a managed candidate only for
`context.documents.intent` with document source; its host-owned asynchronous
coordination remains separate and is never inferred as another native route.
