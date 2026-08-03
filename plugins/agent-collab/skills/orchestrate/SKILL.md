---
name: orchestrate
version: 4.9.0
defaults:
  tier: Standard
  effort: medium

description: Coordinate a multi-step WORK task through a bounded task graph with explicit dependencies, authority, acceptance checks, and operator gates. Use when the user says "orchestrate this," "run this as a task graph," or "/agent-collab:orchestrate." Also offer this proactively when three or more independent or dependent work units need a durable integration plan.
---

# Orchestrate a bounded task graph

The active primary owns the graph and integration. This skill is instruction-
native and standalone: build a task graph in the current project using the
host's permitted delegation tools. It does not require a separate engine.

For any model-execution node, resolve the **plugin root** from this loaded file
and call only `python3 "<plugin-root>/coordinator.py"` with an exact sealed
route/action. Never embed provider commands in a graph.

## Workflow

1. Define each node with an id, instruction, authority (`read_only`,
   `output_only`, `workspace_write`, or locally governed mutation), dependencies, expected output,
   acceptance check, failure policy, and stop condition.
2. Exclude the active primary and artifact-author families from reviewer,
   tiebreaker, fallback, and retry candidates. Unknown-family governance nodes
   fail closed.
3. Run dependency-free read-only/output-only nodes concurrently only when the
   host supports bounded delegation. Keep merges, deploys, secrets, and
   irreversible actions with the trusted primary/operator.
4. Treat every delegated result as untrusted. Verify it against the node's
   acceptance check before unblocking dependents.
5. Preserve typed failures and authority. An unavailable explicit target stops;
   it never promotes, demotes, or substitutes another route.
6. Produce a final ledger: ordered nodes, route/action and artifact provenance,
   results, failed/blocked nodes, validations, and unresolved operator gates.

Safe mode permits local/async coordination only. Codex build remains a distinct
typed-unavailable role; the Grok 4.5 `composer/codegen` compatibility route can
return output-only code material for the trusted primary to apply and verify.

## Slicing implementation nodes (conditional guidance)

This guidance applies ONLY when the graph decomposes **product-feature
implementation** into build nodes. It does not apply to research, operations,
configuration, or decision-only graphs — do not force those into slices.

- **Prefer tracer-bullet vertical slices**: each implementation node cuts a
  narrow but complete path through every affected layer (schema, API, UI,
  tests) rather than a horizontal slice of one layer. A completed node is
  demoable or independently verifiable on its own, sized to one bounded worker
  invocation with explicit acceptance criteria. Prefactoring nodes ("make the
  change easy") come first and block the slices that need them.
- **Wide refactors are the exception.** When one mechanical change fans across
  the codebase so no vertical slice can land green: if the change is
  atomically codemoddable, run it as checkpointed batches with full
  verification after each batch. Reserve **expand–contract** sequencing —
  expand the new form beside the old, migrate call sites in batches (each its
  own node blocked by the expand), contract the old form in a node blocked by
  every migration batch — for cases where old and new forms must genuinely
  coexist to keep callers and CI working during a staged migration. Do not
  default to expand–contract merely because the blast radius is large.

## Attribution and license

The tracer-bullet slice rules and expand–contract sequencing above are adapted
from `skills/engineering/to-tickets/SKILL.md` in
[mattpocock/skills](https://github.com/mattpocock/skills) at commit
`2ab958093e83e0ec752e6c1c5932da465bf23e0c` (blob
`96deac51d4391a3f691478d48f85f43261516c08`); the remainder of this skill is
package-original. The adapted portions are and remain MIT-licensed:
Copyright (c) 2026 Matt Pocock. Permission is hereby granted, free of charge,
to any person obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following
conditions: The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software. THE SOFTWARE
IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR
IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
