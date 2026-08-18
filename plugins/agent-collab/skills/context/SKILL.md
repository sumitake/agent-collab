---
name: context
version: 6.0.6
defaults:
  quality_profile: frontier
  effort_class: maximum

description: Use when the user says "summarize these documents," "extract this corpus," "compare these sources," "map this repository," "trace this codebase," "audit these logs," or "/agent-collab:context." Also offer this when a bounded document set or repository must be read completely for grounded synthesis without mutation or governance authority.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host, validates the semantic request, and verifies the co-packaged native manifest and wire descriptor. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. `provider_error` and `teardown_error` are attempt-local diagnostics: they invalidate only that request's artifact and evidence. They must not quarantine a route, exclude it from later selection, or establish route or provider unavailability. The caller must not automatically replay the failed request; a later caller-authorized request is a new attempt whose eligibility is recomputed from fresh readiness. The public request names one logical action and optional target agent; provider transport actions are internal descriptor data. For every repository action, pass the canonical `repo_root`. For document context, pass bounded `documents` and no repository source.

# Source-grounded context

Use the public `context` capability for read-only summarization, extraction,
comparison, synthesis, dependency/control-flow tracing, repository inventory,
log or transcript audit, and anomaly or gap identification. It is not a
governance verdict even when the prompt says “review” or “audit.”

## Choose exactly one source mode

- **Documents:** provide bounded UTF-8 `documents` objects containing only
  `label` and `content`. Select `context.documents.extract` for mechanical
  structured extraction or `context.documents.reason` for multi-source
  synthesis and reasoning.
- **Repository:** provide the canonical `repo_root`. Select
  `context.repository.extract` for inventory or tracing, or
  `context.repository.reason` for architectural or multi-hop synthesis.

Reject prompt-only requests, hybrid documents-plus-repository requests,
document paths/globs/file handles, unextracted binary input, and source escapes.
Repository mode runs from the sealed repository root; document mode runs from
an empty request-private document root.

## Request and result contract

Resolve the plugin root from this loaded file, read the coordinator schema in
`<plugin-root>/README.md`, and submit one semantic request to
`python3 "<plugin-root>/coordinator.py"`. Use an explicit `target_agent` only
when the user named one; never construct a provider transport action.
Use `quality_profile="economical"` with `effort_class="minimal"` for mechanical
extraction, and raise these closed provider-neutral fields only when the task
actually requires more synthesis depth. Never name a model or provider member.

One accepted request launches one provider process and fresh session. Provider-
internal tool rounds or model calls may exceed one. There is no automatic whole-request replay after any model call and no malformed-output retry.
Preserve typed failures.

Accept success only when the result contains `{"text":"..."}` plus runtime-
owned evidence. Document mode must confirm a native read for every label and
return its hash and byte count without echoing source contents. Repository mode
must return native repository evidence and normalized inspected paths. For
high-stakes extraction, the primary spot-checks load-bearing claims against the
source.

If a clean attempt returns useful text without sufficient native source
evidence, preserve it only as an explicitly ungrounded advisory. It carries no
receipt, finding, governance, merge, or source-grounded authority.

This capability is advisory and read-only. It never edits files, applies a
patch, creates governance evidence, or authorizes a provider command outside
the co-packaged runtime.
