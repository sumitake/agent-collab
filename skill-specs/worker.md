---
name: worker
version: {{ skill_version }}
description: Use when the operator says "delegate this implementation," "generate a private patch," "use Grok for codegen," or "use Moonshot for frontend work." Also offer this when a bounded non-governance task needs output-only code generation without access to the caller checkout.
---

# Delegate bounded worker output

Use `codegen.repository` for ordinary code generation or
`frontend_codegen.repository` for frontend-affinity work. These are private-
repository patch actions, not read-only planning or governance.

Provide the canonical `repo_root`, bounded prompt, target agent only when
explicitly requested, and observed author lineage when independence matters.
Never send a model name, provider CLI version, provider transport action, tool
list, or raw command.

The provider may inspect, edit, and test only the disposable copy. It returns a
binary-safe provider-only patch plus bounded summary and test claims. It never
applies the patch or mutates caller Git metadata. The primary reviews and
applies accepted changes, runs independent tests, and owns commits, PRs,
merges, and deployment.
