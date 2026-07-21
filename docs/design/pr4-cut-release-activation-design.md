# PR-4 design — `cut_release.py` activation path + durable state machine + scoped rollback

Design of record: workspace `drafts/local-activation-release-cut-pipeline.md` §9.2, §9.5, §9.6, §10-A/B/C/D/E/F. Plugin `sumitake/agent-collab`. Tier-3, security-sensitive (release integrity). Operator-approved defaults: **D7** pinned GPG key referenced out-of-tree, **D8** CI-publishes-the-draft.

## Current state (150-line tool)
`cut(dry_run)`: changelog-compiled gate → `run_consistency` → require clean `main` → refuse if tag exists → `git tag -s` + `git push origin <tag>`. `rollback(tag)`: delete remote tag, local tag, `gh release delete` — **unscoped** (no identity checks, reports success on partial failure). No activation, no bundle, no journal, no resume.

## Ownership split (D8: CI publishes)
- **PR-4 (this, local operator tool):** `PREPARED → TAGGED → DRAFT_UPLOADED`, then dispatch CI, plus `--resume` and scoped rollback.
- **PR-5 (CI):** `DRAFT_VERIFIED → PUBLISHED(immutable observed) → ATTESTED`. The publishing job writes the terminal states. Consumers fail closed until `ATTESTED` (§10-D).

## The cut sequence (§9.2 as refined by §10)
0. **Preflight** (existing gates kept): changelog compiled, `run_consistency`, clean tree. NEW: on `main`, and refuse if `main` carries activation artifacts (§10-E: `main` never carries them).
1. **Classify** from the committed manifest (`build_plugin_archive.classify_package`). `policy-only` → existing simple path (unchanged behavior, no bundle, no draft flow) — keeps today's releases working. `activation` → the flow below, requiring `--bundle-source`.
2. **Verify the bundle**: `verify_runtime_release.py` against the 0o500 handoff bundle + committed manifest → must pass (fail-closed).
3. **Release-only commit (§10-E)** — the load-bearing topology:
   - parent == the intended reviewed `main` commit (recorded);
   - diff == an **exact allowlist**: only the activation `artifacts` entry in `runtime-manifest.json` (+ nothing else). Assert the diff touches *only* that path and **never** the GPG trust anchor / workflow files (§10-F/G);
   - created detached (`git commit-tree`-style or a detached checkout) so **no branch points to it**; never pushed as a branch;
   - the signed tag points at THIS commit; `main` is untouched.
