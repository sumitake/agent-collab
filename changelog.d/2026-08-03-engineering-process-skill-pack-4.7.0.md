### Added

- Stamp agent-collab 4.7.0: **engineering-process skill pack (MIT-derived)**.
  Three self-executed skills join the package — `decision-map` (multi-session
  planning as a shared map of decision tickets on the issue tracker, with an
  explicit user-approval gate before any tracker write and a claim discipline
  for concurrent sessions), `prototype` (throwaway logic/UI prototypes that
  answer one design question, built on an isolated worktree/branch with a
  production-safe gate on UI variant mechanisms), and `architecture-review`
  (a self-executed sweep for module-deepening opportunities presented as a
  fully self-contained visual report, composing with — not replacing — the
  routed `architect` consultation). Derived from the MIT-licensed
  [mattpocock/skills](https://github.com/mattpocock/skills) repository at
  pinned commit `2ab958093e83e0ec752e6c1c5932da465bf23e0c` and adapted for
  this package (tracker resolution with feature detection and a local-markdown
  fallback, host-neutral sub-skill references, inlined companion references,
  no CDN assets, mutation gates). The derived portions remain MIT-licensed:
  each generated `SKILL.md` carries the full MIT permission notice, release
  SPDX evidence declares those three members `MIT`
  (`scripts/build_release_evidence.py`), and
  `docs/third-party-skill-provenance.md` records the per-file upstream blob
  SHAs and adaptations. `NOTICE` and both README license boundaries name the
  exception. No coordinator, provider, routing, or runtime surface is touched.
