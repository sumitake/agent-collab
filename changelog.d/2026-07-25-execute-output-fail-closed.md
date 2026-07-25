### agent-collab 4.4.2 — 2026-07-25

### Fixed

- Reject managed `execute` responses whose `result.text` is missing,
  non-string, empty, whitespace-only, Unicode-invisible/filler-only,
  replacement-glyph-only, terminal-control-only, or malformed instead of
  accepting a false-positive `status=ok`.
  Invalid success is a terminal `protocol_error` and cannot enter automatic
  family fallback. `readiness` remains exempt, and typed containment, timeout,
  teardown, and provider failures retain their classifications.

- Ship a content-addressed execute-output conformance contract with a frozen
  Unicode-16 blankness table so the public client can fail closed even when an
  older signed runtime emits a defective success envelope. Include it in the
  canonical release archive beside `runtime_client.py` and verify exact bytes.

- Enforce exact CSI byte-class ordering and a closed OSC/C1 support matrix,
  rejecting malformed sequences and unsupported control strings rather than
  stripping printable residue into an apparent answer.

- Retain the original absolute request deadline through direct and broker
  response parsing. Classification of a near-limit blank/control stream now
  returns typed `timeout` if it consumes the remaining budget.
