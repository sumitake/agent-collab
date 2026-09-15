---
name: governance-review
version: 7.0.6
description: Use when the operator says "governance review," "high-stakes review," "authoritative verdict," or "tiebreaker." Also offer this when reviewer-family independence and an exact repository-grounded verdict must be enforced.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Honor an operator-named provider with `explicit_target`. For an authorized independent review or governance task without an operator-named provider, also use that field to bind the caller-verified distinct reviewer selected by the caller or designated by the workflow. Carry the same target into planning and live dispatch; verify returned response-scoped native evidence before accepting independence. Otherwise use normal untargeted routing. Choose quality and effort for the workload; include context/output token estimates when known. Read the current manifest digest and actual cwd device/inode; do not copy example values. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. Let the native runtime complete its own turns and tool recovery within the original invocation. Keep the OS account's canonical HOME and native configuration; do not create copied login profiles or replacement runtimes. Carry existing operator authorization across tool steps for the same action, source, provider, and scope; do not ask for it again merely because a diagnostic or tool boundary occurred. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not model identity, live availability, or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.
When a completed or terminated read-only review or governance attempt definitively produced no substantive result and no uncertain external mutation, retain that failed attempt as evidence. The caller may then issue at most one new corrected request as a new work unit after fixing a demonstrated setup defect with already authorized context and tools, such as inlining an inaccessible external plan or using an already available interpreter. Keep the same source hash, provider, and known-distinct reviewer requirements, and the original identical authorized scope. Do not copy login profiles or expand permissions. This is not a replay, retry, or failover of the consumed work unit, not a runtime automatic retry, and not a provider switch to evade findings. Do not use it to repair formatting or missing lineage, or when failure is unproven. If findings or usable partial content exist, interpret them instead. Native one-process completion remains separate.

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
