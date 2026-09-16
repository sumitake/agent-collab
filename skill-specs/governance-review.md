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

Independence follows Public repository governance. Exclude the primary and
every contributing author family. Selecting a candidate and accepting
independent approval are different stages. Provider-free planning reports
route eligibility, not model identity. Currently known configuration may
identify a candidate; bind that reviewer with `explicit_target` through
planning and live dispatch. Independent approval requires response-scoped
native evidence correlated to the returned response.

Before dispatch, record observed lineage and source for the active primary and
every contributing artifact author, then select a reviewer whose currently
known lineage differs from all of them. Honor an operator-named provider; a
specifically selected ineligible or same-family agent is not silently replaced.
If no known-distinct eligible reviewer can be established, do not claim
independent governance; explain the missing capability or evidence. Missing
evidence is not a provider outage. An authorized advisory review may still
proceed.

After the response, record observed reviewer lineage and source. Configuration,
a route, provider name, status, receipt, or self-assertion alone does not prove
lineage. Preserve unknown lineage as unknown. If independence, exact source
identity, or scope cannot be established, keep useful advisory content and do
not claim authoritative approval. Do not replay a consumed review to repair
incomplete lineage evidence.

Preserve every nonempty raw or recovered response. Use ordinary model reasoning
over its full content to deduce the best-supported operative verdict; do not
require JSON, verdict keys, findings shape, terminal wrappers, telemetry, or a
receipt, and never synthesize approval from process exit. Retain available
receipts and diagnostics for audit, including any integrity concerns, but do
not discard provider content when they are absent or malformed.
See this skill's Unified runtime invocation and Public repository governance
for the one bounded caller fresh-review allowance. It is a new work unit after
a completed or terminated attempt with no substantive result, not a replay of
the consumed work unit.
