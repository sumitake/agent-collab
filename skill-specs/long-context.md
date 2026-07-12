---
name: long-context
version: {{ skill_version }}
{{ long_context_defaults_block }}
description: Send a large document, codebase, log dump, transcript, contract, or multi-file bundle to {{ verifier_agent }} for read-once-and-summarize tasks — extraction, synthesis, fact-finding, question-answering across a corpus too large to read inline. Use when the user says "summarize this big file with {{ verifier_agent }}," "have {{ verifier_agent }} read the whole codebase," "extract from this transcript," "long-context this with {{ verifier_agent }}," "read this whole document," "process this corpus," "what's in this PDF," "what does the contract say about X," "audit this log dump," or any framing that says "read this large input and tell me what's in it." Also offer this proactively when {{ primary_agent }} is about to either (a) sample-read a clearly-oversized file (instead of reading it whole), (b) iterate read-N-lines-then-read-M-more across a single large document, or (c) hold the entire corpus in working context when a one-shot summarize-and-extract would serve better.
---

# Long-context — read-once-and-summarize on an oversized input

When the input is large and the task is **extraction / synthesis / fact-finding** (not writing), the long-context skill offloads the read to {{ verifier_agent }} and asks for structured output back. The cross-family setup matters less here than in the verification skills; this is **collaborative information retrieval**, not independent verification. No verifier-independence rule applies — use whichever model has the right context window and retrieval fidelity for the input.

The reason this skill is distinct from `second-opinion` or `code-review`: it expects the input to be **too large to inline** and the task to be **one-shot summarize-and-extract**, not iterative refinement. The output is a structured artifact the user consumes; the verifier is not making a judgment call.

## When to use

Use this skill when one or more of the following are true:

- **The user explicitly asks for it** — "summarize this big file with {{ verifier_agent }}," "have {{ verifier_agent }} read the whole codebase," "extract from this transcript," "long-context this with {{ verifier_agent }}," "read this whole document," "process this corpus," "what's in this PDF," "what does the contract say about X," "audit this log dump."
- **A single file is large** — a long PDF, a multi-hour meeting transcript, a big log dump, a large CSV, a lengthy contract, an entire codebase exported as one file, a research-paper bundle.
- **Multiple files need to be read together** to answer one question — comparing two contract versions, synthesizing across a set of interview transcripts, auditing a directory of related files.
- **The user wants summarization, extraction, fact-finding, or thematic synthesis** rather than writing or editing.
- **A codebase audit or architecture mapping** where the verifier reads everything once and produces a structured overview.

## When to skip

Skip this skill when:

- **The task is writing or editing.** Keep that work in {{ primary_agent }} with targeted reads of the relevant sections. Long-context offloading is a poor fit for iterative authoring.
- **The file is small.** {{ primary_agent }} can read a 200-line file directly; the long-context framing adds overhead without value.
- **The user wants iteration** — long-context queries are usually one-shot. If the user will refine the question 5 times based on what comes back, the iterative cost of re-loading the corpus each turn dominates.
- **The user wants precise, line-by-line analysis** of a small but dense artifact — `code-review` or `logic-check` is better suited.
- **The corpus changes per turn** — re-uploading a moving target burns cost and time; consider whether you can stabilize the corpus first or restructure the task.

## Procedure

### 1. Capture the inputs as bounded text documents

The trusted primary reads the selected inputs locally and constructs the exact
`row.documents` array from the coordinator README: each item is
`{"label":"...","content":"..."}`. Paths, globs, directories, file handles,
and binary attachments are never sent to the coordinator. Extract text from
PDFs or other binary formats before routing. Keep the request within the
document-count and aggregate UTF-8 byte limits; pre-filter irrelevant files so
the reviewer is not diluted by lockfiles or generated output.

### 2. Specify the extraction shape

"Summarize this" produces uselessly-shaped summaries. Pick a shape that matches what the user actually wants to do with the output:

- **Question-answering** — "Find every mention of `{topic}` in the attached document and quote the surrounding 2-3 sentences. Group by section."
- **Structured extraction** — "Extract all `{entities, dates, decisions, action items, dollar amounts, parties, deadlines, ...}` into a table with columns `{...}`."
- **Synthesis** — "What are the 3-5 main themes across these documents? For each, quote at least one piece of supporting evidence with the source filename."
- **Audit** — "List every `{function, contract clause, log error pattern, regulatory citation}` in the corpus. Flag the ones that look anomalous, unusual, or worth a closer look. For each flag, quote the exact location."
- **Diff-style** — "What changed between version A and version B (or before/after the event at timestamp T)? Categorize each change as substantive (changes behavior or meaning) or cosmetic (formatting, naming, whitespace)."
- **Inventory / mapping** — "Build a navigable map of {the codebase / the contract / the transcript}: top-level structure, key sections, cross-references, anything that surprises you."

If the user has not specified the shape, pick the one that fits the artifact and confirm with the user in one line before calling: "I'll extract the action items and decisions from this transcript as a structured table; sound right?"

### 3. Call the verifier

Submit an exact `grok/huge_context` execute request with the captured documents
in `row` and the extraction instructions in `prompt`. The Gemini
`long_context` contract is currently containment-unavailable; it may be used
only after signed-runtime readiness advertises it. If Grok is same-family or
unavailable, return typed unavailable rather than inventing an automatic or
raw fallback. Use a structured-output template so downstream tooling and the
user receive predictable section headers.

Example template for a meeting-transcript extraction (adapt the section list to the chosen shape):

