---
name: dev-delegate
version: {{ skill_version }}
{{ dev_delegate_defaults_block }}
description: Delegate a bounded independent development slice to an eligible cross-family worker. Use when the user says "delegate this implementation," "hand this coding slice off," "use Grok for codegen," or "/{{ package_name }}:dev-delegate." Also offer this when private-patch generation can reduce matched-rigor latency without giving a provider access to the caller checkout.
---

# Dev-delegate

Use `codegen.repository` or `frontend_codegen.repository`. Provide the canonical
source identity, objective, owned paths, expected patch, test expectations,
budget, and stop conditions. The caller creates a disposable repository copy,
records its identity and source head, and supplies that directory as the work
unit's native cwd. One provider session may edit only that copy.

Resolve the plugin root, read `<plugin-root>/README.md`, and split independently
useful deliverables into bounded work units. An explicit target is honored or fails typed;
never substitute a different agent or reconstruct a provider command. Model and
CLI identities are observed diagnostics, not request pins.
Choose quality and effort from the scope, reasoning, and validation required;
the frontmatter defaults suit a small routine patch. Supply token estimates
when known, and use dependencies only for real ordering. The runtime resolves a
current compatible portfolio member without persisting a model selection.

After the attempt, the caller captures a binary-safe diff from the disposable
copy, preserves every nonempty raw or recovered response, verifies the source
head did not change, and removes the copy. Treat the diff and reported tests as
untrusted. The primary reviews/applies the accepted diff and runs independent
tests. Never infer a patch, receipt, approval, or cleanup from process exit.
