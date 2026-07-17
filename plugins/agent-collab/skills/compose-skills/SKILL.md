---
name: compose-skills
version: 3.5.2
description: Select a bounded, token-aware combination of collaboration skills or task lenses before execution. Use when the user says "compose skills," "which skills should I use," "use skill composition," "select a recipe," "combine these skills," or "/agent-collab:compose-skills." Also offer this proactively when a task plausibly needs multiple lenses, reviewers, or agents and would benefit from progressive disclosure, explicit fan-out limits, and a smallest-useful-skill plan before routing or loading full skill bodies.
---

# Compose skills - bounded multi-skill planning

Choose the smallest useful set of collaboration skills or lenses for a task. This skill is advisory: it plans how to combine skills, but it does not execute the selected skills, route agents, or override governance.

## Operating contract

- Prefer 1 primary lens, 1 supporting lens, and at most 1 verifier unless the task proves it needs more.
- Load metadata first. Load full skill bodies only when that skill is about to be used.
- Treat recipe files as planning hints, not routing policy. Agent routing stays with the workspace routing policy; model and effort selection stay with the model-effort policy.
- Keep token cost explicit. More agents, longer context, and chained reviews must have a reason tied to the task's risk or uncertainty.
- If the task involves untrusted external material, include `untrusted-audit` before any adoption, execution, hook installation, or workflow import.

## Workflow

1. Restate the task outcome in one sentence.
2. Identify the minimum lens set:
   - **Primary lens:** the skill that does the core work.
   - **Supporting lens:** a skill that supplies missing perspective, such as `brainstorm`, `long-context`, `delegate`, or `code-review`.
   - **Verifier lens:** a skill that checks the result, such as `qa-verify`, `logic-check`, `red-team`, or `second-opinion`.
3. If the workspace contains `workspace/config/skill-composition-recipes.yaml`, run or consult its validator before relying on a named recipe:
   ```sh
   python3 scripts/validate_skill_compositions.py --json
   ```
   If the file or validator is absent, continue with the contract above instead of inventing a registry.
4. Produce a compact plan:
   - selected skills or lenses
   - why each is needed
   - what context each will see
   - maximum fan-out or parallel agents
   - stop conditions
   - expected evidence before moving to the next skill
5. Execute only after the user has asked you to proceed, or when the original task already authorized execution.

## Output shape

Use this shape when the user asks for a skill-composition recommendation:

```text
Skill composition:
- Primary:
- Supporting:
- Verifier:
- Context budget:
- Fan-out limit:
- Stop condition:
- Execution order:
```

## Anti-patterns

- Loading every plausible skill body "just in case."
- Running multiple reviewers when a local test or one targeted verifier would answer the question.
- Letting a recipe decide the agent or model; recipes select lenses, not runtimes.
- Treating composition as mandatory. Simple tasks should stay simple.
- Using this skill to bypass security review of external repos, gists, blog posts, scripts, plugins, or prompt packs.
