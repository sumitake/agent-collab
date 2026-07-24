### agent-collab 4.3.2 — 2026-07-24

#### Fixed

- Enforce one end-to-end monotonic timeout across coordinator preflight,
  automatic reviewer candidates, runtime verification, and provider launch.
  Each fallback is resealed with only the remaining budget.
- Stop automatic fallback after a timed-out or teardown-unproven accepted
  request, preventing a second provider worker from overlapping uncertain
  cleanup.
- Keep selected-dispatcher callability distinct from lifecycle quiescence so
  migration doctor no longer reports a responsive lane unavailable merely
  because another bounded request is active. Bound the status-only quiescence
  observation to one second instead of waiting the full 30-second cold-start
  allowance; lifecycle operations retain their full idle proof.

#### Safety

- Notarization, signature, provenance, route authority, and selector checks are
  unchanged. Install, update, rollback, commit, drain, and other lifecycle
  operations still require a proven non-persistent process state.
