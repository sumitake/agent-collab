---
name: governance-review
version: {{ skill_version }}
description: Use when the operator says "governance review," "high-stakes review," "authoritative verdict," or "tiebreaker." Also offer this when reviewer-family independence and an exact repository-grounded verdict must be enforced.
---

# Independent governance review

Use only `governance.repository` with the canonical `repo_root`, exact
`expected_repo_head`, artifact, or task. The coordinator observes author lineage from the current host; never
supply it as a request field. Resolve the plugin root, read the coordinator
schema, and submit one semantic request. Do not send a provider route/action
pair.
Use `quality_profile="frontier"` and `effort_class="maximum"`. These are closed
provider-neutral request fields and never authorize a model or version pin.

The compiled policy excludes the author lineage and admits only candidates
with governance authority, repository evidence, and the closed verdict
artifact. A specifically selected ineligible or same-family agent fails typed;
it is never silently replaced. Architecture, review, context, frontend critique,
and private-patch codegen artifacts cannot satisfy governance.
An ungrounded advisory also cannot satisfy governance, even when its prose
contains an approving word.

Accept a verdict only with the provider-neutral execution receipt bound to the
selected edge, source, attempt, artifact, and evidence. Provider-specific proof
objects, model names, session identifiers, raw tool streams, and stderr do not
grant authority. The reviewer must demonstrate native reads of the exact
repository and the caller fingerprint must remain unchanged.
