### Changed

- Document that public-export history mode covers refs reachable in the *local* clone, so a clone retaining pre-rewrite refs fails the gate even when the canonical remote is clean. `AGENTS.md`, `docs/public-governance.md`, `docs/migration-from-legacy-packages.md`, and the pull-request template now require comparing against a disposable full clone of the canonical remote, recording the snapshot checked, and treating that comparison as evidence only about the recorded snapshot — never as clearance of the failing clone, the publication candidate, unfetched refs, or prior exposure. Uncertain provenance, a failing publication candidate, a failing canonical fetched ref, or credential material still requires stopping publication under `SECURITY.md`.

### Added

- Emit an advisory triage note when public-export history mode fails, the active tree is clean, and the clone holds commits no remote-tracking ref reaches. The note is purely additive: it never suppresses a violation, never changes the exit code, keeps `RESULT:` as the final line, makes no network call, reports no ref names or counts, and is silent whenever the active tree is contaminated so present-state findings are never accompanied by a reassuring signal.
