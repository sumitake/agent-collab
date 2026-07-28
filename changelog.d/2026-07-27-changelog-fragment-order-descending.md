### Fixed

- `build-changelog.py` now sorts `changelog.d/` fragments in **reverse**
  lexical order (newest filename first) instead of ascending order. The
  compiled `[Unreleased]` block previously placed the oldest fragment at the
  top and the newest at the bottom — backwards from the Keep a Changelog
  convention this file's own header cites (most recent change on top).
  `CHANGELOG.md` is regenerated from the corrected sort; only the ordering
  changed, no entries were added, removed, or reworded.
