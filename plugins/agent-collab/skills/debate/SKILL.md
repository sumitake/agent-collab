---
name: debate
version: 7.0.7
defaults:
  quality_profile: frontier
  effort_class: maximum

description: Stage a structured multi-round adversarial debate between the active primary and the reviewer on a binary or near-binary proposition. Each side is assigned (or self-selects) an opposing position and defends it through openings, rebuttals, and an optional closing round; the agent then steps out of advocacy and synthesizes a verdict for the user. Use when the user says "debate this with the reviewer," "argue both sides," "steelman both positions," "play devil's advocate with the reviewer," "the active primary vs the reviewer on X," "have the reviewer argue the other side," or "make the case against." Also offer this proactively when the user is leaning hard one way on a high-stakes binary choice and a structured opposing case would stress-test the conviction better than a polite second opinion would.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Honor an operator-named provider with `explicit_target`. For an authorized independent review or governance task without an operator-named provider, also use that field to bind the caller-verified distinct reviewer selected by the caller or designated by the workflow. Carry the same target into planning and live dispatch; verify returned response-scoped native evidence before accepting independence. Otherwise use normal untargeted routing. Choose quality and effort for the workload; include context/output token estimates when known. The coordinator fills the installed wire digest and reads each working directory's current device/inode at dispatch. For a repository action, name the exact source directory as `native_restrictions.cwd`; if omitted, a read-only action is bound to the repository its payload names, else the caller's repository. Read the result's `repairs` list. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. Let the native runtime complete its own turns and tool recovery within the original invocation. Keep the OS account's canonical HOME and native configuration; do not create copied login profiles or replacement runtimes. Carry existing operator authorization across tool steps for the same action, source, provider, and scope; do not ask for it again merely because a diagnostic or tool boundary occurred. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not model identity, live availability, or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.
When a completed or terminated read-only review or governance attempt definitively produced no substantive result and no uncertain external mutation, retain that failed attempt as evidence. The caller may then issue at most one new corrected request as a new work unit after fixing a demonstrated setup defect with already authorized context and tools, such as inlining an inaccessible external plan or using an already available interpreter. Keep the same source hash, provider, and known-distinct reviewer requirements, and the original identical authorized scope. The allowance is one correction total per original request across all descendant work units; a corrected work unit cannot issue another correction or reset the allowance. Retain the original-request identity and both attempts in the caller's trace. Do not copy login profiles or expand permissions. This is not a replay, retry, or failover of the consumed work unit, not a runtime automatic retry, and not a provider switch to evade findings. Do not use it to repair formatting or missing lineage, or when failure is unproven or a native mutation is ambiguous. If findings or usable partial content exist, interpret them instead. Native one-process completion remains separate.

# Debate — structured adversarial advocacy with synthesis

A debate is not a second opinion. A second opinion asks a selected reviewer to find blind spots. A debate asks **both sides to advocate maximally** for opposing positions, then asks the agent — stepping out of advocacy — to render a verdict. The point is to **stress-test conviction**, not to manufacture consensus. If the debate ends with "both sides have good points," it failed.

Treat reviewer independence as unverified until the caller establishes the observed families and sources under the verifier-independence contract below. Role names and an opposing position do not establish a different model family.

## When to use

Use this skill when one or more of the following are true:

- **The user explicitly asks for it** — "debate this with the reviewer," "argue both sides," "steelman both positions," "play devil's advocate with the reviewer," "the active primary vs the reviewer on X," "have the reviewer argue the other side," "make the case against," "what's the strongest counter-position."
- **The question is genuinely two-sided.** Plausible cases exist on both sides — build vs. buy, hire vs. defer, ship now vs. wait, settle vs. litigate, in-house vs. outsource, conservative vs. aggressive treatment protocol, partnership vs. acquisition, accept the deal vs. counter, depose vs. negotiate.
- **The user is leaning hard one way** on a high-stakes choice and a polite second opinion will not crack the bias. They need to see the strongest possible case against — assigned, defended, not hedged.
- **The cost of being wrong is high** and the user has time to think. Debate takes 3–5 turns minimum; reserve it for decisions that warrant the latency.
- **The artifact under consideration is a position paper, recommendation memo, or proposal** where the user needs to see whether the strongest opposing case still leaves the original recommendation standing.

