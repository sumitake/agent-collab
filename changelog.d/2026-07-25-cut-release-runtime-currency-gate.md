### Added

- **`cut_release.py` runtime-currency gate (fail-closed).** An activation
  release now refuses to cut when any `runtime:`-scoped merge landed after the
  commit that last staged `plugins/agent-collab/runtime/` — the failure mode
  that shipped a 4.2.0-era runtime in the rolled-back v4.4.0 tag-only cut.
  Explicit operator override: `--allow-stale-runtime` (loud warning). Unit
  tests cover pass/stale/missing/override/wiring paths.
