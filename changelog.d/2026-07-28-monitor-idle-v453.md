### agent-collab 4.5.3 — 2026-07-28

#### Changed

- The Codex inbox-monitor adapter no longer creates or retains a goal for
  liveness. Its canonical leased local process continues at the existing
  10-second interval, but liveness checks occur only on real activation, event,
  status, stop, or failure turns, so the new goal-free lifecycle causes zero
  idle model turns.
- Codex reports `degraded_no_event_wake` when the local process is live without
  a proven host-native model wake. Legacy cleanup ends only a goal whose
  structured creation transcript proves the old monitor lifecycle and after
  the host proves the exact retained exec is currently live and survives
  independently; otherwise it returns `legacy_goal_detach_unavailable` and
  leaves both lifecycles untouched.
- When legacy detach proof is unavailable, the host may continue pre-4.5.3 goal
  continuations until that goal is explicitly stopped. Every such empty turn is
  constrained to no exec/state poll or lifecycle mutation, and explicit stop
  reports `stop_incomplete_legacy_goal` rather than claiming success when the
  old goal cannot be safely bound and ended.
- Claude and Antigravity monitor lifecycles are unchanged.
