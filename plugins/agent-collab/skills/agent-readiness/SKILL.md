---
name: agent-readiness
version: 4.2.1
description: Evaluate whether an agent, model, CLI, plugin, or role is ready for a proposed responsibility. Use when the user says "agent readiness," "is this agent ready," "can Codex be primary," "can Grok handle this role," "promote this agent," "evaluate this worker," "review model readiness," or "/agent-collab:agent-readiness." Also offer this proactively before assigning a new primary, reviewer, worker, delegate, headless, release, or merge-related role to Claude, Codex, Antigravity/Gemini, Grok, or a future agent.
---

# Agent readiness - role promotion review

Decide whether an agent is ready for a specific role. The unit of review is not "is this model good"; it is "is this agent-runtime-role combination ready for this responsibility."

## Readiness dimensions

- **Role fit:** primary author, reviewer, worker delegate, tiebreaker, release agent, headless runner, or specialist.
- **Capability evidence:** successful tasks, failed tasks, live smoke tests, benchmarks, and known weak spots.
- **Runtime health:** CLI availability, auth state, version currency, quotas, cost model, non-interactive behavior, and timeout handling.
- **Tool boundary:** filesystem, network, browser, MCP, shell, credentials, write access, and sandbox behavior.
- **Governance:** review independence, merge/tag authority, compliance trace obligations, escalation rules, and CODEOWNERS/operator gates.
- **Reliability:** retries, failure signatures, audit logs, resumability, handoff quality, and fallback agent.
- **Cost posture:** when to use a cheaper model, when the capability justifies cost, and when to avoid fan-out.

## Workflow

1. Name the exact role and scope being proposed.
2. Collect current evidence from local docs, runtime checks, CI, prior PRs, or recent handoffs.
3. Compare capability needs against known agent strengths and constraints.
4. Identify the minimum pilot or smoke test needed if evidence is incomplete.
5. Decide whether the agent can hold the role now, hold it with conditions, or should stay out of the path.

## Verdicts

- **APPROVE-ROLE:** ready for the named scope.
- **APPROVE-WITH-CONDITIONS:** ready only with explicit guardrails or a pilot.
- **DO-NOT-PROMOTE:** gaps are material enough to keep the role elsewhere.
- **NEEDS-OPERATOR:** authority or risk acceptance is outside agent scope.

## Output shape

```text
Agent readiness:
- Agent/runtime:
- Proposed role:
- Evidence reviewed:
- Strengths:
- Gaps:
- Required guardrails:
- Cost posture:
- Verdict:
```

## Anti-patterns

- Promoting an agent because it succeeded once on a task outside the target role.
- Confusing model capability with runtime readiness; auth, tools, and non-interactive behavior matter.
- Assigning review authority to an agent that is not independent from the author or artifact.
- Ignoring cost because the most capable model is available.
- Letting fallback routes silently pick a weaker or disabled agent without recording the decision.
