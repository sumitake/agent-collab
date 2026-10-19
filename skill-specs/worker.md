---
name: worker
version: {{ skill_version }}
description: Use when the operator says "delegate this implementation," "generate a private patch," "use Grok for codegen," or "use Moonshot for frontend work." Also offer this when a bounded non-governance task needs output-only code generation without access to the caller checkout.
---

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
