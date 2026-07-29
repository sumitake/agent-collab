#!/usr/bin/env python3
"""Unit tests for check_python_version_gated_apis.py.

Covers: each individual gated-API detector (AST path), the floor-relative
filtering (an API introduced at-or-before the declared minimum is never
flagged -- the `str.removeprefix`/`removesuffix` case), the guarded-import
suppression (a `try/except ImportError`-wrapped `tomllib` import must NOT be
flagged, since that's the *correct* fix, not an instance of the incident),
the `ci.yml`-matrix-derived declared-minimum reader (with a regression check
that it agrees with the hardcoded fallback against the real repo file), and
end-to-end `main()` exit-code behavior against real fixture files on disk
(created in a temp directory per test, per the incident's own root cause --
never rely on the *running* interpreter's own version for what "parses
successfully" implies about the declared floor).

Run: python3 scripts/test_check_python_version_gated_apis.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_python_version_gated_apis as cpvga  # noqa: E402


FLOOR_310 = (3, 10)
FLOOR_311 = (3, 11)


class TestScanSourceDetectors(unittest.TestCase):
    """Each detector, exercised via the AST path (scan_source with valid syntax)."""

    def test_enter_context_is_flagged_above_floor(self) -> None:
        source = (
            "import unittest\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_x(self):\n"
            "        self.enterContext(open('f'))\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        keys = [f.api for f in findings]
        self.assertIn("unittest.TestCase.enterContext", keys)

    def test_except_star_is_flagged_above_floor(self) -> None:
        source = (
            "try:\n"
            "    pass\n"
            "except* ValueError:\n"
            "    pass\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        keys = [f.api for f in findings]
        self.assertIn("except*", keys)

    def test_tomllib_import_is_flagged_above_floor(self) -> None:
        findings = cpvga.scan_source("import tomllib\n", "t.py", FLOOR_310)
        self.assertEqual([f.api for f in findings], ["tomllib"])

    def test_tomllib_from_import_is_flagged_above_floor(self) -> None:
        findings = cpvga.scan_source(
            "from tomllib import load\n", "t.py", FLOOR_310
        )
        self.assertEqual([f.api for f in findings], ["tomllib"])

    def test_typing_self_from_import_is_flagged_above_floor(self) -> None:
        findings = cpvga.scan_source(
            "from typing import Self\n", "t.py", FLOOR_310
        )
        self.assertEqual([f.api for f in findings], ["typing.Self"])

    def test_typing_self_attribute_usage_is_flagged_above_floor(self) -> None:
        source = "import typing\n\ndef f() -> typing.Self:\n    ...\n"
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        self.assertEqual([f.api for f in findings], ["typing.Self"])

    def test_clean_source_produces_no_findings(self) -> None:
        source = (
            "import json\n\n"
            "def add(a, b):\n"
            "    return a + b\n\n"
            "class Widget:\n"
            "    def __init__(self, name):\n"
            "        self.name = name\n"
        )
        self.assertEqual(cpvga.scan_source(source, "t.py", FLOOR_310), [])


class TestFloorRelativeFiltering(unittest.TestCase):
    """An API introduced at-or-before the declared floor must never be flagged."""

    def test_removeprefix_not_flagged_at_floor_310(self) -> None:
        # str.removeprefix was added in 3.9, which predates a 3.10 floor.
        findings = cpvga.scan_source(
            "x = 'abcdef'.removeprefix('abc')\n", "t.py", FLOOR_310
        )
        self.assertEqual(findings, [])

    def test_removesuffix_not_flagged_at_floor_310(self) -> None:
        findings = cpvga.scan_source(
            "x = 'abcdef'.removesuffix('def')\n", "t.py", FLOOR_310
        )
        self.assertEqual(findings, [])

    def test_removeprefix_flagged_if_floor_is_lowered_below_39(self) -> None:
        # Demonstrates the table is floor-relative, not hardcoded to today's repo.
        findings = cpvga.scan_source(
            "x = 'abcdef'.removeprefix('abc')\n", "t.py", (3, 8)
        )
        self.assertEqual([f.api for f in findings], ["str.removeprefix"])

    def test_tomllib_not_flagged_once_floor_reaches_311(self) -> None:
        findings = cpvga.scan_source("import tomllib\n", "t.py", FLOOR_311)
        self.assertEqual(findings, [])

    def test_applicable_apis_empty_when_floor_covers_everything(self) -> None:
        # Nothing left in KNOWN_APIS post-dates a very high floor.
        self.assertEqual(cpvga.applicable_apis((3, 20)), ())


class TestGuardedImportSuppression(unittest.TestCase):
    """A try/except ImportError-guarded gated import is the CORRECT fix, not the bug."""

    def test_guarded_tomllib_import_is_not_flagged(self) -> None:
        source = (
            "try:\n"
            "    import tomllib\n"
            "except ModuleNotFoundError:\n"
            "    tomllib = None\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        self.assertEqual(findings, [], "guarded import must not be flagged")

    def test_guarded_tomllib_import_error_variant_is_not_flagged(self) -> None:
        source = (
            "try:\n"
            "    import tomllib\n"
            "except ImportError:\n"
            "    tomllib = None\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        self.assertEqual(findings, [])

    def test_guarded_tomllib_import_tuple_handler_is_not_flagged(self) -> None:
        source = (
            "try:\n"
            "    import tomllib\n"
            "except (ImportError, ModuleNotFoundError):\n"
            "    tomllib = None\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        self.assertEqual(findings, [])

    def test_guarded_typing_self_from_import_is_not_flagged(self) -> None:
        source = (
            "try:\n"
            "    from typing import Self\n"
            "except ImportError:\n"
            "    Self = object\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        self.assertEqual(findings, [])

    def test_unrelated_exception_handler_does_not_suppress(self) -> None:
        # except ValueError would not actually catch a missing-module error,
        # so this import is NOT considered safely guarded.
        source = (
            "try:\n"
            "    import tomllib\n"
            "except ValueError:\n"
            "    tomllib = None\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        self.assertEqual([f.api for f in findings], ["tomllib"])

    def test_unguarded_tomllib_import_still_flagged(self) -> None:
        findings = cpvga.scan_source("import tomllib\n", "t.py", FLOOR_310)
        self.assertEqual([f.api for f in findings], ["tomllib"])


class TestRegexFallback(unittest.TestCase):
    """When a file fails to parse under the running interpreter, detectors fall
    back to a documented regex scan rather than crashing or silently skipping
    the file."""

    def test_syntax_error_falls_back_without_crashing(self) -> None:
        # Deliberately invalid syntax (unrelated to any gated API) -- the
        # scanner must not raise, and should simply find nothing relevant.
        source = "def f(:\n    pass\n"
        findings = cpvga.scan_source(source, "broken.py", FLOOR_310)
        self.assertEqual(findings, [])

    def test_except_star_regex_fallback_direct(self) -> None:
        # Exercise the fallback branch directly (tree=None) regardless of
        # whether the running interpreter can parse `except*` itself.
        source = "try:\n    pass\nexcept* ValueError:\n    pass\n"
        hits = list(cpvga._detect_except_star(None, source))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][0], 3)  # line 3

    def test_tomllib_regex_fallback_direct(self) -> None:
        hits = list(cpvga._detect_tomllib_import(None, "import tomllib\n"))
        self.assertEqual(len(hits), 1)


class TestDeclaredMinimumReader(unittest.TestCase):
    def test_reads_real_ci_workflow(self) -> None:
        self.assertEqual(cpvga._read_declared_minimum(), cpvga.FALLBACK_MIN_VERSION)

    def test_regression_fallback_matches_real_repo_floor(self) -> None:
        # This is the drift-detector: if ci.yml's matrix ever changes without
        # updating FALLBACK_MIN_VERSION (or vice versa), this test fails.
        self.assertEqual(
            cpvga._read_declared_minimum(cpvga.CI_WORKFLOW_PATH),
            cpvga.FALLBACK_MIN_VERSION,
        )

    def test_parses_synthetic_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow = Path(tmp) / "ci.yml"
            workflow.write_text(
                "jobs:\n"
                "  python:\n"
                "    strategy:\n"
                "      matrix:\n"
                '        python: ["3.11", "3.13"]\n'
            )
            self.assertEqual(cpvga._read_declared_minimum(workflow), (3, 11))

    def test_missing_file_falls_back(self) -> None:
        missing = Path("/nonexistent/path/ci.yml")
        self.assertEqual(cpvga._read_declared_minimum(missing), cpvga.FALLBACK_MIN_VERSION)

    def test_missing_matrix_key_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow = Path(tmp) / "ci.yml"
            workflow.write_text("jobs:\n  build:\n    runs-on: ubuntu-latest\n")
            self.assertEqual(
                cpvga._read_declared_minimum(workflow), cpvga.FALLBACK_MIN_VERSION
            )


class TestEndToEndFixtureFiles(unittest.TestCase):
    """main() against real fixture files on disk, verifying exit codes."""

    def test_fixture_using_enter_context_is_flagged_and_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "test_something.py"
            fixture.write_text(
                "import unittest\n\n"
                "class MyTest(unittest.TestCase):\n"
                "    def test_thing(self):\n"
                "        self.enterContext(open(__file__))\n"
                "        self.assertTrue(True)\n"
            )
            exit_code = cpvga.main(
                ["--paths", str(fixture), "--min-version", "3.10"]
            )
            self.assertEqual(exit_code, 1)

    def test_fixture_using_no_gated_apis_passes_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "test_something.py"
            fixture.write_text(
                "import unittest\n\n"
                "class MyTest(unittest.TestCase):\n"
                "    def setUp(self):\n"
                "        self.value = 42\n\n"
                "    def test_thing(self):\n"
                "        self.assertEqual(self.value, 42)\n"
            )
            exit_code = cpvga.main(
                ["--paths", str(fixture), "--min-version", "3.10"]
            )
            self.assertEqual(exit_code, 0)

    def test_fixture_with_guarded_tomllib_import_passes_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "loader.py"
            fixture.write_text(
                "try:\n"
                "    import tomllib\n"
                "except ModuleNotFoundError:\n"
                "    tomllib = None\n"
            )
            exit_code = cpvga.main(
                ["--paths", str(fixture), "--min-version", "3.10"]
            )
            self.assertEqual(exit_code, 0)

    def test_multiple_paths_aggregate_findings_and_exit_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean.py"
            clean.write_text("x = 1\n")
            dirty = Path(tmp) / "dirty.py"
            dirty.write_text("from typing import Self\n")
            exit_code = cpvga.main(
                ["--paths", str(clean), str(dirty), "--min-version", "3.10"]
            )
            self.assertEqual(exit_code, 1)

    def test_high_min_version_disables_check_entirely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "modern.py"
            fixture.write_text("import tomllib\n")
            # Floor already at/above every known gated API -> nothing to check.
            exit_code = cpvga.main(
                ["--paths", str(fixture), "--min-version", "3.20"]
            )
            self.assertEqual(exit_code, 0)


class TestIterPythonFiles(unittest.TestCase):
    def test_iterates_real_repo_without_crashing(self) -> None:
        files = list(cpvga.iter_python_files(cpvga.REPO_ROOT))
        self.assertTrue(files, "expected at least one tracked .py file")
        self.assertTrue(all(p.suffix == ".py" for p in files))

    def test_excludes_common_noise_directories(self) -> None:
        files = list(cpvga.iter_python_files(cpvga.REPO_ROOT))
        for path in files:
            self.assertFalse(
                any(part in cpvga.EXCLUDED_DIR_NAMES for part in path.parts),
                f"{path} should have been excluded",
            )


class TestRealRepoIsClean(unittest.TestCase):
    """Guards against regressions: the repo itself must stay clean under this check."""

    def test_repo_scan_exits_zero(self) -> None:
        exit_code = cpvga.main([])
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
