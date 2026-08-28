---
name: route
version: {{ skill_version }}
description: Use when the operator says "ask Codex," "target Gemini," "target Grok," "target Moonshot," "target Zhipu," or explicitly names a collaboration agent. Also offer this when a semantic action needs primary-family exclusion or a truthful typed availability decision.
---

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
