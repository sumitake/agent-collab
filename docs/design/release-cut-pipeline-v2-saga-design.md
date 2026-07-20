# Release-cut PIPELINE — v2 architecture (release saga + signed intent)

**Status:** design, v2 draft. **Scope: the whole cut pipeline**, not the reconciliation
function alone (operator direction 2026-07-20: "broader scope — the whole cut pipeline /
pieces 2–4 together; expand before designing"). v2 re-architects, as one coherent saga,
every piece split out of the original PR-4: the durable journal + reconciliation
(`require_consistent`), burn / revocation, dispatch verification, and the CLI integration
seam. It supersedes both the matrix approach in `reconciliation-contract-correction.md`
(which adversarial design review round 1 rejected at the architecture level — RECONSIDER /
HIGH, 10 blocking, `reviews/reconciliation-plan-adversarial-review-1.md`) and the
step-scoped V0–V10 in `pr4-cut-release-activation-design.md` where they conflict. No code
is written against this until it converges through its own distinct-family adversarial
review.

**Why pipeline scope is the right frame.** Review finding #10 — the journal is a progress
hint, authority comes from signed intent and attempt-bound receipts — is not a property of
one function. It is the shape of the *entire cut*: every effect (tag, draft, asset,
dispatch, and the compensations rollback + burn) is a saga step with the same eight-part
contract. Designing reconciliation in isolation, as v1 did, is what produced a matrix that
could not express the protocol. The pieces were never independent; they are steps of one
saga sharing one intent and one observation model.

**Author model + effort (directive #7):** design authored by Claude (`claude-opus-4-8`,
frontier tier — architecture reasoning is frontier work and stays with the primary per
directive #8). Implementation, once this converges, is delegated to a worker tier against
the converged spec. (A `claude-fable-5` session drafted an earlier reconciliation-only
cut of this doc; the pipeline-scope expansion is authored on `claude-opus-4-8`.)

**Step-0 note.** The operator disambiguated scope directly via a structured question
("broader scope") and re-issued the task; the intent-drift check flags SIGNIFICANT_DRIFT
because a four-word context-referential prompt cannot literally contain this architecture,
and the check is context-blind. Proceeding is on the operator's explicit selection, not on
inference — recorded here as a visible decision, not a silent bypass.

## What round 1 established, and why the matrix was the wrong object

The reviewer's governing finding: *a fully attacker-writable journal cannot be the
authority that selects weaker guards; at most it is a progress hint.* The state ×
evidence matrix I had been building is a **derived invariant specification** — worth
keeping as a checkable artifact — but it cannot repair an authoritative mutable
journal, and a flat matrix cannot express a protocol whose interleavings are
unbounded. So the four rounds of patching were hardening the wrong structure.

v2 inverts the trust relationship:

- **Authorization comes from signed intent**, never from the journal.
- **Progress comes from attempt-bound remote receipts**, never from the journal.
- **The journal is a resume hint only** — a performance optimization that says "look
  here first." Every decision it might inform is re-established from signed intent +
  authoritatively observed remote state. A journal that is absent, stale, or tampered
  changes latency, never correctness.

## Terminology

- **Release intent** — the immutable, signed description of *what this release IS*:
  repository, version, release-commit OID, channel, the exact expected artifact set,
  and the signer policy. It is the root of authority.
- **Effect** — a remote side effect: push the signed tag, create the draft release,
  upload the asset, dispatch CI. Effects are the saga steps.
- **Receipt** — durable, remotely-observable proof that a specific effect landed,
  bound to *this* attempt where the API permits: tag object OID, release id, asset id
  + digest + size, dispatch run id.
- **Observation** — a four-valued read of one remote predicate (below).
- **Epoch** — one coherent batch of observations. Facts compared against each other
  must share an epoch; cross-epoch comparison stops.

## 1. Release intent — the root of authority (findings 6, 9)

Consistency is not authorization. Three mutually-agreeing sources can consistently
describe the *wrong* release — a replayed signed tag from another repo, a different
channel, artifacts from another attempt. So reconciliation must be anchored to an
object that says what this release is *supposed* to be, and that object must be
**signed** and **bound** so it cannot be replayed into a different context.

**Carrier.** The GPG-signed annotated tag is already the signed root (grammar
`agent-collab-release/1`). v2 extends the signed tag message to bind the full intent,
or references a signed intent blob by digest from the tag — an **open question**
(§ Open questions Q1). The intent binds, at minimum:

- `repository` — the **stable numeric repository id** (GitHub's `repository.id`), NOT
  `owner/name`, which is rename/transfer-mutable. Binding the mutable name would let a rename
  or a same-name repo elsewhere satisfy the check. Closes signature-replay from another repo
  (finding 8, A5; sharpened by the PR-bot on `2ce37a5` — stable id, not name).
- `version` — the tag name; the tag *is* the version.
- `release_commit` — the peeled commit OID the tag points at. Binds the tree that
  ships. (finding 7: tag-object OID **vs** peeled commit OID are distinct facts.)
- `channel` — production/beta/…; closes cross-channel replay.
- `artifacts` — the exact expected set, each carrying the real schema's identifying
  fields (§ 8). Not a count, not a partial shape.
- `signer_policy` — the set of key fingerprints permitted to authorize this release,
  pinned **out of band** (in-repo config that is itself in the release-commit tree, or
  operator-provisioned), never taken from the tag being verified. Closes the
  trust-anchor-substitution and signing-oracle classes (finding 8, A6/A7).

**Authorization check** (before any effect is trusted or resumed): the tag signature
verifies **and** the signer fingerprint is in `signer_policy` **and** the bound
`repository`/`release_commit` match the actual repo and the tag's peeled commit. Fail
any → STOP. A valid signature over the wrong context is a CONFLICT, not a pass.

## 2. Four-valued observation — the never-asked column (finding 2)

Every remote predicate is read as one of:

- **PRESENT** — authoritatively observed to exist, with its attributes.
- **ABSENT** — authoritatively observed *not* to exist (a definitive 404 on an
  authenticated, un-rate-limited, complete read).
- **UNKNOWN** — could not be authoritatively determined: transport timeout, HTTP 403/429
  (permission mask or rate limit), incomplete pagination, malformed body, stale-cache
  suspicion. UNKNOWN is not absence.
- **CONFLICT** — present but with attributes that disagree with intent/receipt (wrong
  digest, wrong commit, wrong channel, duplicate matches).

Rules that make this load-bearing:

- Only **authoritative ABSENT** satisfies a forbidden-evidence rule. UNKNOWN read as
  "not there yet" is exactly what would license replaying a landed effect (F3 × finding 2).
- Only **PRESENT with matching attributes** satisfies a required-evidence rule.
- **UNKNOWN always stops** — never selects a weaker path, never resumes. It is a retry
  point, not a decision.
- **CONFLICT always stops** — it is the tamper/replay signal.
- Observations feeding one decision must share an **epoch**; if the tag read and the
  release read cannot be shown coherent (e.g. one predates a known mutation), stop.

This is `falsey-is-not-absent` ([[falsey.is.not.absent]]) lifted to the network layer,
where the collapse `UNKNOWN → ABSENT` is the specific bug.

## 3. The saga — steps, not states (findings 3, 4, 10)

The cut is an ordered saga. Each step is specified by eight parts, per the reviewer:

| part | meaning |
|---|---|
| precondition | what must hold (from intent + observation) before attempting |
| attempt-id | this cut's identifier, bound into the effect where the API allows |
| effect | the remote mutation |
| receipt | the durable, attempt-bound proof it landed |
| postcondition | what must hold after (required PRESENT + forbidden ABSENT) |
| compensation | how to undo it during rollback |
| retry rule | what is safe to re-attempt, and under what observation |
| revalidation | when resuming, how this step's true status is re-established |

**Steps** (the forward effects; compensations — rollback and burn — are §3b, first-class
saga steps with the same eight-part contract, not an afterthought):

1. **push-signed-tag** — effect: push the annotated signed tag. receipt: remote tag
   object OID == local, signature valid, signer in policy. This step *is* the global
   fence (§ 5). revalidation: re-read remote tag; PRESENT+match ⇒ done, ABSENT ⇒
   not-started, CONFLICT ⇒ stop.
2. **create-draft** — precondition: tag receipt holds. effect: create the draft
   release for the tag. attempt-id bound into the release body/name. receipt: release
   id + isDraft==true + tagName==version.
3. **upload-asset** — precondition: draft receipt holds. effect: upload the archive.
   receipt: asset id + digest==intent + size==intent + **name==signed `Asset-Name`**.
   retry: a re-upload must reconcile asset **identity**, not just digest — a
   deleted-and-recreated asset with the same digest is a different id, and matching bytes
   under a *different filename* is still a CONFLICT because consumers resolve the asset by
   the signed name (finding 7; the `substitution-under-a-stable-name` class). Asset
   identity is the full tuple `(id, digest, size, name)`, every element matched.
4. **dispatch-CI** — precondition: asset receipt holds. effect: `workflow run` with the
   tag ref + attempt-id input. receipt: a run whose head is the tag AND whose input
   carries this attempt-id (closes the substitution the earlier `_dispatch_exists` had).

**Per-effect status resolution** (finding 4) — every step, on resume, resolves to
exactly one of: `confirmed-not-started` (authoritative ABSENT of its receipt) /
`completed-by-this-attempt` (PRESENT + attempt-id matches) / `completed-by-another-attempt`
(PRESENT + attempt-id differs → STOP, not adopt) / `ambiguous` (UNKNOWN → retry/stop) /
`conflicting` (CONFLICT → STOP). Only `confirmed-not-started` re-runs the effect; only
`completed-by-this-attempt` advances past it.

The **forbidden column is symmetric** (F3): before step N's PENDING, step N's receipt
must be authoritative-ABSENT; at PENDING it is legitimately ambiguous; after, PRESENT.

## 3b. Compensations — rollback and burn as saga steps (pieces 2 & 3 of the split)

Rollback and burn are not a separate subsystem; they are the saga's compensating steps,
governed by the same eight-part contract, the same signed intent, and the same four-valued
observation. Folding them in here is the pipeline-scope point: the earlier PR-4 split
treated burn/revocation as its own piece, but under the saga it is just compensation with
a receipt.

**Rollback (compensation for a not-yet-published cut).** Precondition: the target release
is still a draft (`isDraft==true`, authoritative PRESENT) and every deletable object's
identity matches the signed intent + attempt-id — never the checkout's manifest (the v1
"rollback targets the tag, not the checkout" fix, generalized: rollback resolves its target
from the **signed tag**, so a policy-only checkout can never mis-route an activation tag's
rollback into the legacy tag-deleting path). Effect: delete asset(s) by id, then the draft
release, then — only if intent says so — the tag. Receipt: each deleted object re-observes
to **authoritative ABSENT** (not UNKNOWN — a 404 under rate-limit is not proof of deletion,
the residue-as-success trap F1/F3). Postcondition: no residual draft or asset (finding
`residue-as-success`). A published release is never rolled back by the cutter — publication
is CI's terminal state and immutable (operator D6); attempting it is a STOP.

**Burn (terminal compensation — a version is spent).** After a completed rollback, the
version is burned so a later cut of the same version refuses. The burn record must be:

- **SIGNED** — a burn is an authorization statement ("this version is void"), so it carries
  the same signer-policy check as intent. `is_version_burned` as an `is_file()` check was
  the free-tier DoS: any repo writer pushes `revocations/<v>.json` and blocks a version.
  Reachability is not authenticity (the round-1 finding). The read side verifies a **signed,
  committed, `origin/main`-reachable** burn commit, and an unsigned or unreachable burn does
  not count.
- **committed and durably persisted** — write-ahead like any other effect; the directory
  fsync must persist the parent entry (F2), and the clean-tree / HEAD guards run **before**
  the file is written ([[guard.defeats.its.own.precondition]] — the original ordering bug).
- **its own receipt** — the burn's presence is itself observed four-valued; an UNKNOWN read
  of the revocation set stops a re-cut rather than allowing it.

**Open question Q6:** burns live on `main`, which on a free-tier repo has no branch
protection, so an attacker can also *delete* a legitimate burn. Signing proves a present
burn is authentic but does not make a burn's *absence* trustworthy. Does the burn set need
an append-only / signed-log structure (each entry chaining the prior) so deletion is
detectable, or is that out of scope for v2?

## 3c. Orchestration and the CLI seam (piece 4 of the split)

The CLI entry (`cut_release.py`) is the saga's orchestrator, and its v1 defects were all
"the seam was never designed" (the parent PR-4 correction). Under v2:

- **Release-manifest builder, derived not passed.** `build_release_manifest(committed,
  archive, runtime_identity)` derives the release manifest from the **built archive's own
  digest/size** and the **schema-valid** artifact shape (§8, against
  `runtime-manifest.schema.json` — the premise-error fix), so the topology gate has a real
  parent→release delta and the tag's `Manifest-SHA256` binds to the bytes actually shipped.
  `runtime_identity` is derived from the verified runtime, never operator input (closes the
  A7 signing-oracle path at the manifest layer).
- **Gate ordering, applicability-split.** Universal cut gates (changelog compiled, version
  consistency, canonical archive verification) run **before** the mode branch; the
  mode-conditional gate (signed-runtime verification, activation only) runs inside it;
  rollback has its **own** gates (target resolvable from the signed tag, signature/identity
  anchored, still a draft) and the cut gates do not apply. A path cannot skip a gate by
  being selected earlier (the v1 "gates before the branch" fix, made precise).
- **Mode from the committed manifest, never a flag.** `--archive` on a policy-only manifest
  is refused; an unclassifiable tree reaches neither path.
- **policy-only is unchanged.** The whole saga is gated behind
  `classify_package()=="activation"`; today's policy-only releases keep their exact behavior
  (this is the compatibility constraint from `pr4-cut-release-activation-design.md`).

## 3d. Piece 1 (already in PR #27) as saga primitives

The sound, reviewed pieces in PR #27 are the saga's building blocks, unchanged: the signed
**tag grammar** (`agent-collab-release/1`) is the intent carrier (§1); the **release-commit
topology gate** (type-strict semantic delta + file-mode) validates the create-release-commit
sub-step; **strict JSON** and **type-strict comparison** back every manifest comparison; the
**transition graph's forward order** becomes the saga's step order; **path validation**
guards the journal-cache and burn-record file names. v2 adds nothing that invalidates them —
it replaces only `require_consistent` and the journal's *authority*.

## 4. The journal is a hint, provably (finding 10)

The journal records `{attempt-id, last-observed-step, receipts}` as a *cache*, and its
`tag` field **must match the version being cut** — a `v1.0.0` journal handed to a `v2.0.0`
cut is a confused-deputy wiring error (A3) that must fail closed, not silently skip steps.
Under v2 this is enforced structurally as well as by an explicit guard: the journal is
re-observed against intent bound to *this* version, so a wrong-version journal's receipts
cannot match the version's signed intent (→ CONFLICT). On any run: load the journal if
present, but **re-observe** every step's receipt from the remote and re-verify intent from
the signed tag before acting. Formal property to test:
*for every reachable state, the decision `require_resume/refuse/stop` is identical
whether the journal is present-and-correct, absent, stale, or adversarially rewritten.*
If any journal content can change a decision, the design has failed and the test
catches it. This is the executable form of "at most a progress hint."

## 5. Locking and fencing (finding 5)

**Local (single host).** A persistent lockfile with an advisory `flock` on the open
descriptor. Ownership is the held FD, never a pathname token. "Clear a stale lock"
means *acquire* it (the previous holder's FD is gone, so `flock` succeeds); it never
means `unlink`. The inode is never removed while a cut may hold it — removing it is
what lets two holders lock two different inodes under one name.

**Cross-host / cross-clone.** A local `flock` is silent about a cutter in another clone
or on another machine. The **global fence is the signed-tag push itself**: pushing
`refs/tags/vX.Y.Z` to a repo with tag-immutability (operator D9 ruleset) is the atomic
compare-and-set — it succeeds for exactly one cutter; a second observes the tag PRESENT
and either resolves to `completed-by-another-attempt` (STOP) or routes to recover. No
GitHub-native CAS on *releases* exists, so all global serialization is anchored to the
tag ref being the one atomic, immutable fence. **Open question Q2:** whether tag
immutability is enforceable on this free-tier repo, and the fallback if not.

## 6. Recovery protocol (finding 6)

`--recover` is a separate, authenticated decision — never a fall-through, never the
journal-absent default silently adopting remote state.

1. Fetch and verify the signed tag: signature valid, signer in policy, bound repo +
   commit match. Fail → refuse.
2. Reconstruct intent **from the verified tag only** (not the journal, not caller
   input — closes the signing-oracle/confused-deputy adoption path).
3. Observe every step's receipt four-valued under one epoch.
4. Resume **only** if every completed step is `completed-by-this-attempt` (attempt-id in
   the tag-bound intent) and every not-yet step is authoritative-ABSENT. Any UNKNOWN,
   CONFLICT, or `completed-by-another-attempt` → refuse with the specific discrepancy.
5. Recovery never *mutates* to reconcile; it only decides resume/refuse.

## 7. Attacker model, closed further (finding 8)

- **A1 local-state** (edit journal/lock files) — defeated by "journal is a hint" (§4)
  and FD-lock ownership (§5).
- **A2 repo-writer** (no branch protection; create/delete/recreate remote objects) —
  defeated by intent binding + attempt-bound receipts + CONFLICT-stops.
- **A3 confused-deputy caller** — defeated by deriving intent/evidence from git objects
  and the schema, never from caller-supplied data.
- **A1 ∧ A2 composition** — capabilities compose; every guard must hold assuming both.
- **A4 concurrent honest cutter** — the tag-push fence (§5) serializes; the loser stops.
- **A5 signature replay from another repo/release context** — intent binds
  repository + version + release_commit, so a valid signature over a different context
  is CONFLICT.
- **A6 trust-anchor / git-config substitution** — signer policy is pinned out of band,
  not read from the artifact under verification.
- **A7 signing oracle** (cannot extract the key, but steers the cutter into signing
  attacker-chosen intent) — the cutter constructs intent from verified repo/commit/
  schema inputs and shows the operator the exact intent before signing; it never signs
  caller-opaque bytes. **Open question Q3:** the human-confirmation surface for what is
  being signed.

## 8. Artifact identity — rebuilt against the real contract (premise-error fix)

`REQUIRED_ARTIFACT_FIELDS` was invented. The source of truth is
`plugins/agent-collab/runtime-manifest.schema.json` (13 required fields incl. a
`signing` sub-object) and the incumbent validator in `build_plugin_archive.py`. v2:
validate the artifact **against the schema file**, reuse the incumbent validator rather
than parallel it, and derive at least one test fixture from a schema-valid example so a
premise error fails a test instead of passing every test.
([[validator.built.from.prose.not.from.existing.contract]])

## 9. Verification obligations (finding 11, corrected)

- **Schema-level completeness**: every saga step has all eight parts filled; a blank is
  a visible gap.
- **Per-rule mutation detection** (not "exactly one failing subtest" — that is brittle):
  deleting any single rule fails *at least one* targeted test, and no rule is
  covered only by a test that also covers another.
- **Property tests over the observation space**: for each step, over
  PRESENT/ABSENT/UNKNOWN/CONFLICT × attempt-id-match, assert the resolved status.
- **The journal-irrelevance property** (§4): decisions invariant to journal
  content.
- **Scheduled concurrency / fault traces**: two-cutter interleavings and injected
  transport faults (timeout/429/partial-page) assert UNKNOWN-stops rather than adopt.

## 10. Scope — the whole pipeline, and what carries over

v2 owns the entire cut: intent + observation + the forward saga (§3) + the compensations
rollback and burn (§3b) + orchestration and the CLI seam (§3c). That is the four PR-4
split pieces unified. Carried over **unchanged** from PR #27 as saga primitives (§3d): the
tag grammar, the release-commit topology gate, strict JSON, type-strict comparison, and the
transition graph's forward order. What v2 **replaces**: `require_consistent`, the journal's
authority, the invented artifact contract, and the piecemeal burn/dispatch/CLI designs that
the earlier split treated as independent.

**Sequencing.** The design converges first (this doc → adversarial review → converge). Then
implementation is delegated worker-tier (directive #8) and lands incrementally — plausibly
still as separably-reviewable PRs, but each built against *this* converged whole-pipeline
spec rather than designed in isolation, which is the mistake that produced the v1 matrix and
the piece-by-piece findings.

## Open questions for the adversarial review to resolve

- **Q1** — Does intent live *in* the signed tag message (extending
  `agent-collab-release/1`) or in a separate signed blob referenced by digest from the
  tag? Trade-off: message size / grammar complexity vs an extra signed object.
- **Q2** — Is tag-ref immutability enforceable on this free-tier repo (operator D9)? If
  not, the global fence weakens and needs a fallback (e.g. first-writer receipt in an
  append-only location).
- **Q3** — The human-confirmation surface for signing intent (A7): what exactly is
  shown, and is it mandatory in CI-less local cuts.
- **Q4** — Attempt-id binding for effects whose GitHub API has no free-form input to
  carry it (does asset upload let us bind attempt-id, or only infer via draft body?).
- **Q5** — Epoch coherence: how is "these observations share an epoch" established
  against an API with no global snapshot? (ETags? sequential-read ordering assumptions?)
- **Q6** — Burn-set deletion (§3b): signing proves a *present* burn authentic but does not
  make a burn's *absence* trustworthy on an unprotected `main`. Does the revocation set need
  an append-only / chained-signature structure so deletion is detectable, or is that out of
  scope for v2?
- **Q7** — Incremental delivery: given pipeline scope, what is the right PR decomposition of
  the *implementation* so each PR is separately reviewable yet built against this one
  converged spec — and does any piece have a hard ordering dependency (e.g. intent carrier
  before any receipt logic)?

---

## Adversarial design review round 2 — VERDICT: RECONSIDER (HIGH), 13 blocking

Full text: `reviews/pipeline-v2-adversarial-review-2.md`. Reviewer: Codex (distinct family;
Grok's managed route failed closed on two attempts). The findings are correct and converge
on one root, which is an **operator decision**, not a design defect I can iterate away.

### The root finding — authority relocated, not established

v2 correctly removed authority from the tamperable local journal (finding 10, round 1). But
it then made **remote receipts** (releases, assets, bodies, workflow inputs) the authority —
and on this repo those are **equally attacker-writable** by an A2 repo-writer. So v2 moved
the mutable authority from one attacker-writable place to another without adding
authenticity or monotonicity (review findings 10, 11). Concretely, the review showed:

- **Four-valued observation is not enough for a history (2).** ABSENT is transient: observe
  ABSENT → A2 creates the object → cutter issues create. Every read was authoritative, yet
  the sequence was not linearizable. GitHub has no server-side CAS/idempotency and no global
  snapshot, so "epoch" has no implementable definition and ABA is undetectable.
- **The tag-push is not a global fence (5).** Two cutters pushing the *identical* tag object
  both succeed (`git push` reports "up to date", not a losing CAS).
- **The immutability premise is unavailable (6, 12).** On GitHub **Free private** repos,
  branch/tag rulesets require Pro/Team/Enterprise, and immutable releases are Enterprise
  Cloud. §5's fence and Q6's revocation cannot be enforced on this tier at all.
- **Signer policy in the release-commit tree is not out of band (8).** An A2 who can write
  the tree can commit a policy naming its own key.
- **Compensation ordering can destroy the recovery root (7).** Rollback may delete the
  signed tag before burn is durable; a crash there leaves the version unburned with no
  recovery anchor.

### Why this is not a v3-design problem — it is V0, already decided

The parent design's **V0 (operator decision (a))** already states this posture honestly:
repo writers can manage releases; the pipeline **does not** claim a tampered artifact cannot
be *published*; the claim is that a tampered artifact cannot be *accepted/installed by
conforming consumers* (fail-closed until `ATTESTED` + verify the CI receipt). Authority
isolation (a separate publication repo) is recorded there as **"the available upgrade, not
implemented."**

My v2 drifted past that approved baseline: it tried to make the *producer pipeline* prevent
A2, which V0 had already declared out of scope and which the review proves infeasible on the
current infrastructure. Most of the 13 findings are attacks on a prevention guarantee the
design should never have claimed.

### The fork — an operator cost-tier decision

The design genuinely forks on a decision only the operator can make (cost-tier — an
operator-required class), so implementation is blocked on it:

- **Fork A — stay free-tier, align to V0.** Re-scope v2 so the producer defends **A1**
  (local tampering), **A3** (confused-deputy/wiring), accidental corruption, and
  crash-resume correctness; **detects** but does not claim to prevent A2; revocation is
  best-effort → consumer rejection → higher patch (not a hard guarantee). Prevention is
  consumer-side (PR-6, fail-closed). Honest, achievable now, salvages the directionally-
  correct v2 work (finding 14: journal-irrelevance, FD-locking, four-valued observation,
  schema reuse, explicit recovery, mutation tests all stay).
- **Fork B — invest in authority isolation / paid tier.** A separate publication repo with
  protected refs + immutable releases (Enterprise) or Pro/Team rulesets, so the pipeline can
  actually make an A2-resistance claim and enforce hard revocation. Materially different,
  stronger, requires operator spend + infra setup.

The directionally-correct v2 mechanisms are retained under **either** fork; the fork decides
only what the pipeline is allowed to *claim* and what infrastructure backs it.

---

## PREMISE CORRECTION — the repo is PUBLIC with `main` already protected (verified)

The round-2 review and my fork analysis both rested on "GitHub Free **private** repo," which
is **false**. Verified against `sumitake/agent-collab`:

- **Visibility: PUBLIC.** Repository rulesets and branch protection are therefore free and
  available — the operator additionally subscribes to GitHub Pro, but public-repo rulesets
  are the actual enabler and need no paid tier.
- **`main` already carries an active ruleset**: `deletion` blocked, `non_fast_forward`
  blocked, `required_linear_history`, **`required_signatures`**, `pull_request`,
  `required_status_checks`, 1 bypass actor. So a revocation/burn record committed to `main`
  is **already** protected against A2 deletion or history rewrite, and commits to `main`
  must be signed and PR-reviewed.
- **No tag ruleset yet.** Tags can currently be force-updated/deleted by a writer. Adding a
  `v*` tag ruleset (block update + deletion) is a **free config change**, not a spend, and
  makes the signed tag a real immutable fence (§5).
- **A2 surface = 1 collaborator** (public repos still restrict *write* to collaborators),
  not the anonymous public.

**Consequences for the review's 13 findings.** The infrastructure-infeasibility findings
(6, 12) and much of 5 and 8 were arguing against a tier this repo is not on:

- **5 / 6 (tag fence, immutability)** — achievable now via a free `v*` tag ruleset on a
  public repo. Not a fork, a config add (this is the parent design's D9).
- **8 (signer policy not out of band)** — a signer policy committed to the *already-protected*
  `main` (deletion-blocked, non-fast-forward-blocked, signature-required, PR-gated) is
  tamper-resistant against A2. Effectively out of band.
- **12 (burn deletion)** — the burn set on protected `main` cannot be deleted or reset by
  A2 today. Revocation is achievable, not infeasible.

**The honest residual** — what stays consumer-side per V0 and is NOT closed by rulesets:
the **draft release + assets between CI-verify and CI-publish**. GitHub *immutable releases*
as a distinct feature is Enterprise-Cloud; on this tier a writer can still mutate a draft in
that window. This is exactly V0's already-approved concession: prevention there is
consumer-side (fail closed until `ATTESTED` + verify the receipt), not producer-side.

**So there is no A/B fork.** The strong posture — A2-resistance for the tag and revocation
layers — is available now with a free tag-ruleset config; the one genuinely Enterprise-gated
gap (immutable draft *releases*) is the pre-existing, operator-approved consumer-side window.
v3 targets the strong posture. The remaining review findings that are NOT premise-dependent
(2 observation-history/ABA, 4 attempt-id authorship, 7 compensation-ordering, 10/11
receipt-authenticity) are real and must still be resolved in v3 on their merits.

**Operator action (not agent-performed — repo security config):** add a `v*` tag ruleset
(block deletion + update) so the signed-tag fence is enforced. This is a repo-settings /
security change, operator domain.

---

## Durability work-items for the journal-as-hint (carry into v3 impl)

The journal survives v3 as a resume *hint* (§4), so its durable-write primitive
(`_atomic_write`) carries over and must be correct. Two confirmed bugs, grouped here so
they land together with a proper crash-residue / fault-injection test harness (review
finding 14) rather than as isolated patches to a module under redesign:

- **F2 — directory-create not persisted.** `_atomic_write` `mkdir`s the journal root then
  fsyncs only the new directory, not the parent whose entry changed; power loss can remove
  the directory after `save()` returned. Fix: fsync the parent when the directory is created.
- **F4 — PID-named temp collides with crash residue.** `temp = .{name}.tmp.{pid}`. A crash
  after `O_CREAT|O_EXCL` but before `os.replace` leaves the temp; a reused PID (especially
  after reboot) then fails `O_EXCL` before recording write-ahead state, blocking resume until
  the stale file is removed by hand. Fix: a collision-resistant temp name (`mkstemp`), so
  crash residue can never collide with a future writer. (Verified against `406639f`.)

Both are mechanical, both have known fixes, and both need the same crash/fault-injection
tests, so they belong to the v3 durability component, not to five more commits on the frozen
module.

---

## Infrastructure now ENFORCED — tag immutability live (D9 done)

The `v*` tag-immutability ruleset is created and active on `sumitake/agent-collab`
(ruleset id 19198252, verified):

- **target: tag**, condition `refs/tags/v*`, enforcement **active**.
- rules: **`deletion`** blocked, **`non_fast_forward`** blocked → a pushed `v*` tag cannot be
  overwritten or deleted. Creation is *not* blocked, so `git tag -s vX.Y.Z && git push` still
  works — the release path is unaffected.
- bypass: admin role (`actor_id 5`, `always`) — an operator escape hatch for emergencies; a
  **write-scoped token cannot bypass**, so the realistic A2 (a leaked CI/bot token) cannot
  rewrite or delete a release tag.

So §5's "signed-tag global fence" is no longer aspirational: a pushed signed tag is an
**immutable anchor** against the realistic A2. Combined with the already-live `main`
protection (the burn set cannot be deleted/reset by a write token), the two rulesets give the
strong posture the round-2 review wrongly assumed was infeasible.

### Design refinement forced by tag immutability — resolves finding 7

Round-2 finding 7 was: *rollback deletes the signed tag before burn is durable → a crash
destroys the recovery root while the version is unburned.* Under an immutable tag this
**cannot happen**: rollback can no longer delete the tag (a write token is blocked; only an
admin bypass could, and admin-compromise is out of scope per V0). So the saga's rollback
compensation is refined:

- Rollback deletes the **draft release and asset(s)** (both require authoritative-ABSENT
  afterward), then **burns the version** on the protected `main`. It **never deletes the
  tag** — the immutable signed tag remains as a permanent **tombstone**.
- The recovery root (signed tag) is therefore indestructible by the realistic attacker, and a
  crash mid-rollback leaves the tag intact + the burn either durable-on-`main` or re-driven on
  resume. Finding 7's ordering hazard is structurally removed, not merely ordered around.

This is a case where getting the *verified* infrastructure into the design improved it: the
fence the review said we couldn't have turns out to also close a logic finding.

---

## Adversarial design review round 3 — RECONSIDER (HIGH), 5 blocking + 3 non-blocking

Full text: `reviews/pipeline-v3-adversarial-review-3.md`. Reviewer: Codex against the VERIFIED,
ENFORCED infrastructure (Grok's managed route failed closed a third time). This is
**convergence**: round 2's 13 architectural blockers became 5 constructive ones, and the
former infrastructure-infeasibility findings dropped to non-blocking. Each remaining finding
names a specific mechanism, and the two largest point at real GitHub primitives. Resolutions,
all folded into the design:

**R3-1 (ABA on drafts/assets) — idempotent create, drop "epoch".** Tag + `main` immutability
make those two anchors monotonic, but GitHub gives no global snapshot or CAS for
releases/assets, so `ABSENT` justifies at most ONE non-destructive create — it cannot prove
historical "not-started". §2/§3 change from *observe-ABSENT-then-create* to **attempt the
create and handle the response**: `201` → capture server ids; `422` (GitHub's same-name asset
collision) → re-enumerate and validate the existing object's FULL identity against intent
(adopt if equal, STOP if it conflicts). The unimplementable "shared epoch" abstraction is
**removed** (it was never backed by an API primitive). The tag still fences competing intents;
concurrent same-intent recovery is handled by idempotent-create + identity validation.

**R3-2 (attempt-id = correlation, not authorship) — safe-equivalence, not an execution
lease.** This is a conceptual correction that *simplifies* the design. The signed tag is a
valid authorization ROOT but not an execution lease; a public attempt-id is copyable by A2, so
`completed-by-this-attempt` was unjustifiable. Replace it with **`completed-equivalently-to-
intent`**: a step is done iff the landed remote state matches the SIGNED INTENT (repo id,
commit, digests, names, sizes) — regardless of which executor produced it. Safe because the
signed intent fully determines the correct state; if the remote equals intent, it is correct
no matter who wrote it. The whole `*-by-this-attempt` / `-by-another-attempt` distinction is
dropped.

**R3-3 (receipt authenticity) — GitHub artifact attestations.** "Run id + matching public
input" is not an authenticated receipt. `ATTESTED` now means a **cryptographically verified
GitHub artifact attestation** binding {repository id, tag-object OID, peeled commit,
intent digest, release id, full asset identity, workflow identity+commit, run id, verification
result, publication state}. Public-repo attestations are written to an **immutable
transparency log**; PR-6 consumers verify the attestation and pin the signer workflow. This is
the authenticated, monotonic receipt the design needed and could not get from mutable release
metadata.

**R3-4 (rollback direction-loss window) — write-ahead the rollback DECISION.** My tag-tombstone
fix preserved the recovery ROOT but not the rollback DECISION: rollback deletes assets+draft,
crashes before the burn, and recovery then sees an intact tag + no burn + absent forward
effects → and could wrongly RESUME FORWARD, recreating the draft. Fix: commit a **signed
`rollback-started` record to protected `main` BEFORE the first destructive compensation**. Once
durable, cleanup is safely re-drivable and recovery reads the decision. Tombstone (root) +
rollback-started (decision) together close finding 7 completely.

**R3-6 (admin bypass must not be the cutter's identity) — BLOCKING, and it implicates the
ruleset I just created.** The `v*` ruleset gives `actor_id 5` (admin) an `always` bypass as an
operator escape hatch. But `cut_release.py` is described as a local operator tool run with the
operator's own (admin) credentials — which means the **automated cutter would itself bypass the
fence**, so a cutter bug or a stolen release credential could overwrite/delete protected refs.
Fix: the cutter MUST authenticate as a **non-bypass release principal**, and **preflight fails
closed if the authenticated actor has bypass authority** over the tag/main rulesets. The admin
`always` bypass stays for MANUAL operator emergencies only. **This likely requires the operator
to provision a dedicated non-admin release identity/token** — flagged as an operator decision
below.

**R3-7 (non-blocking) — ruleset operational preflight.** Before every cut, verify ruleset
`19198252` is active, targets tags, covers the canonical tag, blocks deletion + non_fast_forward,
and has no unexpected bypass principal. Constrain versions to the canonical `v\d+\.\d+\.\d+`
(already enforced by `validate_tag_name`) so a `V…` or slash-containing ref cannot escape
`refs/tags/v*` (ruleset glob `*` does not cross `/`) — defense in depth with the grammar.

**R3-5, R3-8 (non-blocking, confirmed sound).** Burn records on protected `main` are sound
against the stated A2 given a domain-separated signature under the pinned revocation policy +
reachability from freshly-fetched protected `origin/main` (not GitHub's generic "verified
commit" status). The CI-verify→publish window is acceptable under V0 provided consumers hash the
bytes they downloaded, match the signed digest+name, and verify the CI **attestation** (not
`gh release verify`, which is for Enterprise immutable releases).

### New operator decision surfaced (R3-6)

The automated cutter needs a **non-admin, non-bypass release identity** so it is itself subject
to the tag/main rulesets. Options: (a) a dedicated fine-grained PAT / GitHub App with write (not
admin) scope for the release job; (b) scope the ruleset bypass to a specific operator identity
used only for manual emergencies, never by the cutter. Either is an operator/infra provisioning
choice; the design's preflight enforces "authenticated actor must not have bypass" regardless.
