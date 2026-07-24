---
name: logic-check
version: 4.3.3
defaults:
  tier: Advanced
  effort: xhigh

description: Audit a verifiable, step-wise computation (arithmetic, financial calculation, algorithm trace, constraint solve, scheduling problem) by having the reviewer independently re-derive the answer from the original problem statement and comparing — not by asking the reviewer to "check the work," which anchors on the existing derivation. Use when the user says "audit this calculation," "double-check my math with the reviewer," "verify these computations," "check this trace," "is this cap table right," "re-derive this with the reviewer," "audit my arithmetic," "logic-check this," or "is this number right." Also offer this proactively when the active primary has just performed a long multi-step calculation, an algorithmic trace (DP table, graph traversal, constraint propagation), a financial computation (cap table, tax math, unit conversion, currency-adjusted aggregate), or any computation where a wrong intermediate state silently corrupts the final answer.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host/model, captures artifact provenance, excludes same-family routes, and verifies the co-packaged native manifest. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. Frontmatter `tier` is a routing recommendation, never a coordinator request field. For a review, cross-check, tiebreaker, or fallback over an authored artifact, capture its exact UTF-8 content and observed author model in the optional `artifact` object even when governance is false; never paste it into the prompt as a provenance substitute.

# Logic check — independent re-derivation of a verifiable computation

Some tasks have a definite right answer reachable through mechanical steps where each step locks in state for the next. **A logic check catches the compounding-error class** that a free-form `second-opinion` review of the conclusion does not — because the conclusion looks plausible while a hidden intermediate step is wrong.

The **mechanism is independent re-derivation**, not "review my reasoning." Asking a model to audit another model's stated reasoning trace tends to anchor on the trace rather than check the math — the verifier reads the steps, finds them locally coherent, and signs off. Two independent derivations from the same problem statement diverge cleanly when one is wrong; the divergence point is the bug.

The cross-family setup matters here in a specific way: same-family verifiers are more likely to share systematic computational biases (e.g., recurring off-by-one in particular index conventions, recurring rounding-direction defaults). the reviewer (independent family) brings different defaults; its re-derivation is genuinely independent of the active primary's (resolved-family) computation.

## When to use

Use this skill when one or more of the following are true:

- **The user explicitly asks for it** — "audit this calculation," "double-check my math with the reviewer," "verify these computations," "check this trace," "is this cap table right," "re-derive this with the reviewer," "audit my arithmetic," "logic-check this," "is this number right."
- **the active primary has just done long arithmetic or a financial calculation** with intermediate quantities — cap tables, tax math, multi-currency aggregates, unit conversions, percentage-of-percentage chains, depreciation schedules.
- **the active primary has just done an algorithmic trace** — DP table fill, graph traversal, constraint propagation, BFS/DFS over a structured input — where a wrong intermediate state silently ruins the answer.
- **A logic or scheduling puzzle** with discrete verifiable steps just got an answer.
- **A clinical / scientific computation** with explicit formulae (dose calculations, statistical power, particle counts, dilution series, titration math).

## When to skip

Skip this skill when:

- **The task is open-ended judgment**, strategy, or interpretation. There is no "right answer" to independently re-derive. Use `second-opinion` instead.
- **The conclusion is the artifact** rather than the derivation (a recommendation memo, a draft email, a plan). Use `second-opinion`.
- **The user wants to know "was my thinking right"** on a non-verifiable problem. Too vague for re-derivation; ask `second-opinion` on the conclusion.
- **The computation is trivial.** A single multiplication does not benefit from cross-family re-derivation; the framing overhead exceeds the defect risk.
- **The computation has already been logic-checked this cycle** and the user is asking for a re-run without new input.

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

### 1. Show the active primary's work transparently — do not gate on the audit

Present the active primary's derivation and final answer to the user as you would normally. Then note: "Independent audit in progress; will reconcile if it disagrees." This serves two purposes: the user is not blocked waiting on the verifier, and if the audit later disagrees the reconciliation is visible — the user sees what changed and why.

Do not withhold the answer pending the audit. Suspense without purpose is just latency.

### 2. Ask the reviewer to re-derive — not to review

This is the load-bearing methodological discipline of the skill. **Send the problem and the constraints; do NOT send the active primary's derivation or answer.** Asking the verifier to "review the math" reliably anchors on the existing trace; independent re-derivation does not.

