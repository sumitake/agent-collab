---
name: logic-check
version: 7.0.8
defaults:
  quality_profile: frontier
  effort_class: maximum

description: Audit a verifiable, step-wise computation (arithmetic, financial calculation, algorithm trace, constraint solve, scheduling problem) by having the reviewer separately re-derive the answer from the original problem statement and comparing — not by asking the reviewer to "check the work," which anchors on the existing derivation. Use when the user says "audit this calculation," "double-check my math with the reviewer," "verify these computations," "check this trace," "is this cap table right," "re-derive this with the reviewer," "audit my arithmetic," "logic-check this," or "is this number right." Also offer this proactively when the active primary has just performed a long multi-step calculation, an algorithmic trace (DP table, graph traversal, constraint propagation), a financial computation (cap table, tax math, unit conversion, currency-adjusted aggregate), or any computation where a wrong intermediate state silently corrupts the final answer.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Honor an operator-named provider with `explicit_target`. For an authorized independent review or governance task without an operator-named provider, also use that field to bind the caller-verified distinct reviewer selected by the caller or designated by the workflow. Carry the same target into planning and live dispatch; verify returned response-scoped native evidence before accepting independence. Otherwise use normal untargeted routing. Choose quality and effort for the workload; include context/output token estimates when known. The coordinator fills the installed wire digest and reads each working directory's current device/inode at dispatch. For a repository action, name the exact source directory as `native_restrictions.cwd`; if omitted, a read-only action is bound to the caller's repository or a linked worktree of it, never elsewhere. Read the result's `repairs` list. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. Let the native runtime complete its own turns and tool recovery within the original invocation. Keep the OS account's canonical HOME and native configuration; do not create copied login profiles or replacement runtimes. Carry existing operator authorization across tool steps for the same action, source, provider, and scope; do not ask for it again merely because a diagnostic or tool boundary occurred. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not model identity, live availability, or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.
When a completed or terminated read-only review or governance attempt definitively produced no substantive result and no uncertain external mutation, retain that failed attempt as evidence. The caller may then issue at most one new corrected request as a new work unit after fixing a demonstrated setup defect with already authorized context and tools, such as inlining an inaccessible external plan or using an already available interpreter. Keep the same source hash, provider, and known-distinct reviewer requirements, and the original identical authorized scope. The allowance is one correction total per original request across all descendant work units; a corrected work unit cannot issue another correction or reset the allowance. Retain the original-request identity and both attempts in the caller's trace. Do not copy login profiles or expand permissions. This is not a replay, retry, or failover of the consumed work unit, not a runtime automatic retry, and not a provider switch to evade findings. Do not use it to repair formatting or missing lineage, or when failure is unproven or a native mutation is ambiguous. If findings or usable partial content exist, interpret them instead. Native one-process completion remains separate.

# Logic check — separate re-derivation of a verifiable computation

Some tasks have a definite right answer reachable through mechanical steps where each step locks in state for the next. **A logic check catches the compounding-error class** that a free-form `second-opinion` review of the conclusion does not — because the conclusion looks plausible while a hidden intermediate step is wrong.

The **mechanism is separate re-derivation**, not "review my reasoning." Asking a model to audit another model's stated reasoning trace tends to anchor on the trace rather than check the math — the verifier reads the steps, finds them locally coherent, and signs off. Two separate derivations from the same problem statement diverge cleanly when one is wrong; the divergence point is the bug.

Treat reviewer independence as unverified until the caller establishes the observed families and sources under the verifier-independence contract below. Role names and an opposing position do not establish a different model family.

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

Independence is caller-verified governance evidence, not a routing guarantee.
Selecting a candidate and accepting independent approval are different stages.

Before dispatch, record the observed lineage and source for the active primary
and every contributing artifact author. Use currently known native configuration
or response-scoped observations for potential family selection only.
Provider-free planning inspects eligible actions and routes; it does not prove
model identity. Select a reviewer only when its currently known lineage is
distinct from the primary and every contributing author family. Honor an operator-named provider; do not silently replace it.
For an authorized independent review or governance task without an operator-named
provider, bind the verified reviewer selected by the caller or designated by the
workflow using `explicit_target`. Carry that same target into planning and live
dispatch; untargeted planning does not bind a later live request. If the target
becomes unavailable, report it without silent substitution or replay.
If no known-distinct eligible reviewer is established, do not dispatch
as independent governance; explain the missing capability or evidence before
an expensive dispatch. Do not classify an untried provider unavailable, loop
operator waivers, or invent a required identity probe or schema service before
every review. An authorized advisory review may still proceed.
An OpenCode name is transport information, not lineage. Use only a
descriptor-admitted review or governance action; never substitute document
intent for review.

