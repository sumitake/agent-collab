### agent-collab 4.3.5 — 2026-07-25

#### Fixed

- Accept exact legacy Gemini governance proof v1 and recovery-capable proof v2
  as disjoint public success contracts so a verified retained v1 lane remains
  callable while a v2 runtime is staged.
- Select v2 validation whenever any recovery discriminator is present. Reject
  partial, hybrid, coerced, contradictory, or cross-field-mismatched results
  instead of falling back to the legacy contract.
- Name both exact public proof keysets explicitly and document the verified
  child-runtime/private-pipe trust boundary. The proof hash is a consistency
  check rather than a signature; complete v1 remains accepted only for
  retained-lane rollback continuity.
