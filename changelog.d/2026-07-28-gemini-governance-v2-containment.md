### agent-collab 4.5.4 — 2026-07-28

#### Fixed

- The public Gemini governance consumer no longer rejects the producer's
  access-only canary mode with a false `runtime Gemini result contract
  mismatch` protocol error on both lanes (workspace issue #2422). The proof v2
  contract now admits exactly two raw case-sensitive containment strings,
  `write_contained_shared_home` and `nonwriteback_ephemeral_home`
  (`GEMINI_GOVERNANCE_V2_CONTAINMENTS`), while proof v1 remains exactly
  `write_contained_shared_home` (`GEMINI_GOVERNANCE_V1_CONTAINMENTS`) for
  retained-lane rollback continuity.
- A v2 result's containment must equal the independently supplied proof
  containment exactly; dual set membership without equality, mixed or hybrid
  v1/v2 schemas, unknown, empty, case-variant, whitespace-variant, or
  non-string containment values all fail closed with no trim, folding,
  normalization, coercion, or default.
- Governance readiness recognizes either exact containment mode as
  capability-only; readiness never authorizes execution. Regression tests cover
  both result/proof crossing directions, every mandatory readiness tuple member
  under the ephemeral mode, unrelated tuple tampering under ephemeral v2, v1
  rollback strictness, and the exact public constants.
