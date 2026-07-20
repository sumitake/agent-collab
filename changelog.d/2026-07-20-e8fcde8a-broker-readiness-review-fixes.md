### Fixed

- Type an accepted-request idle-probe failure as a teardown failure, not a
  protocol error: `_wait_for_job_idle` now fails closed on the expected
  `OSError` / `subprocess.SubprocessError` (and a pre-checked
  operator-home-unavailable) instead of letting them escape, while still
  raising on an invalid job label so a caller bug stays visible.
- Bound provider teardown by the caller deadline: `_terminate_and_reap` polls
  to reap the SIGKILLed session-group leader within a small grace of the
  caller deadline rather than two fixed five-second waits, and reports a
  proven teardown only when the whole-group kill was posted AND the leader was
  reaped, so a leader-only fallback is honestly typed as a teardown failure.
- Reject an incomplete Codex rollout tail instead of trusting the preceding
  model context: `_codex_rollout_window` fails closed on a non-newline-
  terminated final record, so a concurrently written model-changing record can
  no longer yield stale governance-ready identity.
