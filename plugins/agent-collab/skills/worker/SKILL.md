---
name: worker
version: 7.0.9
description: Use when the operator says "delegate this implementation," "generate a private patch," "use Grok for codegen," or "use Moonshot for frontend work." Also offer this when a bounded non-governance task needs output-only code generation without access to the caller checkout.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Honor an operator-named provider with `explicit_target`. For an authorized independent review or governance task without an operator-named provider, also use that field to bind the caller-verified distinct reviewer selected by the caller or designated by the workflow. Carry the same target into planning and live dispatch; verify returned response-scoped native evidence before accepting independence. Otherwise use normal untargeted routing. Choose quality and effort for the workload; include context/output token estimates when known. The coordinator fills the installed wire digest and reads each working directory's current device/inode at dispatch. For a repository action, name the exact source directory as `native_restrictions.cwd`; if omitted, a read-only action is bound to the caller's repository or a linked worktree of it, never elsewhere. Read the result's `repairs` list. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. For bounded delegation, explicitly set the supported top-level `deadline_ms`; omitting it uses the 24-hour default. Production actions use an admitted-progress inactivity lease, so this is not a hard total-duration limit: valid progress can renew it. Treat prose duration estimates as expectations, not runtime limits. The caller owns any decision to cancel and verifies the runtime's cleanup; preserve partial content and classify caller cancellation accurately. Never replay the consumed work unit or infer provider outage from cancellation. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. Let the native runtime complete its own turns and tool recovery within the original invocation. Keep the OS account's canonical HOME and native configuration; do not create copied login profiles or replacement runtimes. Carry existing operator authorization across tool steps for the same action, source, provider, and scope; do not ask for it again merely because a diagnostic or tool boundary occurred. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not model identity, live availability, or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.

# Delegate bounded worker output

Use `codegen.repository` for ordinary code generation or
`frontend_codegen.repository` for frontend-affinity work. These are disposable-
repository editing actions, not read-only planning or governance.

The caller creates a disposable repository copy, records its source head and
filesystem identity, and supplies that directory as the work unit's native cwd.
Provide a bounded prompt and an explicit target only when requested. Never send
a model name, provider CLI version, provider transport action, tool list, or raw
provider invocation.
Send closed `quality_profile` and `effort_class` fields chosen for the workload.
Split independently useful deliverables into bounded work units, use dependencies
only for real ordering, and supply context/output token estimates when known.
Standard suits routine work; demanding implementation and validation need a
corresponding quality and effort choice.

For a bounded task, set a supported top-level `deadline_ms` explicitly; if
omitted, the runtime default is 24 hours. For example, a ten-minute inactivity
lease is `deadline_ms=600000`. This is not a promised completion time: production
codegen uses admitted-progress inactivity, so valid progress can renew the
lease. State any prose duration as an expectation, not a hard runtime limit.

Choose one validation handoff before dispatch:

- **Primary-owned validation (default):** ask for the patch and a concise report
  of checks that were not run. The primary runs the focused checks.
- **Worker check:** supply the exact preverified interpreter path and focused
  command, with its working directory and source imports bound to the disposable
  copy. If the command launches a child with a generic interpreter name,
  supply and verify a process-local `PATH` that resolves it to the same
  interpreter. Run one bounded import/version preflight with that context.
  Do not ask the worker to find an
  interpreter or environment. If the preflight or a required import fails, the
  worker reports the missing prerequisite and continues with a coherent partial
  patch when possible. No installation, home-wide search, cache search, or
  sibling-checkout search.

Produce a coherent first patch after the necessary source reads. Optional test
dependencies are not a prerequisite for beginning edits.

For bounded delegation, one request can be shaped like this; use the README's
Python invocation example to submit it:

```python
request = {
    "wire_contract_sha256": manifest["wire_contract_sha256"],
    "request_id": request_id,
    "quality_profile": "standard",
    "effort_class": "standard",
    "deadline_ms": 600000,
    "max_parallel": 1,
    "dispatch_requested": True,
    "work_units": [{
        "id": "patch",
        "capability": "codegen.repository",
        "depends_on": [],
        "payload": brief,
        "native_restrictions": {"cwd": str(disposable_repository)},
    }],
}
```

The provider may inspect, edit, and test only the disposable copy. The caller
preserves every nonempty raw or recovered response, captures the binary-safe
diff, verifies the recorded source head, and removes the copy. Provider
formatting and optional diagnostics do not gate content recovery. The primary
reviews and applies accepted changes, independently validates them, and owns
commits, PRs, merges, and deployment. If the caller decides to stop an attempt,
one caller owns cancellation and verifies the runtime's cleanup; retain partial
content and record caller cancellation as such. Never infer a patch or cleanup
from process exit. Never replay the consumed work unit or describe cancellation
as a provider outage.
