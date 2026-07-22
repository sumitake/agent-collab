### Added

- Coordinator/host_policy: the `("codex","governance")` first-class **synchronous**
  governance-review route (operator-directed 2026-07-22), mirroring
  `gemini/governance` (prompt + artifact) with a pinned reviewer model + governance
  effort. Enables a proof-backed synchronous Codex governance review that anchors a
  Tier-3 peer review without the async inbox. Additive route (`ROUTE_ACTIONS`,
  `AUTHORITIES`, `GOVERNANCE_CONTRACTS`, `REVIEW_CONTRACTS`, `DIRECT_CONTRACTS`,
  a row-validation case); existing contracts are unchanged. Companion workspace
  change adds the runtime emission + the `validate_codex_governance_proof` gate.
