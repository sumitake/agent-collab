---
name: debate
version: 4.1.0
defaults:
  tier: Advanced
  effort: high

description: Stage a structured multi-round adversarial debate between the active primary and the reviewer on a binary or near-binary proposition. Each side is assigned (or self-selects) an opposing position and defends it through openings, rebuttals, and an optional closing round; the agent then steps out of advocacy and synthesizes a verdict for the user. Use when the user says "debate this with the reviewer," "argue both sides," "steelman both positions," "play devil's advocate with the reviewer," "the active primary vs the reviewer on X," "have the reviewer argue the other side," or "make the case against." Also offer this proactively when the user is leaning hard one way on a high-stakes binary choice and a structured opposing case would stress-test the conviction better than a polite second opinion would.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host/model, captures artifact provenance, excludes same-family routes, and verifies the co-packaged native manifest. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. Frontmatter `tier` is a routing recommendation, never a coordinator request field. For a review, cross-check, tiebreaker, or fallback over an authored artifact, capture its exact UTF-8 content and observed author model in the optional `artifact` object even when governance is false; never paste it into the prompt as a provenance substitute.

# Debate — structured adversarial advocacy with synthesis

A debate is not a second opinion. A second opinion asks one independent reader to find blind spots. A debate asks **both sides to advocate maximally** for opposing positions, then asks the agent — stepping out of advocacy — to render a verdict. The point is to **stress-test conviction**, not to manufacture consensus. If the debate ends with "both sides have good points," it failed.

The cross-family setup matters: the active primary (resolved family) and the reviewer (independent family) bring different priors. Each side defending its assigned position with the full weight of its model family's reasoning surfaces objections and framings that a same-family debate would smooth over.

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

A review is independent only when its observed author family differs from both
the immutable primary snapshot and artifact-author snapshot. The shared policy
recognizes Anthropic, Google, OpenAI, xAI, Zhipu, and genuinely unknown lineage;
OpenCode itself is a transport, not a family. Resolve through `coordinator.py`
immediately before every call. Governance fails closed when either snapshot is
unknown or no distinct-family advisory route is eligible. Non-governance work
may proceed only with an independence warning. Claude is async inbox-only.
<!-- verifier-independence:end -->

## Procedure

### 1. Frame the proposition

Reduce the user's question to a clean binary proposition. State it as a claim, not as a question.

- Bad: "Should we build the analytics tool in-house or buy a vendor?"
- Good: **"Resolved: We should build the analytics tool in-house rather than buying a vendor."**
- Bad: "Aggressive or conservative treatment for this patient?"
- Good: **"Resolved: The patient should receive the aggressive treatment protocol rather than the conservative one."**

If the user's framing is fuzzy, distill it into a sharp proposition and confirm with them in one line before proceeding. The whole debate is anchored to the proposition's wording; spend the 30 seconds to get it right.

### 2. Assign sides

Default assignment: **the active primary argues PRO; the reviewer argues CON.** This puts the reviewer in the contrarian seat, which is usually the more valuable framing — the user has typically been hearing the active primary's view in the surrounding conversation, so the cross-family contrarian read is what they have not yet seen.

Override the default when:

- The user has already heard the active primary lean one way in the surrounding context. Assign the active primary the *opposite* of its prior lean — force it to defend the position it has been arguing against.
- The user explicitly asks for a specific side assignment.
- The verifier-independence rule (above) requires a particular assignment to keep the debate cross-family.

State the assignment clearly to the user before starting: "the active primary will argue [X]. the reviewer will argue [Y]. Three rounds, then synthesis."

### 3. Round 1 — Opening statements

**the active primary's opening:** Write the strongest case for the active primary's assigned side. Not a hedge, not "on balance" — the *strongest* case. Three to five specific points with evidence or reasoning. Treat it like a debate brief, not an analysis.

