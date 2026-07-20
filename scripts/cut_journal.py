#!/usr/bin/env python3
"""Durable, lockable, write-ahead cut journal for the release cutter.

Design of record: `docs/design/pr4-cut-release-activation-design.md` V1/V2
(converged through a 2-round distinct-family adversarial design review).

Why this exists
---------------
A release cut performs several REMOTE side effects (push a signed tag, create a
draft release, upload an asset, dispatch CI). A crash between a remote side
effect and the local record of it would otherwise leave the cut unresumable —
the tool would either redo a side effect or report a false state. So every
remote effect is preceded by a **write-ahead (PENDING) record**, and every
resume reconciles the journal against REMOTE truth.

Two invariants carry the security weight:

1. **The signed tag wins.** The journal is operator-local and therefore
   tamperable. It is never authoritative: on any journal/remote/tag conflict
   the signed tag's `Asset-SHA256`/`Manifest-SHA256` are the anchor and the run
   STOPS. A tampered journal can never authorize a rollback or a "proceed".
2. **Inconsistency stops.** A mismatch is never silently repaired and never
   reported as "already released"; it is surfaced with the exact discrepancy.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "agent-collab-cut-journal/1"

def validate_tag_name(tag: str) -> str:
    """Reject anything that is not exactly `vMAJOR.MINOR.PATCH`, before path use.

    Delegates to the tag contract's validator ON PURPOSE. A second copy of the
    regex here drifted from it immediately and in both directions: the contract
    accepted `v01.0.0` while this rejected it, and this accepted `v1.0.0\\n`
    (because `$` matches before a trailing newline) while the contract rejected
    it — so the path-safety check admitted a newline into a filename, which is
    the exact hole it was added to close. Two validators for one concept is a
    drift bug waiting to happen; there is now one.
    """
    try:
        return _tag_contract().validate_tag_name(tag)
    except Exception as exc:                    # contract's error type, re-raised as ours
        raise JournalError(
            f"refusing to derive a journal path from an unsafe tag name: {tag!r} ({exc})"
        ) from exc


def _tag_contract():
    """Load the sibling tag contract by path (both ship together in scripts/)."""
    global _TAG_CONTRACT
    if _TAG_CONTRACT is None:
        spec = importlib.util.spec_from_file_location(
            "_release_tag_contract", Path(__file__).resolve().parent / "release_tag_contract.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _TAG_CONTRACT = module
    return _TAG_CONTRACT


_TAG_CONTRACT = None

# Ordered states. `*_PENDING` are WRITE-AHEAD records: persisted BEFORE the
# corresponding remote side effect so a crash mid-effect is always recoverable.
STATES = (
    "PREPARED",
    "TAG_PUSH_PENDING",
    "TAGGED",
    "DRAFT_CREATE_PENDING",
    "DRAFT_CREATED",
    "ASSET_UPLOAD_PENDING",
    "DRAFT_UPLOADED",
    "DISPATCH_PENDING",
    "DISPATCHED",
)
# Terminal states are written by CI (PR-5), not by the local cutter.
CI_STATES = ("DRAFT_VERIFIED", "PUBLISHED", "ATTESTED")
# Terminal local outcome: the draft was rolled back and the version burned.
TERMINAL_STATES = ("ROLLED_BACK",)
_PENDING = {s for s in STATES if s.endswith("_PENDING")}


class JournalError(RuntimeError):
    """A journal inconsistency. Always fatal — never repaired in place."""


def journal_root(repo_root: Path) -> Path:
    """Journal home, resolved via git-common-dir.

    NEVER a literal ``.git/``: in a linked worktree ``.git`` is a FILE, so a
    hardcoded path silently writes the wrong place (or fails). ``--git-common-dir``
    resolves to the shared object store for both normal and linked worktrees.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, check=True,
    )
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = (repo_root / common).resolve()
    return common / "agent-collab-cut-journal"


