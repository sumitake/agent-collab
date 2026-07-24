---
name: route
version: 4.3.2
description: Use when the operator says "ask Codex," "target=gemini," "target=grok," "target=composer," or explicitly names a managed backend. Also offer this proactively when routing needs dynamic primary-family exclusion.
---

# Route a managed collaboration request

Resolve the **plugin root** from this loaded file and invoke only
`python3 "<plugin-root>/coordinator.py"` with one bounded JSON request.
Read the **Coordinator request schema** in `<plugin-root>/README.md` before
constructing it; never invent fields or route/action pairs.

## Workflow

Resolve the current primary context through the plugin-relative public coordinator,
then seal the request's role, authority, explicit-target flag, and artifact-
author provenance before selecting a backend.

For an explicit target, invoke only that managed target. If it is unavailable,
excluded as same-family, or incompatible with the sealed authority, return the
typed failure and report the capability as temporarily unavailable. Do not
substitute another backend.

For automatic general advisory routing, compute only the eligible Gemini/Codex
set after excluding the active primary and artifact-author families. Grok joins
only the separately sealed automatic architecture or governance action.
Refresh the selected model and family immediately before invocation. Preserve
read-only authority across attempts and attempt each target at most once.
Automatic worker routing is temporarily unavailable; require an explicit
managed worker target.

Seal only supported native contracts: Gemini advisory, governance, and long-context are
read-only; Codex advisory is read-only; OpenCode plan is read-only and OpenCode
build is mutation-capable workspace-write; Grok architecture, governance, and
huge-context are read-only; the `composer/codegen` compatibility route invokes
Grok 4.5 with output-only authority. Codex build
resolves as a separate mutation-capable role but is typed unavailable until the
hardened backend exists, never advisory. Safe mode makes all five model-
execution targets unavailable. A host async inbox is eligible only after an
availability observation and exposes readiness only; the public coordinator
never sends.

Managed provider execution uses canonical passwd HOME for reliable interactive
authentication state. This does not relax family exclusion, route authority,
the signed broker boundary, bounded lifecycle, or the prohibition on raw CLI
fallbacks.

Execution mechanics belong to the verified co-packaged native artifact. This
skill contains no provider command and authorizes no direct invocation.
