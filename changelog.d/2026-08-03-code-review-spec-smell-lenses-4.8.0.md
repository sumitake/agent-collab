### Changed

- Stamp agent-collab 4.8.0: **`code-review` gains spec-fidelity and
  smell-baseline lenses** (deferred follow-up from the 4.7.0 pack). The JSONL
  output contract is extended backward-compatibly — new `Spec` and `Smell`
  severities plus an optional `spec_ref` field; consumers filtering the four
  defect severities are unaffected, and the skill version is the contract
  version. The primary materializes the originating spec before the call
  under explicit precedence (user-passed → issue refs in the reviewed commit
  range only → repo spec files) with ambiguity ("`spec unavailable:
  ambiguous`", ask the user, never pick arbitrarily), no-synthesis and
  no-branch-name-inference rules, a line-numbered snapshot for citations, and
  an explicit untrusted-data instruction to the reviewer. The Fowler smell
  baseline is subordinate and evidence-bound: repo-documented standards
  override it, findings ride `Smell` severity and never escalate to
  Critical/High without an independently demonstrated consequence, and
  tooling-enforced rules are skipped based on materialized config. Spec and
  smell findings stay out of defect merge-blocking aggregation through
  synthesis. Adapted-portion attribution: mattpocock/skills `code-review`
  @`2ab95809` (blob `2a0b5240`); the spec carries the full MIT notice, the
  member's SPDX expression is `LicenseRef-PolyForm-Strict-1.0.0 AND MIT`,
  and `NOTICE` now references the provenance document generically.
