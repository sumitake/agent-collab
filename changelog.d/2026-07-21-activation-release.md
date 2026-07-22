### agent-collab 4.2.2 - first activation release

First public activation release: the plugin now ships the signed and notarized
native runtime committed in the repository, so the documented marketplace install
(`/plugin marketplace add`) delivers a working activation build under any operator
umask, including umask 002 whose group-writable checkout the previous exact-mode
and safe-envelope checks both rejected.

### Added

- Commit the Developer ID signed and notarized darwin-arm64 native runtime bundle
  (38 members) in the repository and advertise it through a schema-version-3
  activation manifest, pinning `EXPECTED_DEVELOPER_ID_TEAM` to the Osumi Consulting
  LLC team in `signing_policy.py`. The plugin remains source-available under the
  PolyForm Strict License 1.0.0; commercial licensing is administered by Osumi
  Consulting LLC.

### Changed

- Treat the git checkout as a trusted source under the trust-the-checkout model:
  the host already executes the plugin's Python control plane from the checkout, so
  the native runtime tolerates the operator umask permission bits on the source
  while keeping content integrity (per-member SHA-256, Developer ID signature,
  notarization, Mach-O checks) and the exact broker-store mode unchanged. The
  `AGENTS.md` runtime policy is updated to distinguish the strict private broker
  store from the tolerant git source.
- Package the committed in-tree runtime in `build_plugin_archive`, binding the whole
  archive to the release commit, alongside the external sealed handoff path.