def _fsync_dir(path: Path) -> None:
    """fsync the DIRECTORY so the rename itself is durable across a crash.

    Without this the write-ahead record can be lost by a power failure even
    though the file content was fsynced — which defeats the entire point of
    persisting intent before a remote side effect.
    """
    # Opening a directory can itself fail (Windows, some restricted or networked
    # filesystems). That must NOT silently return: a caller that cannot fsync the
    # directory has not achieved the durability this module's write-ahead
    # guarantee is built on. It is surfaced as our own typed error rather than a
    # raw OSError so callers see one failure mode, not two.
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as exc:
        raise JournalError(
            f"could not open the journal directory {path} to fsync it "
            f"({exc.strerror}); the write-ahead record may not survive a crash"
        ) from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        # Swallowing this silently would let the module keep claiming durability
        # it did not achieve — the write-ahead record is the only thing standing
        # between a crash and an unrecoverable cut, so a failure to make it
        # durable must be loud.
        raise JournalError(
            f"could not fsync the journal directory {path} ({exc.strerror}); "
            "the write-ahead record may not survive a crash"
        ) from exc
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.tmp.{os.getpid()}"
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _read_nofollow(path: Path, *, limit: int = 1024 * 1024) -> bytes | None:
    """Read a journal file, distinguishing ABSENT (None) from UNREADABLE (raise).

    Collapsing "symlinked / permission-denied / oversized" into "absent" would
    let a tampered or unreadable journal be silently treated as a fresh cut,
    which is exactly the state that must stop instead.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise JournalError(
            f"cut journal at {path} exists but is unreadable ({exc.strerror}); "
            "refusing to treat it as absent"
        ) from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise JournalError(f"cut journal at {path} is not a regular file")
        if info.st_size > limit:
            raise JournalError(f"cut journal at {path} is implausibly large")
        return os.read(descriptor, limit)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


@dataclass
class CutJournal:
    """One release cut's durable record. Local-only; never authoritative."""

    tag: str
    root: Path
    state: str = "PREPARED"
    data: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # The tag is interpolated into filesystem paths below. Validate it HERE,
        # at construction, rather than trusting the caller: an unvalidated tag
        # such as "../../../escaped" walks straight out of the journal root, and
        # the validator living in the sibling module is no protection if nothing
        # calls it. Fail closed before any path is derived.
        validate_tag_name(self.tag)

    @property
    def path(self) -> Path:
        return self.root / f"{self.tag}.json"

    @property
    def lock_path(self) -> Path:
        return self.root / f"{self.tag}.lock"

    # ---------------- persistence ----------------

    @classmethod
    def load(cls, repo_root: Path, tag: str) -> "CutJournal | None":
        # FIRST line, before any path is derived. __post_init__ guards the
        # constructor, but load() builds `root / f"{tag}.json"` itself and returns
        # None for an absent file — so a traversal attempt read out of root and
        # reported "no journal" instead of firing the guard.
        validate_tag_name(tag)
        root = journal_root(repo_root)
        raw = _read_nofollow(root / f"{tag}.json")
        if raw is None:
            return None
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise JournalError(f"cut journal for {tag} is unreadable") from exc
        if not isinstance(document, dict) or document.get("schema") != SCHEMA:
            raise JournalError(f"cut journal for {tag} has an unknown schema")
        state = document.get("state")
        if state not in STATES and state not in CI_STATES and state not in TERMINAL_STATES:
            raise JournalError(f"cut journal for {tag} has an unknown state: {state!r}")
        if document.get("tag") != tag:
            raise JournalError("cut journal tag mismatch")
        return cls(tag=tag, root=root, state=state, data=document)

    def save(self) -> None:
        document = dict(self.data)
        document.update({"schema": SCHEMA, "tag": self.tag, "state": self.state,
                         "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        self.data = document
        _atomic_write(self.path, json.dumps(document, indent=2, sort_keys=True).encode("utf-8"))

    def advance(self, state: str, **fields) -> None:
        """Record a state transition, enforcing the transition GRAPH.

        Accepting any known state name is not a state machine: it permitted
        skipping a write-ahead PENDING record (the one thing that makes a crash
        recoverable), moving backwards to re-open a settled state, and writing
        CI-authored states locally — so a local process could claim PUBLISHED.
        Transitions are therefore checked, and the local cutter cannot mint
        CI-only states at all.
        """
        if state not in STATES and state not in CI_STATES and state not in TERMINAL_STATES:
            raise JournalError(f"refusing to record an unknown state: {state!r}")
        if state in CI_STATES:
            raise JournalError(
                f"{state!r} is written by CI, not by the local cutter; refusing to "
                "forge a CI-authored state locally"
            )
        if self.state in TERMINAL_STATES:
            raise JournalError(
                f"cut for {self.tag} is terminal ({self.state}); refusing to reopen it"
            )
        if state in TERMINAL_STATES:
            # A terminal target is NOT exempt from the graph. Nesting every check
            # under `state in STATES` left ROLLED_BACK reachable from anywhere —
            # including PREPARED (nothing to roll back) and PUBLISHED (a released
            # version cannot be locally un-released). Adding the graph is what
            # created this hole, so the terminal target gets its own rule.
            if self.state in CI_STATES:
                raise JournalError(
                    f"refusing to mark {self.state} (CI-advanced) as {state}; a published "
                    "release cannot be rolled back by the local cutter"
                )
            if self.state not in STATES or STATES.index(self.state) < STATES.index("TAGGED"):
                raise JournalError(
                    f"refusing to roll back from {self.state}: nothing was pushed yet, so "
                    "there is no remote effect to undo"
                )
        if state in STATES:
            if self.state in CI_STATES:
                raise JournalError(
                    f"refusing to move a CI-advanced cut ({self.state}) back to {state!r}"
                )
            current = STATES.index(self.state) if self.state in STATES else -1
            target = STATES.index(state)
            if target < current:
                raise JournalError(
                    f"refusing to move the journal backwards: {self.state} -> {state}"
                )
            if target > current + 1:
                skipped = ", ".join(STATES[current + 1:target])
                raise JournalError(
                    f"refusing to skip {skipped} on the way to {state} — a skipped "
                    "write-ahead record is exactly what makes a crash unrecoverable"
                )
        self.state = state
        self.data.update(fields)
        self.save()

    def note_pending(self, state: str, **fields) -> None:
        """Write-ahead: persist intent BEFORE performing the remote side effect."""
        if state not in _PENDING:
            raise JournalError(f"{state!r} is not a write-ahead state")
        self.advance(state, **fields)

    # ---------------- locking ----------------

    def acquire_lock(self) -> None:
        """Exclusive per-tag lock. A stale lock is reported, never auto-stolen."""
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            holder = (_read_nofollow(self.lock_path) or b"?").decode("utf-8", "replace").strip()
            raise JournalError(
                f"another cut is in progress for {self.tag} (lock held by: {holder}). "
                f"If that process is gone, remove {self.lock_path} deliberately."
            ) from None
        self._lock_token = f"pid={os.getpid()} at={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
        with os.fdopen(descriptor, "w") as handle:
            handle.write(self._lock_token + "\n")

    def release_lock(self) -> None:
        """Release only a lock THIS instance holds.

        An unconditional unlink deletes whichever lock happens to be there —
        including one a different process acquired after ours was cleaned up,
        which silently hands two cutters concurrent access to the same tag. The
        token check makes release a no-op unless we are the holder.
        """
        token = getattr(self, "_lock_token", None)
        if token is None:
            return                      # we never acquired it; nothing to release
        try:
            held = (_read_nofollow(self.lock_path) or b"").decode("utf-8", "replace").strip()
        except JournalError:
            return                      # unreadable: leave it alone, never force
        if held != token:
            return                      # someone else's lock — not ours to remove
        try:
            os.unlink(self.lock_path)
        except OSError:
            pass
        self._lock_token = None


def require_consistent(journal: "CutJournal | None", *, tag: str, remote: dict,
                       tag_fields: dict | None) -> None:
    """Reconcile journal ↔ remote ↔ signed tag. STOP on any divergence.

    Truth precedence (V2): the **signed tag** is the anchor for the asset and
    manifest digests; remote API state is the anchor for object identity; the
    journal is only a resumption hint. This function never mutates anything and
    never "repairs" — an inconsistent cut must be understood by a human.

    ABSENCE IS NOT AGREEMENT. Every comparison here used to require both sides to
    be truthy, so a call with no signed-tag fields and no remote evidence passed
    silently — the function whose whole purpose is to fail closed failed OPEN, and
    the "signed tag wins" invariant was documentation rather than enforcement.
    Required evidence is therefore **state-dependent**: once the journal says an
    effect landed, the evidence for that effect MUST be observable, and missing
    evidence is itself an inconsistency.
    """
    problems: list[str] = []

    # What must be observable, given how far the journal claims the cut got.
    # (journal state that implies it, evidence key, where the evidence lives)
    required: list[tuple[str, str, str]] = [
        ("TAGGED", "tag_object_id", "remote"),
        ("TAGGED", "asset_sha256", "tag"),
        ("TAGGED", "manifest_sha256", "tag"),
        ("DRAFT_CREATED", "release_id", "remote"),
        ("DRAFT_UPLOADED", "asset_sha256", "remote"),
    ]
    # journal is None ⇒ NO CUT HAS CLAIMED ANYTHING, so there is no claim whose
    # evidence could be missing and the required-evidence table does not apply.
    # (Absence-is-not-agreement governs evidence for a CLAIMED effect; it is not
    # a demand that every call carry evidence.) The digest and publication checks
    # below still run, so a remote that disagrees with the signed tag is caught
    # even with no journal at all.
    # A ROLLED_BACK cut deliberately DELETED its draft and asset, so demanding the
    # forward evidence would make every legitimate rollback unresumable. Adding the
    # required-evidence table is what broke this; terminal cuts get their own rule.
    if journal is not None and journal.state in TERMINAL_STATES:
        if remote.get("published"):
            raise JournalError(
                f"cut for {tag} is recorded {journal.state} but the remote release is "
                "PUBLISHED; a rolled-back version must never appear published"
            )
        return
    reached = (
        STATES.index(journal.state)
        if journal is not None and journal.state in STATES
        else (len(STATES) if journal is not None else -1)   # CI/terminal ⇒ past every local state
    )
    for at_state, key, where in required:
        if reached < STATES.index(at_state):
            continue
        present = (tag_fields or {}).get(key) if where == "tag" else remote.get(key)
        if not present:
            problems.append(
                f"{key}: journal claims the cut reached {journal.state}, but no {where} "
                f"evidence for it is observable — absent evidence is an inconsistency, "
                f"not agreement"
            )

    if tag_fields:
        for key in ("asset_sha256", "manifest_sha256"):
            signed = tag_fields.get(key)
            if journal is not None and signed and journal.data.get(key) not in (None, signed):
                problems.append(
                    f"{key}: signed tag says {signed}, journal says {journal.data.get(key)} "
                    f"(the signed tag wins — the journal is untrusted)"
                )
            observed = remote.get(key)
            if signed and observed and observed != signed:
                problems.append(f"{key}: signed tag says {signed}, remote asset is {observed}")

    if journal is not None:
        for key in ("tag_object_id", "release_id"):
            recorded, observed = journal.data.get(key), remote.get(key)
            if recorded and observed and recorded != observed:
                problems.append(f"{key}: journal has {recorded}, remote has {observed}")

    # Publication AFTER we dispatched is the normal, expected CI outcome: CI runs
    # on GitHub and cannot write to the operator's local journal, so a completed
    # cut legitimately rests at DISPATCHED forever. Only publication we never
    # dispatched for is anomalous — someone published outside the pipeline.
    if remote.get("published") and journal is not None and journal.state in STATES:
        if STATES.index(journal.state) < STATES.index("DISPATCHED"):
            problems.append(
                f"remote release is PUBLISHED but this cut never got past "
                f"{journal.state} — it was published outside the pipeline"
            )

    if problems:
        raise JournalError(
            f"cut state for {tag} is inconsistent; refusing to proceed:\n  - "
            + "\n  - ".join(problems)
        )
