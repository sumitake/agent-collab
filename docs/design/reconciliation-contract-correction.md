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

---

## Threat model and enumerated bypass classes (added; should have come FIRST)

This section is what the adversarial-architecture-review directive requires *before*
codegen, and its absence is why this surface took four post-hoc rounds instead of one
confirming round. The reviewer's job is to attack this enumeration and name what is
missing, before any code is written against it.

**Attacker model.** Three distinct capabilities, deliberately separated because they
defeat different controls:

- **A1 — local-state attacker.** Can write the operator-local journal and lock files
  (they are plain files under `.git/`). Cannot forge a signed tag. This is the model
  the "signed tag wins" invariant exists for.
- **A2 — repo-writer attacker.** Can push commits/tags/releases to a repo with no
  branch protection (this repo is free-tier). Can create, delete, and recreate remote
  tags, drafts, and assets. Cannot obtain the signing key.
- **A3 — confused-deputy caller.** Not malicious; a future wiring caller that omits an
  argument, passes the wrong commit, or supplies caller-derived data instead of
  git-derived data. Historically the most productive class in this PR.

**Bypass classes the matrix must be shown to handle.** Illustrative, not exhaustive —
the reviewer should add classes:

1. **Absence-as-agreement.** Missing evidence read as consistent. Has now appeared
   three times in one function (required evidence, recorded identity, `journal=None`).
   Every cell must state what absence MEANS, never leave it implicit.
2. **Residue-as-success.** State that should be GONE but is not — a rollback that
   deleted the tag but not the draft, or the asset but not the release. The column
   never asked about, and the source of P1-b.
3. **Substitution under a stable name.** A remote object deleted and recreated with
   the same name but a different identity (tag → different OID, asset → same digest,
   different id). Defeats any check keyed on name rather than identity.
4. **Adoption of unowned state.** A fresh clone, or a journal-less run, silently
   inheriting a remote cut it never performed (P1-a). Must route to explicit verified
   recovery, never proceed.
5. **Tampered-journal steering.** A2 or A1 editing the local journal to select a
   weaker path — routing an activation cut into a legacy path, or marking a live cut
   terminal so its guards are skipped.
6. **Type and value punning.** Python equality collapsing `3/3.0`, `1/True`, `0/False`,
   and truthiness collapsing `0`/`""`/`[]`/`{}` with `None`. Already bit this PR twice
   at different depths; the matrix must specify comparisons as type-strict.
7. **TOCTOU on ownership.** Any check separated from the action it guards — the lock's
   read-then-unlink (P2), and by extension any "verify then act" on remote state that
   can change between the two calls.
8. **Partial-progress ambiguity.** A `*_PENDING` state is genuinely "may or may not have
   landed"; the matrix must distinguish that legitimate ambiguity from an inconsistency,
   or resume either re-fires effects or refuses valid resumes.
9. **Terminal-state escape.** Transitions into or out of terminal/CI states that bypass
   the graph because the graph only governs the forward list (already seen once).
10. **Caller-supplied evidence.** Anything the gate accepts as fact rather than deriving
    from a pinned git object — paths, manifests, modes today. A3's main lever.

**What the reviewer is asked to attack:** which class above is under-specified enough
that an implementer improvises; which class is missing entirely; and whether the R1
matrix as scoped can actually be enumerated finitely, or whether it hides an unbounded
case space that needs a different structure.

---

## PREMISE ERROR — the artifact contract was invented, not read

Found by the Codex PR bot on `f323e8b`, verified immediately. It invalidates the
artifact-validation work in this PR and part of the plan above.

`REQUIRED_ARTIFACT_FIELDS` was written as `platform, sha256, size_bytes,
runtime_identity`. The repository's own `plugins/agent-collab/runtime-manifest.schema.json`
requires **thirteen** fields: `platform, arch, kind, minimum_macos, path, entrypoint,
size, sha256, provider_runtime_version, route_contract_version, signing, files,
contracts`.

Measured against the real schema:

- `size_bytes` and `runtime_identity` **do not exist**. I invented both.
- **11 of 13** genuinely required fields are not checked at all.
- A schema-valid artifact is **REJECTED** (`missing required field(s):
  runtime_identity, size_bytes`), so this gate would have blocked every activation
  release while validating almost nothing.

**Root cause.** The field list came from this design document's own prose ("platform,
digest, size, and runtime identity") rather than from the schema that already existed
in the repository being edited. Nothing verified the premise — not me, not two CLI
review rounds, not three bot rounds. The tests all passed because they were written
around the invented shape, so they asserted the implementation instead of the
contract: the reward-hacking signature the project directive names explicitly.

**Consequences for this plan.** The adversarial design review dispatched before this
was found is running against a document containing the wrong artifact premise. Its
findings on the reconciliation matrix (R1–R5) remain valid — that part does not depend
on artifact shape — but anything it concludes about artifact validation must be
re-derived.

**Correction (design, not patch).** Do NOT hardcode the thirteen fields; a duplicated
list drifts exactly as the tag-name regex did earlier in this PR, and for the same
reason. Validate against `runtime-manifest.schema.json` as the single source of truth,
so the gate cannot disagree with the schema the repository already enforces. The
existing `_validate_activation_manifest()` is the incumbent contract and should be
reused rather than paralleled.

**Process rule this earns.** Before building a validator for an existing artifact,
locate and read that artifact's existing contract. "Audited execution on an unaudited
premise is still wrong" is already in the project directives as a delegation rule; it
applies to my own work identically. A premise check is one grep and it would have
saved this entire sub-effort.

---

## Two further findings, both routed to the matrix rather than patched

Codex bot on `84ba93d`. Confirmed, deliberately not fixed inline — the first is
inside the design stop, and the second is recorded rather than coded because the
lesson of this PR is that reactive fixes to this module generate the next finding.

**F1 (P1) — a CI-labelled state in the local journal skips the publication check.**
Setting the journal to `DRAFT_VERIFIED` / `PUBLISHED` / `ATTESTED` puts it outside
`STATES`, so the publication-before-dispatch guard never runs. With otherwise
matching evidence, `require_consistent` accepts a published release with no
dispatch and no CI receipt. Verified: an A1 attacker edits one local file and an
out-of-pipeline publication is reported consistent.

This is **bypass class 5 (tampered-journal steering)** from the enumeration above,
and worth noting as a positive signal: the threat model named this class before the
bot found the instance. The matrix should therefore cover it *by construction*
rather than as a patch — which is the entire argument for R1.

The rule it implies, for the CI-state rows: a CI-labelled state is a CLAIM by the
most-tamperable source about work only CI can perform, so it may never be *trusted*
— it must be corroborated by authenticated external evidence (a dispatch run, a CI
receipt) or treated as inconsistent. Concretely, the three CI rows require dispatch
evidence and forbid "published without it", and the local cutter still cannot write
them (already enforced in `advance()`; this closes the read side).

**F2 (P2) — creating the journal directory is not durably persisted.**
`_atomic_write` calls `mkdir` then fsyncs only the newly created directory, not the
parent whose entry changed. Power loss can therefore remove the directory after
`save()` returned success, destroying the write-ahead `*_PENDING` record that
recovery exists for. The fix is to fsync the parent when the directory is created —
narrow and mechanical, but it belongs with the durability work rather than as a
sixth reactive commit to this file.

Both are work items for the post-convergence implementation, not inline patches.
