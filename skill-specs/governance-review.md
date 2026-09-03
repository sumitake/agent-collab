---
name: governance-review
version: {{ skill_version }}
description: Use when the operator says "governance review," "high-stakes review," "authoritative verdict," or "tiebreaker." Also offer this when reviewer-family independence and an exact repository-grounded verdict must be enforced.
---

# Independent governance review

Use only `governance.repository`. The caller creates one bounded work unit for
the immutable review scope and runs it from the canonical repository at the
exact expected source head. Do not send a provider route/action pair or
reconstruct a provider command.
Use `quality_profile="frontier"` and `effort_class="maximum"`. These are closed
provider-neutral request fields and never authorize a model or version pin.

The caller must positively establish that the selected reviewer is independent
from the author and that the response addresses the exact source head and
declared scope before treating it as governance evidence. A specifically
selected ineligible or same-family agent is not silently replaced.

Preserve every nonempty raw or recovered response. Use ordinary model reasoning
over its full content to deduce the best-supported operative verdict; do not
require JSON, verdict keys, findings shape, terminal wrappers, telemetry, or a
receipt, and never synthesize approval from process exit. Retain available
receipts and diagnostics for audit, including any integrity concerns, but do
not discard provider content when they are absent or malformed. If reviewer
independence, exact source identity, or scope cannot be positively established,
keep the response as advisory content and do not claim authoritative approval.
