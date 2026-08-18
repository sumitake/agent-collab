### Changed

- Dependabot PRs now auto-merge (all update types; operator decision
  2026-08-17), which changes the public contribution contract in
  `docs/public-governance.md`: `dependabot[bot]`-authored PRs carry no
  compliance trace, and a dedicated base-controlled required context
  `dependabot-gate.yml` (`pull_request_target` + `ref: main`,
  `scripts/dependabot_gate.py`) instead hard-fails unless every commit is
  authentically Dependabot's (author + web-flow committer + verified
  signature) and a clean Codex review response bound to the current head
  exists. `dependabot-automerge.yml` summons the Codex review and arms native
  auto-merge only once `dependabot-gate` is a required context (fail-closed);
  Codex silence or findings keep the PR on the manual review path. Repository
  CI/governance only — no distributed plugin content, no version bump.
