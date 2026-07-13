### agent-collab 3.2.0 — zero-idle provider broker

- Route managed Gemini, OpenCode, Grok, and Composer requests through an explicit, digest-bound
  launchd socket broker that starts for one request and returns to zero idle
  processes. Add closed install, status, rollback, and uninstall lifecycle
  commands with transactional prior-version restoration and no direct fallback.
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
