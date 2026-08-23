### agent-collab 6.2.1 — 2026-08-23

#### Fixed

- Complete one newline-terminated TTY request without waiting for EOF while
  preserving the exact EOF-delimited contract for noninteractive input.
- Recover identity-preserving public request spellings within one invocation,
  report each accepted normalization, and return bounded criteria for ambiguous
  target, action, effort, or future-runtime requests without starting a provider.

#### Changed

- Pre-admit the next signed descriptor projections for logical agents, model
  lineages, action-compatible targets, and effort floors without forwarding
  schema-7-only request context to the current schema-6 runtime.
- Keep the unchanged project-estimation aggregate, pricing, and quota evidence
  receipt-bound to the 6.2.1 source version.

Addressed: #130
