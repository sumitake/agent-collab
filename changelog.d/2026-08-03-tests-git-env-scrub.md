### Changed

- `tests/__init__.py` scrubs inherited per-repo git environment pointers
  (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_PREFIX`,
  `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`,
  `GIT_COMMON_DIR`) at package import, so any runner — not only the sanitized
  pre-push hook — is safe from the incident where a hook-inherited absolute
  `GIT_DIR` made temp-directory git calls inside the suite mutate the real
  repository config. `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` are deliberately
  untouched (temp-repo commits rely on machine identity); the `scripts/` root
  is deliberately untouched (namespace package, and empirically unexposed —
  327/327 under a poisoned `GIT_DIR` with zero config writes). Regression
  tests pin both the in-process absence and a freshly-poisoned child-import
  scrub. Test infrastructure only — no version bump.
