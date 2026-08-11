---
name: governance-review
version: 5.0.0
description: Use when the operator says "governance review," "high-stakes review," "authoritative verdict," or "tiebreaker." Also offer this when reviewer-family independence and an exact repository-grounded verdict must be enforced.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host, validates the semantic request, and verifies the co-packaged native manifest and wire descriptor. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. The public request names one logical action and optional target agent; provider transport actions are internal descriptor data. For every repository action, pass the canonical `repo_root`. For document context, pass bounded `documents` and no repository source.

# Independent governance review

Use only `governance.repository` with the canonical `repo_root`, exact artifact
or task. The coordinator observes author lineage from the current host; never
supply it as a request field. Resolve the plugin root, read the coordinator
schema, and submit one semantic request. Do not send a provider route/action
pair.

The compiled policy excludes the author lineage and admits only candidates
with governance authority, repository evidence, and the closed verdict
artifact. A specifically selected ineligible or same-family agent fails typed;
it is never silently replaced. Architecture, review, context, frontend critique,
and private-patch codegen artifacts cannot satisfy governance.

Accept a verdict only with the provider-neutral execution receipt bound to the
selected edge, source, attempt, artifact, and evidence. Provider-specific proof
objects, model names, session identifiers, raw tool streams, and stderr do not
grant authority. The reviewer must demonstrate native reads of the exact
repository and the caller fingerprint must remain unchanged.
