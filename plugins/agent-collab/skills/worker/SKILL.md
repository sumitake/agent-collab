---
name: worker
version: 6.3.0
description: Use when the operator says "delegate this implementation," "generate a private patch," "use Grok for codegen," or "use Moonshot for frontend work." Also offer this when a bounded non-governance task needs output-only code generation without access to the caller checkout.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host, validates the semantic request, and verifies the co-packaged native manifest and wire descriptor. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. `provider_error` and `teardown_error` are attempt-local diagnostics: they invalidate only that request's artifact and evidence. They must not quarantine a route, exclude it from later selection, or establish route or provider unavailability. The caller must not automatically replay the failed request; a later caller-authorized request is a new attempt whose eligibility is recomputed from fresh readiness. The public request names one logical action and optional target agent; provider transport actions are internal descriptor data. For every repository action, pass the canonical `repo_root`. For document context, pass bounded `documents` and no repository source.

# Delegate bounded worker output

Use `codegen.repository` for ordinary code generation or
`frontend_codegen.repository` for frontend-affinity work. These are private-
repository patch actions, not read-only planning or governance.

Provide the canonical `repo_root`, bounded prompt, target agent only when
explicitly requested. The coordinator observes author lineage from the current
host; never supply it as a request field. Never send a model name, provider CLI
version, provider transport action, tool list, or raw command.
Send closed `quality_profile` and `effort_class` fields; use `standard` for
both unless the task justifies an economical or frontier profile.

The provider may inspect, edit, and test only the disposable copy. It returns a
binary-safe provider-only patch plus bounded summary and test claims. It never
applies the patch or mutates caller Git metadata. The primary reviews and
applies accepted changes, runs independent tests, and owns commits, PRs,
merges, and deployment.
