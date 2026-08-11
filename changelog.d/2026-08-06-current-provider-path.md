### Fixed

- Preserve the caller's current `PATH` at the signed direct-runtime launch
  boundary so current unpinned Codex, Gemini, Grok, and OpenCode CLIs remain
  discoverable; use the fixed system path only when the caller supplies none.