But: **do send the constraints and assumptions** the active primary used. Implicit choices (currency, rounding rule, FIFO/LIFO ordering, time zone, leap-year handling, edge-case treatment, unit conventions, statistical-test-tail-handling) will produce spurious divergence if the verifier defaults differently. Stating constraints explicitly is not "leading the witness" — it pins the problem to the same instance the active primary was solving.

Submit the sealed logic-check role through `python3 "<plugin-root>/coordinator.py"` with
`effort='xhigh'` in every eligible advisory row and no `tier` request field. Central policy resolves an independent eligible
reviewer; Claude/Anthropic remains async inbox-only. Use this prompt template —
the `ANSWER:` line is a functional contract that the comparison step keys on:

```
Solve this problem from scratch. Show step-by-step work, then emit the final answer on its own line as `ANSWER: <value>`.

PROBLEM:
[Problem statement — exactly as the user posed it, or the active primary's clean restatement if the original was ambiguous]

CONSTRAINTS (do not deviate):
- [Currency: e.g., "USD, rounded half-up at 2 decimal places at each intermediate step"]
- [Ordering: e.g., "FIFO for inventory withdrawals"]
- [Edge case: e.g., "leap-year handled per Julian calendar; February 29 counts as a separate day"]
- [Unit convention: e.g., "all weights in kg; convert input pounds to kg at problem-statement time, not output time"]
- [Tie-breaking: e.g., "earliest-arrival wins on duplicate timestamps"]
- [Other implicit assumptions the active primary relied on]

No preamble. No commentary. Show work, then `ANSWER: <value>` on the last line.
```

**Retry-on-malformed.** If the response does not contain a line matching `ANSWER: <value>`, retry exactly once with:

> Previous response did not include the required `ANSWER:` line. Re-emit with work shown above and a final line beginning `ANSWER:`, nothing else after.

If the second attempt is also malformed, surface explicitly and fall back to manual inspection. Do not infer an answer from the prose — the explicit `ANSWER:` line is the comparison-step anchor.

### 3. For very large structured traces — switch to transition critique

When the computation is a 30+ step trace (full DP table fill, multi-page constraint-propagation log, lengthy proof), blind re-derivation often produces structurally-incompatible solutions that are hard to compare meaningfully (the verifier may use a different DP indexing scheme, a different propagation order, etc.). For these:

- **Switch to transition critique**: send the active primary's trace and ask the verifier to verify each transition's correctness, not re-derive the whole thing.
- This sacrifices some anti-anchoring benefit for tractability; the verifier now sees the trace and is susceptible to the anchoring effect, but the alternative (incomparable parallel derivations) is worse.
- Use re-derivation as the default; switch to transition critique only when the trace is too large to expect parallel reconstruction.

Prompt template for transition critique:

```
Verify each transition in the trace below. For each step, confirm the state transition is correct given the constraints. If a transition is wrong, identify which step and why.

Output ONLY:
STEP <n>: CORRECT | WRONG — <one-sentence reason>
(one line per step; nothing else)

FINAL: AGREE | DISAGREE | INDETERMINATE — <one-sentence reason>

CONSTRAINTS:
[constraints as in re-derivation template]

TRACE:
[paste the full trace; number the steps if not already]
```

### 4. Compare the two derivations

**Both agree on the final answer AND key intermediates:** report "Independent re-derivation agrees: answer = X." High confidence (but not certainty — agreement is one signal, not a proof; both models can be wrong in the same way on a textbook-style problem with a well-known wrong answer).

**Disagree on the final answer:** first, evaluate the verifier's derivation **quality**. Is it coherent end-to-end? Or is it garbled / hallucinated / internally inconsistent? If the verifier's work is broken, do not try to reconcile — flag the verifier's failure to the user, fall back to re-checking the active primary's math against the constraints. If both derivations are coherent, identify the **step where they diverge**, then work out which is correct: re-check the arithmetic at that step, re-check the constraints, re-check the definitions, re-check the edge-case treatment. Report the corrected result with the source of the error explicitly named ("step 7 used a different rounding rule than the constraints specified"). **Do not silently switch the answer** — show the user what changed and why.

**Agree on the final answer but diverge on intermediates:** investigate the divergence; usually one path is wrong in a way that the answer was coincidentally still right. Report the agreement but flag the intermediate discrepancy if it matters for downstream reuse.

### 5. Close the loop

End the user-facing report with a one-line statement of the audited result and a confidence note. Examples:

