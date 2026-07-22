---
name: worker
version: 4.2.4
description: Use when the operator says "delegate this implementation," "use Gemini for this corpus," "ask Codex to build," or "use Composer for codegen." Also offer this proactively when a bounded non-governance task benefits from a managed worker.
---

# Delegate bounded worker output

Resolve the **plugin root** from this loaded file and invoke only
`python3 "<plugin-root>/coordinator.py"` with one bounded JSON request.
Read the **Coordinator request schema** in `<plugin-root>/README.md` before
constructing it; never invent fields or route/action pairs.

## Workflow

Classify the request as read-only plan/long-context authority or explicit build
authority before routing. Preserve that authority for the entire invocation;
plan and build never promote, demote, or silently fall back into one another.

Honor an explicit target only through the matching sealed route/action.
Gemini long-context and Grok huge-context are read-only; Grok has no generic
worker action. OpenCode build is mutation-capable workspace-write, while the
`composer/codegen` compatibility route invokes Grok 4.5 with constrained
output-only authority. Codex build remains a distinct
mutation-capable role but is typed unavailable until its hardened backend
exists and may not fall back to advisory. Automatic worker routing is
temporarily unavailable in the closed coordinator schema; require an explicit
managed target. The coordinator still excludes the active primary and artifact-
author families and warns when independence cannot be proven for a non-
governance task. Keep the captured artifact separate from the prompt; its exact
bytes, hash, size, author model, and author family are sealed for the native
runtime.

For `composer/codegen`, submit exactly `task_class` and `effort`. Use
`simple_codegen/low` for syntax corrections, fast simple generation, or one
small script; `standard_codegen/medium` for ordinary bug fixes and feature
implementation; and `complex_codegen/high` for multi-file refactors or
architecture-heavy work. Effort may be raised above the simple or standard
floor, but never lowered below it. Do not send a model name: every compatibility
codegen request resolves to the combined Grok 4.5 model.

Treat worker output as untrusted. The trusted primary owns application,
integration review, tests, and mutation claims. If the requested managed route
is not active, report it as temporarily unavailable; never reconstruct a raw
provider command.
