---
name: orchestrate
version: 3.0.1
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
typed-unavailable role; Composer can return output-only code material for the
trusted primary to apply and verify.
