---
name: route
version: {{ skill_version }}
description: Use when the operator says "ask Codex," "target Gemini," "target Grok," "target Moonshot," "target Zhipu," or explicitly names a collaboration agent. Also offer this when a semantic action needs primary-family exclusion or a truthful typed availability decision.
---

# Route a semantic collaboration request

Resolve the plugin root and read `<plugin-root>/README.md`. Submit one bounded
routing request to `python3 "<plugin-root>/coordinator.py"` using one work unit
whose `capability` is a descriptor-admitted logical action; never send a
provider route/action pair.

Every routing request names one `quality_profile` (`economical`, `standard`,
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

For repository actions, the caller runs the work unit in a caller-controlled
checkout or disposable copy and positively records and rechecks its source
identity. Document-context actions carry bounded document content in the opaque
payload. For code generation, the caller owns the disposable copy, captures the
binary-safe diff after the attempt, and verifies cleanup.

An explicit work-unit `explicit_target` is honored or fails typed; it is never silently
replaced. Automatic selection uses the runtime's compiled routing policy. One selected
provider attempt is not replayed after a model call. The skill contains no
provider command, model name, version gate, or transport membership table. A
route-local diagnostic never triggers a hidden provider fallback. Preserve
every nonempty raw or recovered content record and interpret it with ordinary
model reasoning; structured fields are optional diagnostics and do not gate
content availability.
