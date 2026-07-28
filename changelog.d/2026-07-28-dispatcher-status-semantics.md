### agent-collab 4.5.2 — 2026-07-28

### Fixed

- Bind `broker-status`'s `persistent_process` field to an exact live launchd
  properties proof instead of deriving it from a one-second point-in-time idle
  observation or trusting only the mutable on-disk plist.
- Add `persistence_state=nonpersistent|persistent|unproven`; report the matching
  `persistent_process=false|true|null`, fail readiness closed on unproven
  diagnostic output, and never conflate unknown configuration with observed
  persistence.
- Report that observation separately as `process_idle=true|false|null`; null
  means the idle probe did not run, while a measured active process does not
  make authoritative status reject a callable dispatcher during bounded
  post-request grace.
- Keep both new status observations optional for rolling-upgrade consumers and
  keep `process_idle` independent from the selected-lane liveness verdict when
  present.
- Pin sanitized golden transcripts captured from real nonpersistent,
  KeepAlive, and conditional-KeepAlive launchd jobs; closed brace structure,
  top-level property tokens, and structured event-trigger evidence fail closed
  on malformed or ambiguous format drift. Any event-trigger block is
  intentionally persistence-like rather than eligible for socket-only status.
- Leave every mutating lifecycle command on the existing full idle-proof
  boundary; a failed full-idle proof restores the pre-mutation selector.

### Cross-check

- Companion to workspace PR #2438. The revised cross-repo design is pending an
  exact-head distinct-family review before either PR may merge.
