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
