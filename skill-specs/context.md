---
name: context
version: {{ skill_version }}
{{ context_defaults_block }}
description: Use when the user says "summarize these documents," "extract this corpus," "compare these sources," "map this repository," "trace this codebase," "audit these logs," or "/{{ package_name }}:context." Also offer this when a bounded document set or repository must be read completely for grounded synthesis without mutation or governance authority.
---

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
- **Repository:** provide the canonical `repo_root` and exact
  `expected_repo_head`. Select
  `context.repository.extract` for inventory or tracing, or
  `context.repository.reason` for architectural or multi-hop synthesis.

Reject prompt-only requests, hybrid documents-plus-repository requests,
document paths/globs/file handles, unextracted binary input, and source escapes.
Repository mode runs from the sealed repository root; document mode runs from
an empty request-private document root.

## Request and result contract

Resolve the plugin root from this loaded file, read the routing schema in
`<plugin-root>/README.md`, and submit one work unit to
`python3 "<plugin-root>/coordinator.py"`. Use an `explicit_target` only when
the user named one; never construct a provider transport action.
Use `quality_profile="economical"` with `effort_class="minimal"` for mechanical
extraction, and raise these closed provider-neutral fields only when the task
actually requires more synthesis depth. Never name a model or provider member.

One accepted request launches one provider process and fresh session. Provider-
internal tool rounds or model calls may exceed one. There is no automatic whole-request replay after any model call and no malformed-output retry.
Preserve typed failures.

Preserve every bounded returned content frame or recovered partial. Interpret
the raw text with ordinary reasoning, then spot-check load-bearing claims
against the caller-owned document or exact repository source. Missing or
conflicting diagnostics do not hide content and do not create authority.

This capability is advisory and read-only. It never edits files, applies a
patch, creates governance evidence, or authorizes a provider command outside
the co-packaged runtime.
