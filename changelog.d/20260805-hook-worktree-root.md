### Fixed

- The `.githooks/pre-commit` and `.githooks/pre-push` wrappers now resolve the
  repository root from the INVOKING worktree (`git rev-parse --show-toplevel`,
  failing closed when it cannot be resolved) instead of from the hook
  file's own location. `core.hooksPath` is an absolute path into the primary
  checkout, so the old hook-file-relative resolution validated and tested the
  primary checkout's tree — stale or dirty with another session's edits —
  whenever a commit or push ran from a linked session worktree (observed
  2026-08-05 as a false `NOTICE ... drifted` pre-commit FAIL; the same shape
  could produce false PASSes). Wrapper tests cover the hook-lives-elsewhere
  scenario for both hooks, a fail-closed block when the root cannot be
  resolved (per Codex cross-family review — no cwd fallback), and a real-git
  linked-worktree integration test reproducing the production topology.
  Repository tooling only — no distributed content, no version bump. Note:
  the fix takes effect once the primary checkout (whose working tree hosts
  the active hooksPath copies) is updated to a commit containing it.
