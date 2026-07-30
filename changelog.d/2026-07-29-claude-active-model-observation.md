### Fixed

- Observe the active model on a Claude Code host from the live session's own transcript. Claude Code does not export the model to the environment, so `active_model` resolved to `unknown`, no Claude session was ever `governance_ready`, and every governance route failed closed with `unknown_family` — the only host family with that gap. Callers worked around it by hand-authoring `primary`, which invited an invented `session_identifier` that conflicted with the strongly observed one and turned every route into a configuration error.

### Changed

- Document that `primary` should be sent as `{}` and that a `session_identifier` must never be fabricated by a caller, in both the coordinator request schema and the `intent-check` skill. Complete explicit configuration remains supported for a host that genuinely cannot be observed; what is prohibited is inventing a signal the caller does not have.

### Security

- The transcript observation is bounded and fails closed: strict lowercase-UUID session keys before any path join, owner/symlink/hardlink/permission checks reused unchanged from the Codex rollout path, post-open `fstat` re-validation against the pre-open identity, a bounded tail read, and strict JSON decoding. A model that is not anthropic-shaped is rejected rather than allowed to reassign `primary_family`, so a forged record cannot defeat reviewer family-exclusion. Model validation is by shape, not by a pinned model list, so future models resolve without a code change.

- Identity on a Claude host is now observation-only: every identity field is recorded non-empty, so none of them can be supplied through `AGENT_COLLAB_*` or an explicit `primary`. A supplied value that disagrees with observation registers as a conflict rather than an override. Previously an unobserved field was left empty, and the overlay fills an empty field — so configuration alone could make a wholly unobserved session governance-ready, including by pairing a filled model with a filled session identifier. A nonempty session identifier that fails the UUID contract also now fails closed rather than reading as merely absent.

- Same-uid integrity is explicitly out of scope. The transcript is a weaker signal than the `CLAUDE_CODE_SESSION_ID` it is keyed by: that value is inherited at process start and a sibling same-uid process cannot rewrite it, whereas the transcript can be modified mid-flight. The identity re-checks detect append races and replacement, not a same-size in-place rewrite or an append-then-truncate.
