---
name: worker
version: {{ skill_version }}
description: Use when the operator says "delegate this implementation," "generate a private patch," "use Grok for codegen," or "use Moonshot for frontend work." Also offer this when a bounded non-governance task needs output-only code generation without access to the caller checkout.
---

# Delegate bounded worker output

Use `codegen.repository` for ordinary code generation or
`frontend_codegen.repository` for frontend-affinity work. These are disposable-
repository editing actions, not read-only planning or governance.

The caller creates a disposable repository copy, records its source head and
filesystem identity, and supplies that directory as the work unit's native cwd.
Provide a bounded prompt and an explicit target only when requested. Never send
a model name, provider CLI version, provider transport action, tool list, or raw
command.
Send closed `quality_profile` and `effort_class` fields; use `standard` for
both unless the task justifies an economical or frontier profile.

The provider may inspect, edit, and test only the disposable copy. The caller
preserves every nonempty raw or recovered response, captures the binary-safe
diff, verifies the recorded source head, and removes the copy. Provider
formatting and optional diagnostics do not gate content recovery. The primary
reviews and applies accepted changes, runs independent tests, and owns commits,
PRs, merges, and deployment. Never infer a patch or cleanup from process exit.
