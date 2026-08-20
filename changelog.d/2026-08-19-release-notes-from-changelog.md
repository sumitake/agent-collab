### Changed

- GitHub Release notes are now generated from the release's own compiled
  `CHANGELOG.md` section (via `scripts/extract_changelog_section.py`,
  fail-closed: a missing or empty section blocks the release) instead of a
  generic one-line boilerplate that had gone stale (the v6.1.1 notes still
  said "Darwin-arm64" after the release went dual-architecture). Published
  release notes for existing tags were backfilled to the same standard as
  editable release metadata; tags and assets are untouched.
