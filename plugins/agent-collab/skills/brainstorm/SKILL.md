---
name: brainstorm
version: 4.3.3
defaults:
  tier: Fast
  effort: low

description: Use the reviewer as a divergent-thinking partner to widen the option space on an open-ended problem — generate alternatives, surface unfamiliar angles, or pressure-test an idea against a different model's priors. Use when the user says "brainstorm with the reviewer," "let's ideate," "what are some options," "think this through with the reviewer," "thinking partner," "give me alternatives," or asks any "what could we do about X" type question with no single right answer. Also offer this proactively when the user is early in an open-ended task with no clear answer, when the active primary has already proposed one approach and a fresh divergent angle would help, when a list of options would serve better than a single recommendation, or when the user is visibly stuck in a single line of thinking and a different model's priors could break the rut.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host/model, captures artifact provenance, excludes same-family routes, and verifies the co-packaged native manifest. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. Frontmatter `tier` is a routing recommendation, never a coordinator request field. For a review, cross-check, tiebreaker, or fallback over an authored artifact, capture its exact UTF-8 content and observed author model in the optional `artifact` object even when governance is false; never paste it into the prompt as a provenance substitute.

# Brainstorm — divergent ideation with the cross-family partner

Brainstorming is for **widening the option space**, not narrowing it. Convergence and decisions happen after. The point of using the reviewer as the brainstorming partner is that the reviewer sits in a different model family from the active primary (independent vs. resolved) — so its priors, training corpora emphases, and default failure modes are different. Those differences are exactly what generates ideas the active primary would not have surfaced on its own.

## When to use

Use this skill when one or more of the following are true:

- **The user explicitly asks for it** — "brainstorm with the reviewer," "let's ideate," "what are some options," "think this through with the reviewer," "thinking partner," "give me alternatives," "spitball this with the reviewer."
- **The user poses an open-ended question** with no obviously-correct answer — "what could we do about X," "how should we frame Y," "what are some ways to Z."
- **The problem is early-stage and exploratory** — naming, positioning, structuring, organizational design, hypothesis generation, methodology choice, candidate-feature-set generation.
- **the active primary has already proposed one approach to an open-ended question** and the user is weighing whether to commit. Surface alternatives rather than defending the existing proposal.
- **The user appears stuck in one line of thinking on an open-ended problem** and a different model family's priors would break the rut. Offer the brainstorm even if they did not ask — but only when the problem is genuinely open-ended; do not propose brainstorming during routine fact-finding, debugging, or step-by-step execution work.

## When to skip

Skip this skill when:

- The question has a single correct answer that a quick lookup would resolve. Call `python3 "<plugin-root>/coordinator.py"` directly for fact-finding.
- The user is **converging**, not diverging — they have a few candidates and need to choose one. Brainstorming at this stage is decision-avoidance.
- The artifact under consideration is high-stakes and the user wants critique, not more options. Use `second-opinion` instead.
- The user has already brainstormed three times this cycle and is asking for a fourth round in the same direction. The bottleneck is decision-making, not idea-shortage.

## Procedure

### 1. Frame the problem as a precise question

Vague prompts produce vague output. "Help me name the product" is bad; "I am naming a {what it does} for {who it's for}; the desired tone is {tone}; what are 15 candidate names spanning literal-descriptive to abstract-evocative?" is good. The reframe forces the user to surface constraints they have been carrying implicitly — which makes the brainstorm output sharper.

If the user's question is too vague to call the tool productively, ask one targeted clarifying question first. Do not invent the constraints yourself.

### 2. Invoke `python3 "<plugin-root>/coordinator.py"` with `effort='low'` in every eligible advisory row and no `tier` request field

Divergent generation favors **throughput over depth** — `flash` (resolves to the fastest eligible independent reviewer allowed by central policy) is the right default. Bump to `pro` (resolves to the strongest eligible independent reviewer allowed by central policy) only for highly nuanced creative work where reasoning depth on each candidate idea is more valuable than candidate breadth.

