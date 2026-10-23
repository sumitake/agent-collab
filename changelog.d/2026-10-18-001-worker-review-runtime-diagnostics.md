### agent-collab 7.0.9 — runtime 5.0.12

#### Changed
- Worker guidance distinguishes expected task duration from the configured
  inactivity bound and keeps cancellation, partial work, cleanup, and provider
  status separate. Validation stays primary-owned unless a focused worker
  check has an exact preverified interpreter.
- Review guidance grounds external API blockers in the exact called method and
  relevant version, and identifies uncertainty when that evidence is missing.
- Runtime 5.0.12 improves diagnostics for certain Gemini startup failures
  without changing request status or returned content.
- Add OpenCode 2 compatibility with clearer readiness reporting.
- Keep existing routing eligibility and public request/response contracts.
- Refresh version-bound project-estimation bootstrap data, retaining calibration
  warnings and unknown numeric quotas. Pricing covers exact configured models
  without borrowing prices for unknown models.

#### Why
- Make bounded delegation predictable, reduce worker time spent searching for
  unavailable test environments, and prevent review findings from encoding an
  unsupported SDK contract.
- Make startup failures easier to diagnose while preserving existing routing
  and returned content.
