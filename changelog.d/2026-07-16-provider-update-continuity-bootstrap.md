### agent-collab 3.4.0 — provider update continuity bootstrap

- Add a strict, legacy-default blue/green broker selector so a newly installed
  client can continue using the separately verified legacy broker while a
  content-derived dispatcher lane is staged.
- Preserve blue on missing, invalid, unproven, refused, or timed-out green
  connections before any send attempt; never retry another lane after a
  connection succeeds. Mechanically refuse green promotion until a later
  authenticated no-side-effect acceptance handshake exists.
- Block packaged broker install, rollback, and uninstall from the Codex
  seatbelt before lifecycle reads or writes while retaining read-only status.
