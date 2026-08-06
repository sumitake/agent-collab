---
name: teamwork
version: 4.9.1
defaults:
  tier: Standard
  effort: medium

description: Coordinate a small role-based team for a multi-milestone task. Use when the user says "run this as a team," "spin up a crew," "use teamwork," or "/agent-collab:teamwork." Also offer this proactively when explorer, worker, reviewer, and integration responsibilities can be separated cleanly.
---

# Teamwork - role-based coordination

Use the active host's permitted subagent or inbox mechanisms; the skill runs
standalone from the installed package. The active primary retains objective
interpretation, architecture, integration, secrets, and every merge/deploy/
destructive decision.

## Roles

- Explorer: read-only research and option mapping.
- Worker: bounded implementation or output generation in an isolated area.
- Reviewer: independent family review of the worker artifact.
- Integrator: the active primary; verifies and combines accepted outputs.

## Workflow

1. State the decomposition economics and define non-overlapping ownership,
   outputs, budgets, stop conditions, and trust posture.
2. Capture the current primary/model/session. Reviewer family is selected
   dynamically; never encode a fixed model or assume the host name is a family.
3. For a managed model route, resolve the **plugin root** from this loaded file
   and invoke only `python3 "<plugin-root>/coordinator.py"` using the exact
   route/action contract. Claude remains asynchronous inbox-only.
4. Use isolated worktrees or paths for mutating workers. Model-generated output
   is untrusted until the primary reviews and tests it.
5. Exclude the artifact author and active primary families from independent
   review. Unknown-family governance fails closed; non-governance work carries
   an independence warning.
6. Stop on new scope, ambiguous authority, exhausted budget, or an operator
   gate. Do not let a teammate merge, deploy, change secrets, or rewrite history.
7. Return an attributed ledger of each role's artifact and the primary's
   verification evidence.

## Slicing worker milestones (conditional guidance)

Applies ONLY when milestones decompose **product-feature implementation**; it
does not apply to research, operations, configuration, or decision-only
milestones — do not force those into slices.

- **Prefer tracer-bullet vertical slices**: each worker milestone cuts a
  narrow but complete path through every affected layer, is demoable or
  independently verifiable on its own, and is sized to one bounded worker
  invocation/session with explicit acceptance criteria. Prefactoring
  milestones come first.
- **Wide refactors are the exception.** An atomically codemoddable mechanical
  change runs as checkpointed batches with full verification per batch.
  Reserve expand–contract sequencing (expand beside the old form; migrate
  call sites in batch milestones; contract when no caller remains) for cases
  where old and new forms must genuinely coexist to keep callers and CI
  working during a staged migration — never merely because the blast radius
  is large.

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