## When to skip

Skip this skill when:

- **One side is obviously right.** Manufacturing a debate where the evidence one-sidedly favors one position produces false equivalence and wastes the user's time. Use `second-opinion` instead — that is what cross-checking is for.
- **The choice has more than two viable options.** Debate forces a binary. For three-plus options, use `brainstorm` to widen the space, then `second-opinion` to evaluate the shortlist, then debate the final pair if needed.
- **The user wants a fast answer.** Three rounds + synthesis is the minimum cadence; this is the wrong tool for "should we deploy now or in an hour."
- **The question is empirical and decidable.** "Did our churn rate go up last quarter" is a data question, not a debate. Run the numbers.
- **The user has already debated this exact question recently** and is asking again without new information. The bottleneck is decision-fatigue, not under-argumentation.

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

### 1. Frame the proposition

Reduce the user's question to a clean binary proposition. State it as a claim, not as a question.

- Bad: "Should we build the analytics tool in-house or buy a vendor?"
- Good: **"Resolved: We should build the analytics tool in-house rather than buying a vendor."**
- Bad: "Aggressive or conservative treatment for this patient?"
- Good: **"Resolved: The patient should receive the aggressive treatment protocol rather than the conservative one."**

If the user's framing is fuzzy, distill it into a sharp proposition and confirm with them in one line before proceeding. The whole debate is anchored to the proposition's wording; spend the 30 seconds to get it right.

### 2. Assign sides

Default assignment: **the active primary argues PRO; the reviewer argues CON.** This puts the reviewer in the contrarian seat, which is usually the more valuable framing — the user has typically been hearing the active primary's view in the surrounding conversation, so a contrarian argument can add a useful perspective. Assigning sides does not establish reviewer lineage. Independent evidence requires the shared reviewer-selection contract; same-family or unverified contributions remain advisory.

Override the default when:

- The user has already heard the active primary lean one way in the surrounding context. Assign the active primary the *opposite* of its prior lean — force it to defend the position it has been arguing against.
- The user explicitly asks for a specific side assignment.
- The argument benefits from a different role assignment. Role assignment never substitutes for selecting and verifying an independent reviewer.

State the assignment clearly to the user before starting: "the active primary will argue [X]. the reviewer will argue [Y]. Three rounds, then synthesis."

### 3. Round 1 — Opening statements

**the active primary's opening:** Write the strongest case for the active primary's assigned side. Not a hedge, not "on balance" — the *strongest* case. Three to five specific points with evidence or reasoning. Treat it like a debate brief, not an analysis.

**the reviewer's opening:** Before dispatch, select a reviewer with
known lineage distinct from the observed primary and every contributing artifact author. Submit the
sealed debate role through `python3 "<plugin-root>/coordinator.py"` with `quality_profile='frontier'` and `effort_class='maximum'`.
Verify the observed reviewer lineage before treating its response as independent
governance evidence. Use this prompt template for debate content; the returned
content remains opaque to the runtime:

```
You are in a structured debate. Proposition: "[proposition]"

You argue [PRO|CON]. Make the strongest case. Do not hedge, concede, or balance.

ARGUMENT 1 (strongest): <claim + specific reasoning>
EVIDENCE 1: <concrete example or scenario>
ARGUMENT 2: <claim + reasoning>
EVIDENCE 2: <example or scenario>
[up to 5 numbered arguments; stop when arguments stop being load-bearing]

Context (background only — do NOT summarize back to me):
[paste the relevant context the user has shared, plus the proposition's domain framing]
```

