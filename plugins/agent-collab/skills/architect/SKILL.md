---
name: architect
version: 5.0.0
description: Request read-only architecture consultation for codebase analysis, system design, implementation planning, decomposition, or long-horizon strategy. Use when the user says "ask the architect," "have Grok design this," "architecture consultation," "plan this implementation," or "/agent-collab:architect." Also offer this before a substantial multi-system implementation where an independent architecture pass can reduce rework.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host, validates the semantic request, and verifies the co-packaged native manifest and wire descriptor. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. The public request names one logical action and optional target agent; provider transport actions are internal descriptor data. For every repository action, pass the canonical `repo_root`. For document context, pass bounded `documents` and no repository source.

# Architecture consultation

Use `architecture.repository` for repository-aware analysis and
`architecture.conceptual` only for genuinely conceptual consultation. A
repository request must include the canonical `repo_root` and succeeds only
with native inspected-path evidence; there is no repository-blind fallback.

Resolve the plugin root, read `<plugin-root>/README.md`, and submit one semantic
request through the public coordinator. Set `target_agent` only when the user
explicitly names one. Do not construct provider commands or transport actions.

Ask for the recommended architecture, invariants and threat boundaries,
dependency-ordered implementation units, verification plan, and unresolved
assumptions. The result is read-only advice. The primary owns edits, tests,
integration, commits, merge/release/deploy, and secrets.
