# `require_consistent` — the reconciliation contract needs designing, not patching

**Status:** design phase. The implement→review loop on this function is STOPPED per
the adversarial-review tripwire. No further inline patches until this converges.

## Why the loop stopped

`require_consistent` has been fixed four times in this PR. Each fix was correct for
the case it was given, and each one created or left the next round's finding:

| Round | Fix applied | What that fix caused |
|---|---|---|
| 1 | Added a state-indexed required-evidence table (absence ≠ agreement) | Broke rollback: a `ROLLED_BACK` cut was asked for evidence rollback deletes on purpose |
| 2 | Documented `journal is None` as "no claim, nothing to verify" | **P1-a**: a fresh clone silently adopts an existing remote cut |
| 3 | Added a terminal-state early return | **P1-b**: a rollback that only partly deleted its remote objects reports consistent |
| 3 | Pinned each required-evidence row individually | **P1-c**: a *recorded* identity that is missing still skips its comparison (falsey ≠ absent, third instance in this function) |

Plus the lock's read-then-unlink TOCTOU, deferred in round 2, which came back as
P2 with a sharper failure: an operator clears a stale lock as instructed, a new
cutter acquires the pathname, and the old holder's `unlink` deletes *their* lock —
so the token check does not actually establish ownership.

Four rounds of findings in one function, each traceable to the previous fix, is
not bad luck. It means the function has no specified contract — I have been
filling in a table one reviewer-reported cell at a time, and an unfilled cell is
invisible until someone reports it.

## The actual gap

`require_consistent` reconciles three sources (journal, remote, signed tag) across
**twelve** journal states plus *absent*. Its contract is a table, and it was never
written down. For every state it must answer three questions, and today it answers
them only where a reviewer happened to look:

1. **What remote evidence MUST exist?** (absence is an inconsistency)
2. **What remote evidence MUST NOT exist?** (residue is an inconsistency — the
   question P1-b exposed, and which is currently never asked)
3. **What must the journal itself have recorded?** (a completed state that lost its
   own `tag_object_id` cannot legitimately compare anything — P1-c)

Question 2 is the one that never got asked at all. Every fix so far has been about
*required* evidence; nothing checks for evidence that should be *gone*.

## What has to be designed

**R1 — The full state × evidence matrix, written down before any code.** All
thirteen states (nine `STATES`, three `CI_STATES`, one `TERMINAL_STATES`) plus
absent, each with its required / forbidden / recorded-identity answers. A cell that
is genuinely "no constraint" says so explicitly. The matrix is the artifact to
review; the implementation is a transcription of it.

**R2 — Absent journal is its own row, not a fall-through.** V1 says a fresh-clone
resume must REFUSE an existing remote cut and route to an explicit verified
`--recover`. Today `reached = -1` skips every check, so it silently adopts. This
row needs designing against the recover path, not a boolean.

**R3 — Forbidden-evidence is a first-class column.** `ROLLED_BACK` must assert the
release and asset are *gone*, not merely that nothing is published. Rollback that
half-succeeded is the failure mode that most needs catching, and it is the one
currently reported clean.

**R4 — Recorded identity is required before comparison.** A completed state whose
journal lacks `tag_object_id`/`release_id` must stop, not adopt whatever the remote
currently holds. This is the falsey-vs-absent class ([[falsey.is.not.absent]])
appearing a third time here, so it should be enforced structurally — the required
row asserts the recorded value exists before any comparison happens.

**R5 — Ownership must be an inode/descriptor, not a pathname token.** Replace
read-then-unlink with an FD-backed advisory lock (`flock`), so ownership cannot be
invalidated between the check and the removal. A pathname comparison can never be
atomic with the removal it guards.

## Verification obligations

- Every cell of the R1 matrix gets a test, including the "no constraint" cells,
  so an unfilled cell is a visible gap rather than silent acceptance.
- Each required and each forbidden rule is mutation-checked individually —
  per-cell, not per-guard. Deleting one row must fail exactly one subtest. (Coarse
  mutation already produced a false pass earlier in this PR.)
- The lock is tested with a genuine interleaving: holder → operator clears →
  new acquirer → stale holder releases.

## Scope note

This is a correction to a module already in flight, not new scope. The rest of the
PR — tag grammar, release-commit topology, strict JSON, type-strict comparison,
transition graph, path validation — is unaffected and stays as reviewed. What must
not happen is a fifth reactive patch to this function while its contract is still
undefined.
