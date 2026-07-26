### Fixed

- Restore the unreleased v4.5.0 source line to the canonical policy-only
  package shape by removing the retained v4.4.2 production runtime bundle and
  publishing an empty, schema-v3 runtime manifest.
- Keep the OpenCode Go policy and skill changes in v4.5.0 while making the
  source tree eligible for the governed private build/sign/notarize pipeline.

### Why

- A populated runtime is admissible to the private builder only when the
  requested source is the exact commit behind a trusted signed release tag.
  Carrying the older runtime into an untagged v4.5.0 commit made the source
  neither a valid policy-only input nor a valid signed activation input.
