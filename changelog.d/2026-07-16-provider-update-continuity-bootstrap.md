### agent-collab 3.5.0 — provider update continuity

- Add a strict, legacy-default blue/green broker selector so a newly installed
  client can continue using the separately verified legacy broker while a
  content-derived dispatcher lane is staged.
- Preserve blue on missing, invalid, unproven, refused, or timed-out green
  connections before any send attempt; never retry another lane after a
  connection succeeds. Each request captures one lane ordering so an in-flight
  blue request completes even if the next request atomically selects green.
- Add closed stage, status, no-provider ping, canonical-lock probe, selector
  commit, candidate abort, committed-control recovery, and retiring-blue drain
  operations. Green uses a distinct content-derived label/socket; commitment
  never bootouts blue, and recovery never changes desired provider binaries.
- Keep one canonical Gemini/Grok/OpenCode lock across blue and green for the
  complete request through provider teardown. Credential-free contention and
  acquisition probes let every installed client prove that namespace before
  green traffic is enabled.
- Permit a bounded two-selector overlap when both entries are the unified
  `agent-collab` package, allowing Codex to retain its old cache while a distinct
  candidate selector is proven. Retired package names remain blocking, and old
  client retirement stays behind the private fresh-session finalization gate.
- Block every packaged mutating broker/dispatcher lifecycle operation from the
  Codex seatbelt before lifecycle reads or writes while retaining read-only
  status and probes.
