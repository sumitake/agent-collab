---
name: governance-review
version: 7.0.6
description: Use when the operator says "governance review," "high-stakes review," "authoritative verdict," or "tiebreaker." Also offer this when reviewer-family independence and an exact repository-grounded verdict must be enforced.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Honor an operator-named provider with `explicit_target`. For an authorized independent review or governance task without an operator-named provider, also use that field to bind the caller-verified distinct reviewer selected by the caller or designated by the workflow. Carry the same target into planning and live dispatch; verify returned native lineage before accepting independence. Otherwise use normal untargeted routing. Choose quality and effort for the workload; include context/output token estimates when known. Read the current manifest digest and actual cwd device/inode; do not copy example values. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not live availability or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.

# Independent governance review

Use only `governance.repository`. The caller creates one bounded work unit for
the immutable review scope and runs it from the canonical repository at the
exact expected source head. Do not send a provider route/action pair or
reconstruct a provider command.
Use `quality_profile="frontier"` and `effort_class="maximum"`. These are closed
provider-neutral request fields and never authorize a model or version pin.

Before dispatch, the caller must record the observed lineage and source of both
the active primary and artifact author, then select a reviewer whose known
lineage differs from both. After the response, record the observed reviewer
lineage and source before treating it as governance evidence. A route, provider
name, status, receipt, or self-assertion alone does not prove lineage. Preserve
unknown lineage as unknown. If no known-distinct eligible reviewer can be
established, do not dispatch a claimed independent governance review; explain
the missing lineage or selection evidence. A specifically selected ineligible
or same-family agent is not silently replaced.

Preserve every nonempty raw or recovered response. Use ordinary model reasoning
over its full content to deduce the best-supported operative verdict; do not
require JSON, verdict keys, findings shape, terminal wrappers, telemetry, or a
receipt, and never synthesize approval from process exit. Retain available
receipts and diagnostics for audit, including any integrity concerns, but do
not discard provider content when they are absent or malformed. If reviewer
independence, exact source identity, or scope cannot be positively established,
keep the response as advisory content and do not claim authoritative approval.
Do not replay a consumed review to repair incomplete lineage evidence.
