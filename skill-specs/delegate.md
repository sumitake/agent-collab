---
name: delegate
version: {{ skill_version }}
{{ delegate_defaults_block }}
description: Fan out summary, extraction, or analysis subtasks over supplied bounded documents or a sealed repository to an eligible delegate — {{ verifier_agent }} by default — for parallel execution alongside {{ primary_agent }} where parallel coverage adds value. Use when the user says "delegate to {{ verifier_agent }}," "split this with {{ verifier_agent }}," "fan this out," "have {{ verifier_agent }} take half of these," "research these in parallel with {{ verifier_agent }}," "divide and conquer with {{ verifier_agent }}," or when {{ primary_agent }} would otherwise process many independent items serially and additional source coverage or lower serial latency would help.
---

# Delegate — fan out independent subtasks for parallel advisory work

When the work applies the same operation across independent items, splitting it
between the primary and an eligible worker can reduce serial work and improve
coverage of the supplied sources. This skill does not discover or browse for new
sources. A bare topic or list of names is not a valid context request; first
obtain a bounded corpus through an already authorized source-reading mechanism,
or request the missing source material before dispatch. Delegation does not establish a different model family or independent
governance evidence. Compare the coverage and latency benefit against the cost
of doing the same work to the same standard with the host's native parallel tool.
Use the route when that benefit justifies the coordination overhead.

## When to use

Use this skill when:

- **The user explicitly asks for it** — "delegate to {{ verifier_agent }}," "split this with {{ verifier_agent }}," "fan this out," "have {{ verifier_agent }} take half of these," "research these in parallel with {{ verifier_agent }}," "divide and conquer with {{ verifier_agent }}."
- **A supplied set of source documents** needs per-item extraction or analysis — competitor reports, company filings, candidate profiles, regulatory excerpts, or academic papers. Topic names and links alone are not document contents.
- **A set of independent documents** needs parallel summarization where two readers may surface different signal.
- **A bounded repository inventory or tracing task** can be split into independent questions about the same sealed repository.

## When to skip

