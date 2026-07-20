"""Durable cut-journal contract: write-ahead, locking, and truth precedence."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cut_journal.py"


def _load():
    spec = importlib.util.spec_from_file_location("cut_journal", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CutJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cj = _load()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    # ---------- location ----------

    def test_journal_root_uses_git_common_dir_not_literal_dot_git(self) -> None:
        # A linked worktree has a `.git` FILE, so a hardcoded ".git/" path is wrong.
        # Resolving via --git-common-dir must work for BOTH layouts and must point
        # at the shared object store.
        root = self.cj.journal_root(self.repo)
        self.assertTrue(root.is_absolute())
        self.assertEqual(root.name, "agent-collab-cut-journal")
        self.assertEqual(root.parent.name, ".git")

        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "--allow-empty",
                        "-m", "base"], check=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        linked = Path(self.temp.name) / "linked"
        subprocess.run(["git", "-C", str(self.repo), "worktree", "add", "-q",
                        str(linked)], check=True)
        self.assertTrue((linked / ".git").is_file(), "linked worktree should have a .git FILE")
        # Same shared journal root from the linked worktree — the whole point.
        self.assertEqual(self.cj.journal_root(linked), root)

    # ---------- persistence ----------

    def test_save_is_atomic_owner_only_and_roundtrips(self) -> None:
        j = self.cj.CutJournal(tag="v9.9.9", root=self.cj.journal_root(self.repo))
        j.advance("PREPARED", asset_sha256="a" * 64)
        self.assertEqual(stat.S_IMODE(j.path.stat().st_mode), 0o600)
        self.assertFalse([p for p in j.path.parent.iterdir() if ".tmp." in p.name])

        loaded = self.cj.CutJournal.load(self.repo, "v9.9.9")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.state, "PREPARED")
        self.assertEqual(loaded.data["asset_sha256"], "a" * 64)

    def test_unknown_schema_state_or_tag_is_fatal(self) -> None:
        root = self.cj.journal_root(self.repo)
        root.mkdir(parents=True, exist_ok=True)
        for payload, why in (
            ({"schema": "other/1", "tag": "v1.0.0", "state": "PREPARED"}, "schema"),
            ({"schema": self.cj.SCHEMA, "tag": "v1.0.0", "state": "NOPE"}, "state"),
            ({"schema": self.cj.SCHEMA, "tag": "vOTHER", "state": "PREPARED"}, "tag"),
        ):
            (root / "v1.0.0.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.subTest(why=why), self.assertRaises(self.cj.JournalError):
                self.cj.CutJournal.load(self.repo, "v1.0.0")

    def test_advance_refuses_unknown_state(self) -> None:
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        with self.assertRaises(self.cj.JournalError):
            j.advance("TOTALLY_MADE_UP")

    # ---------- write-ahead ----------

    def test_write_ahead_survives_a_crash_between_effect_and_record(self) -> None:
        # The whole point: persist INTENT before the remote side effect, so a
        # crash right after the effect still leaves a resumable PENDING record.
        j = self.cj.CutJournal(tag="v1.2.3", root=self.cj.journal_root(self.repo))
        j.note_pending("TAG_PUSH_PENDING", tag_object_id=None)
        # ... simulated crash here (the push happened; nothing else was written) ...
        resumed = self.cj.CutJournal.load(self.repo, "v1.2.3")
        self.assertEqual(resumed.state, "TAG_PUSH_PENDING",
                         "a crash after the remote effect must leave a resumable PENDING state")

    def test_note_pending_rejects_a_non_pending_state(self) -> None:
        j = self.cj.CutJournal(tag="v1.2.3", root=self.cj.journal_root(self.repo))
        with self.assertRaises(self.cj.JournalError):
            j.note_pending("TAGGED")

    # ---------- locking ----------

    def test_lock_is_exclusive_and_never_auto_stolen(self) -> None:
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        j.acquire_lock()
        other = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        with self.assertRaisesRegex(self.cj.JournalError, "another cut is in progress"):
            other.acquire_lock()
        j.release_lock()
        other.acquire_lock()  # released → acquirable
        other.release_lock()

    # ---------- truth precedence (the security-carrying part) ----------

    def _walk_to(self, journal, target: str, **fields) -> None:
        """Advance through every intermediate state, as the graph now requires."""
        for state in self.cj.STATES[self.cj.STATES.index(journal.state) + 1:]:
            journal.advance(state, **(fields if state == target else {}))
            if state == target:
                return

    def test_signed_tag_wins_over_a_tampered_journal(self) -> None:
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        self._walk_to(j, "DRAFT_UPLOADED", asset_sha256="b" * 64)  # journal (tamperable)
        with self.assertRaisesRegex(self.cj.JournalError, "the signed tag wins"):
            self.cj.require_consistent(
                j, tag="v1.0.0",
                remote={"tag_object_id": "abc", "release_id": "111",
                        "asset_sha256": "a" * 64},
                tag_fields={"asset_sha256": "a" * 64,
                            "manifest_sha256": "f" * 64},      # signed tag = anchor
            )

    def test_absent_evidence_is_an_inconsistency_not_agreement(self) -> None:
        """The fail-CLOSED property, pinned.

        Every comparison in require_consistent used to require both sides to be
        truthy, so a call carrying no signed-tag fields and no remote evidence
        passed silently — the function whose entire purpose is to stop on
        divergence failed OPEN, and "the signed tag wins" was a comment rather
        than a control. Once the journal claims an effect landed, the evidence
        for it must be observable.
        """
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        self._walk_to(j, "TAGGED")
        with self.assertRaisesRegex(self.cj.JournalError, "absent evidence"):
            self.cj.require_consistent(j, tag="v1.0.0", remote={}, tag_fields=None)
        # ... and a cut that has not claimed anything yet is legitimately quiet.
        fresh = self.cj.CutJournal(tag="v1.0.1", root=self.cj.journal_root(self.repo))
        self.cj.require_consistent(fresh, tag="v1.0.1", remote={}, tag_fields=None)

    def test_journal_path_cannot_escape_the_journal_root(self) -> None:
        # The tag is interpolated into a filesystem path; an unvalidated one
        # walks straight out of the root. The validator living in a sibling
        # module protects nothing unless construction actually calls it.
        for bad in ("../../../escaped", "v1.0.0/../../etc/passwd", "not-a-tag",
                    "v1.0", "v1.0.0.json", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(self.cj.JournalError):
                    self.cj.CutJournal(tag=bad, root=self.cj.journal_root(self.repo))

    def test_transition_graph_is_enforced_in_every_direction(self) -> None:
        root = self.cj.journal_root(self.repo)
        j = self.cj.CutJournal(tag="v1.0.0", root=root)
        # forward skip — the skipped write-ahead record is what breaks resume
        with self.assertRaisesRegex(self.cj.JournalError, "refusing to skip"):
            j.advance("DRAFT_UPLOADED")
        # backwards — reopening a settled state
        self._walk_to(j, "TAGGED")
        with self.assertRaisesRegex(self.cj.JournalError, "backwards"):
            j.advance("PREPARED")
        # CI-authored states cannot be minted locally
        for ci_state in self.cj.CI_STATES:
            with self.subTest(ci_state=ci_state):
                with self.assertRaisesRegex(self.cj.JournalError, "written by CI"):
                    j.advance(ci_state)
        # a legal single step still works — the graph must not block progress
        j.advance("DRAFT_CREATE_PENDING")
        self.assertEqual(j.state, "DRAFT_CREATE_PENDING")

    def test_release_lock_will_not_remove_a_lock_it_does_not_hold(self) -> None:
        # An unconditional unlink deletes whoever's lock is present, handing two
        # cutters concurrent access to the same tag.
        root = self.cj.journal_root(self.repo)
        first = self.cj.CutJournal(tag="v1.0.0", root=root)
        first.acquire_lock()
        # A non-holder that never acquired is a no-op — but that is a DIFFERENT
        # guard, so it cannot stand in for the ownership check.
        self.cj.CutJournal(tag="v1.0.0", root=root).release_lock()
        self.assertTrue(first.lock_path.exists())

        # The real hazard: a STALE holder. `first` legitimately releases, `second`
        # acquires, and then `first` releases again — a double-release that an
        # unconditional unlink turns into two cutters holding the same tag at once.
        first.release_lock()
        second = self.cj.CutJournal(tag="v1.0.0", root=root)
        second.acquire_lock()
        first._lock_token = "pid=99999 at=1970-01-01T00:00:00Z"   # stale token
        first.release_lock()
        self.assertTrue(second.lock_path.exists(),
                        "a stale holder must not be able to release the current lock")
        second.release_lock()
        self.assertFalse(second.lock_path.exists())

    def test_remote_asset_digest_must_match_the_signed_tag(self) -> None:
        with self.assertRaisesRegex(self.cj.JournalError, "remote asset is"):
            self.cj.require_consistent(
                None, tag="v1.0.0",
                remote={"asset_sha256": "c" * 64},
                tag_fields={"asset_sha256": "a" * 64},
            )

    def test_object_identity_divergence_stops(self) -> None:
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        self._walk_to(j, "TAGGED", tag_object_id="deadbeef", release_id="111")
        with self.assertRaisesRegex(self.cj.JournalError, "tag_object_id"):
            self.cj.require_consistent(j, tag="v1.0.0",
                                       remote={"tag_object_id": "feedface"}, tag_fields=None)

    def test_published_without_ever_dispatching_is_anomalous(self) -> None:
        # Published while we never dispatched CI = published outside the pipeline.
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        self._walk_to(j, "DRAFT_UPLOADED")
        with self.assertRaisesRegex(self.cj.JournalError, "outside the pipeline"):
            self.cj.require_consistent(j, tag="v1.0.0",
                                       remote={"published": True}, tag_fields=None)

    # A fully-evidenced cut: what a real DISPATCHED/DRAFT_UPLOADED state looks
    # like once the required-evidence rule applies.
    FULL_REMOTE = {"tag_object_id": "abc", "release_id": "111",
                   "asset_sha256": "a" * 64}
    FULL_TAG = {"asset_sha256": "a" * 64, "manifest_sha256": "f" * 64}

    def test_published_after_dispatch_is_the_normal_outcome(self) -> None:
        # CI runs on GitHub and cannot write the operator's local journal, so a
        # completed cut rests at DISPATCHED forever. Publication after that is
        # success — flagging it would mark EVERY published release inconsistent.
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        self._walk_to(j, "DISPATCHED", **self.FULL_REMOTE)
        self.cj.require_consistent(
            j, tag="v1.0.0",
            remote={**self.FULL_REMOTE, "published": True}, tag_fields=self.FULL_TAG)

    def test_consistent_state_passes(self) -> None:
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        self._walk_to(j, "DRAFT_UPLOADED", **self.FULL_REMOTE)
        self.cj.require_consistent(
            j, tag="v1.0.0",
            remote={**self.FULL_REMOTE, "published": False}, tag_fields=self.FULL_TAG)


if __name__ == "__main__":
    unittest.main()
