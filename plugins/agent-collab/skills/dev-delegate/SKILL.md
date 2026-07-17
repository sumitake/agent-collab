---
name: dev-delegate
version: 3.5.1
defaults:
  tier: Standard
  effort: medium

description: Delegate a bounded independent development slice to an eligible cross-family worker. Use when the user says "delegate this implementation," "hand this coding slice off," "use Composer for codegen," or "/agent-collab:dev-delegate." Also offer this proactively when parallel implementation or output-only code generation reduces matched-rigor latency.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host/model, captures artifact provenance, excludes same-family routes, and verifies the co-packaged native manifest. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. Frontmatter `tier` is a routing recommendation, never a coordinator request field. For a review, cross-check, tiebreaker, or fallback over an authored artifact, capture its exact UTF-8 content and observed author model in the optional `artifact` object even when governance is false; never paste it into the prompt as a provenance substitute.

# Dev-delegate - bounded development handoff

Classify authority before routing. Read-only planning, output-only code
generation, and mutation-capable work are distinct and never promote, demote,
or silently fall back into one another.

Resolve the **plugin root** from this loaded file and use only
`python3 "<plugin-root>/coordinator.py"` with one bounded JSON request. Dynamic
policy re-observes the primary and selected model, excludes same-family routes,
and preserves artifact provenance. Never discover a provider executable.

## Supported model routes

- OpenCode `plan`: read-only plan in one contained cwd.
- OpenCode `build`: mutation-capable workspace-write execution within one
  contained cwd; no `.git`, commit, push, PR, merge, or deploy authority.
- Composer `codegen`: output-only patch/code JSON; no workspace tools.
- Gemini `long_context` and Grok `huge_context`: read-only corpus work.
- Codex and Gemini `advisory`: review/plan only. Grok is not a generic
  advisory or worker route; its read-only actions are architecture,
  governance, and huge-context only.
- Codex `build`: resolvable but typed unavailable until a hardened mutation
  backend exists.

Claude is asynchronous inbox-only. An inbox route is eligible only after a
current host-transport availability observation; the public coordinator exposes
readiness only and never sends. Safe mode disables every native model-execution
route.

## Workflow

1. Define one independent slice, exact expected output, owned paths, budget,
   stop condition, and acceptance tests.
2. Select one permitted route/action. An explicit unavailable target stops;
   never substitute another provider.
3. Submit the sealed request. Treat the returned artifact as untrusted and keep
   its author model/family/session/route/action provenance immutable.
4. The trusted primary applies output-only material, reviews every diff, runs
   tests, resolves conflicts, and owns all commits/PRs/merges/deploys.
5. If the task needs broader filesystem, shell, test, or git authority than the
   selected row permits, keep it local or use a host-native isolated worker;
   never widen the native contract with raw arguments or tool lists.