```
Read the attached transcript and produce ONLY the four sections below — no preamble, no closing, no commentary outside the sections.

1. SUMMARY (1 paragraph, ≤80 words): <what happened>
2. ACTION ITEMS (bulleted, format: `owner | task | deadline-or-"none"`): <items>
3. DECISIONS (vs. discussed-but-undecided): <items>
4. OPEN QUESTIONS: <items>

```

**Retry-on-malformed.** If the response does not contain all the requested numbered sections, retry exactly once with:

> Previous response did not include all required sections. Re-emit strictly per the template above, no preamble.

If the second attempt is also malformed, surface the failure rather than fabricating section structure around the verifier's prose. A malformed long-context output usually signals one of: the file was truncated mid-read; the verifier hit a content-policy block on the corpus; the template was ambiguous. All three are worth surfacing.

### 4. Handle chunked responses

For oversized output, prefer narrowing the prompt or splitting the source files
into explicit batches. The fixed native protocol enforces bounded output; do
not bypass that limit with a provider-specific command or an unadvertised
fetch-chunk mechanism.

### 5. Verify before reporting (high-stakes extractions)

For extractions where the user will act on the result — legal clauses, contractual commitments, action-item ownership, financial figures, dosing parameters, regulatory citations — spot-check 2–3 of the verifier's claims against the source. Long-context models can confabulate plausible-but-absent details, especially in dense or repetitive corpora. If a claim looks load-bearing, quote the exact source line so the user can verify themselves.

Verification is not optional for high-stakes extractions. Trust-but-verify is the discipline; "the verifier said it, so it must be there" is the failure mode.

### 6. Distill before relaying

Do not dump the verifier's full response back to the user. Extract the parts that answer the user's actual question, formatted for their consumption.

- If the user asked "what should I follow up on after that meeting?", the answer is a 5-bullet list of follow-ups — not a 2-page meeting summary.
- If the user asked "is there anything in this contract that should worry me?", the answer is a prioritized list of concerning clauses with the contract-section reference — not the full clause-by-clause extraction.
- If the user asked "what does this codebase do?", the answer is a 3-paragraph architecture summary — not the full inventory.

The verifier's structured output is the working artifact; the user-facing answer is what addresses the user's actual question.

## Examples across domains

Long-context applies wherever a corpus is too large to inline and the task is read-once-summarize. A representative sample:

| Domain | Corpus | Typical extraction shape |
|---|---|---|
| Legal | Multi-party vendor MSA (40+ pages) | Audit: list every indemnity clause, liability cap, termination right, governing-law clause; flag deviations from organization's standard template |
| Clinical research | Phase 2 trial protocol amendment + the existing protocol | Diff-style: what changed; categorize as substantive (changes endpoint, eligibility, dosing) vs administrative (typos, contact info, formatting) |
| Software architecture | Full codebase of a 30-file microservice | Inventory: map the modules, their responsibilities, their inter-dependencies; flag circular deps, dead code, undocumented public surface |
| Research synthesis | 8 user-interview transcripts (90 minutes each) | Synthesis: top themes across users, quoted evidence per theme, where users disagreed, what surprised the interviewer |
| Compliance | A quarter of customer-support tickets (~5,000) | Structured extraction: ticket-class distribution, top product areas mentioned, mentions of regulated topics (PHI, PII, financial details), escalation patterns |
| Finance | Quarterly earnings transcript + earnings release + 10-Q | Question-answering: what did management say about [specific risk factor]? Quote the exact lines from each document |
| Operations | A week's worth of production logs from a critical service (~200MB compressed) | Audit: anomalous error patterns, error-rate-by-endpoint, deploy-correlated incidents, novel error signatures |
| Product management | 6 months of user-research notes + feature-request inbox | Synthesis: emerging user-need themes, gaps between stated requests and observed behavior, decision-ready prioritization candidates |
| Engineering / ML | A research paper + the existing implementation reference | Diff-style: what the paper proposes vs what is already implemented; identify the actionable delta |
| Strategy | Competitor's last 4 earnings calls + their product-launch announcements | Synthesis: strategic-narrative shifts over time, recurring themes, what they've stopped saying that they used to say |

The structured-output discipline applies uniformly; the section list shifts with the extraction shape.

## Anti-patterns

- **Sending files without specifying the extraction shape.** "Summarize this" produces uselessly-shaped output. Pick a shape; constrain the format.
- **Trusting high-stakes extractions without verification.** Confabulation is real on long inputs. Spot-check 2–3 claims against the source before the user acts on the extraction.
- **Using {{ verifier_agent }} for tasks {{ primary_agent }} can do faster on a small file.** Long-context is for oversized inputs; small files are direct-read territory.
- **Inventing an unadvertised chunk-fetch path.** The response is bounded; narrow or batch the request instead.
- **Dumping the verifier's full structured output to the user** instead of distilling. The structured output is the working artifact; the user wants the answer to their actual question.
- **Adding a `tier` field to the request.** The closed schema accepts only the documented route/action and row fields.
- **Sending paths instead of captured content.** The coordinator never reads caller paths; use labeled UTF-8 documents.
- **Iterating long-context queries 5 times in a row.** The cost-per-iteration is high (re-loading the corpus); restructure the task so the verifier's one read produces multiple answers, or extract into a structured intermediate that {{ primary_agent }} can re-read locally for the follow-ups.
- **Asking long-context to *write*.** This skill is read-once-extract; writing belongs in {{ primary_agent }} with targeted reads of the relevant slices.
- **Sending a corpus that changes between calls.** Re-uploading a moving target burns cost; stabilize the corpus first or accept that each call is a fresh snapshot.
