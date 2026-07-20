### Fixed

- Type an accepted-request idle-probe failure as a teardown failure, not a
  protocol error: `_wait_for_job_idle` now fails closed on the expected
  `OSError` / `subprocess.SubprocessError` and on a typed
  `_OperatorHomeUnavailable` raised by `_launchctl`'s per-call operator-home
  re-resolution (a `ValueError` subclass, so the environmental case is caught
  race-free while a genuine code-bug `ValueError` and an invalid job label
  still surface).
- Bound provider teardown by the caller deadline: `_terminate_and_reap` polls
  to reap the SIGKILLed session-group leader within a small grace of the
  caller deadline rather than two fixed five-second waits, and reports a
  proven teardown only when the whole-group kill was posted AND the leader was
  reaped, so a leader-only fallback is honestly typed as a teardown failure.
- Bound the request-dispatch path's retained-lane availability probe by the
  request deadline: `_launch_broker` now starts the deadline before capturing
  lanes and threads it through `_capture_broker_lanes` → `_job_loaded` →
  `_launchctl`, so a small-`timeout_ms` request no longer blocks on
  launchctl's ~20s default before dispatch (lifecycle/status callers keep the
  default bound).
- Reject an incomplete Codex rollout tail instead of trusting the preceding
  model context: `_codex_rollout_window` fails closed on a non-newline-
  terminated final record, so a concurrently written model-changing record can
  no longer yield stale governance-ready identity.