- "Audited result: $47,283.50 (independent re-derivation by the reviewer agrees on the final answer AND each intermediate)."
- "Audited result: $47,283.50 (revised from the original $47,282.50 — the year-3 vesting acceleration was applied to the wrong tranche in the active primary's computation; verifier's derivation surfaced the error at step 9)."
- "Audited result: PENDING — the reviewer returned an incoherent derivation; falling back to manual re-check against constraints."

## Examples across domains

Logic checking applies wherever a verifiable computation exists. A representative sample:

| Domain | Computation under audit | Common error modes the re-derivation catches |
|---|---|---|
| Finance | Cap-table waterfall under multiple liquidity-preference tiers | Wrong stack order on preferences; double-counting on participating preferred; rounding-direction inconsistency across tranches |
| Tax | Quarterly federal-plus-state tax estimate with deductions | Wrong applicability date for a rule change; standard-deduction-vs-itemized misapplication; depreciation-schedule off-by-one |
| Insurance | Premium calculation for a multi-coverage policy with discounts | Discount-stacking order matters and gets it wrong; eligibility-floor for a discount missed |
| Clinical | Pediatric dosing calculation by weight-and-age | Wrong bracket boundary; mg-vs-mg/kg unit slip; max-dose ceiling missed |
| Scientific | Statistical-power calculation for a planned trial | Wrong test-tail handling (one-vs-two-sided); effect-size definition mismatch; alpha-adjustment for multiple comparisons missed |
| Operations research | Vehicle-routing optimization sub-problem (verifiable instance) | Wrong distance metric; missed pickup-before-delivery constraint; capacity-violation on an intermediate leg |
| Algorithms / interviews | DP solution to a tabulated problem (e.g., longest-common-subsequence) | Off-by-one on table bounds; wrong base case; reconstructing from table indexing the wrong direction |
| Crypto / security | Multi-round key-derivation hash chain | Wrong endianness; wrong padding scheme; wrong domain-separator label on a sub-hash |
| Game / puzzle | Logic puzzle with discrete state space (Sudoku variant, constraint satisfaction) | Missed implicit constraint; backtracking-order produces a different-but-also-valid solution that contradicts "uniqueness assumed" |
| Engineering / physics | Beam-deflection calculation for a multi-load-point cantilever | Wrong moment-of-inertia formula for the cross-section; superposition applied incorrectly; sign convention slip on one load direction |

The `ANSWER:` line discipline and the constraints-explicit pattern apply uniformly across all of these. Domain-specific shifts: which conventions are easiest to mis-state in the constraints block (currency rules and rounding for financial; unit slips for clinical; sign conventions for physics; endianness for crypto).

## Anti-patterns

- **Withholding the answer from the user while waiting on the audit.** Show the active primary's work; reconcile in public if needed. Latency-without-purpose is wasted user time.
- **Sending the active primary's reasoning and asking the verifier to "audit my steps."** This is the failure mode the skill exists to prevent. The verifier anchors on the trace; the audit's value evaporates. Re-derivation requires the problem statement only.
- **Sending the problem without the constraints.** Spurious divergence from unstated conventions wastes the audit. The constraints are non-optional context; explicit is better than implicit here.
- **Trying to reconcile when the verifier's derivation is itself incoherent.** Evaluate the verifier's work quality first. If it is garbled or internally inconsistent, do not merge it — flag it and re-check the active primary's math against constraints manually.
- **Using this skill for non-verifiable judgment work.** Open-ended reasoning, strategy, recommendations belong in `second-opinion`. The re-derivation mechanism requires a definite right answer.
- **Treating final-answer agreement as proof.** Two models can both be wrong in the same way, especially on textbook-style problems with well-known wrong answers (or on problems where the constraint statement is ambiguous in the same way to both models). Agreement is one signal, not a guarantee.
- **Using `flash` tier.** Multi-step computational care benefits from reasoning depth; `flash` produces faster derivations that are more prone to compounding-error patterns. Reserve for tier 1 only.
- **Skipping the verifier-independence check** when the original computation came from a independent-family agent. Same-family re-derivation may share systematic computational biases.
- **Silently switching the answer** if the audit disagrees and the verifier is right. Show the user what changed and why; the source-of-error attribution is the deliverable, not just the corrected number.
- **Re-deriving a 30+ step trace blindly when transition critique would work.** Incomparable parallel derivations waste both turns; fall back to step-by-step transition verification for large traces.
