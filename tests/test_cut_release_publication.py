"""Release tags succeed only after exact immutable publication verification."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cut_release.py"


def _load():
    spec = importlib.util.spec_from_file_location("cut_release_publication", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CutReleasePublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load()
        cls.tag = "v5.0.0"
        cls.commit = "1" * 40
        cls.archive_name = "agent-collab.v5.0.0.plugin"
        cls.checksum_name = cls.archive_name + ".sha256"
        cls.sbom_name = "agent-collab-v5.0.0.spdx.json"
        archive = b"exact deterministic plugin archive"
        checksum = (
            hashlib.sha256(archive).hexdigest()
            + f"  {cls.archive_name}\n"
        ).encode()
        sbom = b'{"spdxVersion":"SPDX-2.3","name":"agent-collab"}\n'
        cls.downloaded = {
            cls.archive_name: archive,
            cls.checksum_name: checksum,
            cls.sbom_name: sbom,
        }
        cls.expected = {
            name: hashlib.sha256(data).hexdigest()
            for name, data in cls.downloaded.items()
        }

    def _state(self):
        return {
            "tag_commit": self.commit,
            "tag_is_annotated": True,
            "tag_signature_verified": True,
            "workflow_runs": [{
                "id": 101,
                "run_attempt": 1,
                "path": ".github/workflows/release.yml",
                "event": "push",
                "head_branch": self.tag,
                "head_sha": self.commit,
                "status": "completed",
                "conclusion": "success",
            }],
            "release": {
                "tag_name": self.tag,
                "draft": False,
                "prerelease": False,
                "assets": [
                    {"name": name, "size": len(data)}
                    for name, data in self.downloaded.items()
                ],
            },
            "downloaded_assets": dict(self.downloaded),
        }

    def _validate(self, **state):
        validator = getattr(
            self.mod,
            "_validate_publication_state",
            lambda **_kwargs: None,
        )
        return validator(
            tag=self.tag,
            commit=self.commit,
            expected_asset_sha256=self.expected,
            **state,
        )

    def test_exact_successful_workflow_release_and_assets_pass(self) -> None:
        self.assertIsNone(self._validate(**self._state()))

    def test_missing_or_failed_exact_workflow_never_counts_as_release(self) -> None:
        cases = {
            "missing": [],
            "failed": [{
                **self._state()["workflow_runs"][0],
                "conclusion": "failure",
            }],
            "wrong commit": [{
                **self._state()["workflow_runs"][0],
                "head_sha": "2" * 40,
            }],
        }
        for label, workflow_runs in cases.items():
            state = self._state()
            state["workflow_runs"] = workflow_runs
            with self.subTest(label=label), self.assertRaises(ValueError):
                self._validate(**state)

    def test_tag_must_be_signed_annotated_and_resolve_to_exact_commit(self) -> None:
        cases = {
            "wrong commit": {"tag_commit": "2" * 40},
            "lightweight": {"tag_is_annotated": False},
            "unverified": {"tag_signature_verified": False},
        }
        for label, changes in cases.items():
            state = {**self._state(), **changes}
            with self.subTest(label=label), self.assertRaises(ValueError):
                self._validate(**state)

    def test_missing_release_or_required_asset_never_counts_as_release(self) -> None:
        missing_release = self._state()
        missing_release["release"] = None
        missing_asset = self._state()
        missing_asset["release"]["assets"] = missing_asset["release"]["assets"][:-1]
        for label, state in (
            ("missing release", missing_release),
            ("missing asset", missing_asset),
        ):
            with self.subTest(label=label), self.assertRaises(ValueError):
                self._validate(**state)

    def test_wrong_archive_checksum_or_sbom_digest_never_counts_as_release(self) -> None:
        for name in self.downloaded:
            state = self._state()
            state["downloaded_assets"][name] += b"tampered"
            with self.subTest(asset=name), self.assertRaises(ValueError):
                self._validate(**state)

    @staticmethod
    def _git_result(stdout: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["git"], 0, stdout=stdout, stderr="")

    def _cut_with_publication_mocks(self, *, tag_exists: bool):
        module = self.mod

        def fake_git(*args: str, **_kwargs):
            if args == ("rev-parse", "--abbrev-ref", "HEAD"):
                return self._git_result("main\n")
            if args == ("rev-parse", "HEAD"):
                return self._git_result(self.commit + "\n")
            if args == ("status", "--porcelain"):
                return self._git_result("")
            if args == ("rev-parse", f"{self.tag}^{{commit}}"):
                return self._git_result(self.commit + "\n")
            if args[:2] in {
                ("tag", "-s"), ("verify-tag", self.tag),
                ("push", "origin"),
            }:
                return self._git_result("")
            raise AssertionError(f"unexpected git command: {args}")

        patches = (
            mock.patch.object(module, "_changelog_compiled_or_fail"),
            mock.patch.object(module, "_release_mode_or_fail", return_value="policy-only"),
            mock.patch.object(
                module,
                "_archive_contract_verified_or_fail",
                return_value=copy.deepcopy(self.expected),
            ),
            mock.patch.object(module, "_head_is_published_main_or_fail"),
            mock.patch.object(module, "_tag_exists", return_value=tag_exists),
            mock.patch.object(module, "_git", side_effect=fake_git),
            mock.patch.object(module.crc, "run_consistency", return_value=(True, ["ok"])),
            mock.patch.object(module.crc, "current_version", return_value="5.0.0"),
            mock.patch.object(
                module, "_verify_published_release_or_fail", create=True
            ),
            mock.patch.object(
                module, "_wait_and_verify_published_release_or_fail", create=True
            ),
        )
        entered = [patcher.start() for patcher in patches]
        self.addCleanup(lambda: [patcher.stop() for patcher in reversed(patches)])
        return entered

    def test_existing_tag_is_verification_only_not_assumed_success(self) -> None:
        entered = self._cut_with_publication_mocks(tag_exists=True)
        verify = entered[-2]
        wait = entered[-1]
        self.assertEqual(self.mod.cut(dry_run=False), 0)
        verify.assert_called_once_with(self.tag, self.commit, self.expected)
        wait.assert_not_called()

    def test_new_tag_waits_for_exact_publication_before_success(self) -> None:
        entered = self._cut_with_publication_mocks(tag_exists=False)
        verify = entered[-2]
        wait = entered[-1]
        self.assertEqual(self.mod.cut(dry_run=False), 0)
        wait.assert_called_once_with(self.tag, self.commit, self.expected)
        verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
