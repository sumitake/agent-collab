- Added a strict, fail-closed grammar for signed release-tag messages: exact field
  set in canonical order, no duplicates or unknown fields, no trailing material,
  lowercase-hex digests, ASCII-only, bare-basename asset names, and a
  `vMAJOR.MINOR.PATCH` tag validator used before a tag name reaches any ref or
  path. Not yet wired to a release path — it is the parsing substrate the
  activation cut will use (agent-collab 4.1.0).
