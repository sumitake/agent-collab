---
name: knowledge-compile
version: 4.3.4
description: Compile multiple sources into a durable, cited knowledge dossier without mixing claims, assumptions, and decisions. Use when the user says "compile knowledge," "build a dossier," "create a knowledge base," "synthesize these sources," "preserve research context," "make this reviewable later," or "/agent-collab:knowledge-compile." Also offer this proactively when a task spans several repos, PRs, papers, articles, logs, agent messages, or drafts and future agents need source-separated context for independent review.
---

# Knowledge compile - durable research synthesis

Turn scattered sources into a reviewable knowledge artifact. The goal is not to maximize detail; it is to preserve enough source-separated context that another agent can audit the reasoning without repeating the entire search.

## Principles

- Separate facts, interpretations, decisions, and recommendations.
- Cite or identify every source clearly enough that another agent can reopen it.
- Keep direct quotations short and only when the exact wording matters.
- Record uncertainty and contradictions instead of smoothing them away.
- Do not update project memory, durable docs, or release notes unless the user or workflow explicitly authorizes that write.

## Workflow

1. **Define the review question.** State what the dossier is meant to help decide.
2. **Build a source inventory.** For each source, record title/path/URL, owner, date when available, trust level, and why it matters.
3. **Extract claims.** Capture atomic claims with source pointers. Mark whether each is observed, inferred, disputed, or stale-risk.
4. **Group by decision area.** Examples: security, workflow fit, release impact, cost, maintenance, portability, agent-specific constraints.
5. **Preserve contradictions.** Put conflicting claims side by side with evidence and a suggested way to resolve them.
6. **Write a compact synthesis.** Lead with the conclusion, then the evidence table, then unresolved questions.

## Output shape

```text
Knowledge dossier:
- Review question:
- Sources:
- Stable facts:
- Inferences:
- Contradictions:
- Decisions already made:
- Open questions:
- Recommended next review:
```

## Good uses

- Preserving external-repo research for Claude review.
- Summarizing draft PR context before a release agent takes over.
- Converting several agent messages into an auditable decision record.
- Building a source-separated methodology note from articles, docs, and code.

## Anti-patterns

- Flattening a source's claims into a single confident narrative.
- Dropping links or file paths because the summary "sounds complete."
- Treating one agent's synthesis as primary evidence.
- Mixing private local context into a document intended for external review.
- Writing memory updates just because the dossier exists.
