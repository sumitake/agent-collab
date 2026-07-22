### agent-collab 4.2.1 — 2026-07-21

#### Fixed

- Align the closed coordinator schema with the collaboration-skill contract for
  read-only OpenCode planning and review. `opencode/plan` now accepts the exact
  optional artifact snapshot (`content` plus `author_model`) so the client can
  preserve artifact bytes, provenance, and family-exclusion evidence instead of
  rejecting a correctly constructed request before managed execution.

#### Verification

- Added a coordinator regression for an artifact-bound `opencode/plan` request;
  the test fails on 4.2.0 with `request fields violate the closed coordinator
  schema` and passes with the corrected review-contract set.
