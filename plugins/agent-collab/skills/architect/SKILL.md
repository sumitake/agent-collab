---
name: architect
version: 6.1.1
description: Request read-only architecture consultation for codebase analysis, system design, implementation planning, decomposition, or long-horizon strategy. Use when the user says "ask the architect," "have Grok design this," "architecture consultation," "plan this implementation," or "/agent-collab:architect." Also offer this before a substantial multi-system implementation where an independent architecture pass can reduce rework.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host, validates the semantic request, and verifies the co-packaged native manifest and wire descriptor. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. `provider_error` and `teardown_error` are attempt-local diagnostics: they invalidate only that request's artifact and evidence. They must not quarantine a route, exclude it from later selection, or establish route or provider unavailability. The caller must not automatically replay the failed request; a later caller-authorized request is a new attempt whose eligibility is recomputed from fresh readiness. The public request names one logical action and optional target agent; provider transport actions are internal descriptor data. For every repository action, pass the canonical `repo_root`. For document context, pass bounded `documents` and no repository source.

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
