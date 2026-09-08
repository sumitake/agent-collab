---
name: intent-check
version: {{ skill_version }}
{{ intent_check_defaults_block }}
description: Verify that the active primary's interpretation matches the operator's request before consequential planning or execution. Use when the user says "intent check," "confirm what I asked," "check for scope drift," or "/{{ package_name }}:intent-check." Also offer this proactively when a major request has multiple constraints whose omission would materially change the result.
---

# Intent check - independent interpretation comparison

Freeze two artifacts: the operator's original request and the active primary's
plain-language interpretation. Do not include an implementation plan; this
step checks understanding, not design quality.

Resolve the **plugin root** from this loaded file and invoke only
`python3 "<plugin-root>/coordinator.py"` with one normally untargeted
`context.documents.intent` work unit. Put the verbatim operator request and
plain-language primary interpretation in its bounded opaque payload. Use a
provider-free planning request to inspect known family evidence before dispatch;
set `explicit_target` only when the operator names a provider. The caller does
not construct an agent/action pair or invent primary/author exclusion fields.
Record the active-primary and interpretation-author families from session and
artifact evidence. Before dispatch, establish that the proposed reviewer has a
known family distinct from both; a planned route name alone does not prove it.

## Workflow

1. Quote the original request exactly, preserving negations and scope limits.
2. Write the interpretation as objective, in-scope work, out-of-scope work,
   constraints, success criteria, and stop conditions.
3. Put the two frozen documents in the payload and ask the reviewer to compare
   missed constraints, added scope, ambiguities, and a recommended interpretation.
   Do not add unsupported identity or family-exclusion fields.
4. Dispatch an independent intent comparison only after the caller has established a
   known-distinct eligible reviewer. If that cannot be established, explain the
   missing lineage or selection evidence without dispatching a claimed
   independent comparison. After the response, verify its observed reviewer family
   differs from both recorded families and that it addresses the frozen
   documents. If family or source evidence is missing, retain the response as
   advisory and do not claim an independent intent check. Even with verified
   lineage, document intent remains context only: it cannot satisfy a review or
   governance evidence contract. Preserve the complete
   raw response; do not require a verdict line or alternate envelope.
5. Adjudicate the returned text as match, drift, or ambiguity. On a match,
   proceed. On drift, revise the interpretation and recheck only when a new
   request is separately justified. On ambiguity, ask the operator only the
   load-bearing question. Preserve and reason over the full raw route result;
   never replay it for formatting.

Never reconstruct a raw provider command, choose an explicit target unless the
operator names its provider, invoke Claude synchronously, or turn a route-local
typed failure into a claim that global governance is unavailable.
