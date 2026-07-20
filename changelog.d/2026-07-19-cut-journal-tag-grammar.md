- Added the durable cut journal and the signed release-tag grammar + release-commit
  topology contract that a future activation release cut will build on. The journal
  write-ahead-records every remote side effect so an interrupted cut is resumable and
  never silently repeats one; the tag contract pins an exact, fail-closed message
  grammar and asserts that a release-only commit changes nothing but the manifest's
  artifacts. Both are standalone and not yet wired to a release path (agent-collab
  4.1.0).
