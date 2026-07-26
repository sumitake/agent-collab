### Fixed

- agent-collab 4.5.1 makes managed containment a rare structural signal rather
  than an output heuristic.
- Make managed containment provider-agnostic and structural: authenticated
  provider state resolves from the canonical user HOME, caller checkouts stay
  read-only by default, and each request receives a private temporary workspace
  for agentic tools, edits, builds, and reasoning.
- Seal `opencode/build` as output-only to the caller. OpenCode may work inside
  its private workspace, but the trusted primary reviews and applies returned
  material instead of granting the provider direct caller-worktree mutation.
- Reserve `containment_error` for failure to establish the boundary before
  launch or positive write-escape/protected-state evidence. A successfully
  blocked access attempt proves containment worked; return code, empty output,
  and stderr wording cannot manufacture a containment failure.
- Keep authentication, protocol/output, timeout, provider, teardown, and
  cleanup failures orthogonal. Disable in-request binary updates, require
  bounded descendant teardown and positively verified temporary cleanup, and
  treat routine direct-CLI fallback as a managed-path reliability defect.
