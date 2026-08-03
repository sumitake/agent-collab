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
`python3 "<plugin-root>/coordinator.py"` for the required logical actions.

Readiness is action- and source-mode-specific. Report logical agent, provider
surface, lineage, shared pool, and observed executable/model/catalog identity
only when the runtime returns them diagnostically. Never compare those observed
values to a fixed version or model string.

Preserve the runtime's typed status (`ok`, `unavailable`, `auth_error`,
`quota_error`, `protocol_error`, `capability_error`, `timeout`, `cancelled`,
`output_limit`, or `provider_error`). Do not infer provider health from a
coordinator delivery failure and do not invoke a provider as a readiness probe.

Report all 11 logical actions, their eligible agent set, and readiness source.
The 12 provider transport actions and source-qualified pairs are diagnostics
derived from the co-packaged wire descriptor, not a second public routing
surface. Claude remains host-owned asynchronous coordination and is never
invented as a headless provider route.
