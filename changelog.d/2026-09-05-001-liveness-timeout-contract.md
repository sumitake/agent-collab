### agent-collab 7.0.3 — 2026-09-05

#### Changed

- All 12 logical provider actions use admitted progress inactivity in the
  source candidate, so active work can continue while it reports progress.
  Homogeneous total-deadline requests remain an explicit compatibility mode;
  mixed timeout-mode requests are rejected before launch.
