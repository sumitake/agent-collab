### agent-collab 6.3.0 — 2026-08-25

#### Added

- Capture typed terminal coordinator failures automatically in a private,
  allowlist-only host-local outbox after the response is complete. Sensitive
  invocation material and provider output are excluded; capture failure cannot
  change the original response, authority, or no-replay contract. External
  issue filing remains a separately governed workspace operation.

Addressed: #171
