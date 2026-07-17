---
name: autonomy-readiness
version: 3.5.1
description: Evaluate whether an autonomous, always-on, scheduled, headless, or self-evolving workflow is ready to run safely. Use when the user says "autonomy readiness," "activation gate review," "is this workflow ready to run autonomously," "go/no-go autonomy," "always-on readiness," "headless operation review," or "/agent-collab:autonomy-readiness." Also offer this proactively before enabling background agents, recurring automations, auto-merge/self-evolution, external actions, unattended host runs, or any workflow that can continue without a human watching.
---

# Autonomy readiness - go/no-go review

Review an autonomous workflow before it is activated. This skill is a gate review, not an implementation shortcut.

## Readiness dimensions

- **Authority:** who approved the workflow, what it may do, and what it must not do.
- **Scope:** objective, trigger, stop condition, and maximum runtime.
- **Action policy:** read/write boundary, irreversible actions, external services, secrets, network, and code execution.
- **Evidence:** dry runs, tests, smoke checks, evals, observed burn-in, and reviewer verdicts.
- **Controls:** rollback, pause/kill switch, rate limits, budget limits, audit logs, alerts, and failure classification.
- **Context hygiene:** prompt-injection containment, progressive disclosure, source provenance, and memory/update rules.
- **Ownership:** who reviews outputs, who merges or tags, and what requires operator approval.

## Workflow

1. State the proposed autonomous behavior in concrete terms.
2. Identify every action the workflow can take without a live human.
3. Classify risk by blast radius, reversibility, cost, and credential exposure.
4. Check that each readiness dimension has evidence, not just assertions.
5. Require a dry-run or bounded pilot when evidence is weak.
6. Return one verdict and list blocking conditions.

## Verdicts

- **READY:** evidence and controls are sufficient for the stated scope.
- **READY-WITH-CONDITIONS:** safe only if named conditions are met first.
- **NOT-READY:** material gaps make activation unsafe or unreliable.
- **NEEDS-OPERATOR:** authority, risk acceptance, or approval is outside the agent's scope.

## Output shape

```text
Autonomy readiness:
- Workflow:
- Autonomous actions:
- Evidence reviewed:
- Missing controls:
- Token/cost posture:
- Failure and rollback path:
- Verdict:
```

## Anti-patterns

- Treating a passing unit test as readiness for autonomous operation.
- Enabling write actions before a dry run has proved the trigger and stop conditions.
- Hiding cost, context, or quota burn because the workflow is "important."
- Letting an agent self-approve expansion of its own authority.
- Running headless without a durable audit trail and a clean pause path.
