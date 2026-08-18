- docs: add a public-disclosure boundary for changelog fragments
  (`changelog.d/README.md`): fragments record user-visible effect and contract
  changes at coarse resolution; private-runtime implementation strategy, host
  fleets, and internal route detail stay out of public release prose. The
  release-closeout layering rule (`docs/architecture/repository-and-release.md`)
  and the status-snapshot update rules (`docs/architecture/status-and-evidence.md`)
  now reference the same boundary for release notes and future evidence
  snapshots (existing snapshots remain as recorded history).
