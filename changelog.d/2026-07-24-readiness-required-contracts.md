### agent-collab 4.3.4 — 2026-07-24

### Fixed

- Fixed `migration_doctor` reporting `provider_routing="BLOCKED"` for the shipped runtime.
  Readiness compared the client's full acceptance set against the manifest, so the accepted
  but deliberately unadvertised `codex/governance` route marked the entire runtime invalid.
  Readiness is now judged against a required baseline (`REQUIRED_CONTRACTS`), with
  `OPTIONAL_CONTRACTS` holding routes a signed artifact may advertise but need not ship.
