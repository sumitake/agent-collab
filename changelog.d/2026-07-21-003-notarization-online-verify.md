### agent-collab 4.2.1 — 2026-07-21

#### Fixed

- Verify notarization online at both the release gate (`verify_runtime_release.py`)
  and consumer activation (`runtime_client.py`) by adding `--check-notarization` to
  the `codesign --test-requirement '=notarized'` check. A bare Mach-O cannot have a
  notarization ticket stapled, so without the online lookup the requirement is
  satisfied only by the notarizing host's local trust state and fail-closes on any
  clean host — the CI runner (which blocked the first activation release) and every
  fresh end-user install. Empirically fail-closed when the Apple notary is
  unreachable, and it rejects unsigned, ad-hoc, and Developer-ID-signed-unnotarized
  binaries on macOS 14 and 15.