After the response returns, record the observed reviewer lineage and source.
Configuration-scoped observations remain configuration; they never prove the
model that produced the returned response. Independent approval requires
response-scoped native evidence correlated to that returned response, with
known primary, contributing-author, and reviewer lineages, and a reviewer
distinct from the primary and every contributing author family. A route,
provider name, status, receipt, self-assertion, or configuration observation
alone does not prove lineage. Preserve unknown lineage as unknown. Do not replay a
consumed review to repair missing lineage, formatting, or adverse findings;
retain useful advisory content without looping waivers or clearing required
independent approval.
<!-- verifier-independence:end -->

See this skill's Unified runtime invocation and Public repository governance
for the one bounded caller fresh-review allowance. It is a new work unit after
a completed or terminated attempt with no substantive result, not a replay of
the consumed work unit.

## Procedure

### 1. Show the active primary's work transparently — do not gate on the audit

Present the active primary's derivation and final answer to the user as you would normally. Then note: "Advisory re-derivation in progress; will reconcile if it disagrees." Reviewer independence is pending until the returned response-scoped evidence establishes it. The user can use the initial answer while seeing any later correction and its reason.

Do not withhold the answer pending the audit. Suspense without purpose is just latency.

### 2. Ask the reviewer to re-derive — not to review

This is the load-bearing methodological discipline of the skill. **Send the problem and the constraints; do NOT send the active primary's derivation or answer.** Asking the verifier to "review the math" reliably anchors on the existing trace; independent re-derivation does not.

But: **do send the constraints and assumptions** the active primary used. Implicit choices (currency, rounding rule, FIFO/LIFO ordering, time zone, leap-year handling, edge-case treatment, unit conventions, statistical-test-tail-handling) will produce spurious divergence if the verifier defaults differently. Stating constraints explicitly is not "leading the witness" — it pins the problem to the same instance the active primary was solving.

Before dispatch, select a reviewer with known lineage distinct from the observed
primary and every contributing artifact author. Submit the sealed logic-check role through
`python3 "<plugin-root>/coordinator.py"` with `quality_profile='frontier'` and `effort_class='maximum'`. Verify the observed
reviewer lineage before treating its response as independent governance evidence.
Use this prompt template for substantive derivation. The caller reasons over the
complete raw response; provider formatting is not an output contract:

```
Solve this problem from scratch. Show step-by-step work and clearly identify the final answer.

PROBLEM:
[Problem statement — exactly as the user posed it, or the active primary's clean restatement if the original was ambiguous]

CONSTRAINTS (do not deviate):
- [Currency: e.g., "USD, rounded half-up at 2 decimal places at each intermediate step"]
- [Ordering: e.g., "FIFO for inventory withdrawals"]
- [Edge case: e.g., "leap-year handled per Julian calendar; February 29 counts as a separate day"]
- [Unit convention: e.g., "all weights in kg; convert input pounds to kg at problem-statement time, not output time"]
- [Tie-breaking: e.g., "earliest-arrival wins on duplicate timestamps"]
- [Other implicit assumptions the active primary relied on]

Include enough intermediate work for independent comparison.
```

Reason over every nonempty raw response, including recovered partial prose, and
deduce the best-supported result. Verify its steps manually before relying on
it; never replay for formatting.

### 3. For very large structured traces — switch to transition critique

When the computation is a 30+ step trace (full DP table fill, multi-page constraint-propagation log, lengthy proof), blind re-derivation often produces structurally-incompatible solutions that are hard to compare meaningfully (the verifier may use a different DP indexing scheme, a different propagation order, etc.). For these:

- **Switch to transition critique**: send the active primary's trace and ask the verifier to verify each transition's correctness, not re-derive the whole thing.
- This sacrifices some anti-anchoring benefit for tractability; the verifier now sees the trace and is susceptible to the anchoring effect, but the alternative (incomparable parallel derivations) is worse.
- Use re-derivation as the default; switch to transition critique only when the trace is too large to expect parallel reconstruction.

Prompt template for transition critique:

