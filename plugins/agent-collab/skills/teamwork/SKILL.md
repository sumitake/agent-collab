---
name: teamwork
version: 7.0.3
defaults:
  quality_profile: standard
  effort_class: standard

description: Coordinate a small role-based team for a multi-milestone task. Use when the user says "run this as a team," "spin up a crew," "use teamwork," or "/agent-collab:teamwork." Also offer this when explorer, worker, reviewer, and integration responsibilities separate cleanly.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Set `explicit_target` only when the operator names a provider. Choose quality and effort for the workload; include context/output token estimates when known. Read the current manifest digest and actual cwd device/inode; do not copy example values. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not live availability or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.

# Teamwork

Use the host's permitted subagent or coordination mechanisms. The primary owns
objective interpretation, architecture, integration, secrets, and merge/deploy
decisions.

- Explorer: read-only research or architecture.
- Worker: bounded `codegen.repository` or `frontend_codegen.repository`,
  returning a private patch.
- Reviewer: independent `review.repository`, `frontend_review.repository`, or
  `governance.repository` with the exact required authority.
- Integrator: the primary, which verifies and combines accepted outputs.

State decomposition economics, ownership, budgets, source roots, authority,
acceptance evidence, and stop conditions. Do not mix artifact types in one
candidate set. Treat every output as untrusted, keep mutating work isolated,
and return an attributed ledger.

## Delivery estimate checkpoint

When producing a formal implementation design or plan, after scope, completion
boundary, phases, dependencies, and gates are concrete and before final
presentation, invoke `project-estimation` once for the artifact scope. Attach
its compact `Delivery estimate` as `design_provisional` or
`implementation_plan`; attach typed `estimate_unavailable` if no defensible
range exists. A typed cost such as `unavailable_no_token_prior` must remain
visible; it must not become zero or a workflow failure. On an unsupported host,
use explicit invocation and state that
the automatic checkpoint is unavailable rather than claiming it ran.

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
