### Fixed

- Observe the active model on a Claude Code host from the live session's own transcript. Claude Code does not export the model to the environment, so `active_model` resolved to `unknown`, no Claude session was ever `governance_ready`, and every governance route failed closed with `unknown_family` — the only host family with that gap. Callers worked around it by hand-authoring `primary`, which invited an invented `session_identifier` that conflicted with the strongly observed one and turned every route into a configuration error.

### Changed

- Document that `primary` should be sent as `{}` and that `session_identifier` must never be supplied by a caller, in both the coordinator request schema and the `intent-check` skill.

### Security

- The transcript observation is bounded and fails closed: strict lowercase-UUID session keys before any path join, owner/symlink/hardlink/permission checks reused unchanged from the Codex rollout path, post-open `fstat` re-validation against the pre-open identity, a bounded tail read, and strict JSON decoding. A model that is not anthropic-shaped is rejected rather than allowed to reassign `primary_family`, so a forged record cannot defeat reviewer family-exclusion. The observation is same-uid best-effort anti-confusion, not a forgery-resistant attestation, and is the same trust class as the `CLAUDE_CODE_SESSION_ID` it is keyed by. Model validation is by shape, not by a pinned model list, so future models resolve without a code change.
