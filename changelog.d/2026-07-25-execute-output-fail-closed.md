### agent-collab 4.4.2 — 2026-07-25

### Fixed

- Reject managed `execute` responses whose `result.text` is missing,
  non-string, empty, whitespace-only, Unicode-invisible-only, terminal-control
  only, or malformed instead of accepting a false-positive `status=ok`.
  Invalid success is a terminal `protocol_error` and cannot enter automatic
  family fallback. `readiness` remains exempt, and typed containment, timeout,
  teardown, and provider failures retain their classifications.

- Ship a content-addressed execute-output conformance corpus so the public
  client can fail closed even when an older signed runtime emits a defective
  success envelope.