The public coordinator accepts no brainstorm-specific fields. Put the
following as labeled sections inside the single `prompt` string and dispatch
only through an advertised read-only advisory contract. If the native route
is unavailable, return typed unavailable; do not invent coordinator fields or
reconstruct a provider invocation:

- `prompt` — the framed problem statement.
- `domain` — the subject-matter area (e.g., "product naming," "experimental design," "audit-finding mitigation").
- `constraints` — the must-haves and must-avoids (audience, tone, budget, regulatory bounds, scope limits).
- `existingContext` — what the active primary or the user has already tried, decided, or ruled out (so the brainstorm does not waste turns retreading).
- `ideaCount` — how many candidates to generate (default 12 is a reasonable starting point; raise for very broad option spaces, lower for tightly-constrained ones).
- `methodology` — see § Methodology selection below; default `auto` lets the tool pick.
- `includeAnalysis` — whether the tool should produce its own grouping/analysis alongside the ideas; default true is usually right, but turn off if you intend to do the synthesis yourself in step 4.

Always specify the **output shape** in the prompt — a numbered list with one candidate per line, no preamble, no closing commentary. Free-form prose responses are hard to synthesize across.

### 3. Ask for variation along axes, not a flat list

A flat list of 12 ideas often collapses to 3 clusters of variants. Force divergence by naming the axes the candidates should span. Examples:

- "Span conservative ↔ ambitious and technical ↔ user-facing — give me at least one candidate in each of the four quadrants."
- "Generate three candidates each at: low-cost / medium-cost / high-cost; immediate-deploy / six-month / two-year."
- "Surface candidates from at least four different methodologies (SCAMPER, design-thinking, lateral-thinking, first-principles)."

Axes-based prompts produce systematic coverage of the option space; flat prompts produce clustering around the most obvious solution category.

### 4. Do not pre-filter; let the weird ones through

If the tool returns three or four ideas that seem strange or impractical, **do not silently drop them** before showing the user. Pre-filtering at this stage destroys the value of the brainstorm — the user is often the one best positioned to spot the unexpected gem. If the tool returns a list that is uniformly safe or uniformly variations on the same theme, push back with a follow-up: "those are too similar — give me five more that take a genuinely different angle, including at least one you think is probably wrong."

### 5. Synthesize, then close

Do not just relay the raw list. When you present the result to the user:

- **Group** the candidates into 2–4 thematic clusters or methodological families. Name each cluster.
- **Surface 1–2 unexpected ones** that did not fit a cluster — flag them explicitly as "the outliers worth a look."
- **Hand the user a question** — "which cluster is most interesting?" or "do any of these change how you are framing the problem?" — that moves them toward convergence.

A brainstorm that ends with a raw list dump puts the synthesis work back on the user; this skill is not done until the synthesis is done.

## Methodology selection

Put a `methodology` instruction inside the prompt. It is not a coordinator
field. Default `auto` lets the selected role choose; explicit selection is
useful when you want a specific style of divergence. Brief guide:

| Methodology | Best for |
|---|---|
| `divergent` | Pure quantity — when you want many candidates, breadth over depth |
| `convergent` | Narrowing a generated set toward decision; use after an initial divergent pass |
| `scamper` | Modifying or recombining existing ideas (Substitute, Combine, Adapt, Modify, Put to other uses, Eliminate, Reverse) |
| `design-thinking` | Human-centered problem framing — when the question is "what should we build for whom" |
| `lateral` | Breaking conceptual ruts — when the user is anchored on one solution direction and needs alternatives that question the framing |
| `auto` | The tool picks; the right default unless you have a reason to override |

## Iteration

A single brainstorm round is rarely the whole job. After the first round:

