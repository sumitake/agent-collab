### Changed

- Make release tags immutable and fail closed: the release helper no longer offers stale-runtime or tag-deletion escape hatches, and an existing tag is never treated as proof that a release succeeded.
- Bind release success to the signed annotated tag's exact commit, the completed successful `release.yml` push run, the non-draft GitHub release, and byte-for-byte archive, checksum, and SPDX assets generated from that commit.
