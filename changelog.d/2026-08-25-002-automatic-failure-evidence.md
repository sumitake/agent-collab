### agent-collab 6.3.0 — 2026-08-25

#### Added

- Capture typed terminal coordinator failures automatically in a private,
  allowlist-only host-local outbox after the response is complete. Sensitive
  invocation material and provider output are excluded; capture failure cannot
  change the original response, authority, or no-replay contract. External
  issue filing remains a separately governed workspace operation. The capture
  module is included in the closed release archive, and even a broken stderr
  warning channel cannot suppress the already-formed typed response.
- Admit invocation selectors into failure evidence only after the coordinator
  has validated them against its closed wire contract. Rejected raw request
  values are omitted even when they resemble syntactically valid control
  tokens.
- Serialize the host-local capacity check with atomic publication across
  concurrent coordinator processes under a bounded lock wait, preserving
  ordinary concurrent evidence while keeping the 10,000 unresolved-event bound
  hard; locally accepted history does not consume that active limit.
- Omit the request-identifier digest when a malformed identifier cannot encode
  as UTF-8, preserving the typed failure event without retaining raw input.

Addressed: #171, #173, #174
