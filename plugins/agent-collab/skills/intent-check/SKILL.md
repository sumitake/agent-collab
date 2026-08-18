---
name: intent-check
version: 6.0.6
defaults:
  quality_profile: standard
  effort_class: standard

description: Verify that the active primary's interpretation matches the operator's request before consequential planning or execution. Use when the user says "intent check," "confirm what I asked," "check for scope drift," or "/agent-collab:intent-check." Also offer this proactively when a major request has multiple constraints whose omission would materially change the result.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON request on stdin. Before constructing it, read the **Coordinator request schema** in `<plugin-root>/README.md`; never invent fields or route/action pairs. The public coordinator re-observes the active host, validates the semantic request, and verifies the co-packaged native manifest and wire descriptor. It runs standalone from the installed plugin. Never discover a provider executable or reconstruct a raw command. `provider_error` and `teardown_error` are attempt-local diagnostics: they invalidate only that request's artifact and evidence. They must not quarantine a route, exclude it from later selection, or establish route or provider unavailability. The caller must not automatically replay the failed request; a later caller-authorized request is a new attempt whose eligibility is recomputed from fresh readiness. The public request names one logical action and optional target agent; provider transport actions are internal descriptor data. For every repository action, pass the canonical `repo_root`. For document context, pass bounded `documents` and no repository source.

# Intent check - independent interpretation comparison

Freeze two artifacts: the operator's original request and the active primary's
plain-language interpretation. Do not include an implementation plan; this
step checks understanding, not design quality.

Resolve the **plugin root** from this loaded file and invoke only
`python3 "<plugin-root>/coordinator.py"` with this descriptor-owned, untargeted
request. The runtime selects an eligible independent route; the caller does not
construct an agent/action pair.

```json coordinator-request
{"request_id":"intent-check-1","logical_action":"context.documents.intent","quality_profile":"standard","effort_class":"standard","target_agent":null,"timeout_ms":120000,"prompt":"Compare the operator request with the primary interpretation. Identify only material omissions, added scope, or ambiguity; do not design or execute the work.","documents":[{"label":"operator_request","content":"<verbatim operator request>"},{"label":"primary_interpretation","content":"<plain-language interpretation>"}]}
```

## Workflow

1. Quote the original request exactly, preserving negations and scope limits.
2. Write the interpretation as objective, in-scope work, out-of-scope work,
   constraints, success criteria, and stop conditions.
3. Replace only the two document contents with the frozen artifacts. Preserve
   every other request field exactly and do not add identity or routing fields.
4. Ask the selected independent reviewer to return exactly:

```text
VERDICT: MATCH | DRIFT | AMBIGUOUS
MISSED CONSTRAINTS:
- ...
ADDED SCOPE:
- ...
AMBIGUITIES:
- ...
RECOMMENDED INTERPRETATION:
<concise restatement>
```

5. If `MATCH`, proceed. If `DRIFT`, revise the interpretation and recheck once.
   If `AMBIGUOUS`, ask the operator only the load-bearing question. Preserve the
   typed route result and immutable provenance.

Never reconstruct a raw provider command, choose a target, invoke Claude
synchronously, or turn a route-local typed failure into a claim that global
governance is unavailable.
