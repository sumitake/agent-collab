### agent-collab 4.3.3 — 2026-07-24

### Fixed

- Allow verified development or future runtime manifests to advertise the
  `codex/governance` route by adding it to the public client's manifest parser
  allowlist and the matching JSON schema enumeration. The currently shipped
  signed and notarized public runtime manifest remains unchanged at its honest
  ten-route capability set, so it does not claim the unshipped route and
  continues to return typed unavailable for it.

### Tests

- Pin the distinction between the client's accepted contract vocabulary and
  the exact routes advertised by the current signed public runtime.
