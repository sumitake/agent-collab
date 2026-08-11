### agent-collab 5.0.0 — 2026-08-11

#### Changed

- Activated the v5 direct runtime with one manifest-bound, signed, notarized
  Darwin arm64 standalone bundle.
- Replaced the policy-only runtime placeholder without publishing provider
  executor source or invocation recipes.

#### Verification

- Bound the activation package to runtime protocol 3, native contract 4, and
  the closed schema-4 public manifest before publication.
