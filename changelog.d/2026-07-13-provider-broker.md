### agent-collab 3.2.0 — zero-idle provider broker

- Route managed Gemini and OpenCode requests through an explicit, digest-bound
  launchd socket broker that starts for one request and returns to zero idle
  processes. Add closed install, status, rollback, and uninstall lifecycle
  commands with transactional prior-version restoration and no direct fallback.
- Resolve the OpenCode model per request from live OpenCode/ZCode observation,
  explicit central configuration, or the fixed `opencode/glm-5.2` preset while
  ignoring ambient and row-level model fallbacks.
