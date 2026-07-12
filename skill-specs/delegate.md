---
name: delegate
version: {{ skill_version }}
{{ delegate_defaults_block }}
description: Fan out independent research, summary, extraction, or fact-finding subtasks to a cross-family delegate — {{ verifier_agent }} by default — for parallel execution alongside {{ primary_agent }} where dual-model coverage adds value. Use when the user says "delegate to {{ verifier_agent }}," "split this with {{ verifier_agent }}," "fan this out," "have {{ verifier_agent }} take half of these," "research these in parallel with {{ verifier_agent }}," "divide and conquer with {{ verifier_agent }}," or when {{ primary_agent }} would otherwise process many independent items serially and cross-family coverage would help.
---

# Delegate — fan out independent subtasks for parallel cross-family coverage

When the work is **the same operation across many independent items**, splitting the workload between {{ primary_agent }} and {{ verifier_agent }} cuts latency AND adds cross-family coverage value (the two families surface different sources, framings, defaults). This is **map-reduce with two readers**, not just parallel dispatch — the latter is what {{ primary_agent }}'s native parallel tool (e.g., subagent fan-out) does without the cross-model coordination overhead.

The cross-family value is the gating criterion. If the items can be processed identically by one family with no coverage benefit from a second, prefer the native parallel tool. The delegate skill is for when **two perspectives across the list** is the point.

## When to use

Use this skill when:

- **The user explicitly asks for it** — "delegate to {{ verifier_agent }}," "split this with {{ verifier_agent }}," "fan this out," "have {{ verifier_agent }} take half of these," "research these in parallel with {{ verifier_agent }}," "divide and conquer with {{ verifier_agent }}."
- **A list of independent research items** needs coverage — competitors, companies, candidates, regulatory citations, academic papers — where two model families surfacing different sources or framings is valuable.
- **A set of independent documents** needs parallel summarization where two readers may surface different signal.
- **Any map-reduce task** where the subtasks don't depend on each other AND dual-model coverage is desirable.

## When to skip

- **The subtasks have sequential dependencies** (Step 2 needs Step 1's output). The skill is for independent fan-out only.
- **The task is "do this N times" with no cross-model coverage value.** Use {{ primary_agent }}'s native parallel-subagent tool — it avoids the cross-model coordination overhead, has lower latency, and produces uniform output without annotation.
- **The list has only 1–2 items.** The orchestration overhead exceeds the benefit; just do them serially.
- **The user wants a single synthesized answer** rather than per-item output. Cross-family delegation produces per-item attributed results; a single synthesized answer is `long-context` or `second-opinion` territory.

## Procedure

### 1. Split the workload

Decide how to divide the items. A reasonable default: roughly even split, with {{ primary_agent }} taking the items that benefit most from context the user has already shared with this session and {{ verifier_agent }} taking the rest. For a list of 5 items, that's typically 2 to {{ primary_agent }} + 3 to {{ verifier_agent }} (or the inverse).

Avoid pathological splits: giving {{ verifier_agent }} a single item alone wastes the parallelism; giving {{ verifier_agent }} all items defeats the dual-coverage purpose.

### 2. Frame {{ verifier_agent }}'s portion with strict formatting

The killer failure mode of delegation is **inconsistent output formats** between {{ primary_agent }}'s portion and {{ verifier_agent }}'s portion. The merge step then has to normalize them, which loses signal and adds latency. Avoid this by giving {{ verifier_agent }} a strict format that exactly matches what {{ primary_agent }} will produce on its own portion.

Pick a structured output format that both halves will share:

- **Markdown table** for tabular comparisons (competitor research, candidate calibration, vendor evaluation)
- **JSONL one-per-item** for downstream programmatic consumption
- **Numbered list with consistent fields** for human-readable summaries

### 3. Dispatch {{ verifier_agent }}'s portion

Submit the sealed delegate role through `{{ mcp_tool_ask }}`. Use
{{ delegate_call_params_flash }} for bulk extraction and
{{ delegate_call_params_pro }} for judgment-heavy items. Central policy
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

**Retry-on-malformed.** If {{ verifier_agent }}'s output doesn't match the requested format, retry once with: "Previous response didn't match the requested format. Re-emit strictly per the template above ([format constraint]), no preamble or commentary." If still malformed, surface that to the user — a malformed-after-retry response is information, not something to paper over.

### 4. Execute {{ primary_agent }}'s portion in parallel

While the verifier works, process {{ primary_agent }}'s assigned items using the same output format. The parallel execution is the whole point of the skill; serializing {{ primary_agent }}'s work after the verifier returns defeats the latency reduction.

### 5. Synthesize and ANNOTATE attribution

Merge the two halves into a unified response. **Mark which items came from {{ verifier_agent }}** — either inline (`*(via {{ verifier_agent }})*` beside each item) or in a footer (`Items 3–5 researched by {{ verifier_agent }}; items 1–2 by {{ primary_agent }}`). The user has different calibration on each model's outputs; they need to know which is which.

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

- **Hiding the split.** Always annotate which items came from {{ verifier_agent }}. The user's calibration on each model is different; conflating the sources misleads them.
- **Delegating sequential work** where one subtask depends on another's output. The skill is for independent fan-out only.
- **Failing to give {{ verifier_agent }} strict formatting instructions.** Mismatched format requires manual normalization in the merge step, which adds latency and loses signal.
- **Using this when a single {{ primary_agent }} parallel-subagent call would do the same job** with no cross-family coverage value. The orchestration overhead is unjustified.
- **Pathological splits** (give {{ verifier_agent }} a single item or all the items). The first wastes parallelism; the second defeats dual coverage. Aim for roughly even.
- **Using `pro` tier on bulk extraction or lookups.** `flash` is the right default — throughput matters more than depth on each item. Reserve `pro` for items genuinely requiring analysis.
- **Asking {{ verifier_agent }} for *judgment* synthesis** across its items (e.g., "rank these 3 competitors"). The judgment should happen in the merge step where the user can see both halves; the verifier produces per-item structured output only.
- **Skipping the retry-on-malformed step.** Format mismatch defeats the merge; the retry is non-optional. If the second attempt is also malformed, surface the failure.
