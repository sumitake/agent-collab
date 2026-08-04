### Changed

- CI security-contract tests now assert action-pin *properties* instead of
  exact pin fixtures: the Gitleaks, CodeQL init/analyze, and upload-artifact
  assertions require a real `uses:` line pinned to a full 40-hex commit SHA
  with a version comment, but no longer freeze WHICH SHA or major version.
  The frozen fixtures broke every Dependabot actions-group PR by construction
  (#9, #29, #67) while adding no enforcement beyond the repo-wide
  full-SHA pin test and CODEOWNERS review of workflow diffs — Dependabot
  cannot update test fixtures that mirror the workflow it bumps. The
  replacement regexes are anchored to `uses:` lines (a comment or string
  mentioning an action no longer satisfies them — a strictness *increase*
  over the old substring assertions, per Codex cross-family review) and
  accept dotted version comments (`# v3.0.0`) as Dependabot writes them.
  Test infrastructure only — no version bump.
