---
name: intent-check
version: {{ skill_version }}
{{ intent_check_defaults_block }}
description: Verify that the active primary's interpretation matches the operator's request before consequential planning or execution. Use when the user says "intent check," "confirm what I asked," "check for scope drift," or "/{{ package_name }}:intent-check." Also offer this proactively when a major request has multiple constraints whose omission would materially change the result.
---

# Intent check - distinct-family interpretation comparison

Freeze two artifacts: the operator's original request and the active primary's
plain-language interpretation. Do not include an implementation plan; this
step checks understanding, not design quality.

Resolve the **plugin root** from this loaded file and invoke only
`python3 "<plugin-root>/coordinator.py"` with a bounded governance-review
request. The public policy captures the active primary/model/session and
artifact-author model, excludes both families, and selects only an eligible
Gemini or Grok governance row, or a Codex advisory row. No reviewer
or escalation model is fixed in this skill. Claude is asynchronous inbox-only.

## Workflow

1. Quote the original request exactly, preserving negations and scope limits.
2. Write the interpretation as objective, in-scope work, out-of-scope work,
   constraints, success criteria, and stop conditions.
3. Capture artifact author-model provenance. If primary or artifact family is
   unknown, fail closed; do not accept a caller-provided family assertion.
4. Ask the dynamically selected independent reviewer to return exactly:

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

Safe mode leaves governance model routes unavailable. Never reconstruct a raw
provider command, invoke Claude synchronously, or silently use a same-family
reviewer.
