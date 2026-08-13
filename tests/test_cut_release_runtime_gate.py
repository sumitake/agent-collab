"""Runtime-currency gate: activation requires an imported runtime bundle.

The governed workspace build and atomic public import establish source
currency. The public release verifies exact bundle bytes and signed/notarized
identity; descriptive commit subjects are not byte authority.
"""
from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "cut_release.py"


def _load():
    spec = importlib.util.spec_from_file_location("cut_release_runtime_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _GitStub:
    """Return the staged bundle commit and reject prose-history queries."""

    def __init__(self, staged_sha: str):
        self.staged_sha = staged_sha

    def __call__(self, *args, capture=True, check=True):
        out = mock.Mock()
        if args[:3] == ("log", "-1", "--format=%H"):
            # Presence is proven from the imported bundle directory itself.
            assert args[3] == "--"
            assert list(args[4:]) == ["plugins/agent-collab/runtime/"], args
            out.stdout = self.staged_sha
        else:
            raise AssertionError(f"unexpected git call: {args}")
        return out


class StagedRuntimeGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def _run(self, staged_sha):
        with mock.patch.object(self.mod, "_git", _GitStub(staged_sha)):
            self.mod._staged_runtime_present_or_fail()

    def test_commit_subject_is_not_queried_as_runtime_authority(self):
        self._run("a" * 40)

    def test_no_staged_runtime_fails(self):
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                self._run("")

    def test_stale_runtime_override_is_not_a_command_line_surface(self):
        with mock.patch.object(self.mod, "cut", return_value=0) as cut_mock:
            with self.assertRaises(SystemExit):
                self.mod.main(["--allow-stale-runtime", "--dry-run"])
        cut_mock.assert_not_called()

    def test_tag_deletion_rollback_is_not_a_command_line_surface(self):
        with mock.patch.object(self.mod, "cut", return_value=0) as cut_mock:
            with self.assertRaises(SystemExit):
                self.mod.main(["--rollback", "v5.0.0", "--dry-run"])
        cut_mock.assert_not_called()

    def test_release_tool_contains_no_tag_deletion_rollback(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("def rollback(", source)
        self.assertNotIn(":refs/tags/", source)
        self.assertNotIn('"release", "delete"', source)


if __name__ == "__main__":
    unittest.main()
