### Changed

- Replace the Dependabot auto-merge review gate with a deterministic, free,
  no-AI design (GitHub Models, the intended free reviewer, was retired
  2026-07-30). `dependabot-gate.yml` now hard-fails unless every commit is
  authentically Dependabot's, every changed path is within
  `.github/workflows|actions` with no control-plane file touched, and every
  dependency update is patch or minor via SHA-pinned
  `dependabot/fetch-metadata` (majors held). The Codex summon/retrigger/signal
  machinery is removed; `dependabot-automerge.yml` is arm-only. CI/governance
  only, no distributed content, no version bump.
