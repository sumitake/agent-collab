### agent-collab 3.3.0 — closed standalone provider bundle

- Route managed Gemini, OpenCode, Grok, and Composer requests through an explicit, digest-bound
  launchd socket broker that starts for one request and returns to zero idle
  processes. Add closed install, status, rollback, and uninstall lifecycle
  commands with transactional prior-version restoration and no direct fallback.
- Replace the failed onefile launch path with manifest schema 2, native contract
  3, and broker transport 2 over one closed standalone bundle. Bind its identity
  to the sorted role/mode/size/digest/Mach-O facts of every member; publish only
  exact immutable `0500` files; verify the kernel-reported entrypoint and the
  complete lifecycle state before provider dispatch. Provider protocol 1 and
  all existing route-authority boundaries remain unchanged.
- Resolve the OpenCode model per request from live OpenCode/ZCode observation,
  explicit central configuration, or the fixed `opencode/glm-5.2` preset while
  ignoring ambient and row-level model fallbacks.
- Reject duplicate/non-finite broker responses and state before typed parsing.
- Preserve typed `cancelled` and `input_limit` Grok/Composer failures, require
  exact terminal-state validation, and document the one bounded cancellation
  retry and comprehensive architecture-reviewed Composer coding-packet policy.
- Strip the Codex Desktop Seatbelt marker from broker-dispatched work so every
  Grok/Composer attempt validates its own nested read-only sandbox, preserve
  closed provider-child environments, and keep runtime management direct-only.
- Propagate client disconnect through managed OpenCode, Grok, and Composer
  calls, reap provider child groups, discard partial output, prohibit retry of
  disconnect cancellation, and fail with typed `timeout` before setup when the
  managed-boundary deadline reserve is exhausted.
- Harden repository configuration with full-SHA Action pin enforcement while
  retaining squash-only, signed, linear, review-thread-resolved releases.
- Align OpenCode preflight with issuance model resolution; key immutable broker
  versions by both artifact and manifest digests; preserve complete rollback
  state across failures and no-op reactivation; reject unverified rollback
  targets; treat a never-installed root as typed uninstalled/unavailable; and
  map bounded `launchctl` failures to closed lifecycle results.
