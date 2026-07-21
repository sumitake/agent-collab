- The signed runtime bundle can now be distributed by committing it to the public
  git repository, so the documented marketplace install delivers a working
  activation build. Member-mode verification for the git-installed **plugin tree**
  uses a shared safe-envelope predicate (owner read+execute, no group/other write,
  no special bits) instead of an exact `0o500` match, because a git checkout cannot
  preserve `0o500` and yields `0o755`/`0o700`. Tamper resistance is unchanged: the
  digest, Developer-ID signature, and Mach-O checks are untouched, and the same
  envelope the bundle root already used (operator-approved) now covers members. The
  privately-extracted **broker store** keeps the exact `0o500` check (agent-collab
  4.1.0).