**the reviewer's opening:** Submit the sealed debate role through
`python3 "<plugin-root>/coordinator.py"` with `effort='high'` in every eligible advisory row and no `tier` request field. Central policy selects an
eligible independent advocate. Use this prompt template (the structured fields
are a functional contract — downstream synthesis steps key on them):

```
You are in a structured debate. Proposition: "[proposition]"

You argue [PRO|CON]. Make the strongest case. Do not hedge, concede, or balance.

Output ONLY (no preamble, no "in conclusion"):

ARGUMENT 1 (strongest): <claim + specific reasoning>
EVIDENCE 1: <concrete example or scenario>
ARGUMENT 2: <claim + reasoning>
EVIDENCE 2: <example or scenario>
[up to 5 numbered arguments; stop when arguments stop being load-bearing]

Context (background only — do NOT summarize back to me):
[paste the relevant context the user has shared, plus the proposition's domain framing]
```

If the reviewer's response does not contain at least two `ARGUMENT N (...) :` / `EVIDENCE N:` pairs, retry exactly once with: "Previous response did not follow the structured format (ARGUMENT N / EVIDENCE N pairs). Re-emit strictly per the template, no preamble." If the second attempt is also malformed, surface that explicitly to the user rather than papering over it.

### 4. Round 2 — Rebuttals

Both sides now attack each other's openings directly.

**the active primary's rebuttal:** Read the reviewer's opening. Pick its two strongest arguments and rebut them specifically — not "but on the other hand," but "here is why that argument fails, is incomplete, or rests on a false assumption." Quote the argument before rebutting it so the reader can follow the chain.

**the reviewer's rebuttal:** Send the active primary's opening through
the same sealed managed route (`python3 "<plugin-root>/coordinator.py"`;
`effort='high'` in every eligible advisory row and no `tier` request field):

```
Continuing the debate. The opposing side ([PRO|CON]) just argued:

[paste the active primary's opening verbatim]

You are still arguing [your side]. Rebut the two strongest points from the opposing side. Be specific — quote the claim, then explain why it is wrong, weak, or based on a false assumption. Do not concede.

Output ONLY (no preamble):

REBUTTAL 1 (target: <quote of opposing argument>): <your rebuttal>
REBUTTAL 2 (target: <quote of opposing argument>): <your rebuttal>
```

Same retry rule as the opening: if format breaks, retry once with the format-correction prompt; if still broken, surface the failure.

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
- **Conceding mid-debate.** Both sides defend until synthesis. the reviewer conceding in Round 2 ("yes, the PRO side has a fair point...") defeats the purpose. If the reviewer's rebuttal reads as conciliatory, push back: "this is a debate, defend the side you were assigned forcefully."
- **Skipping synthesis.** Leaving the user with two transcripts and no verdict is strictly worse than running `second-opinion`. The synthesis step is the deliverable, not the debate itself.
- **Manufacturing two sides on a question where one is clearly right.** This produces false equivalence. Use `second-opinion` for one-sided questions; reserve debate for genuine binaries.
- **Running more than three rounds.** Diminishing returns; the user checks out. If the proposition is unresolved after three rounds, the bottleneck is decision-fatigue or missing information, not under-argumentation.
- **Letting the reviewer hedge.** If its opening reads as balanced or its rebuttal includes "to be fair," push back: "you are arguing [side], defend it without hedging. The synthesis step is where balance returns."
- **Using `flash` tier for the debate calls.** Argumentation depth matters; `flash` produces shallow openings and superficial rebuttals. `pro` is the right default for every debate-tool invocation.
- **Skipping the verifier-independence check** when the user's pre-existing position came from a independent-family agent. Same-family debate is correlated; structurally one-sided. Apply the independence rule before assigning sides.
- **Phrasing the proposition as a question rather than a claim.** "Should we X?" is fuzzy; "Resolved: we should X" anchors the debate. The two-second reframe pays off across all three rounds.
- **Debating an empirically-decidable question.** "Did our churn rate go up" is a data question. Run the numbers; do not argue the answer.
