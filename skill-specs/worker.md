---
name: worker
version: {{ skill_version }}
description: Use when the operator says "delegate this implementation," "generate a private patch," "use Grok for codegen," or "use Moonshot for frontend work." Also offer this when a bounded non-governance task needs output-only code generation without access to the caller checkout.
---

# Delegate bounded worker output

Use `codegen.repository` for ordinary code generation or
`frontend_codegen.repository` for frontend-affinity work. These are private-
repository patch actions, not read-only planning or governance.

Provide the canonical `repo_root`, exact `expected_repo_head`, bounded prompt, target agent only when
explicitly requested. The coordinator observes author lineage from the current
host; never supply it as a request field. Never send a model name, provider CLI
version, provider transport action, tool list, or raw command.
Send closed `quality_profile` and `effort_class` fields; use `standard` for
both unless the task justifies an economical or frontier profile.

The provider may inspect, edit, and test only the disposable copy. It returns a
binary-safe provider-only patch plus bounded summary and test claims. It never
applies the patch or mutates caller Git metadata. The primary reviews and
applies accepted changes, runs independent tests, and owns commits, PRs,
merges, and deployment.
