### agent-collab 4.3.1 — 2026-07-23

#### Fixed

- Keep provider adoption callable after a dispatcher update commits by using
  the exact verified `selected` lane when no staged `candidate` exists.
- Bind both staged and committed canary paths to the co-packaged signed and
  notarized runtime identity, preserving fail-closed behavior on any selector
  mismatch or transient verification failure.

#### Verification

- Added regression coverage for staged-candidate, committed-selected,
  identity-mismatch, and notarization-unavailable paths.
