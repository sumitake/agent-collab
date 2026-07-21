### agent-collab 3.3.0 — managed Gemini governance and reliable provider state

- Add a distinct broker-only `gemini/governance` action with exact Gemini 3.1
  Pro/high selection, immutable artifact binding, shared-HOME/PTY containment
  evidence, response hashing, and public-client proof-digest validation.
- Keep Gemini advisory and long-context separate and explicitly ineligible as
  governance evidence; automatic governance now maps Gemini and Grok to their
  explicit governance actions while Codex remains advisory.
- Advance the signed-runtime route contract to version 2 across policy,
  manifests, schemas, archive/release verification, generated skills, and
  deterministic tests.
- Document canonical passwd HOME as the managed-provider reliability policy
  without relaxing family exclusion, authority separation, bounded lifecycle,
  or the prohibition on raw provider fallbacks.
- Make Codex, Gemini, OpenCode, Grok, and Composer uniformly broker-only and
  bind provider startup to the signed guardian's acknowledged pre-exec gate;
  only local runtime management retains direct exact-artifact execution.
