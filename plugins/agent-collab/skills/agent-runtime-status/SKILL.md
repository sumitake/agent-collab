---
name: agent-runtime-status
version: 5.0.0
defaults:
  tier: Fast
  effort: low

description: Use when the user says "agent runtime status," "check agent runtimes," "list agent versions," "is a reviewer available," or "/agent-collab:agent-runtime-status." Also offer this after a direct runtime request returns unavailable or before a multi-agent workflow whose action-scoped readiness has not been checked this session.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host, validates the semantic request, and verifies the co-packaged native manifest and wire descriptor. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. The public request names one logical action and optional target agent; provider transport actions are internal descriptor data. For every repository action, pass the canonical `repo_root`. For document context, pass bounded `documents` and no repository source.

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