- Pick the cluster that surfaces the most interest and request 5–10 more candidates in that direction. (This is convergence-via-divergence — narrowing the option space by going wider in the chosen sub-space.)
- Pick the cluster that feels weakest and ask "what would it take to make this category actually viable?" — the constraints that surface often illuminate the real problem.
- For follow-up clarification or fact-checking of a specific candidate, call `python3 "<plugin-root>/coordinator.py"` directly with the focused question. Reserve `python3 "<plugin-root>/coordinator.py"` for the divergent passes.

Iteration ends when the user converges on a direction or explicitly steps out of ideation into decision-making. Do not keep generating because more is always available.

## Examples across domains

Brainstorming is broadly applicable. A representative sample of where cross-family ideation pays off:

| Domain | Problem framing | What the brainstorm typically surfaces |
|---|---|---|
| Product management | Naming a new product line | Candidates spanning the literal-descriptive ↔ abstract-evocative axis, including names the active primary's training would have under-weighted |
| Software architecture | Choosing a messaging pattern for a new distributed system | Alternatives beyond the obvious queue-vs-stream binary — pub/sub variants, log-as-truth, event sourcing, peer-to-peer |
| Clinical research | Generating candidate primary endpoints for a Phase 2 trial | Outcome measures across short-term symptomatic, long-term functional, biomarker, patient-reported, and composite categories |
| Finance | Structuring a hedge against a multi-currency exposure | Instruments spanning forwards, options, natural hedges, operational re-shoring, and partial-exposure-acceptance strategies |
| Legal | Drafting a remedy clause for a vendor SLA breach | Remedies across service credits, termination rights, audit triggers, escalation paths, and reputational protections |
| Systems engineering | Mitigation strategies for a recurring network-segmentation incident | Options across topology change, monitoring change, runbook change, organizational change, and accept-and-document |
| Strategy | Market-entry approach for a new geography | Modes spanning greenfield, partnership, acquisition, licensing, and observe-and-wait, with the trade-offs each route enforces |
| Hiring | Restructuring the interview loop for a hard-to-fill role | Loop designs spanning depth-first, panel, work-sample, async take-home, and trial-engagement formats |
| Research methodology | Choosing a study design for a new research question | Designs across observational, cross-sectional, longitudinal, RCT, natural-experiment, and mixed-method options |
| Operations | Reducing on-call paging burden | Interventions across alert-threshold tuning, runbook automation, ownership rotation, tooling upgrades, and root-cause platform investments |

Pick examples from the user's domain when explaining the brainstorm scope. Match where they are — generic framing produces generic interest.

## Anti-patterns

- **Asking the reviewer to decide.** Brainstorming is divergent. Asking "which is best?" pushes the model into a synthesis it has no business making for the user — and trains the user to outsource judgment.
- **Accepting the first list without pressing for divergence.** The first list often clusters around the most obvious solution category. Push back at least once for genuinely different angles before settling.
- **Mixing convergence into the brainstorm prompt.** "Give me 10 options ranked by likelihood of success" is a different request — and a worse one for this stage. Generate first, evaluate later. If the user genuinely wants ranking, do a second-pass convergent invocation, not a mixed-mode first pass.
- **Using `pro` tier reflexively because the topic feels weighty.** Divergent generation favors `flash` — more candidates, faster, at the same quality. Reserve `pro` for cases where each candidate genuinely needs reasoning depth (e.g., generating hypothetical contract clauses where each one needs internal coherence, not just one-line bullet points).
- **Pre-filtering the weird ones before showing the user.** The strange-looking candidate is often where the gem hides. Show everything; let the user prune.
- **Dumping the raw list and calling it done.** Synthesis (cluster, name the clusters, flag outliers, hand the user a forward question) is the user-facing deliverable. The list itself is intermediate.
- **Running this on a question the user has already brainstormed three times.** At that point the bottleneck is decision-making, not idea-shortage. Say so and pivot to convergence support.
- **Brainstorming a question that has a single right answer.** "What is the capital of France" does not need a divergent thinking partner. Route fact-finding through `python3 "<plugin-root>/coordinator.py"` directly.
