---
name: agent-runtime-status
version: 4.2.4
defaults:
  tier: Fast
  effort: low

description: Show availability and typed readiness for the unified collaboration routes. Use when the user says "agent runtime status," "check agent runtimes," "list agent versions," "is a reviewer available," or "/agent-collab:agent-runtime-status." Also offer this proactively after a managed route returns unavailable or before a multi-agent workflow whose runtime state has not been checked this session.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host/model, captures artifact provenance, excludes same-family routes, and verifies the co-packaged native manifest. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. Frontmatter `tier` is a routing recommendation, never a coordinator request field. For a review, cross-check, tiebreaker, or fallback over an authored artifact, capture its exact UTF-8 content and observed author model in the optional `artifact` object even when governance is false; never paste it into the prompt as a provenance substitute.

# Agent runtime status

Report the installed plugin's own verified state. Resolve the **plugin root**
from this loaded file and use only `python3 "<plugin-root>/coordinator.py"` for
native readiness plus `python3 "<plugin-root>/migration_doctor.py" --json` for
legacy-package and host-profile status. These files are co-packaged with the
skill; no external repository is required.

## Workflow

1. Run the migration doctor. Report its `broker_runtime` field separately from
   native artifact availability. Routing is blocked until retired selections
   are removed and the canonical selected broker lane passes its closed
   liveness proof.
2. Resolve the current primary/model/session from host evidence or explicit
   configuration. Do not infer the primary from installed CLIs.
3. Submit a bounded `readiness` request for each exact matrix row:
   Gemini `advisory|governance|long_context`; Codex `advisory`; OpenCode `plan|build`;
   Grok `architecture|governance|huge_context`; Grok 4.5 compatibility
   `composer/codegen` with `standard_codegen/medium` as the readiness profile.
4. Preserve typed results such as `unavailable`, `auth_error`, `quota_error`,
   `containment_error`, `timeout`, and `output_limit`. Do not flatten them into
   a generic failure or try another provider command.
5. Probe `inbox/async` only as non-governance readiness with the exact target
   row `{"target_id":"claude|antigravity","target_family":"anthropic|google","target_session_identifier":"..."}`.
   The id/family pair and nonblank target session must be trustworthy. Report
   it available only when the current host explicitly observes its async
   transport available and the target is not same-family; otherwise preserve
   the typed blocked or unavailable result. Public coordinator never sends.
   In safe mode every native model route is unavailable. Claude is always
   async inbox-only and is never invoked headlessly.

## Output

```text
agent-collab runtime:
- host: <primary id> / <family> / <model> / <session>
- package conflicts: <none | names>
- async inbox: <observed ready | typed unavailable; readiness only>
- native artifact: <verified | typed unavailable | invalid status>
- broker runtime: <ready | unavailable | integrity_error | unproven>
- gemini/advisory: <status>
- gemini/governance: <status + artifact-bound proof readiness>
- gemini/long_context: <status>
- codex/advisory: <status>
- opencode/plan: <status + observed author family>
- opencode/build: <status + observed author family>
- grok/architecture: <status>
- grok/governance: <status>
- grok/huge_context: <status>
- composer/codegen (Grok 4.5 compatibility): <status>
- codex/build: temporarily unavailable (separate mutation role)
```

Never list a fixed fleet from prose. The current model and author family are
observations, not plugin identities; OpenCode may change providers during a
session and must be re-observed on every request.
