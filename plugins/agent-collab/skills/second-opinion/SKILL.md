---
name: second-opinion
version: 4.3.1
defaults:
  tier: Advanced
  effort: high

description: Send a draft, analysis, plan, or decision to the reviewer for an independent cross-family read before the active primary commits. Use when the user says "second opinion," "what does the reviewer think," "sanity check this," "cross-check," or "have the reviewer review," and before any consequential, hard-to-reverse choice — architecture commitment, clinical protocol, contract clause, pricing change, finalized strategy, hiring decision, launch go/no-go. Also offer this proactively when the user is about to ship, sign, or send something the same draft will not easily walk back, especially when the active primary has reasoned its way to a confident answer without outside friction.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host/model, captures artifact provenance, excludes same-family routes, and verifies the co-packaged native manifest. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. Frontmatter `tier` is a routing recommendation, never a coordinator request field. For a review, cross-check, tiebreaker, or fallback over an authored artifact, capture its exact UTF-8 content and observed author model in the optional `artifact` object even when governance is false; never paste it into the prompt as a provenance substitute.

# Second opinion — independent cross-family read

A second opinion is an explicitly *adversarial* read on a piece of the active primary's reasoning by an eligible model from a distinct family. Its job is to expose disagreements and blind spots, not to ratify.

## When to use

Use this skill when one or more of the following are true:

- **The user explicitly asks for it** — "second opinion," "what does the reviewer think," "sanity-check this," "cross-check," "have the reviewer review."
- **A commit is imminent and reversal is expensive.** Examples: shipping a release, signing a contract, sending a board-deck draft, executing a database migration, approving a clinical-trial amendment, posting an incident retrospective externally.
- **The decision is a judgment call** where two model families' priors differ usefully — strategy trade-offs, vendor selection, methodology choices, ethics calls, contested interpretations.
- **The user appears to want reassurance** but has not asked for the contrarian view. Offer it. Validation-shaped questions ("does this sound right?") are usually the moments where an independent read pays off most.

## When to skip

Skip this skill when:

- The artifact is a routine lookup or factual query — invoke the underlying console backend (`python3 "<plugin-root>/coordinator.py"`) directly.
- The artifact was authored by a model in the independent family (see Verifier independence below).
- The cost of being wrong is trivially recoverable (a draft no one has seen, a sketch of a sketch). The framing overhead is not worth it.
- The user has *already* received a second opinion this cycle and is asking for a third — at that point the issue is decision avoidance, not under-scrutiny.

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

### 1. Identify the artifact and the stakes

Pin down what is under review (draft email, schema migration, trial protocol section, vendor proposal, architecture diagram, talking points) and what specifically is at risk if it is wrong. If the user has given you a folder full of files or a long thread of context, ask one clarifying question rather than guessing — generic input produces generic critique.

### 2. Frame the request deliberately

Do not dump the artifact at the reviewer with a vague "thoughts?" — that produces flattery-shaped paragraphs. Ask for four specific things:

- The single **strongest counter-argument** to whatever the artifact concludes or proposes.
- Concrete **risks and failure modes** — what actually breaks, where, and under what conditions.
- **Unsupported assumptions** — claims the artifact relies on without evidence, especially load-bearing ones the author may not have noticed they were making.
- A calibrated **confidence rating** on the artifact's recommendation, with a one-sentence reason.

### 3. Call the panel — in parallel

Send the **same** framed request (the four-section template below) to **every available cross-family panelist at once**, not sequentially — the reads are independent, so issue them concurrently and collect all responses before synthesizing. Each panelist gets the identical artifact + template, so their outputs are directly comparable.

The panel is **every eligible managed advisory route whose observed family
differs from both snapshots**. A raw binary or legacy plugin is never a route.
An absent signed route is typed unavailable and reported from current
readiness, not from a fixed inventory in this skill. Claude/Anthropic has no
synchronous route. An Anthropic governance peer review may occur only through
a separately configured host-owned async transport after its readiness is
observed; the public coordinator neither sends nor accepts governance over
`inbox/async`. It is therefore a supplementary async view, never a live
synchronous panelist, and must never use `claude -p`.

Per-panelist invocation is centralized: submit the sealed review role through
the managed runtime, exclude the active primary and artifact-author families,
and use only preflight-eligible routes. Claude/Anthropic is async inbox-only.
An absent native route is typed unavailable and omitted; never restore a
retired package or provider command. Hold one eligible independent reviewer as
the tiebreaker rather than including it in the first wave.

The `pro` tier resolves on this side to the strongest eligible independent reviewer allowed by central policy, which is the tier configured for slow, skeptical analysis — exactly what a cross-check wants. The faster `flash` tier is the wrong choice here; it optimizes for throughput, not for finding objections. Ensure each panelist receives the **whole** artifact — a divergence that is actually an artifact of one model truncating the context is a false signal, not a real disagreement.

Use this prompt template — the four numbered sections are a functional contract, not stylistic suggestion. Downstream tooling (parity tests, audit logs, chain runners) keys on them:

