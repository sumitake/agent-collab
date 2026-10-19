---
name: dev-delegate
version: {{ skill_version }}
{{ dev_delegate_defaults_block }}
description: Delegate a bounded independent development slice to an eligible worker. Use when the user says "delegate this implementation," "hand this coding slice off," "use Grok for codegen," or "/{{ package_name }}:dev-delegate." Also offer this when private-patch generation can reduce matched-rigor latency without giving a provider access to the caller checkout.
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

Set a supported top-level `deadline_ms` for bounded work; omission uses the
24-hour default. Production codegen uses an admitted-progress inactivity lease,
so valid progress can renew it. A prose duration is an expectation, not a hard
runtime limit. Choose primary-owned validation by default, or provide the exact
preverified interpreter and focused command for a worker check. Do not ask the
worker to change global aliases; provide a verified process-local `PATH` when
the check launches a child interpreter by a generic name. Do not ask the
worker to search for environments or install dependencies; a missing optional
dependency must be reported without blocking a coherent partial patch.

Record observed worker lineage and its source when available; otherwise label
it lineage-unverified. Same-family and unverified worker output remains advisory;
role or route selection does not prove cross-family coverage. This does not
prevent ordinary development work or replace required independent review.

After the attempt, the caller captures a binary-safe diff from the disposable
copy, preserves every nonempty raw or recovered response, verifies the source
head did not change, and removes the copy. Treat the diff and reported tests as
untrusted. The primary reviews/applies the accepted diff and independently
validates it. If the caller stops an attempt, one caller owns cancellation and
verifies the runtime's cleanup; preserve partial content and identify caller
cancellation accurately. Never infer a patch, receipt, approval, cleanup, or
provider outage from process exit. Never replay the consumed work unit.
