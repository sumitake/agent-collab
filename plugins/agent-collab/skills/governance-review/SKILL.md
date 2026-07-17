---
name: governance-review
version: 4.0.4
description: Use when the operator says "governance review," "high-stakes review," "tiebreaker," or "second opinion." Also offer this proactively when reviewer-family independence must be enforced.
---

# Run an independent governance review

Resolve the **plugin root** from this loaded file and invoke only
`python3 "<plugin-root>/coordinator.py"` with a bounded governance request that
includes captured artifact content and author-model provenance.
Read the **Coordinator request schema** in `<plugin-root>/README.md` before
constructing the request; never invent fields or route/action pairs.

## Workflow

Resolve both the active primary family and the immutable artifact-author
family. If either is unknown, fail closed with `unknown_family`; preserve the
error detail that identifies which snapshot could not be proved. Exclude both
families from the reviewer panel, tiebreaker, fallback, and retry set.

Seal the request as read-only authority. A governance review must
never enter a mutation-capable worker route. If no independent managed reviewer
is eligible, return `unavailable`; a specifically selected same-family route is
`same_family_blocked`. Do not weaken independence or use a same-family result.

The only eligible advertised read-only actions are Gemini `governance`, Codex
advisory, and Grok `governance`. OpenCode plan, every build role, and
the output-only `composer/codegen` compatibility route are never governance-
review candidates.

Gemini governance is a distinct broker-only action, never an advisory alias.
Accept its result only when the public client validates the complete artifact-
bound governance proof, including canonical real-HOME containment, controlling
PTY, state lease, cleanup, exact model/effort, response hash, and proof hash.
Gemini advisory or long-context output is not governance evidence.

Claude participation can occur only through a separately configured host-owned
async transport after readiness is observed. The public coordinator neither
sends nor accepts governance over `inbox/async`; never create a synchronous
Claude route. Execution mechanics stay inside the verified co-packaged native
artifact, with typed result and provenance preserved.
