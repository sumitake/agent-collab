---
name: chain
version: 4.3.0
defaults:
  tier: Standard
  effort: medium

description: Execute a YAML-defined chain of skill invocations as a single reproducible, audited workflow — with template-driven input piping, schema validation, retry-on-malformed, conditional steps, gates (filesystem / semantic / tool), per-step worktree isolation, and JSONL audit logging. Use when the user says "run the X chain," "execute the X chain on Y," "chain these skills," "run this skill sequence," "run chain," "execute validate-<topic>," or names a chain defined in the workspace `chains/` or `drafts/sample-chains/` directories. Also offer this proactively when the active primary is about to manually run several skills in sequence on the same artifact, where the same sequence is likely to repeat — turning the ad-hoc flow into a chain YAML up-front buys reproducibility, audit trail, and consistent gate enforcement across runs.
---

# Chain — YAML-defined multi-step skill orchestration

When invoked, **the active primary IS the chain runtime**: parse the chain YAML, execute each step in declared order (delegating to the skill named in `runner: skill` steps or to the active primary's own reasoning for `runner: <primary>` steps), validate each step's output against its declared schema, evaluate gates, write the JSONL audit log, present the consolidated result.

This is a single-session, active-primary runtime. Chain YAML is supplied by the
operator or current project and uses package-neutral step references of the form
`agent-collab:<skill>@<version>`. Reject unsupported fields rather than
consulting an external private schema.

## When to use

- **The user explicitly asks for it** — "run the X chain," "execute the X chain on Y," "chain these skills," "run this skill sequence," "run chain," "execute validate-<topic>."
- **A multi-step verification workflow is already documented as a chain YAML** in `chains/` (production) or `drafts/sample-chains/` (in-progress prototypes).
- **High-stakes repeating work** where ad-hoc skill invocation risks inconsistency — release validation, change-management approval gating, compliance sweeps, regulated-workflow execution.
- **the active primary is about to manually invoke 3+ skills in sequence** on the same artifact, where the same sequence is likely to repeat. Codify it as a chain up-front; future runs get reproducibility + audit trail by construction.

## When to skip

- **One-off task with no repetition** — invoke the target skill(s) directly. The chain framing's overhead doesn't pay back.
- **Novel scope with no documented chain** — ad-hoc invocation per the operating workflow doc is right; if the pattern proves useful, codify it AFTER as a chain.
- **1–2 sequential skills with no schema validation or audit requirement** — direct invocation is simpler.

## Procedure

### 1. Locate and parse the chain YAML

From the user's invocation, identify the chain name. Search in priority order:

1. Project-scoped: `<project-root>/chains/<name>.yaml`
2. User-scoped: `~/Library/Application Support/agent-collab/chains/<name>.yaml`
3. Drafts: `<project-root>/drafts/sample-chains/<name>.yaml`

Read via the host's permitted file tool, parse the YAML, and validate the closed
fields described in this skill. Halt with a clear error if required fields are
missing.

### 2. Bind and validate inputs

Extract input values from the user's invocation (inline natural-language is the dominant case). If incomplete, ask ONE consolidated question listing all missing required fields. Apply declared defaults; type-check each value per its declared type. Build the `inputs` namespace for template expansion.

### 3. Initialize the audit log

Generate `run_id`: `<chain-name>_<ISO8601>_<6-char-random>`. Write the first JSONL line under the chain's `audit.log_path` (default `~/Library/Application Support/agent-collab/chain-logs/<chain-name>/<run-id>.jsonl`). Surface the path to the user upfront so the trace is locatable.

### 4. Execute steps in declared order

For each step:

- **Evaluate `run_if`** (if present) and skip if false.
- **Render input templates** — expand `{{ inputs.<name> }}`, `{{ steps.<id>.output }}`, `{{ steps.<id>.success }}` references per the workspace spec grammar.
- **Apply `isolation:` block** (if present) — create + enter the requested git worktree before dispatching the step.
- **Dispatch based on `runner:`**:
  - `runner: skill`: invoke via the Skill tool with the rendered `input:` map. The `<package>:<skill>@<version>` reference parses to plugin + skill + version; compute `skill_hash` of the version-pinned SKILL.md for the audit log.
  - `runner: <primary>` (the lowercased primary-agent identifier as declared in the chain spec): process the rendered `instruction:` directly via the active primary's own reasoning. Output formatted per the step's declared schema.
- **Validate output** against `output_schema` (`text` / `json` / `jsonl` / `structured-text` with `output_anchor` regex). On validation failure, retry per the step's `retry:` budget (default 1), then apply `on_failure:` (`halt` / `continue` / `escalate`).
- **Execute gates** (`gates:` block) in declared order — filesystem checks (file_exists, bash_exit_code, http_status, …), semantic checks (ai_cross_check, skill, json_schema), tool checks (mcp_call). Each gate's `on_fail:` (`halt` / `retry` / `warn`) is mandatory and applied individually.
- **Cross-model verification** (if `verification:` block opts in): re-dispatch the step on a different-family runner per the verifier-independence routing rule (see Family-aware routing below). Compare outputs; log divergence; do NOT auto-halt on divergence (it often surfaces real model disagreement worth seeing).
- **Cleanup** (deferred): when the NEXT step starts, run pending worktree cleanups per each prior step's `cleanup:` policy.
- **Log step completion** as JSONL.

### 5. Render and present final outputs

Expand templates in the chain's `outputs:` section against the accumulated `steps[*]` namespace. Compose a headline (succeeded / partial / failed / halted), the rendered outputs section, a step-results table, the audit log path, any warnings, and the cost-budget summary (managed model calls made + budget remaining if set). Write the final `chain_complete` JSONL entry.

## Family-aware routing (verifier-independence for cross-check steps)

When a chain has a `kind: cross_check` step or a semantic AI gate, the runner
must route through the shared dynamic policy. It recognizes Anthropic, Google,
OpenAI, xAI, Zhipu, and unknown lineage, excludes both immutable primary and
artifact-author families, and fails closed for unknown governance provenance.
The YAML does not expose a `verifier_family` override; reject one rather than
honoring a caller assertion.

This mirrors the orchestrator's Router rule and the verifier-independence block in `second-opinion`, `code-review`, etc. Bypassing it produces an audit log entry that reads as cross-checking but is structurally one-family.

## Skill-reference contract

Chain step skill references take the form `<package>:<skill>@<version>` (for
example, `agent-collab:second-opinion@4.1.1`). Retired namespaces and
family-prefixed skill names are invalid.

If a reference does not resolve in the current package, halt. Never search a
retired namespace or family-prefixed alias, and never reconstruct a raw
provider fallback.

## Anti-patterns

- **Executing a chain without validating the spec first** — silent failures defeat the verifiability goal.
- **Skipping the audit log to "save time"** — the log IS the verifiability evidence and is cheap to write.
- **Treating schema-validation failures as warnings and proceeding** — the chain's contract is broken; halt or retry, don't paper over.
- **Hand-editing the audit log post-hoc** — destroys provenance. Append-only.
- **Treating cross-model divergence as automatic failure** — divergence often surfaces real model disagreement worth surfacing; report it, don't halt.
- **Treating verifier tool-use claims as facts.** Models occasionally hallucinate tool-use mid-response (claim "I'll write to file X" without actually writing). Treat all tool-use claims as suggestions to verify, not actions taken. Use `gates:` `filesystem` checks for any step whose output asserts a side effect.
- **Using `chain` when a single direct skill invocation would do the same work** — overhead without benefit. Reserve chains for repeating workflows.
- **Promising state persistence across sessions** — be explicit that an
  instruction-native chain is single-session unless the current project saves
  its own audit artifact.
- **Pinning to a non-existent skill version** — silent fallback would defeat versioning. Halt-on-not-found, not silent-fall-through.
- **Bypassing the family-aware routing rule on cross-check steps** — same-family cross-checks defeat the independence guarantee that downstream consumers rely on.

## Limitations (instruction-native runtime)

the active primary is the runtime. This has trade-offs vs an external code-native orchestrator:

- **Verifiability is weaker than a code runtime**: execution depends on the active primary consistently following these instructions, not on deterministic code paths. For strict-precision long-term needs, an external runtime is the right answer.
- **Single-session ephemerality**: chain state lives in this conversation. A new session cannot resume a partially-run chain.
- **No true concurrency**: parallel-eligible steps execute sequentially. Batch-style parallelism from the spec is not available in this runtime.
- **Local audit logs only**: integrity is single-user trust. No cryptographic guarantees, no managed log store, no off-machine backup.
- **Retry / error handling is softer than code**: re-instruction prompts work but are not as rigorous as exception-based control flow.
- **Versioning enforcement is honor-system**: `skill_hash` is computed for the audit, but resolving `@version` references depends on the active primary correctly parsing and looking up the version. Halt-on-not-found is the safety mechanism.

For genuinely high-stakes production work (e.g., automated release validation gating real deploys), revive the external runtime path. For prototyping, exploring chain patterns, single-user verification workflows, and learning what chains actually need to do, this active-primary runtime works.
