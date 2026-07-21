---
name: teamwork
version: 4.2.0
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
