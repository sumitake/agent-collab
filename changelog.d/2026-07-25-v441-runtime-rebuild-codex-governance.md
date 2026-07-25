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

- **Release verifiers accept an enumerated optional route.**
  `verify_runtime_release.py` and `build_plugin_archive.py` previously required
  the advertised contract set to equal an exact ten-route set, which rejected
  any runtime advertising the new route. They now apply a bounded containment
  check — `REQUIRED <= advertised <= REQUIRED | OPTIONAL` — mirroring the
  public client's existing REQUIRED/OPTIONAL partition, with `OPTIONAL` holding
  exactly `codex/governance`. This is deliberately not an open superset: an
  advertised route outside the enumerated union is still rejected, the ten-route
  baseline is still mandatory, and the route stays optional so a runtime that
  omits it continues to verify.

### Tests

- Pin that the verifier containment check is bounded: an unenumerated extra
  route is rejected, a missing required route is rejected, and OPTIONAL is
  exactly `codex/governance` in both verifiers.
- Update the route-shipping test to the new reality (route now advertised) while
  still asserting it remains accepted-but-not-required.
