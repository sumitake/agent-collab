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

    def test_signed_tag_wins_over_a_tampered_journal(self) -> None:
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        j.advance("DRAFT_UPLOADED", asset_sha256="b" * 64)   # journal (tamperable)
        with self.assertRaisesRegex(self.cj.JournalError, "the signed tag wins"):
            self.cj.require_consistent(
                j, tag="v1.0.0",
                remote={"asset_sha256": "a" * 64},
                tag_fields={"asset_sha256": "a" * 64},      # signed tag = anchor
            )

    def test_remote_asset_digest_must_match_the_signed_tag(self) -> None:
        with self.assertRaisesRegex(self.cj.JournalError, "remote asset is"):
            self.cj.require_consistent(
                None, tag="v1.0.0",
                remote={"asset_sha256": "c" * 64},
                tag_fields={"asset_sha256": "a" * 64},
            )

    def test_object_identity_divergence_stops(self) -> None:
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        j.advance("TAGGED", tag_object_id="deadbeef", release_id="111")
        with self.assertRaisesRegex(self.cj.JournalError, "tag_object_id"):
            self.cj.require_consistent(j, tag="v1.0.0",
                                       remote={"tag_object_id": "feedface"}, tag_fields=None)

    def test_published_without_ever_dispatching_is_anomalous(self) -> None:
        # Published while we never dispatched CI = published outside the pipeline.
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        j.advance("DRAFT_UPLOADED")
        with self.assertRaisesRegex(self.cj.JournalError, "outside the pipeline"):
            self.cj.require_consistent(j, tag="v1.0.0",
                                       remote={"published": True}, tag_fields=None)

    def test_published_after_dispatch_is_the_normal_outcome(self) -> None:
        # CI runs on GitHub and cannot write the operator's local journal, so a
        # completed cut rests at DISPATCHED forever. Publication after that is
        # success — flagging it would mark EVERY published release inconsistent.
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        j.advance("DISPATCHED")
        self.cj.require_consistent(j, tag="v1.0.0",
                                   remote={"published": True}, tag_fields=None)

    def test_consistent_state_passes(self) -> None:
        j = self.cj.CutJournal(tag="v1.0.0", root=self.cj.journal_root(self.repo))
        j.advance("DRAFT_UPLOADED", tag_object_id="abc", release_id="111",
                  asset_sha256="a" * 64)
        self.cj.require_consistent(
            j, tag="v1.0.0",
            remote={"tag_object_id": "abc", "release_id": "111",
                    "asset_sha256": "a" * 64, "published": False},
            tag_fields={"asset_sha256": "a" * 64},
        )


if __name__ == "__main__":
    unittest.main()
