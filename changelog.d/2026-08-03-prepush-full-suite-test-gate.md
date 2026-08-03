### Changed

- The tracked `.githooks/pre-push` wrapper now runs BOTH unittest roots
  (`tests/` and `scripts/`, mirroring CI's exact discovery invocations) as a
  fail-fast gate before the existing compliance-trace check. Fail-closed
  opt-out for the test gate only via exactly `AGENT_COLLAB_PREPUSH_TESTS=0`
  (loud skip warning; compliance check always runs, now `exec`'d so the
  hook's stdin ref data reaches it); an affirmatively detected `main` branch
  skips the test gate while detached HEAD or detection failure runs it.
  Wrapper-level tests added (`scripts/test_hook_pre_push_wrapper.py`, 8
  cases, including sanitization of git's exported hook environment —
  GIT_DIR et al. — from the suite subshells, which otherwise poisons
  tests that spawn git in temp directories). Repository tooling only — no distributed content, no version bump.
  Motivation: ledger `partial.suite.run.hides.ci.failure` (recurred on #83).
