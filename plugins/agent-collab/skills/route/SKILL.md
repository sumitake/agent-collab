---
name: route
version: 7.0.1
description: Use when the operator says "ask Codex," "target Gemini," "target Grok," "target Moonshot," "target Zhipu," or explicitly names a collaboration agent. Also offer this when a semantic action needs primary-family exclusion or a truthful typed availability decision.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host, validates the semantic request, and verifies the co-packaged native manifest and wire descriptor. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. `provider_error` and `teardown_error` are attempt-local diagnostics: they invalidate only that request's artifact and evidence. They must not quarantine a route, exclude it from later selection, or establish route or provider unavailability. The caller must not automatically replay the failed request; a later caller-authorized request is a new attempt whose eligibility is recomputed from fresh readiness. The public request names one logical action and optional target agent; provider transport actions are internal descriptor data. For every repository action, pass the canonical `repo_root` and its exact `expected_repo_head`. The signed artifact schema is the sole terminal output contract: prompts may state review criteria but must not append a `VERDICT:` line, alternate JSON envelope, or trailing prose. Preserve `invalid_final` as a terminal failure without salvage or replay. For document context, pass bounded `documents` and no repository source.

# Route a semantic collaboration request

Resolve the plugin root and read `<plugin-root>/README.md`. Submit one bounded
semantic request to `python3 "<plugin-root>/coordinator.py"` using a closed
`logical_action`; never send a provider route/action pair.

Every semantic request names one `quality_profile` (`economical`, `standard`,
or `frontier`) and one `effort_class` (`minimal`, `standard`, or `maximum`).
These express desired quality and depth without selecting a model. The runtime
resolves a current compatible provider portfolio member and reports the
observed member and effective effort only as diagnostics.

The public actions are:

- `architecture.conceptual` and `architecture.repository`
- `review.repository` and `governance.repository`
- `codegen.repository` and `frontend_codegen.repository`
- `frontend_review.repository`
- `context.documents.extract`, `context.documents.reason`,
  `context.repository.extract`, and `context.repository.reason`

Repository actions require the canonical `repo_root` and exact
`expected_repo_head`. Document-context actions
require bounded `documents` and reject a repository source. Code generation
returns a private-repository patch and never applies it to the caller.

An explicit `target_agent` is honored or fails typed; it is never silently
replaced. Automatic selection uses the runtime's compiled policy, authority,
source, artifact, readiness, and family-independence gates. One selected
provider attempt is not replayed after a model call. The skill contains no
provider command, model name, version gate, or transport membership table. A
route-local capability drift or unavailability result stays typed and includes
fixed runtime-owned assistance; it never triggers a hidden provider fallback.
