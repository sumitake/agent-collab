### agent-collab 4.0.2 — protocol-v1 blue lifecycle bridge

- Keep normal protocol-v2 routing fail-closed against protocol-v1 runtimes and
  responses while allowing dispatcher lifecycle control to prove the exact
  signed v1 blue baseline needed for make-before-break staging.
- Stage and verify protocol-v2 green without rewriting or stopping v1 blue, and
  derive the selected blue protocol from its immutable manifest during mutable
  control-plane recovery.
