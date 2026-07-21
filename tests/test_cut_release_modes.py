"""Policy-only and activation tags must use distinct release gates."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cut_release.py"


def _load():
    spec = importlib.util.spec_from_file_location("cut_release_modes", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CutReleaseModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cut_release = _load()

    @staticmethod
    def _git_result(stdout: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["git"], 0, stdout=stdout, stderr="")

    def _dry_run(self, mode: str):
        module = self.cut_release

        def fake_git(*args: str, **_kwargs):
            if args == ("rev-parse", "--abbrev-ref", "HEAD"):
                return self._git_result("main\n")
            if args == ("status", "--porcelain"):
                return self._git_result("")
            raise AssertionError(f"unexpected git command: {args}")

        with (
            mock.patch.object(module, "_changelog_compiled_or_fail"),
            mock.patch.object(module, "_release_mode_or_fail", return_value=mode),
            mock.patch.object(module, "_archive_contract_verified_or_fail") as archive,
            mock.patch.object(module, "_signed_runtime_verified_or_fail") as activation,
            mock.patch.object(module, "_head_is_published_main_or_fail"),
            mock.patch.object(module, "_tag_exists", return_value=False),
            mock.patch.object(module, "_git", side_effect=fake_git),
            mock.patch.object(module.crc, "run_consistency", return_value=(True, ["ok"])),
            mock.patch.object(module.crc, "current_version", return_value="3.0.0"),
        ):
            result = module.cut(dry_run=True)
        return result, archive, activation

    def test_policy_only_release_verifies_archive_without_activation_evidence(self) -> None:
        result, archive, activation = self._dry_run("policy-only")
        self.assertEqual(result, 0)
        archive.assert_called_once_with("policy-only")
        activation.assert_not_called()

    def test_activation_release_requires_archive_and_live_runtime_evidence(self) -> None:
        result, archive, activation = self._dry_run("activation")
        self.assertEqual(result, 0)
        archive.assert_called_once_with("activation")
        activation.assert_called_once_with()

    def test_unknown_release_mode_fails_before_tagging(self) -> None:
        module = self.cut_release
        with mock.patch.object(module.subprocess, "run") as runner:
            runner.return_value = subprocess.CompletedProcess(
                ["python"], 0, stdout="unexpected\n", stderr=""
            )
            with self.assertRaises(SystemExit):
                module._release_mode_or_fail()


if __name__ == "__main__":
    unittest.main()
