---
name: delegate
version: 4.2.2
defaults:
  tier: Fast
  effort: low

description: Fan out independent research, summary, extraction, or fact-finding subtasks to a cross-family delegate — the reviewer by default — for parallel execution alongside the active primary where dual-model coverage adds value. Use when the user says "delegate to the reviewer," "split this with the reviewer," "fan this out," "have the reviewer take half of these," "research these in parallel with the reviewer," "divide and conquer with the reviewer," or when the active primary would otherwise process many independent items serially and cross-family coverage would help.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host/model, captures artifact provenance, excludes same-family routes, and verifies the co-packaged native manifest. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. Frontmatter `tier` is a routing recommendation, never a coordinator request field. For a review, cross-check, tiebreaker, or fallback over an authored artifact, capture its exact UTF-8 content and observed author model in the optional `artifact` object even when governance is false; never paste it into the prompt as a provenance substitute.

# Delegate — fan out independent subtasks for parallel cross-family coverage

When the work is **the same operation across many independent items**, splitting the workload between the active primary and the reviewer cuts latency AND adds cross-family coverage value (the two families surface different sources, framings, defaults). This is **map-reduce with two readers**, not just parallel dispatch — the latter is what the active primary's native parallel tool (e.g., subagent fan-out) does without the cross-model coordination overhead.

The cross-family value is the gating criterion. If the items can be processed identically by one family with no coverage benefit from a second, prefer the native parallel tool. The delegate skill is for when **two perspectives across the list** is the point.

## When to use

Use this skill when:

- **The user explicitly asks for it** — "delegate to the reviewer," "split this with the reviewer," "fan this out," "have the reviewer take half of these," "research these in parallel with the reviewer," "divide and conquer with the reviewer."
- **A list of independent research items** needs coverage — competitors, companies, candidates, regulatory citations, academic papers — where two model families surfacing different sources or framings is valuable.
- **A set of independent documents** needs parallel summarization where two readers may surface different signal.
- **Any map-reduce task** where the subtasks don't depend on each other AND dual-model coverage is desirable.

## When to skip

