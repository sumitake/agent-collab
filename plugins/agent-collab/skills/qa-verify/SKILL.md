---
name: qa-verify
version: 4.2.1
defaults:
  tier: Fast
  effort: low

description: Ask the reviewer to independently QA the output of a completed execution against the original request — did the work actually meet the spec, or are there ignored constraints, off-by-one errors, hallucinated fields, or silent partial successes. Use when the user says "did this actually do what I asked," "verify my work with the reviewer," "QA check this," "sanity-check the output," "did the execution meet the spec," "did we actually complete the task," or "validate the result." Also offer this proactively when the active primary has just finished a complex multi-step execution (data transformation, large refactor, batched file edits, multi-API workflow, deploy script) and is about to report success — an independent QA pass before claim-of-completion catches the silent-success-with-missing-constraint failure mode that visual inspection often misses.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host/model, captures artifact provenance, excludes same-family routes, and verifies the co-packaged native manifest. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. Frontmatter `tier` is a routing recommendation, never a coordinator request field. For a review, cross-check, tiebreaker, or fallback over an authored artifact, capture its exact UTF-8 content and observed author model in the optional `artifact` object even when governance is false; never paste it into the prompt as a provenance substitute.

# QA verify — independent verification of a completed execution

A second-opinion is a review of a *plan*. A code-review is a critique of a *code artifact*. **qa-verify is verification of a completed *execution* against the original request.** The point is to catch the gap between "the script ran" and "the script accomplished what was actually asked for" — missed constraints, off-by-one results, hallucinated output fields, silent partial successes that look complete at a glance.

The cross-family setup matters because the active primary just *did* the work — its reasoning is anchored to its own implementation choices. the reviewer sees the original request, the work product, and the output with fresh eyes and no commitment to the path that was taken.

## When to use

Use this skill when one or more of the following are true:

- **The user explicitly asks for it** — "did this actually do what I asked," "verify my work with the reviewer," "QA check this," "sanity-check the output," "did the execution meet the spec," "did we actually complete the task," "validate the result," "QA pass."
- **A complex multi-step execution just finished** — data pipeline run, schema migration, large refactor, batched file edits, multi-API workflow, automated deployment, parameter sweep, bulk transformation — and the output is non-trivial to inspect by eye.
- **the active primary is about to report success** on something hard-to-reverse and visual inspection would not catch a silent partial-success. (Examples: 47 of 50 records migrated successfully but 3 silently dropped; a refactor passes tests but changed a constant from `1000` to `100`; a deploy script ran without errors but rolled out only 2 of 3 replicas.)
- **The task had explicit numerical or structural constraints** — "transform all rows matching X," "produce exactly N rows," "include columns A B C D," "ignore comments starting with `//`" — that can be checked against the output deterministically by a careful reader.

## When to skip

Skip this skill when:

- **The success is visually obvious to the user.** A two-line script that prints `Hello, World!` doesn't need QA verification.
- **There is no defined "did it meet the spec" criterion.** Open-ended creative work (a draft email, a brainstorm output) has no pass/fail; use `second-opinion` for general critique instead.
- **The task was so trivial that QA-pass-cost > defect-risk-cost.** Don't burn a verifier call on a renamed variable.
- **The execution produced its own test suite that already covers the constraint.** A migration that ran a `SELECT COUNT(*)` post-check and asserted equality with the input row count has self-verified that constraint; piling on a verifier pass adds noise.

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

## Procedure

### 1. Gather the three pieces of evidence

A QA pass needs all three:

- **The original request** — exactly what the user asked for, with all constraints. Paraphrasing here defeats the QA; the verifier must see the actual ask.
- **The work product** — the code, query, script, or process that was run. Without this, the verifier cannot see whether the implementation could plausibly meet the constraints.
- **The output / result trace** — the actual output, log, summary statistics, file diff, or whatever artifact the execution produced. If the work touched multiple files or systems, include a comprehensive trace; partial evidence produces partial QA.

If any of the three is missing, gather it before invoking. A QA pass on incomplete evidence is worse than no QA pass — the false-pass signals "all clear" when the verifier never saw the relevant gap.

### 2. Instruct the verifier as a strict QA inspector

Submit the sealed QA role through `python3 "<plugin-root>/coordinator.py"` with
`effort='low'` in every eligible advisory row and no `tier` request field (the skill default; raise effort only for subtle correctness constraints). Central policy selects
an independent eligible reviewer; Claude/Anthropic remains async inbox-only.

Use this prompt template — the VERDICT format is a functional contract; downstream tooling (chain runners, audit logs, CI gates) keys on the `VERDICT: PASS` / `VERDICT: FAIL` line:

```
You are a strict QA inspector. Verify the Final Output against the Original Request below. Look for hallucinations, off-by-one errors, ignored constraints, silent partial successes, and any gap between what was asked and what was delivered.

Output ONLY (no preamble, no closing, no meta-commentary):

VERDICT: PASS | FAIL
REASON: <one sentence — the single most important reason for the verdict>
[If FAIL] FAILED CONSTRAINTS: <bullet each constraint that was not met, with a one-line explanation of how it was missed>

--- ORIGINAL REQUEST ---
[paste the user's actual request, with all constraints]

--- WORK PRODUCT ---
[paste the code / query / script / process that was run]

--- FINAL OUTPUT ---
[paste the actual output / log / result trace / summary]
```

