### agent-collab 7.0.0 — 2026-08-27

#### Changed

- Require every repository request to bind its canonical absolute root to the
  exact expected 40- or 64-hex repository head before provider execution.
- Classify terminal runtime failures from typed failure traces. Recovery is
  replay-safe, source-specific, and aware of the public timeout cap; provider
  attempts with started or unknown inference require inspection and a
  separately authorized new request rather than replay.
- Treat `provider_cli_incompatible` as an inspection outcome repaired through
  the official Agy update path, never by increasing the same request's timeout.
- Reject real TTY input before loading the runtime. Supported coordinator
  requests use one EOF-framed JSON object from a pipe or regular file.
- Keep long-running code generation alive while the supervised provider shows
  admitted progress, while retaining bounded total setup and inactive-stall
  limits.
- Ship signed provider runtime `5.0.0` for Darwin arm64 and x86_64. Wire schema
  advances 7 to 8 and the descriptor digest advances from `774067d0…` to
  `9ec0c1d0…`; the 12-action surface is unchanged. Gemini remains eligible and
  subscription-preferred through compatible Agy, Grok gains request-private
  provider state, and no new provider or model route is introduced.

#### Removed

- Remove the automatic host-local failure-evidence module, hooks, tests, and
  archive member. Explicit issue reporting remains a separately authorized
  operation after the typed response is available.