```
Verify each transition in the trace below. For each step, confirm the state transition is correct given the constraints. If a transition is wrong, identify which step and why.

Identify each wrong transition by step, explain why, and state whether the
overall trace agrees, disagrees, or remains indeterminate.

CONSTRAINTS:
[constraints as in re-derivation template]

TRACE:
[paste the full trace; number the steps if not already]
```

### 4. Compare the two derivations

First verify the returned response-scoped evidence against the primary and every
contributing author family. Use independent wording only when every independent-
governance requirement is met; otherwise label the comparison advisory. Asking
for a derivation without sharing the original answer reduces anchoring, but does
not itself establish reviewer-family independence.

**Both agree on the final answer AND key intermediates:** report "Independent re-derivation agrees: answer = X" only after that verification; otherwise report "Advisory re-derivation agrees: answer = X; reviewer independence unverified." Agreement is one signal, not a proof; both models can be wrong in the same way on a textbook-style problem with a well-known wrong answer.

**Disagree on the final answer:** first, evaluate the verifier's derivation **quality**. Is it coherent end-to-end? Or is it garbled / hallucinated / internally inconsistent? If the verifier's work is broken, do not try to reconcile — flag the verifier's failure to the user, fall back to re-checking the active primary's math against the constraints. If both derivations are coherent, identify the **step where they diverge**, then work out which is correct: re-check the arithmetic at that step, re-check the constraints, re-check the definitions, re-check the edge-case treatment. Report the corrected result with the source of the error explicitly named ("step 7 used a different rounding rule than the constraints specified"). **Do not silently switch the answer** — show the user what changed and why.

**Agree on the final answer but diverge on intermediates:** investigate the divergence; usually one path is wrong in a way that the answer was coincidentally still right. Report the agreement but flag the intermediate discrepancy if it matters for downstream reuse.

### 5. Close the loop

End with the result, a confidence note, and the established review status. Use
"Independently audited result" only when the response-scoped evidence establishes
all independent-governance requirements. Otherwise use "Advisory result" and
state that reviewer independence remains unverified. Examples:

- "Independently audited result: $47,283.50 (the verified independent reviewer agrees on the final answer AND each intermediate)."
- "Advisory result: $47,283.50 (reviewer independence unverified; revised from $47,282.50 after checking the year-3 vesting error surfaced at step 9)."
- "Advisory result: PENDING — the reviewer returned an incoherent derivation; falling back to manual re-check against constraints."

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

The constraints-explicit final-answer pattern applies uniformly across all of these. Domain-specific shifts: which conventions are easiest to mis-state in the constraints block (currency rules and rounding for financial; unit slips for clinical; sign conventions for physics; endianness for crypto).

## Anti-patterns

- **Withholding the answer from the user while waiting on the audit.** Show the active primary's work; reconcile in public if needed. Latency-without-purpose is wasted user time.
- **Sending the active primary's reasoning and asking the verifier to "audit my steps."** This is the failure mode the skill exists to prevent. The verifier anchors on the trace; the audit's value evaporates. Re-derivation requires the problem statement only.
- **Sending the problem without the constraints.** Spurious divergence from unstated conventions wastes the audit. The constraints are non-optional context; explicit is better than implicit here.
- **Trying to reconcile when the verifier's derivation is itself incoherent.** Evaluate the verifier's work quality first. If it is garbled or internally inconsistent, do not merge it — flag it and re-check the active primary's math against constraints manually.
- **Using this skill for non-verifiable judgment work.** Open-ended reasoning, strategy, recommendations belong in `second-opinion`. The re-derivation mechanism requires a definite right answer.
- **Treating final-answer agreement as proof.** Two models can both be wrong in the same way, especially on textbook-style problems with well-known wrong answers (or on problems where the constraint statement is ambiguous in the same way to both models). Agreement is one signal, not a guarantee.
- **Using economical/minimal for multi-step calculations.** Computational care benefits from reasoning depth; use frontier/maximum unless the check is genuinely trivial.
- **Claiming independent verification when observed reviewer and computation-author lineages match or are unknown.** Re-derivation may still provide useful advisory findings, but cannot clear an independent verification requirement.
- **Silently switching the answer** if the audit disagrees and the verifier is right. Show the user what changed and why; the source-of-error attribution is the deliverable, not just the corrected number.
- **Re-deriving a 30+ step trace blindly when transition critique would work.** Incomparable parallel derivations waste both turns; fall back to step-by-step transition verification for large traces.
