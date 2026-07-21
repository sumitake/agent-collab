### agent-collab 3.5.1 — fail-closed dispatcher boundary

- Treat malformed or noncanonical dispatcher-client output after the
  request-bearing child launches as a post-request failure, preventing a
  possible second execution through blue after green acceptance.
- Preserve typed unsupported-platform behavior when POSIX `fcntl` is absent,
  while failing lifecycle locking closed before filesystem I/O.
