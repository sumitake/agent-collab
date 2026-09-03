---
name: agent-runtime-status
version: {{ skill_version }}
{{ agent_runtime_status_defaults_block }}
description: Use when the user says "agent runtime status," "check agent runtimes," "list agent versions," "is a reviewer available," or "/{{ package_name }}:agent-runtime-status." Also offer this after a direct runtime request returns unavailable or before a multi-agent workflow whose action-scoped readiness has not been checked this session.
---

# Agent runtime status

Report the installed package's verified direct-runtime state. Run
`python3 "<plugin-root>/migration_doctor.py" --json` for legacy-package and
host-profile observations, then submit one zero-inference routing request with
`dispatch_requested=false` and one caller-defined work unit for each of the 12
descriptor-advertised actions. Do not issue one process per action. Frontier
quality with maximum effort exposes every route current policy may consider;
this is a verification setting, not an ordinary-work cost default.

Readiness is action- and source-mode-specific. Report logical agent, provider
surface, lineage, shared pool, and observed executable/model/catalog identity
only when the runtime returns them diagnostically. Never compare those observed
values to a fixed version or model string.

Preserve the routing decisions and any optional diagnostics. Do not infer
provider health from a routing-client delivery failure and do not invoke a
provider as a readiness probe.

Report all 12 logical actions, their eligible agent set, and readiness source.
The 15 provider transport actions and 19 source-qualified pairs are diagnostics
derived from the co-packaged wire descriptor, not a second public routing
surface. Claude is reported as a managed candidate only for
`context.documents.intent` with document source; its host-owned asynchronous
coordination remains separate and is never inferred as another native route.