4. **Build the archive**: `build_plugin_archive.py --bundle-source <leaf> --output <tmp>` from that release commit's tree → deterministic archive; compute `Asset-SHA256` + `Manifest-SHA256`.
5. **Signed annotated tag (§10-A)** with a MANDATORY structured message:
   ```
   agent-collab <tag>
   schema: agent-collab-release/1
   Asset-Name: <exact asset filename>
   Asset-SHA256: <64-hex>
   Manifest-SHA256: <64-hex>
   ```
   `git tag -s` (signing stays explicit; D7's pinned fingerprint is CI-side verification, not a local change). Push the **tag only**.
6. **Draft release (§9.2/§10-C)**: `gh release create <tag> --draft --verify-tag <archive>` attaching **ONLY the archive** (CI generates checksum + SPDX per §10-C). Capture release ID + asset ID(s).
7. **Dispatch CI (§10-B)**: `gh workflow run` / `repository_dispatch` carrying `release_id`, `tag_object_id`, `asset_id`, `asset_sha256`. Draft releases do NOT fire `release:*`, and a CI-published release does not trigger another run — so the dispatch is the only correct trigger.
8. Print the journal state + what CI will do. **cut_release never publishes** (D8).

## Durable cut journal (§9.5)
- Location: `.git/agent-collab-cut-journal/<tag>.json` (inside `.git` → never committed, never in the archive, survives checkouts). Mode `0o600`, atomic write (temp + `os.replace`), `O_NOFOLLOW` reads.
- Record per state: `state`, `tag`, `parent_commit`, `release_commit`, `tag_object_id`, `asset_name`, `asset_sha256`, `manifest_sha256`, `release_id`, `asset_ids`, `dispatch_run_id`, timestamps, and a `schema` version.
- **Idempotent, remote-identity-checked transitions.** Every `--resume` step re-reads the REMOTE truth (`git ls-remote` for the tag object ID; `gh release view` for release/asset IDs + draft status) and compares to the journal. **Any mismatch STOPS with the discrepancy** — never "already released", never silent repair (§9.5).
- `--resume` re-enters at the recorded state and continues; a missing journal for an existing remote tag is itself an inconsistency → stop.

## Scoped rollback (§9.6)
- `--rollback <tag>` operates **only** on an unpublished DRAFT whose **tag object ID + release ID + asset IDs + asset digest all match the journal**. Any mismatch (or no journal) → refuse, print residual state, non-zero exit.
- If the release is **published** (or `immutable` observed true) → **refuse**: instruct to publish an explicit revocation + a higher patch release (never delete/reuse a published tag).
- Verify EVERY deletion (re-query after each); on partial failure report exactly what remains and exit non-zero — **never** declare success (today's `check=False` swallow is exactly the bug).
- **Burn the version**: after a rollback, record the burned version in the journal so a later cut of the SAME version refuses (forces a patch bump).

## Compatibility
`policy-only` releases keep today's exact behavior (gate → signed tag → push; release.yml handles it). All new machinery is gated behind `classify_package() == "activation"` so this PR cannot regress the current release path. `--dry-run` must print the full activation plan without mutating anything (including no release commit, no tag, no draft).

## Tests
- policy-only path byte-identical to today (regression).
- activation: full happy path with fakes for `git`/`gh` — asserts tag message carries the 4 mandatory fields with the REAL computed digests; draft-only (never `--draft=false`); only the archive attached.
- release-commit topology: parent == reviewed main; diff is exactly the allowlist; refuses if the diff touches anything else (esp. workflows/`.gpgkeys/`); no branch points to it; `main` unchanged after the cut.
- journal: each transition persists; `--resume` continues; a REMOTE/journal mismatch (tag object ID differs, release ID differs, asset digest differs, release already published) STOPS with a discrepancy, never proceeds.
- rollback: refuses on published/immutable; refuses on identity mismatch; verifies each deletion; reports residual + non-zero on partial failure; burns the version so a re-cut of the same version refuses.
- fail-closed: activation without `--bundle-source`; `verify_runtime_release` failure; `main` carrying activation artifacts; dirty tree; non-main branch.

## Reviewer questions
1. Journal in `.git/` — right home? (Not committed, survives checkout, but wiped by a fresh clone; is a fresh-clone resume expected to be impossible-by-design, or should the journal be reconstructible from remote truth alone?)
2. Release-only commit created detached with no branch: is `git commit-tree` + `git tag -s <commit>` the safest construction (vs a temp branch that is deleted)? Any way an attacker/mistake leaves it reachable or gets it onto `main`?
3. Is "burn the version" the right rollback posture, or should it allow re-cutting the same version when the draft was provably fully deleted?
4. §10-C says producer uploads ONLY the archive. Confirm nothing else (no .sha256) should be attached locally, and that CI attaching them later cannot be raced by the producer.
5. Any TOCTOU between step 4 (build+digest) and step 6 (upload) — the archive file on disk could be swapped before `gh` reads it. Should the upload re-digest immediately before/after and compare to the tag's `Asset-SHA256`?

# ============ v2 — CONVERGED after design review round 1 (supersedes above on conflict) ============
Codex RECONSIDER/H (9 blocking) + GLM PROCEED-WITH-MODIFICATIONS (18). Operator decision: **option (a)** — narrow the threat claim; no authority-isolation repo.

## V0. Threat claim, stated honestly (operator decision (a); Codex #6)
GitHub repo **writers can manage releases**, and immutability protects assets **only after publication** — so a writer could mutate or prematurely publish the draft between CI verification and CI publish. Therefore the pipeline does **NOT** claim "a tampered artifact cannot be published."
**The claim IS: a tampered artifact cannot be accepted or installed by CONFORMING PR-6 consumers.** Consumers fail closed until `ATTESTED` **and** verify the CI verification receipt (V7). **Manual/legacy install paths are explicitly OUTSIDE the claim.** Premature tampered publication remains possible; its outcome is consumer rejection → signed revocation → higher patch release — not installation. Documented in the spec + PR-6 enforces it. Authority isolation (separate publication repo) is recorded as the available upgrade, not implemented.

## V1. Journal: location, locking, write-ahead (Codex #1; GLM #5)
- Path: `$(git rev-parse --git-common-dir)/agent-collab-cut-journal/<tag>.json` — **never literal `.git/`** (linked worktrees have a `.git` FILE). Mode 0o600, atomic temp+`os.replace`, `O_NOFOLLOW` reads.
- **Per-tag lock** (`<tag>.lock`, `O_CREAT|O_EXCL`) around every transition; stale-lock detection by pid+mtime, never auto-steal silently.
- **Write-ahead (intent) records before every remote side effect**: `TAG_PUSH_PENDING → TAGGED`, `DRAFT_CREATE_PENDING → DRAFT_CREATED`, `ASSET_UPLOAD_PENDING → DRAFT_UPLOADED`, `DISPATCH_PENDING → DISPATCHED`. A crash after the remote effect but before the commit record leaves a PENDING state that `--resume` reconciles against remote truth — without write-ahead this permanently bricks resume.
- **Fresh clone (no journal) `--resume` REFUSES by default.** Explicit `--recover` reconstructs from remote, and only if: tag signature verifies against the pinned fingerprint, the asset re-download digest matches the **signed tag's** `Asset-SHA256`, and the release is still a draft; marks `reconstructed: true`.

## V2. Truth precedence: THE SIGNED TAG WINS (GLM #4 — anti-fail-open)
Per-field source of truth: `tag_object_id` ← `git ls-remote`; release/asset IDs + draft status ← `gh release view`; **`asset_sha256` ← re-download + re-digest of the remote asset**, never the journal. On ANY journal↔remote↔tag conflict the **signed tag's `Asset-SHA256`/`Manifest-SHA256` are authoritative** and the run STOPS with the discrepancy. A tampered journal can therefore never authorize a rollback or a "proceed".

## V3. Release-only commit (Codex #2; GLM #1/#2/#3)
- Construct with **`git commit-tree`** (mandated; drop "or detached checkout") so it is reachable ONLY via the tag. It is intentionally reachable forever through the (never-deleted) signed tag — report that as an **audit tombstone**, not a leak.
- Preflight asserts **`local main == origin/main`** (no ahead/behind/diverged) so `parent_commit` is the genuine reviewed tip.
- Diff gate is a **semantic JSON delta**, not "one path changed": exactly the expected `artifacts` insertion into `runtime-manifest.json`, unchanged file mode, no other path, and **never** the GPG trust anchor or `.github/workflows/**` (§10-F/G).
- The cutter's one-time assertion is **defense-in-depth only**; a permanent **main-branch CI gate** rejecting activation artifacts / release-only topology on `main` is required (filed for PR-5).

## V4. Draft creation + upload are SEPARATE ops (Codex #4)
`gh release create <tag> --draft` (empty, `--verify-tag`) → journal the **release ID** → THEN upload the archive by numeric release ID → journal the **asset ID**. The combined form is not crash-atomic. Producer attaches **ONLY the archive**; within the conforming pipeline CI is the only component that adds checksum/SPDX (this is a pipeline convention, NOT authority isolation — repo writers retain GitHub release permissions) and re-checks the final asset allowlist.

## V5. TOCTOU closure (Codex #5; GLM #11/#12)
Build into a 0o400 temp; hash **through the already-open descriptor** (not a re-open by path); upload by numeric release ID; then **download the captured asset ID and hash those REMOTE bytes**; three-way compare {open-fd digest, signed-tag `Asset-SHA256`, remote-download digest}. Any mismatch → STOP, do **not** dispatch CI. (`--verify-tag` verifies the tag exists, NOT asset content — do not be lulled.) CI independently re-downloads + re-builds from the release tree (PR-5).

## V6. Dispatch pinned to the tag (Codex #8; GLM #15)
`gh workflow run <wf> --ref <tag>` — **never** `repository_dispatch` off a moving default branch. After dispatch, **verify the run exists** (`gh run view`) and re-dispatch if lost; `gh workflow run` returning 0 means "accepted", not "started". The pipeline's only `contents:write` job sits behind a **tag-restricted protected environment** (a pipeline constraint, not an authority boundary), per-tag concurrency, cancellation disabled (PR-5).

## V7. Verification receipt ≠ generic attestation (Codex #7)
`DRAFT_VERIFIED` requires a **CI-generated verification receipt** binding: tag object ID, peeled commit, release ID, asset ID(s), asset digest, workflow file SHA + ref, run ID + attempt, and policy version. GitHub's automatic immutable-release attestation proves tag/commit/assets — NOT that our verification policy ran — so consumers verify the receipt's signer identity + predicate (PR-5 emits, PR-6 verifies).

## V8. Rollback (GLM #7/#8/#9/#10; Codex #3)
- Scope: unpublished DRAFT only, with tag object ID + release ID + asset IDs + **remote-re-digested** asset all matching, and the signed tag authoritative (V2). Published/immutable → **refuse**; require a signed revocation + higher patch.
- **Three-phase per deletion**: confirm-exists → delete → confirm-gone. Order: assets → release → (tag is **never deleted**). Report exact residual state and exit non-zero on any partial failure — never declare success.
- **Version burn is a committed, signed, pushed artifact** (e.g. `revocations/<version>.json` on a protected branch), **not** `.git/` — a `.git/`-only burn is erased by a fresh clone (the clearest fail-open in v1). Burn **unconditionally**; no "re-cut on provable full deletion" (unverifiable; CDN/cache residue; digest ambiguity). The signed tag is never deleted, which independently blocks name reuse under immutable releases.

## V9. Canonical grammar + classification boundary (Codex #9; GLM #14)
Tag message parsed strictly: exact field set, no duplicates/unknown fields, ASCII asset name, safe basename, lowercase 64-hex digests, annotated (not lightweight/nested) tag, signer fingerprint == pinned. **Classification must be explicit**: unknown/contradictory → **FAIL**, never fall through to `policy-only`. **`policy-only` releases are ATTESTED-gated too** (else an activation→policy-only manifest flip bypasses attestation entirely).

## V10. `--dry-run` (GLM #17)
Builds the archive to a temp for a **real** digest (a printed fake digest would be worse than none), prints the full plan incl. the exact tag message, then discards. No commit, no tag, no draft, no dispatch, no journal mutation.

## Tests (superseding v1's list)
Add: write-ahead crash injection at EVERY remote boundary (kill between side effect and journal write → `--resume` reconciles); fresh-clone resume refuses, `--recover` path verified; journal-tamper → tag wins → STOP; semantic-JSON-delta gate rejects an extra path / workflow / trust-anchor edit; separate create-then-upload journaling; three-way digest mismatch stops before dispatch; rollback three-phase + residual reporting + unconditional burn survives a simulated fresh clone; policy-only is attestation-gated; tag-grammar fuzz (dup/unknown/non-ASCII/uppercase-hex/lightweight).
**Note (Codex #9):** command fakes cannot validate real races — a real-GitHub canary cut is required before the production cut; flagged as an operator-run step.