Interpret every nonempty returned response as the advocate's contribution;
preserve partial or mixed prose and never replay for formatting.

### 4. Round 2 — Rebuttals

Both sides now attack each other's openings directly.

**the active primary's rebuttal:** Read the reviewer's opening. Pick its two strongest arguments and rebut them specifically — not "but on the other hand," but "here is why that argument fails, is incomplete, or rests on a false assumption." Quote the argument before rebutting it so the reader can follow the chain.

**the reviewer's rebuttal:** Send the active primary's opening through
the same sealed managed route (`python3 "<plugin-root>/coordinator.py"`;
`quality_profile='frontier'` and `effort_class='maximum'`):

```
Continuing the debate. The opposing side ([PRO|CON]) just argued:

[paste the active primary's opening verbatim]

You are still arguing [your side]. Rebut the two strongest points from the opposing side. Be specific — quote the claim, then explain why it is wrong, weak, or based on a false assumption. Do not concede.

REBUTTAL 1 (target: <quote of opposing argument>): <your rebuttal>
REBUTTAL 2 (target: <quote of opposing argument>): <your rebuttal>
```

As in the opening, preserve every observed response without a formatting replay.

### 5. Round 3 (optional) — Closing arguments

If the debate is genuinely tight after Round 2 — both sides still standing, the user not yet leaning either way — run a closing round. Each side gets one final paragraph: not new arguments, but the *strongest* compression of what has already been said, plus a one-sentence answer to "even granting the opposing side's strongest point, why does my side still win." Skip this round if Round 2 already resolved the tension.

### 6. Synthesis — step out of advocacy

This is the most important step and the easiest to skip. After the debate ends, **stop arguing** and tell the user, in plain prose:

1. **Which side won the debate on the merits**, and which specific arguments were load-bearing in that verdict. Do not say "both sides had good points" — call it.
2. **Where the disagreement is real vs. semantic.** Sometimes a debate surfaces that the two sides agree on the facts but disagree on values (or vice versa). Name the actual axis of disagreement.
3. **What the user's decision criteria should be** in light of what the debate surfaced. The criteria the user started with may not be the right ones.
4. **Your honest recommendation now.** Not a hedge, not "it depends" — your actual call. The user can reject it, but they need the agent's verdict on the record.

The debate is the diagnostic; the synthesis is the prescription. A debate without synthesis hands the user two transcripts and no verdict — strictly worse than running `second-opinion`.

## Output format

Present the debate as a clear transcript with headers, not a wall of paragraphs. The format is reader-friendly and also lets the synthesis step refer back to specific arguments by number.

```
## Proposition
"[proposition]"

## Sides
- PRO: the active primary
- CON: the reviewer

---

### Round 1 — Opening statements

**PRO (the active primary):**
ARGUMENT 1: ...
EVIDENCE 1: ...
[etc.]

**CON (the reviewer):**
ARGUMENT 1: ...
EVIDENCE 1: ...
[etc.]

---

### Round 2 — Rebuttals

**PRO rebuttal (the active primary):**
REBUTTAL 1 (target: ...): ...
REBUTTAL 2 (target: ...): ...

**CON rebuttal (the reviewer):**
REBUTTAL 1 (target: ...): ...
REBUTTAL 2 (target: ...): ...

---

### Round 3 — Closing arguments (if run)

**PRO closing:** ...

**CON closing:** ...

---

### Synthesis (the active primary, stepping out of advocacy)

[Verdict: who won the debate on the merits.]

[Real vs. semantic disagreement.]

[Decision criteria.]

[Recommendation.]
```

When relaying to the user, **quote the reviewer directly** for the sharp objections in its openings and rebuttals — paraphrasing softens them, and softened objections are exactly what this skill exists to prevent.

## Examples across domains

