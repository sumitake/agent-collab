---
name: merge-resolve
version: 4.0.4
defaults:
  tier: Advanced
  effort: high

description: Use when a user asks to resolve a git merge conflict or conflicting patch, says "ai-merge" or "AI-resolve," when merge or rebase exits with conflict markers and next steps are requested, when parallel worktrees need integration, or when a chain diff targets a file being edited.
---

# Merge resolve — cross-family merge-conflict resolution, operator-gated by default

This skill is the inter-branch analogue of `chain`'s semantic gate (`kind: semantic, check: ai_cross_check`): a cross-family read on the two sides' intent + commit context, a proposed unified resolution as a diff, and an **operator-confirm gate** before any change touches the working tree. The cross-check is the engine; the operator-confirm and the validator gates are the safety net.

**The default is operator-confirm. Auto-apply is opt-in, gated by a multi-condition policy file, and refuses for high-sensitivity paths regardless of operator opt-in.** These are the operator's risk-acceptance posture; they are not stylistic prose, and the skill enforces them at runtime.

## When to use

**Explicit triggers** (user-typed): "resolve this merge conflict," "ai-merge," "merge with the reviewer," "have the reviewer help merge," "AI-resolve this conflict," "use the reviewer to merge this."

**Situational triggers** (proactive):

- A `git merge` or `git rebase` exited non-zero with conflict markers in the recent transcript.
- `git status` shows `Unmerged paths:` and the user asks anything about next steps.
- Worktree-fanout / parallel-agent flows need N parallel results to integrate back to a base branch.
- A chain step produces a diff destined for a file the user is currently editing (potential conflict surface).

## When to skip

- **The conflict is trivial** (whitespace-only, deterministic merge of a generated file) — let `git mergetool` or the user's editor handle it; the cross-check overhead is not worth it.
- **The user wants the AI to *commit* and *push* the merge** — out of scope. This skill ends at "applied to working tree, operator confirms"; commit + push are the operator's actions.
- **The conflict is in `forbidden_paths` (defined below) and the user wants auto-apply** — refuse and surface; require operator-confirm regardless of any auto-apply opt-in.

<!-- verifier-independence:start -->
## Verifier independence (functional contract)

A review is independent only when its observed author family differs from both
the immutable primary snapshot and artifact-author snapshot. The shared policy
recognizes Anthropic, Google, OpenAI, xAI, Zhipu, and genuinely unknown lineage;
OpenCode itself is a transport, not a family. Resolve through `coordinator.py`
immediately before every call. Governance fails closed when either snapshot is
unknown or no distinct-family advisory route is eligible. Non-governance work
may proceed only with an independence warning. Claude is async inbox-only.
<!-- verifier-independence:end -->

## Inputs

| Input | Required | Type | Description |
|---|---|---|---|
| `conflict_files` | yes | list[path] | Files with conflict markers (or a patch + base ref) |
| `base_ref` | yes | string | Common ancestor ref (e.g., `main`) |
| `intent_a` | optional | string | Free-form description of side A's goal (defaults to commit message(s) on side A) |
| `intent_b` | optional | string | Free-form description of side B's goal |
| `auto_apply` | optional, default `false` | bool | If `true`, skip operator-confirm — RESERVED for non-interactive CI with strict preconditions (see Safety constraints) |

If the operator only said "resolve this conflict" without listing files, START with `git status` via Bash to identify the conflicted files; ask one consolidated question if any required input remains unclear.

## Procedure

### 1. Verifier-independence check

Per the section above. If both sides are the active primary-authored, proceed; otherwise switch the independent-resolver direction or refuse if cross-family independence is required.

### 2. Hunk extraction

For each file in `conflict_files`:

1. Read the file via the Read tool.
2. Parse conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).
3. Build a structured `Conflict` record per hunk: file path, line range, side-A lines, side-B lines, ±20 lines of surrounding context.
4. If a file has no conflict markers (listed but already resolved), skip and report.

### 3. Context gather

For each side, collect:

1. Commit message(s) introducing the hunk on each branch (`git log -p <base_ref>..<side_ref> -- <file>` or `git blame` on the conflict lines).
2. The pre-merge file state on each side (downstream-impact analysis).
3. The base-ref version of the file (`git show <base_ref>:<file>`).

