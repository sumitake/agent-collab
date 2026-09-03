---
name: architect
version: 7.0.2
description: Request read-only architecture consultation for codebase analysis, system design, implementation planning, decomposition, or long-horizon strategy. Use when the user says "ask the architect," "have Grok design this," "architecture consultation," "plan this implementation," or "/agent-collab:architect." Also offer this before a substantial multi-system implementation where an independent architecture pass can reduce rework.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on stdin. Before constructing it, read the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit for this skill's logical action, with a bounded opaque payload. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.

# Architecture consultation

Use `architecture.repository` for repository-aware analysis and
`architecture.conceptual` only for genuinely conceptual consultation. A
repository consultation runs from a caller-controlled checkout at the exact
expected source head. The caller records and rechecks that identity; path or
telemetry output from the provider is diagnostic only. A response whose source
identity cannot be positively established remains useful advisory content but
is not repository authority.

Resolve the plugin root, read `<plugin-root>/README.md`, and submit one bounded
work unit through the routing runtime. Set `explicit_target` only when the user
explicitly names one. Do not construct provider commands or transport actions.
Use `quality_profile="frontier"` and `effort_class="maximum"` for substantial
architecture work; these choose desired quality and depth, never a model ID.

Ask for the recommended architecture, invariants and threat boundaries,
dependency-ordered implementation units, verification plan, and unresolved
assumptions. Preserve every nonempty raw or recovered response and interpret it
with ordinary model reasoning; provider formatting and optional diagnostics do
not gate the advice. The primary owns edits, tests, integration, commits,
merge/release/deploy, and secrets.

## Delivery estimate checkpoint

When producing a formal implementation design or plan, after scope, completion
boundary, phases, dependencies, and gates are concrete and before final
presentation, invoke `project-estimation` once for the artifact scope. Attach
its compact `Delivery estimate` as `design_provisional` or
`implementation_plan`; attach typed `estimate_unavailable` if no defensible
range exists. A typed cost such as `unavailable_no_token_prior` must remain
visible; it must not become zero or a workflow failure. On an unsupported host,
use explicit invocation and state that
the automatic checkpoint is unavailable rather than claiming it ran.
