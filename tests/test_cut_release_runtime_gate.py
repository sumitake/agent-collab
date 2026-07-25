"""Runtime-currency gate: an activation cut must not ship a stale runtime.

Motivation (2026-07-25): v4.4.0 was cut tag-only and shipped the 4.2.0-era
runtime bundle although five `runtime:`-scoped merges had landed since; the
operator rolled the release back. The gate fails the cut whenever a
runtime-scoped subject exists after the commit that last touched the staged
runtime paths, unless the operator passes --allow-stale-runtime.
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
    """Return canned stdout per git argv prefix."""

    def __init__(self, staged_sha: str, subjects: list[str]):
        self.staged_sha = staged_sha
        self.subjects = subjects

    def __call__(self, *args, capture=True, check=True):
        out = mock.Mock()
        if args[:3] == ("log", "-1", "--format=%H"):
            out.stdout = self.staged_sha
        elif args[:2] == ("log", "--format=%s"):
            out.stdout = "\n".join(self.subjects)
        else:
            raise AssertionError(f"unexpected git call: {args}")
        return out


class RuntimeCurrencyGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def _run(self, staged_sha, subjects, allow_stale=False):
        with mock.patch.object(self.mod, "_git", _GitStub(staged_sha, subjects)):
            self.mod._runtime_currency_or_fail(allow_stale)

    def test_current_runtime_passes(self):
        self._run("a" * 40, ["docs: readme", "skills: add pack (#55)"])

    def test_no_staged_runtime_fails(self):
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                self._run("", [])

    def test_stale_runtime_fails_closed(self):
        err = io.StringIO()
        with self.assertRaises(SystemExit):
            with redirect_stderr(err):
                self._run("a" * 40, [
                    "skills: add pack (#55)",
                    "runtime: accept Gemini governance proof v2 (#54)",
                ])
        self.assertIn("runtime: accept Gemini governance proof v2", err.getvalue())
        self.assertIn("STALE", err.getvalue())

    def test_stale_runtime_prefix_match_is_case_insensitive(self):
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                self._run("a" * 40, ["Runtime: judge readiness (#52)"])

    def test_non_prefix_mention_does_not_trip(self):
        # A subject merely *mentioning* runtime is not a runtime-scoped merge.
        self._run("a" * 40, ["docs: clarify runtime: notes layout"])

    def test_operator_override_warns_but_passes(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self._run("a" * 40, ["runtime: bound routing (#50)"], allow_stale=True)
        self.assertIn("WARNING", err.getvalue())

    def test_cut_wires_flag_through_main(self):
        # main() must accept the flag and hand it to cut().
        with mock.patch.object(self.mod, "cut", return_value=0) as cut_mock:
            self.mod.main(["--allow-stale-runtime", "--dry-run"])
        cut_mock.assert_called_once_with(True, allow_stale_runtime=True)


if __name__ == "__main__":
    unittest.main()
