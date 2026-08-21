---
name: architect
version: {{ skill_version }}
description: Request read-only architecture consultation for codebase analysis, system design, implementation planning, decomposition, or long-horizon strategy. Use when the user says "ask the architect," "have Grok design this," "architecture consultation," "plan this implementation," or "/{{ package_name }}:architect." Also offer this before a substantial multi-system implementation where an independent architecture pass can reduce rework.
---

# Architecture consultation

Use `architecture.repository` for repository-aware analysis and
`architecture.conceptual` only for genuinely conceptual consultation. A
repository request must include the canonical `repo_root` and succeeds only
with native inspected-path evidence. Safe substantive text without that
evidence may be returned only as an explicitly ungrounded advisory; it is
useful analysis but not repository authority.

Resolve the plugin root, read `<plugin-root>/README.md`, and submit one semantic
request through the public coordinator. Set `target_agent` only when the user
explicitly names one. Do not construct provider commands or transport actions.
Use `quality_profile="frontier"` and `effort_class="maximum"` for substantial
architecture work; these choose desired quality and depth, never a model ID.

Ask for the recommended architecture, invariants and threat boundaries,
dependency-ordered implementation units, verification plan, and unresolved
assumptions. The result is read-only advice. The primary owns edits, tests,
integration, commits, merge/release/deploy, and secrets.

## Delivery estimate checkpoint

When producing a formal implementation design or plan, after scope, completion
boundary, phases, dependencies, and gates are concrete and before final
presentation, invoke `project-estimation` once for the artifact scope. Attach
its compact `Delivery estimate` as `design_provisional` or
`implementation_plan`; attach typed `estimate_unavailable` if no defensible
range exists. On an unsupported host, use explicit invocation and state that
the automatic checkpoint is unavailable rather than claiming it ran.
