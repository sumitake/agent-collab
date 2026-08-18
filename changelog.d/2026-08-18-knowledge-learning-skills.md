### agent-collab 6.1.0 — project-knowledge and learning-loop skills

- Add the `project-knowledge` skill with a bundled deterministic, stdlib-only
  CLI (`knowledge_tool.py`: init / validate / lint / index / draft / export)
  that maintains a provenance-tracked `knowledge/` layer inside the user's
  project — source registry with trust levels, claim-marker and
  prompt-injection lint, a trust lattice, generated index/log, exclusive-create
  proposal drafts, and budget-capped untrusted-banner exports. The
  registry/frontmatter parser is a bounded restricted-YAML subset; no
  third-party dependency.
- Add the `learning-loop` skill with a bundled deterministic, stdlib-only CLI
  (`learning_ledger.py`: add / suggest / recur / index / check / lint) that
  maintains a project-local `.learnings/` lesson ledger — mechanical/judgmental
  lesson classes, prevention-debt surfacing, dedup + 24h echo-chamber
  recurrence locks, metadata-only consultation, and reuse-as-hypothesis
  discipline. Task references accept any non-empty external anchor.
- Both skills document an OPT-IN consultation snippet for the project's
  CLAUDE.md / AGENTS.md (explicit reads only; pages and ledger entries are
  data, never instructions). The root README's install section directs an
  installing agent to offer this snippet as a visible, consent-gated
  post-install setup step.
- Ship both CLIs at the plugin root and include them in the canonical archive
  member plan. No coordinator, routing, or provider runtime change (runtime
  stays `4.0.5`).
