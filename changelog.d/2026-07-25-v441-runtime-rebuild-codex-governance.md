<!-- release: agent-collab 4.4.1 -->
### Changed

- **Rebuilt, re-signed, and re-notarized the darwin-arm64 provider runtime**
  from the current workspace source closure. The bundle shipped in the
  rolled-back v4.4.0 tag-only cut predated several runtime-behavior changes,
  including the public-client digest pin; a runtime built before that pin
  rejects the client this package actually ships.

- **The signed runtime now advertises the `codex/governance` route.** This is a
  capability expansion: v4.3.3 added the route to the public client's parser
  allowlist and JSON schema while the shipped runtime deliberately did not
  claim it, and the v4.4.1 runtime is built from a source closure where it is a
  real read-only contract.

- **`codex/governance` is now REQUIRED at the release gates.** All three
  independent copies of the contract allowlist —
  `verify_runtime_release.py`, `build_plugin_archive.py`, and
  `check-public-export-safety.py` — move from a ten-route to an
  eleven-route required set, keeping exact-set equality. Release gates
  validate what this repository is about to publish, so requiring the route
  stops a future cut from silently dropping a governance capability. The
  public client deliberately keeps it OPTIONAL, because it validates whatever
  is already installed, including older field artifacts that predate the
  route. The two postures are intentionally opposite.

### Tests

- Enforce the contract set at the real `verify_release` call site in both
  directions: omitting `codex/governance` is rejected, and an unenumerated
  extra route is rejected. Pin that all three gate copies agree exactly, and
  that the client keeps the opposite (optional) posture.
- Derive the contract fixtures in `test_plugin_archive.py` and
  `test_release_evidence.py` from the builder's own allowlist instead of
  restating ten routes inline. Both hardcoded copies had silently rotted the
  moment the required set changed; deriving them makes that impossible.
- Update the route-shipping test to the new reality (route now advertised) while
  still asserting it remains accepted-but-not-required.