- **The subtasks have sequential dependencies** (Step 2 needs Step 1's output). The skill is for independent fan-out only.
- **The task is "do this N times" with no additional coverage or latency benefit.** Use {{ primary_agent }}'s native parallel-subagent tool — it avoids the coordination overhead, has lower latency, and produces uniform output while retaining source attribution.
- **The list has only 1–2 items.** The orchestration overhead exceeds the benefit; just do them serially.
- **The user wants a single source-grounded synthesis** rather than per-item output. Use `context` for a bounded corpus or `second-opinion` for an authored draft.

## Procedure

### 1. Split the workload

Decide how to divide the items. A reasonable default: roughly even split, with {{ primary_agent }} taking the items that benefit most from context the user has already shared with this session and {{ verifier_agent }} taking the rest. For a list of 5 items, that's typically 2 to {{ primary_agent }} + 3 to {{ verifier_agent }} (or the inverse).

Avoid pathological splits: giving {{ verifier_agent }} a single item alone wastes the parallelism; giving {{ verifier_agent }} all items should be justified by the workload and integration plan.

### 2. Bind the sources and request a useful output format

Choose exactly one admitted source mode for each work unit, following `context`:

- Documents: bounded UTF-8 `documents` objects with `label` and `content`, using
  `context.documents.extract` or `context.documents.reason`.
- Repository: canonical `repo_root` and exact `expected_repo_head`, using
  `context.repository.extract` or `context.repository.reason`.

Do not submit prompt-only topics, hybrid source modes, document paths/globs/file
handles, unextracted binaries, or requests to escape the supplied source boundary.
If a source is missing, report the gap before dispatch; do not imply that the
worker will browse for it. Each portion must have the source material needed to
answer its assigned questions.

Request a shared table or numbered-record format to ease synthesis. This is a
presentation preference; useful native prose remains available for interpretation.

### 3. Dispatch {{ verifier_agent }}'s portion

Select an existing descriptor-admitted context extraction or reasoning action
that matches the bounded documents or repository being supplied. Do not invent
a logical `delegate` action. Submit the bounded work unit through
`{{ mcp_tool_ask }}`. Use {{ delegate_call_params_flash }} for bulk extraction and
{{ delegate_call_params_pro }} for reasoning-heavy items. The runtime selects an
eligible worker; it does not perform primary/author family exclusion for the
caller. These context results remain advisory, not review or governance evidence.

Use only the co-packaged coordinator. Do not make Grok or any absent provider
mandatory, reconstruct a provider command, or silently replace an operator-named
target. A consumed work unit is never replayed or failed over. Normal untargeted
routing is appropriate for ordinary advisory delegation.

Record observed worker lineage and its source when available. Role, route,
provider name, status, receipt, and target selection do not establish a different
family. Label same-family or unknown-lineage contributions as advisory, and do
not claim dual-family coverage without positive observed-lineage evidence.

Example document work unit:

Supply three source reports as bounded `documents` objects, then use this
payload with `context.documents.extract`:

```
Extract the stated product, audience, price and reporting date from each supplied
report. Return a Markdown table with those columns plus the document label and
supporting passage. Mark missing information as absent from the supplied corpus.
Use only the supplied contents; do not infer current facts or find new sources.
```

If the returned output does not match the requested format, preserve and interpret
the full raw response. A formatting preference is not a native failure or a
content gate. Do not replay the provider request to repair formatting.

### 4. Execute {{ primary_agent }}'s portion in parallel

While the worker works, process {{ primary_agent }}'s assigned items using the same output format. The parallel execution is the whole point of the skill; serializing {{ primary_agent }}'s work after the worker returns defeats the latency reduction.

### 5. Synthesize and ANNOTATE attribution

Merge the two halves into a unified response. **Mark which items came from {{ verifier_agent }}** — either inline (`*(via {{ verifier_agent }})*` beside each item) or in a footer (`Items 3–5 analyzed by {{ verifier_agent }}; items 1–2 by {{ primary_agent }}`). The user has different calibration on each model's outputs; they need to know which is which.

The annotation also matters for the user's audit trail. If a downstream fact turns out to be wrong, the user needs to know which model produced it so they know which side's reliability they're recalibrating.

## Examples across domains

Every example requires supplied document contents or the repository source mode
above. These are corpus-analysis tasks, not open-ended source discovery.

| Supplied corpus | Per-item output | Benefit of splitting the work |
|---|---|---|
| Six competitor reports with dates | Product, audience and price with source passages | Cover every supplied report and expose conflicting claims |
| Eight vendor proposals and a rubric | Criterion-by-criterion evidence | Reduce serial reading while preserving the same rubric |
| Ten customer-interview transcripts | Themes, quotes and unanswered questions | Cover the full interview set with traceable attribution |
| Five jurisdictions' supplied regulatory excerpts | Stated rule, effective date and citation | Preserve jurisdiction-specific sources and flag missing material |
| Eight supplied academic papers | Method, findings and limitations | Extract comparable fields from every paper |
| Seven supplied company filings | Reported metrics, period and currency | Keep period differences and absent data explicit |
| Fifty supplied customer tickets | Category and supporting text | Split high-volume categorization and examine disagreements |
| One sealed repository at an exact commit | Per-module inventory or control-flow traces | Divide source-reading questions against a common source identity |

Split independent items, keep their source bindings, and annotate attribution in
the synthesis. Multiple workers do not imply multiple model families.

## Anti-patterns

- **Hiding the split.** Always annotate which items came from {{ verifier_agent }}. The user's calibration on each model is different; conflating the sources misleads them.
- **Delegating sequential work** where one subtask depends on another's output. The skill is for independent fan-out only.
- **Omitting source contents or treating a requested format as a gate.** Bind the corpus before dispatch and interpret all returned content, including prose that differs from the preferred format.
- **Using this when a single {{ primary_agent }} parallel-subagent call would do the same job** with no additional coverage or latency benefit. The orchestration overhead is unjustified.
- **Pathological splits** (give {{ verifier_agent }} a single item or all the items). The first wastes parallelism; the second needs a workload and integration justification. Aim for roughly even.
- **Using frontier/maximum on bulk extraction or lookups.** Economical/minimal is the right default — throughput matters more than depth on each item. Reserve frontier/maximum for items genuinely requiring analysis.
- **Asking {{ verifier_agent }} for *judgment* synthesis** across its items (e.g., "rank these 3 competitors"). The judgment should happen in the merge step where the user can see both halves; the worker produces per-item structured output only.
- **Silently replaying for formatting.** Preserve and interpret the raw output;
  formatting alone is not a provider failure or authorization for another attempt.
