---
name: architect
version: {{ skill_version }}
description: Request read-only architecture consultation for codebase analysis, system design, implementation planning, decomposition, or long-horizon coding strategy. Use when the user says "ask the architect," "have Grok design this," "architecture consultation," "plan this implementation," "decompose this build," "analyze the system design," or "/{{ package_name }}:architect." Also offer this proactively before a substantial multi-system or long-horizon implementation where an independent architecture pass can reduce rework. This role never edits files, runs shell commands or tests, mutates a worktree, opens PRs, merges, or deploys.
---

# Architecture consultation

Use the unified coordinator's sealed architecture action for read-only analysis
and planning. Grok 4.5 is eligible only through this action (or the separately
sealed governance action); generic advisory, brainstorm, debate, QA, and worker
requests can never reach Grok.

## Workflow

Resolve the plugin root from this loaded file and read the exact request schema
in `<plugin-root>/README.md`. Submit either:

- `route=auto`, `action=architecture`, `governance=false`, with exact Gemini,
  Codex, and Grok candidate rows; or
- `route=grok`, `action=architecture`, `governance=false`, with the exact Grok
  architecture row for an explicit `target=grok` request.

Use `operation=execute`, a bounded prompt, and the observed primary snapshot.
When consulting on an authored design or plan, include its exact content and
observed author model in the optional artifact snapshot so that family is also
excluded. A frontmatter tier is not a coordinator field.

## Scope

Eligible work includes:

- read-only codebase structure and dependency analysis;
- system and interface design;
- implementation sequencing and milestone plans;
- decomposition into bounded work units;
- risk, failure-mode, and tradeoff analysis;
- long-horizon coding strategy.

The architecture result is advice or a plan only. The trusted primary owns
edits, shell/tests, integration, commits, PRs, merges, releases, deploys, and
secrets. Never reinterpret "worker" language as execution authority.

## Output contract

Ask for:

1. recommended architecture;
2. key invariants and threat boundaries;
3. implementation decomposition and dependency order;
4. verification plan;
5. unresolved decisions or assumptions.

If no eligible independent route is advertised, return typed unavailable. Do
not reconstruct a raw Grok command or silently reuse a same-family reviewer.
