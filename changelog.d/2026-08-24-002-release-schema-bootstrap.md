### agent-collab 6.2.2 — 2026-08-24

#### Fixed

- Provision an exact pinned `uv` toolchain on the GitHub-hosted release runner
  before the mandatory Draft 2020-12 runtime manifest-schema gate. Clean-runner
  publication and release execution by any agent now use the same
  repository-owned validation path.
- Recover publication after `v6.2.1` stopped before archive creation. The
  immutable failed tag remains unchanged and has no GitHub Release.
- Correct the public lifecycle guide's readiness example so it supplies the
  coordinator's exact closed quality and effort fields instead of returning a
  preventable `readiness_not_closed` rejection.

Addressed: #150