```
Review the following [artifact type, e.g. "architecture proposal", "trial protocol amendment", "vendor MSA redline"]. Output only the four sections below — no preamble, no closing, no meta-commentary. Cap total response at 350 words.

1. STRONGEST COUNTER-ARGUMENT: <single best objection>
2. RISKS / FAILURE MODES: <bulleted, specific>
3. UNSUPPORTED ASSUMPTIONS: <bulleted>
4. CONFIDENCE: H | M | L — <one-sentence reason>

--- ARTIFACT ---
[paste the full artifact verbatim]
```

**Retry-on-malformed.** If the response does not contain all four numbered sections (`1. STRONGEST COUNTER-ARGUMENT`, `2. RISKS / FAILURE MODES`, `3. UNSUPPORTED ASSUMPTIONS`, `4. CONFIDENCE`), retry exactly once with:

> Previous response did not include all four required sections. Re-emit strictly per the template above, no preamble.

If the second attempt is also malformed, surface that explicitly when you report back — do not silently paper over the format failure with a fabricated structure. A malformed cross-check is itself a signal worth reporting. (Apply this per panelist; one panelist's malformed reply does not invalidate the others.)

### 3b. Tiebreaker — only on a conflicting verdict

After the parallel panel returns, decide whether a tiebreaker is needed. Invoke
an eligible independent managed reviewer **only** when the panel is in genuine
*verdict* conflict:

- **Trigger:** the panelists reach **opposing bottom-line conclusions** — e.g. one lands on a confident "this is sound / proceed" while another lands on "this is unsound / do not proceed" — **OR** one panelist flags a **load-bearing risk** (a critical architectural / security / correctness defect) that another explicitly dismisses or did not surface. Resolving *which read is right* is high-stakes and a neutral third family earns its cost here.
- **NOT a trigger:** panelists broadly agree on the verdict but list different,
  additive risks. Aggregate the union and move on; do not add a third reviewer.
- A tiebreaker is selected dynamically from the remaining eligible distinct-
  family advisory routes and receives the same template plus conflicting reads.

If no eligible independent tiebreaker is reachable, surface the unresolved
conflict to the operator; never fabricate a resolution.

### 4. Synthesize — high-water-mark of risk, never consensus

When you relay the panel to the user, the cardinal rule is **never average the reads into a softer middle, and never let a 2-of-N "agree" lull the decision.** Operate on a **high-water-mark of risk**: surface the **union** of all identified risks, led by the **single sharpest concern raised by *any* panelist** — even if only one panelist raised it and the others said "proceed." If one verifier issues a confident PROCEED and another a sharp RECONSIDER, the RECONSIDER's load-bearing objection leads; it is not netted against the PROCEED.

**Surface the raw reads — do not paraphrase them into compliance.** Present each panelist's four-section output (or a faithful direct quote of its sharpest objections), attributed by name, so the operator sees the actual critiques and not the authoring model's softened summary of critiques of its own work. Lead with **divergence** across the panel, not agreement; quote the sharp objections directly.

A useful structure for the user-facing report:

> **Panel:** <currently eligible managed panelists> (dynamic tiebreaker: <route + verdict | not needed | unavailable>).
>
> **Sharpest concern (high-water mark):** <the single most load-bearing objection from any panelist, attributed, quoted>.
>
> **Where the panel diverges:** <conflicting verdicts/risks, attributed> — and, where used, how the dynamic tiebreaker resolved it.
>
> **Union of risks / assumptions flagged:** <aggregated across panelists, deduplicated, attributed where it matters>.
>
> **Panel confidence:** <each panelist's H/M/L>. **Where the panel agrees with the active primary:** <briefly, last>.

### 5. Adjudicate, then close

Finish with a short synthesis paragraph that **calls the question** for the user. Which of the panel's points are load-bearing — i.e., should change the artifact or the decision? Which are noise the user can set aside? What, if anything, should be revised before commit? A cross-check that ends "here is what the panel said" without an adjudication has pushed the synthesis work back onto the user; do not stop there. The operator remains the final gate on any consequential or irreversible decision — the panel informs, it does not decide.

## Structured-artifact review lens

When the artifact under review is a **structured change** — configuration, schema migration, infrastructure-as-code, policy, pipeline definition, RBAC ruleset — rather than free-form prose, augment the prompt with a domain-agnostic checklist. These categories have empirically caught real defects across many invocations:

1. **Syntax errors** — version-skew with deployed tool, deprecated flags, wrong predicate form, missing required field, malformed escape.
2. **Race conditions and ordering hazards** — assumed sequencing that is not actually enforced, optimistic locks against pessimistic writers, hardcoded paths to files written by another process.
3. **Scope overreach** — selectors, globs, or regexes that catch more than intended (`Resource: "*"`, `match: '.*'`, `host: '*'`, wildcard `kind:` selectors).
4. **Excessive privilege** — root or admin credentials where scoped tokens would work, blanket roles where named permissions would, no-auth paths where minimum auth is feasible.
5. **Missing or untested rollback** — no documented revert command, no pre-state snapshot, no test of the revert path under load.
6. **Inadequate idempotency** — re-running the change breaks rather than no-ops, resources leak on retry, partial-failure state is not safely resumable.
7. **Cross-system implication blind spots** — change in system A breaks a consumer in system B that was not audited (a column drop that an analytics pipeline reads, a network ACL change that an external monitor depends on, a schema rename a downstream report binds to).

Append this addendum to the standard prompt for structured-change reviews:

```
This is a STRUCTURED CHANGE (configuration / schema / IaC / policy / pipeline), not free-form prose. In your RISKS / FAILURE MODES section, check explicitly for each of these categories and call any that surface:

1. Syntax errors (version-skew, deprecated flags, wrong predicate form)
2. Race conditions and ordering hazards
3. Scope overreach (broad selectors that catch more than intended)
4. Excessive privilege (full credentials where scoped suffice)
5. Missing or untested rollback
6. Inadequate idempotency (re-run breaks instead of no-op)
7. Cross-system implications (consumers in other systems that bind to the changed surface)

For each category that surfaces a real concern, include one bullet with a one-line explanation.
```

## Examples across domains

The skill is domain-agnostic. A representative sample of where independent cross-family review pays off:

| Domain | Artifact under review | What second-opinion typically surfaces |
|---|---|---|
| Product management | Pricing-tier restructure proposal | Anchoring biases the author's family shares; segment cannibalization the deck's narrative buried |
| Software architecture | Async-vs-sync messaging choice | Concurrency failure modes that one family's training corpus over-weighted |
| Clinical research | Trial protocol — primary endpoint definition | Measurement biases, statistical-power assumptions, ethical considerations the author's review pass normalized |
| Finance | Quarterly forecast model assumptions | Numeric / scaling errors, currency-conversion edge cases, year-end timing assumptions |
| Legal | Indemnity clause in a vendor MSA | "Standard language" that is actually high-risk in this jurisdiction or for this counterparty class |
| Systems engineering | Network segmentation policy change | Scope overreach in firewall selectors, missing rollback, cross-system implications |
| Strategy | Go/no-go on a market entry | Strongest counter-argument the deck's narrative structure suppressed |
| Hiring / talent | Final-round candidate calibration brief | Halo effects and family-correlated bias signatures across panel feedback |
| Research methodology | Draft paper — methods section | Hidden assumptions, alternative-explanation gaps, replicability hazards |
| Operations | Incident retrospective conclusions | Alternative root-cause hypotheses that consensus narrowed prematurely |

When picking the right example to share with the user mid-invocation, match the user's domain — not the operator's. The skill works the same way regardless of subject matter; the framing should meet the user where they are.

## Anti-patterns

- **Dumping the artifact with no framing.** "Thoughts?" produces vague, polite output. The four-section template exists for a reason.
- **Using this for trivia or quick lookups.** Call `python3 "<plugin-root>/coordinator.py"` directly. The framing overhead and `pro`-tier latency are not worth it for "what does X mean."
- **Treating the reviewer as an oracle.** A second opinion is one more input, not adjudication. The synthesis step is non-optional — the agent owes the user a call, not a relay.
- **Burying disagreements under polite framing.** "Mostly agreed, with some minor notes…" defeats the entire purpose. Lead with disagreement; quote directly.
- **Averaging a panel into consensus.** With more than one verifier the tempting failure is to net a sharp RECONSIDER against a confident PROCEED into a comfortable "PROCEED-WITH-MODIFICATIONS." Do not. A panel's value is the *union* of its catches, not the intersection of its agreements; one verifier's load-bearing objection is not diluted by the others missing it. A 2-of-3 "looks fine" is not a safety signal — surface the lone dissent at full strength (high-water-mark rule).
- **Paraphrasing the panel's critiques of your own work.** When the authoring model summarizes the verifiers' objections, it tends — even unintentionally — to soften the sharpest ones. Surface the raw four-section reads (or faithful direct quotes), attributed; let the operator see the actual critiques.
- **Firing a tiebreaker on agreement.** A tiebreaker resolves a verdict conflict;
  it does not ratify a panel or adjudicate additive compatible notes.
- **Skipping the verifier-independence check** when the artifact came from work authored within the independent family. That "review" is correlated with its author; the audit log will record a cross-check that did not, in substance, occur.
- **Reviewing a structured config diff with the generic four-section template only.** Invoke the structured-artifact lens above — the recurring failure categories catch defects the generic template will miss.
- **Skipping the retry on malformed output.** If the verifier returns a wall of prose without the four numbered sections, the parity tests and audit logs cannot consume it. Retry once; if it fails again, report the failure rather than fabricating structure around the prose.
- **Running this against a draft the user has already revised three times based on prior cross-checks.** At that point, the decision-quality issue is no longer "needs more critique" — it is "needs a decision." Say so.
