### agent-collab 4.5.3 — 2026-07-28

#### Changed

- The Codex inbox-monitor adapter no longer creates or retains a goal for
  liveness. Its canonical leased local process continues at the existing
  10-second interval, but liveness checks occur only on real activation, event,
  status, stop, or failure turns, so idle monitoring causes zero model turns.
- Codex reports `degraded_no_event_wake` when the local process is live without
  a proven host-native model wake, and a first-empty-continuation tripwire
  prevents a legacy goal from producing repeated no-event turns.
- Claude and Antigravity monitor lifecycles are unchanged.