If `intent_a` / `intent_b` were not supplied, derive them from the commit messages as one-sentence summaries per side.

### 4. Cross-check prompt

Submit the sealed merge-review role through `python3 "<plugin-root>/coordinator.py"` with
`effort='high'` in every eligible advisory row and no `tier` request field. Central policy chooses an eligible
independent reviewer. The prompt forces a **disagreement-first** output
structure; the six-section schema is a functional contract:

```
Two branches modified the same region. Produce a unified resolution OR refuse if the change is semantically incompatible. Output ONLY these six sections — no preamble, no closing, cap 500 words total:

1. INTENT-A SUMMARY: <one sentence>
2. INTENT-B SUMMARY: <one sentence>
3. COMPATIBILITY: COMPATIBLE | INCOMPATIBLE | NEEDS-HUMAN — <one-sentence reason>
4. PROPOSED RESOLUTION (if COMPATIBLE): a unified diff block, fenced as ```diff
5. RISKS / FAILURE MODES: bulleted
6. CONFIDENCE: H | M | L — <one-sentence reason>

--- HUNK ---
{structured hunk + commit-context + surrounding-±20-lines}
```

**Retry-on-malformed.** If the response does not contain all six numbered sections, retry exactly once with: "Previous response did not include all six required sections. Re-emit strictly per the template above, no preamble." If the second attempt is also malformed, surface to operator and refuse to proceed.

### 5. Operator-confirm gate (DEFAULT)

UNLESS `auto_apply=true` AND **all** the auto-apply preconditions in Safety constraints below are met, present the proposed resolution as a clear diff with the cross-check's six sections rendered for the operator. The operator chooses:

- **`apply`** — apply the resolution to the working tree
- **`apply-and-amend`** — apply AND amend the in-progress merge commit (only valid mid-merge)
- **`reject`** — discard the proposal; leave conflict markers in place for manual resolution
- **`revise <free-form>`** — re-run Step 4 with the operator's additional instruction prepended to the prompt

Empty / ambiguous operator responses default to **`reject`** (safe choice).

### 6. Apply (only on `apply` / `apply-and-amend`)

1. `git apply --3way --check` to verify the patch applies cleanly.
2. If the check fails, fall back to in-place file replacement (Read → modify conflicted region → Write).
3. If the in-place replacement produces a syntactically invalid file (compiler / parser detects), surface to operator and refuse to proceed.
4. Verify no conflict markers remain after apply (re-Read; no `<<<<<<<` / `=======` / `>>>>>>>`).

### 7. Post-apply validation (via `gates:` block — operator-defined)

If invoked from inside a chain step, the calling step's `gates:` block defines the post-apply validators. Typical operator-configured validators:

- A `kind: filesystem, check: bash_exit_code` running the project's test suite (`pytest -q`, `go test ./...`, `npm test`, etc.), `on_fail: halt`.
- A `kind: semantic, check: ai_cross_check` verifying the applied resolution preserves both sides' intent without semantic loss, `on_fail: halt`.

Invoked standalone (not from a chain), Step 7 is informational — surface the operator a suggested validator set + offer to run the project-detected test runner via Bash and report the exit code.

## Safety constraints (NON-NEGOTIABLE)

These are runtime-enforced by the skill. They are not stylistic suggestions; the skill refuses to proceed past them.

- **Never auto-apply without operator-confirm by default** (`auto_apply` defaults to `false`).

- **`auto_apply=true` preconditions (ALL four required, no exceptions)**:

  1. **An operator-pre-approved validator-policy file is present** at `.claude/merge-resolve-policy.yaml` (project-scoped) OR `~/.claude/merge-resolve-policy.yaml` (user-scoped). The policy file's *presence* is the operator's signed acknowledgment of the auto-apply opt-in; the skill refuses auto-apply if the policy file is missing.

     **Caveat — presence-checked, not substance-checked**: the skill verifies the calling chain step's `gates:` block contains each `required_gates:` entry from the policy (by kind + check). It does NOT verify the gate's substance is meaningful — an operator could configure `bash_exit_code: { command: "true" }` to satisfy the letter of the policy while bypassing the actual test suite. Substance is the operator's responsibility.

     The current project's policy file is authoritative. At minimum it declares:
     `enabled`, `required_gates`, `min_confidence` (default `H`), and
     `forbidden_paths`; reject unknown policy fields.

  2. **The cross-check's `CONFIDENCE` must equal the policy's `min_confidence`** (default `H`). `M` or `L` falls back to operator-confirm regardless of `auto_apply`. A confident-but-wrong automated merge is a high-risk failure mode; this is the policy's hard line.

  3. **The conflicted file MUST NOT match any pattern on the policy's `forbidden_paths` list.** Default forbidden paths cover authentication / secrets / migrations / schema / configuration / environment files — i.e., the surfaces where an LLM-merge mistake has the worst blast radius. Operators extend the list for project-specific sensitive surfaces (HIPAA-PHI, PCI-DSS-cardholder-data, regulated-trading code, dosing calculations, etc.). The default list at minimum: `migrations/**`, `**/secrets/**`, `.env*`, `**/auth*`, `*.sql`.

  4. **The calling chain step's `gates:` block MUST include at minimum each `required_gates:` entry from the policy file.** If any required gate is missing, refuse auto-apply.

- **Never resolve `COMPATIBILITY: INCOMPATIBLE` or `NEEDS-HUMAN` verdicts automatically.** Surface to operator with the verifier's reasoning and refuse.

- **Never `git push` from this skill.** Resolution applies to working tree only; push is the operator's call.

- **Never `git commit` from this skill** (the `apply-and-amend` operator choice is the only commit-touching action, and only amends the in-progress merge commit).

- **Conflict-marker integrity check.** After any apply, re-Read the file and confirm no `<<<<<<<` / `=======` / `>>>>>>>` markers remain. If they do, the apply silently failed — refuse to mark the merge resolved and surface to operator.

### Known inherent risks (acknowledged, mitigated, not eliminated)

The design fundamentally assumes a language model can reliably infer the semantic *intent* of two conflicting changes. This is a hard problem. A passing test suite does not prove a resolution preserves both sides' intent — tests may have gaps around the specific logic being merged. These risks are inherent to the LLM-merge problem class, not introduced by this skill's design.

Mitigations:

- Operator-confirm default (the single biggest one).
- Multi-condition auto-apply preconditions (policy file + min_confidence + forbidden_paths + required_gates).
- `CONFIDENCE: H` floor.
- Cross-family verifier-independence (enforced).
- Post-apply validator gates (operator-defined).

These shift residual risk down but do not eliminate it. Operators adopting `auto_apply=true` accept the residual risk explicitly via the policy file's presence-as-acknowledgment.

### Suggested rollout: shadow-mode first

For the first 10–20 real merges, run with the policy file present but `shadow_mode: true`. The runner logs the would-be auto-apply decision and compares against the operator's manual choice. After high agreement, flip `shadow_mode: false`. (Shadow-mode is a v0.2 pattern in the workspace spec doc; v0.1 ships with operator-confirm-default and no shadow-mode infrastructure.)

## Examples across domains

| Domain | Conflict scenario | Why this skill fits |
|---|---|---|
| Backend / web | Two PRs both touched the same handler's auth check | Cross-family read catches if one side relaxed a check the other tightened |
| Data engineering | Concurrent edits to a transformation function in an ETL pipeline | Semantic-incompatibility detection (one side filters X, other aggregates X) |
| Platform / infra | Parallel changes to a Terraform module's resource block | Forbidden-paths default catches `.sql`, `migrations/**`; operator opts in for IaC if appropriate |
| Documentation | Two authors revised the same section of a spec doc | Lower-stakes; operator-confirm + auto-apply if doc passes a build-the-docs gate |
| Localization | Translation team and product-team both edited a strings file | Auto-apply candidate after the build-the-app gate passes |
| Configuration | Parallel changes to a feature-flag YAML | Forbidden-paths often includes config; operator-confirm by default |
| Test code | Concurrent additions to the same test file | High auto-apply suitability — test-suite-gate verifies correctness directly |
| Schema migration | Conflicting `ALTER TABLE` statements | Forbidden-paths default `*.sql` + `migrations/**` blocks auto-apply — operator must review |
| Clinical / regulated | Concurrent edits to a dosing-calculation module | Operator extends `forbidden_paths` to include this; operator-confirm only |
| Library upgrade | Two PRs upgraded a shared dependency to different versions | Cross-check often returns `NEEDS-HUMAN` — version-pin disagreement is a coordination question, not a merge question |

## Failure modes

| Failure | Skill behavior |
|---|---|
| Conflict markers malformed | REFUSE; surface raw conflict + line number that failed parsing |
| Cross-check returns no `PROPOSED RESOLUTION` after one retry | REFUSE; surface verifier's sections 1–3 + 5 + 6 |
| `git apply --3way --check` fails on the proposed resolution | RETRY ONCE with regenerated resolution; second failure → REFUSE |
| Operator gives empty / ambiguous response to confirm gate | Default to `reject` (safe) |
| `CONFIDENCE: L` on a file matching `forbidden_paths` | REFUSE auto-mode; require operator-confirm |
| Verifier-independence check fails (both sides independent-family-authored) | Switch to the active primary-as-resolver, or surface and ASK operator |
| Policy file is syntactically invalid | REFUSE auto-apply; fall back to operator-confirm; surface YAML error |
| Post-apply marker-integrity check finds remaining markers | REFUSE to mark merge resolved; surface failed line(s) to operator |

## Output format

Whether the operator chose `apply`, `reject`, `apply-and-amend`, or `revise`, surface a final summary:

```
merge-resolve summary:
  file: <path>
  hunks resolved: <N> of <M>
  verifier CONFIDENCE: H | M | L
  decision: applied | rejected | applied-and-amended | revised-and-re-proposed
  validators run (if Step 7 applicable): <list with PASS/FAIL>
  remaining conflicts: <list of files still with markers, or "none">
  next step: <e.g., "run `git status`; if clean, `git commit` the merge", or "re-run on remaining files">
```

## Anti-patterns

- **Auto-applying because the operator said "just merge it."** The `auto_apply=true` requires the policy file's presence + `CONFIDENCE: H` + forbidden-paths-clear + required-gates-met. Verbal operator urgency does NOT substitute for the policy file's presence-as-acknowledgment.
- **Configuring trivial bypass gates** (e.g., `bash_exit_code: { command: "true" }`) to satisfy a `required_gates:` requirement while bypassing the actual test suite. The skill verifies kind + check; substance is operator responsibility. If chains consistently use trivial-bypass gates, revisit the policy or the chains — someone is gaming the linter.
- **Skipping the cross-check on a "trivial" merge.** Every merge looks trivial until it isn't. The cross-check cost is small; bypassing defeats the skill's purpose.
- **Trusting `CONFIDENCE: H` on a merge involving auth, secrets, or schema** even if the policy doesn't explicitly forbid the path. The default `forbidden_paths` list exists for a reason; if the operator has narrower paths, they should still review high-sensitivity merges manually.
- **Treating `apply-and-amend` as the default.** It rewrites the in-progress merge commit. Use only when the operator explicitly chose it; default `apply` leaves the apply uncommitted so the operator can review one more time.
- **Pushing or committing from this skill.** Out of scope; the skill ends at "applied to working tree, operator confirms."
- **Re-running the same `revise` instruction repeatedly without operator input.** `revise` is a single-iteration instruction; if it fails, ASK the operator for next direction rather than looping.
- **Resolving merges where one side was authored by a independent-family agent without flipping the resolver direction.** Same-family resolution defeats the verifier-independence guarantee that downstream consumers (operator decisions, audit logs, compliance reviews) rely on.
- **Skipping the marker-integrity check** after apply. A silent apply failure leaves markers in the file; the merge appears resolved in the skill's response but the working tree is still in conflict. The check is one Read; never skip it.
- **Adding `forbidden_paths` to the policy without versioning the change in source control.** The policy is the operator's risk-acceptance posture; its history is auditable evidence. Edit, commit, push — don't `chmod 644 && vim` it in place.