- **The subtasks have sequential dependencies** (Step 2 needs Step 1's output). The skill is for independent fan-out only.
- **The task is "do this N times" with no cross-model coverage value.** Use the active primary's native parallel-subagent tool — it avoids the cross-model coordination overhead, has lower latency, and produces uniform output without annotation.
- **The list has only 1–2 items.** The orchestration overhead exceeds the benefit; just do them serially.
- **The user wants a single synthesized answer** rather than per-item output. Cross-family delegation produces per-item attributed results; a single synthesized answer is `long-context` or `second-opinion` territory.

## Procedure

### 1. Split the workload

Decide how to divide the items. A reasonable default: roughly even split, with the active primary taking the items that benefit most from context the user has already shared with this session and the reviewer taking the rest. For a list of 5 items, that's typically 2 to the active primary + 3 to the reviewer (or the inverse).

Avoid pathological splits: giving the reviewer a single item alone wastes the parallelism; giving the reviewer all items defeats the dual-coverage purpose.

### 2. Frame the reviewer's portion with strict formatting

The killer failure mode of delegation is **inconsistent output formats** between the active primary's portion and the reviewer's portion. The merge step then has to normalize them, which loses signal and adds latency. Avoid this by giving the reviewer a strict format that exactly matches what the active primary will produce on its own portion.

Pick a structured output format that both halves will share:

- **Markdown table** for tabular comparisons (competitor research, candidate calibration, vendor evaluation)
- **JSONL one-per-item** for downstream programmatic consumption
- **Numbered list with consistent fields** for human-readable summaries

### 3. Dispatch the reviewer's portion

Submit the sealed delegate role through `python3 "<plugin-root>/coordinator.py"`. Use
low-effort advisory rows for bulk extraction and
high-effort advisory rows for judgment-heavy items. Central policy
resolves the eligible worker after family exclusion; Claude/Anthropic remains
async inbox-only.

**Grok delegation is native-runtime-only.** The standalone worker plugin and
its raw CLI recipe are retired. Do not invoke `grok` directly, reconstruct the
removed recipe, or silently substitute a same-family delegate. If the signed
runtime does not advertise the required Grok role, state that portion is
temporarily unavailable and continue only with another preflight-eligible,
independent-family route.

Example prompt:

```
Research the 3 [items] below. Output ONLY a Markdown table with columns: [Column A | Column B | Column C | Column D]. No preamble, no closing.

ITEMS: [Item 1, Item 2, Item 3]

For each row, [domain-specific instruction — e.g., "use publicly verifiable sources only" or "cite the year of the data point in parentheses"].
```

**Retry-on-malformed.** If the reviewer's output doesn't match the requested format, retry once with: "Previous response didn't match the requested format. Re-emit strictly per the template above ([format constraint]), no preamble or commentary." If still malformed, surface that to the user — a malformed-after-retry response is information, not something to paper over.

### 4. Execute the active primary's portion in parallel

While the verifier works, process the active primary's assigned items using the same output format. The parallel execution is the whole point of the skill; serializing the active primary's work after the verifier returns defeats the latency reduction.

### 5. Synthesize and ANNOTATE attribution

Merge the two halves into a unified response. **Mark which items came from the reviewer** — either inline (`*(via the reviewer)*` beside each item) or in a footer (`Items 3–5 researched by the reviewer; items 1–2 by the active primary`). The user has different calibration on each model's outputs; they need to know which is which.

The annotation also matters for the user's audit trail. If a downstream fact turns out to be wrong, the user needs to know which model produced it so they know which side's reliability they're recalibrating.

## Examples across domains

| Domain | List to fan out | Per-item output | Why dual coverage helps |
|---|---|---|---|
| Competitive research | 6 competitors to profile | Markdown row per competitor (name, value prop, audience, pricing, last funding round) | Two families surface different sources; one may catch a recent funding round the other missed |
| Vendor evaluation | 8 vendors against a 5-criterion rubric | Markdown table (vendor × criterion) | Different families weight criteria differently; surfacing both reads catches single-family bias |
| Hiring / sourcing | 12 candidate profiles to screen against a JD | One paragraph per candidate (fit / red flags / questions to ask in screen) | Different families flag different red flags; coverage on a long list reduces miss rate |
| Multi-document summarization | 10 customer-interview transcripts | One structured summary per interview (themes / quotes / open questions) | Two readers surface different framings; merge produces broader coverage of insights |
| Regulatory research | 5 jurisdictions' rules on a specific topic | Markdown table (jurisdiction × rule × source citation) | Per-jurisdiction sources differ in coverage; dual reads catch more accurately-cited material |
| Academic literature scan | 8 papers on a methodology | One summary per paper (method / findings / limitations / relevance) | Different families weight what's "relevant" differently; coverage is broader |
| Clinical trial landscape | 6 active trials in an indication | One row per trial (phase, endpoint, eligibility, primary investigator) | Cross-family sourcing catches different trial registries |
| Patent landscape | 10 patents to summarize | One row per patent (claim summary / freedom-to-operate impact / status) | Patent databases have different coverage; dual reads improve completeness |
| Financial peer benchmarking | 7 peer companies' last-quarter metrics | Table (company × revenue × growth × margin × cap structure) | Source disagreement is itself a signal; dual reads surface the disagreements |
| Customer ticket categorization | 50 recent tickets to label | Per-ticket label (category, severity, suggested-routing) | High-volume bulk categorization where one family's category boundaries differ from the other's; the disagreements are the interesting cases |

The pattern is constant: list of independent items, structured output per item, split between families, annotate attribution in the merge.

## Anti-patterns

- **Hiding the split.** Always annotate which items came from the reviewer. The user's calibration on each model is different; conflating the sources misleads them.
- **Delegating sequential work** where one subtask depends on another's output. The skill is for independent fan-out only.
- **Failing to give the reviewer strict formatting instructions.** Mismatched format requires manual normalization in the merge step, which adds latency and loses signal.
- **Using this when a single the active primary parallel-subagent call would do the same job** with no cross-family coverage value. The orchestration overhead is unjustified.
- **Pathological splits** (give the reviewer a single item or all the items). The first wastes parallelism; the second defeats dual coverage. Aim for roughly even.
- **Using `pro` tier on bulk extraction or lookups.** `flash` is the right default — throughput matters more than depth on each item. Reserve `pro` for items genuinely requiring analysis.
- **Asking the reviewer for *judgment* synthesis** across its items (e.g., "rank these 3 competitors"). The judgment should happen in the merge step where the user can see both halves; the verifier produces per-item structured output only.
- **Skipping the retry-on-malformed step.** Format mismatch defeats the merge; the retry is non-optional. If the second attempt is also malformed, surface the failure.
