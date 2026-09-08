---
name: intent-check
version: {{ skill_version }}
{{ intent_check_defaults_block }}
description: Verify that the active primary's interpretation matches the operator's request before consequential planning or execution. Use when the user says "intent check," "confirm what I asked," "check for scope drift," or "/{{ package_name }}:intent-check." Also offer this proactively when a major request has multiple constraints whose omission would materially change the result.
---

# Intent check - advisory interpretation comparison

Freeze two artifacts: the operator's original request and the active primary's
plain-language interpretation. Do not include an implementation plan; this
step checks understanding, not design quality.

Resolve the **plugin root** from this loaded file and invoke only
`python3 "<plugin-root>/coordinator.py"` with one normally untargeted
`context.documents.intent` work unit. Put the verbatim operator request and
plain-language primary interpretation in its bounded opaque payload. Use a
provider-free planning request to inspect route eligibility before dispatch;
set `explicit_target` only when the operator names a provider. The caller does
not construct an agent/action pair or invent primary/author exclusion fields.
This is an advisory context comparison and has no pre-dispatch family gate.

## Workflow

1. Quote the original request exactly, preserving negations and scope limits.
2. Write the interpretation as objective, in-scope work, out-of-scope work,
   constraints, success criteria, and stop conditions.
3. Put the two frozen documents in the payload and ask the reviewer to compare
   missed constraints, added scope, ambiguities, and a recommended interpretation.
   Do not add unsupported identity or family-exclusion fields.
4. Dispatch the advisory comparison and check that it addresses the frozen
   documents. Record the observed reviewer lineage and its source when available;
   otherwise label it lineage-unverified advisory. Same-family output remains
   advisory. Even with verified distinct lineage, document intent remains context
   only: it cannot satisfy a review or governance evidence contract. Preserve the
   complete raw response; do not require a verdict line or alternate envelope.
5. Adjudicate the returned text as match, drift, or ambiguity. On a match,
   proceed. On drift, revise the interpretation and recheck only when a new
   request is separately justified. On ambiguity, ask the operator only the
   load-bearing question. Preserve and reason over the full raw route result;
   never replay it for formatting.

Never reconstruct a raw provider command or invoke a provider outside the
co-packaged coordinator. Choose an explicit target only when the operator names
its provider. A route-local failure does not establish that global governance
is unavailable.