**Retry-on-malformed.** If the response does not lead with `VERDICT: PASS` or `VERDICT: FAIL` (e.g., it starts with conversational preamble or wraps the output in markdown), retry exactly once with:

> Previous response did not match the required format. Re-emit strictly per the template above (VERDICT / REASON / FAILED CONSTRAINTS if FAIL), no preamble or commentary.

If the second attempt is also malformed, surface that explicitly — do not infer a verdict from the prose. A malformed QA response is a signal that the verifier could not reduce the work to a binary judgment; that itself is information.

### 3. Adjudicate the QA result

The verdict is not the deliverable; the adjudication is.

**On `VERDICT: FAIL`:**

- Investigate each failed constraint. Open the relevant code or output and confirm the verifier's claim. Verifier hallucinations are less common in QA than in code-review (the schema is tighter) but not zero.
- If the failed constraint is real, inform the user clearly: **the QA pass failed, here are the missed constraints, here is the proposed fix.** Do not minimize.
- If the failed constraint is hallucinated, report that explicitly: "the reviewer flagged X, but X is not in fact missing — the {field/line/path} is present at {location}." Then either re-run the QA with the clarification or move on.

**On `VERDICT: PASS`:**

- Report "no issues flagged on independent review" — **not** "verified correct." A clean QA pass is one signal, not a guarantee; an independent reviewer can also miss bugs the executor missed. Overstating a PASS as "correctness verified" trains the user to trust the QA layer more than it deserves.

**On malformed-twice:**

- Surface to the user: "the reviewer could not return a clean PASS/FAIL verdict on this execution after one retry. Recommend manual inspection of [the relevant constraints]." Do not pretend a verdict happened.

## Examples across domains

QA verification applies wherever a task has a defined "did it meet the spec" criterion. A representative sample:

| Domain | Execution being verified | What a typical FAIL surfaces |
|---|---|---|
| Data engineering | A pipeline run that transformed 50,000 input rows into a target schema | Silent drop of N rows due to a null in an unexpected column; off-by-one in a date-range filter; aggregate-function mismatch (SUM where MEAN was specified) |
| Database engineering | A schema migration that added a column with backfill | Backfill missed rows that matched a NULL condition the migration script didn't anticipate; new column constraint not enforced on pre-existing rows |
| Backend / web | A bulk-update API call across 200 customer records | 197 records updated, 3 silently failed with a swallowed exception; updates applied with wrong currency for non-USD customers |
| Financial reporting | A quarterly variance-report regeneration | Missing one segment that was added in the source data mid-quarter; rounding-error accumulation in the running totals |
| Clinical research | An adverse-event extraction across 500 patient records | Missed events recorded only in free-text notes; classification miscategorized two events under a similar but distinct MedDRA code |
| Operations | An on-call runbook execution (rotate certificates across 12 hosts) | 11 hosts rotated successfully, host #12 silently skipped due to a hostname pattern mismatch in the script's regex |
| ML / data science | A feature-store backfill computing a new aggregate over historical data | Backfill produced values for 90% of users; the other 10% used an older code path that doesn't emit the new feature |
| Compliance | A consent-record audit that flagged users for re-consent | Missed users whose consent record had a timezone-offset format the audit query didn't normalize |
| Product / growth | An A/B test variant rollout to 5% of traffic | Variant rolled out to 5% of *sessions* but only 3% of *users* due to a multi-device de-dup oversight |
| Systems engineering | A coordinated configuration push across 30 edge nodes | 29 nodes updated; node #30 silently failed because its disk was full — the push script reported success because the file write succeeded into the OS write cache |

The VERDICT-style binary verdict applies to all of these uniformly; what shifts is the categories of "ignored constraint" the verifier should be on the lookout for, framed in step 2's instruction.

## Anti-patterns

- **Sending only the final output without the original constraints.** The verifier cannot QA against a spec it has never seen. The triple-evidence requirement (request + work product + output) is non-negotiable.
- **Using this for simple tasks where success is visually obvious.** Wastes a verifier call and adds noise to the audit log.
- **Overstating a PASS as "verified correct."** A PASS means "no issues flagged on this independent review." Independent reviewers also miss bugs. Phrasing matters; precision protects the user from over-trusting the layer.
- **Skipping the verifier-independence check** when the work was executed by a independent-family agent. Same-family QA is correlated blind spots, not independent verification.
- **Skipping the retry-on-malformed step.** If the response doesn't lead with `VERDICT: PASS` or `VERDICT: FAIL`, the parser breaks. Retry once; if still malformed, surface — do not infer a verdict from prose.
- **Treating a hallucinated FAIL as a real fail.** Verify each FAILED CONSTRAINT against the actual output before alarming the user. Hallucinations happen in QA too.
- **Using `pro` tier reflexively.** Binary verification is the right job for `flash`; reserve `pro` only when the constraint requires subtle correctness reasoning (numerical stability, regulatory-compliance interpretation, domain-specific edge-case judgment).
- **Running QA on incomplete evidence** and reporting the PASS to the user. A QA pass on partial evidence signals "all clear" when the verifier never saw the relevant gap. Better to gather full evidence first and accept the latency.
- **Inferring "this is correct" from a clean PASS.** Re-read the prior point. Words matter; the user will calibrate their downstream trust on yours.