| Domain | Proposition | Why a debate fits |
|---|---|---|
| Product management | "Resolved: we should ship the half-finished v2 in two weeks rather than waiting for the full feature set in two months." | High-stakes timing call; both sides have plausible cases; user is often biased by the deadline pressure |
| Software architecture | "Resolved: we should migrate the order pipeline from a monolithic database to event-sourced storage now rather than after the holiday freeze." | Strong arguments both ways; the debate surfaces what "we're not ready" actually means in concrete terms |
| Clinical | "Resolved: this patient should receive the aggressive combination protocol rather than the standard monotherapy." | Two-sided medical-judgment call where the debate forces explicit weighing of efficacy gain vs. side-effect risk |
| Finance | "Resolved: we should accept the acquirer's revised offer rather than holding out for the higher bid in negotiations." | Genuine binary; loss aversion biases the hold-out case; the CON side forces the user to confront real risks of the deal falling through |
| Legal | "Resolved: we should settle the breach-of-contract claim rather than proceed to trial." | Classic two-sided call; debate surfaces strongest opposing arguments around costs, precedent, and reputational impact |
| Systems engineering | "Resolved: we should roll forward to v2.4 of the production database rather than rolling back to v2.2 after the v2.3 incident." | Operational decision under uncertainty; both sides need their strongest case before the on-call decides |
| Strategy | "Resolved: we should enter the European market via partnership rather than direct subsidiary." | Multi-axis trade-off; debate forces the strategy team to confront the strongest case for the path they have already de-prioritized |
| Hiring | "Resolved: we should make an offer to candidate A over candidate B." | Final-round calibration call; assigning sides forces explicit articulation of the cases that hiring debate often only half-surfaces |
| Research methodology | "Resolved: the experiment should use the larger sample with the cheaper measurement rather than the smaller sample with the gold-standard measurement." | Genuine methodological trade-off; debate surfaces the precision-vs-power axis explicitly |
| Operations | "Resolved: we should ride out the current on-call paging burst with the existing on-call rotation rather than activate the emergency rotation." | Tense operational call; the CON side forces a concrete articulation of what could go wrong if the burst is not properly resourced |

Match the example you cite to the user's domain. The skill applies wherever binary decisions are made under uncertainty.

## Anti-patterns

- **Soft openings.** "There are good points on both sides" is not a debate, it is mush. Both sides should defend their assigned position with conviction, not hedge.
- **Conceding mid-debate.** Both sides defend until synthesis. the reviewer conceding in Round 2 ("yes, the PRO side has a fair point...") weakens that round. Treat a conciliatory or hedged round as weaker evidence in the synthesis. Do not issue a replacement provider request automatically. A later caller-authorized request is a new attempt.
- **Skipping synthesis.** Leaving the user with two transcripts and no verdict is strictly worse than running `second-opinion`. The synthesis step is the deliverable, not the debate itself.
- **Manufacturing two sides on a question where one is clearly right.** This produces false equivalence. Use `second-opinion` for one-sided questions; reserve debate for genuine binaries.
- **Running more than three rounds.** Diminishing returns; the user checks out. If the proposition is unresolved after three rounds, the bottleneck is decision-fatigue or missing information, not under-argumentation.
- **Letting the reviewer hedge.** If its opening reads as balanced or its rebuttal includes "to be fair," record that limitation and weigh it in the synthesis rather than steering a replacement round automatically.
- **Using economical/minimal for debate calls.** Argumentation depth matters; frontier/maximum is the default for every debate invocation.
- **Treating opposing positions as independent model evidence.** Verify the observed reviewer, primary, and position-author lineages under the shared contract. Same-family or unknown-lineage arguments remain advisory regardless of side assignment.
- **Phrasing the proposition as a question rather than a claim.** "Should we X?" is fuzzy; "Resolved: we should X" anchors the debate. The two-second reframe pays off across all three rounds.
- **Debating an empirically-decidable question.** "Did our churn rate go up" is a data question. Run the numbers; do not argue the answer.
