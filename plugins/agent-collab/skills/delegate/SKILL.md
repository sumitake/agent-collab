---
name: delegate
version: 7.0.6
defaults:
  quality_profile: economical
  effort_class: minimal

description: Fan out summary, extraction, or analysis subtasks over supplied bounded documents or a sealed repository to an eligible delegate — the reviewer by default — for parallel execution alongside the active primary where parallel coverage adds value. Use when the user says "delegate to the reviewer," "split this with the reviewer," "fan this out," "have the reviewer take half of these," "research these in parallel with the reviewer," "divide and conquer with the reviewer," or when the active primary would otherwise process many independent items serially and additional source coverage or lower serial latency would help.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Honor an operator-named provider with `explicit_target`. For an authorized independent review or governance task without an operator-named provider, also use that field to bind the caller-verified distinct reviewer selected by the caller or designated by the workflow. Carry the same target into planning and live dispatch; verify returned native lineage before accepting independence. Otherwise use normal untargeted routing. Choose quality and effort for the workload; include context/output token estimates when known. Read the current manifest digest and actual cwd device/inode; do not copy example values. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not live availability or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.

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

- **The user explicitly asks for it** — "delegate to the reviewer," "split this with the reviewer," "fan this out," "have the reviewer take half of these," "research these in parallel with the reviewer," "divide and conquer with the reviewer."
- **A supplied set of source documents** needs per-item extraction or analysis — competitor reports, company filings, candidate profiles, regulatory excerpts, or academic papers. Topic names and links alone are not document contents.
- **A set of independent documents** needs parallel summarization where two readers may surface different signal.
- **A bounded repository inventory or tracing task** can be split into independent questions about the same sealed repository.

## When to skip

- **The subtasks have sequential dependencies** (Step 2 needs Step 1's output). The skill is for independent fan-out only.
- **The task is "do this N times" with no additional coverage or latency benefit.** Use the active primary's native parallel-subagent tool — it avoids the coordination overhead, has lower latency, and produces uniform output while retaining source attribution.
- **The list has only 1–2 items.** The orchestration overhead exceeds the benefit; just do them serially.
- **The user wants a single source-grounded synthesis** rather than per-item output. Use `context` for a bounded corpus or `second-opinion` for an authored draft.

## Procedure

### 1. Split the workload

Decide how to divide the items. A reasonable default: roughly even split, with the active primary taking the items that benefit most from context the user has already shared with this session and the reviewer taking the rest. For a list of 5 items, that's typically 2 to the active primary + 3 to the reviewer (or the inverse).

Avoid pathological splits: giving the reviewer a single item alone wastes the parallelism; giving the reviewer all items should be justified by the workload and integration plan.

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

### 3. Dispatch the reviewer's portion

Select an existing descriptor-admitted context extraction or reasoning action
that matches the bounded documents or repository being supplied. Do not invent
a logical `delegate` action. Submit the bounded work unit through
`python3 "<plugin-root>/coordinator.py"`. Use economical-quality, minimal-effort advisory rows for bulk extraction and
frontier-quality, maximum-effort advisory rows for reasoning-heavy items. The runtime selects an
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

### 4. Execute the active primary's portion in parallel

While the worker works, process the active primary's assigned items using the same output format. The parallel execution is the whole point of the skill; serializing the active primary's work after the worker returns defeats the latency reduction.

### 5. Synthesize and ANNOTATE attribution

Merge the two halves into a unified response. **Mark which items came from the reviewer** — either inline (`*(via the reviewer)*` beside each item) or in a footer (`Items 3–5 analyzed by the reviewer; items 1–2 by the active primary`). The user has different calibration on each model's outputs; they need to know which is which.

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

- **Hiding the split.** Always annotate which items came from the reviewer. The user's calibration on each model is different; conflating the sources misleads them.
- **Delegating sequential work** where one subtask depends on another's output. The skill is for independent fan-out only.
- **Omitting source contents or treating a requested format as a gate.** Bind the corpus before dispatch and interpret all returned content, including prose that differs from the preferred format.
- **Using this when a single the active primary parallel-subagent call would do the same job** with no additional coverage or latency benefit. The orchestration overhead is unjustified.
- **Pathological splits** (give the reviewer a single item or all the items). The first wastes parallelism; the second needs a workload and integration justification. Aim for roughly even.
- **Using frontier/maximum on bulk extraction or lookups.** Economical/minimal is the right default — throughput matters more than depth on each item. Reserve frontier/maximum for items genuinely requiring analysis.
- **Asking the reviewer for *judgment* synthesis** across its items (e.g., "rank these 3 competitors"). The judgment should happen in the merge step where the user can see both halves; the worker produces per-item structured output only.
- **Silently replaying for formatting.** Preserve and interpret the raw output;
  formatting alone is not a provider failure or authorization for another attempt.
