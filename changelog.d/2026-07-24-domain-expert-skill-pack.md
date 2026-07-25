### Added

<!-- release: agent-collab 4.4.0 -->

- **Domain-expert skill pack (16 new skills).** New pure-prompt, host-neutral
  expertise skills alongside the existing collaboration/governance set:
  `rust-engineer`, `go-engineer`, `elixir-engineer`, `sql-engineer`,
  `kubernetes-specialist`, `terraform-engineer`, `sre-engineer`,
  `incident-responder`, `mlops-engineer`, `llm-architect`,
  `postgres-engineer`, `data-engineer`, `eval-engineer`,
  `prompt-regression-tester`, `hallucination-investigator`, and
  `ai-writing-auditor`. Authored under workspace ownership, informed by the
  MIT-licensed VoltAgent subagent corpora at pinned SHAs (947b44ca /
  5605c9c1) after an untrusted-input security audit; all supply-chain
  patterns flagged by that audit (third-party installers, external MCP
  endpoints, fictional tools) are excluded by construction. No coordinator,
  provider, or delegation surface is touched.
