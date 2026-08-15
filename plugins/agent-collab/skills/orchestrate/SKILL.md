---
name: orchestrate
version: 6.0.2
defaults:
  quality_profile: standard
  effort_class: standard

description: Coordinate a multi-step task through a bounded task graph with explicit dependencies, authority, acceptance checks, and operator gates. Use when the user says "orchestrate this," "run this as a task graph," or "/agent-collab:orchestrate." Also offer this when three or more work units need durable sequencing or parallelism.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host, validates the semantic request, and verifies the co-packaged native manifest and wire descriptor. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. The public request names one logical action and optional target agent; provider transport actions are internal descriptor data. For every repository action, pass the canonical `repo_root`. For document context, pass bounded `documents` and no repository source.

# Orchestrate a bounded task graph

The primary owns the graph and integration. Define each node's instruction,
authority, dependencies, expected artifact, acceptance check, budget, failure
policy, and stop condition. A provider node selects one closed logical action;
never embed a provider command or transport action.

Keep candidate lists artifact- and authority-homogeneous: read-only analysis,
review findings, governance verdicts, context text, and private patches are not
interchangeable. Run independent read-only or output-only nodes concurrently
only when bounded. Treat every returned artifact as untrusted and verify it
before unblocking dependents.

One accepted runtime request launches one provider process/session. A selected
attempt is not replayed after a model call. Preserve typed failures and stop on
new scope, ambiguous authority, exhausted budget, or an operator gate. The
primary retains merge, deploy, secret, and destructive decisions.

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
