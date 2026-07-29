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

    def test_exitstack_enter_context_is_not_flagged(self) -> None:
        # contextlib.ExitStack.enterContext has existed since Python 3.3 --
        # a fully 3.10-compatible, standard pattern. Flagging by method name
        # alone (the original implementation) would false-positive on this
        # every bit as often as it catches the real unittest.TestCase
        # incident. Only a bare `self.enterContext(...)` receiver is flagged.
        source = (
            "from contextlib import ExitStack\n\n"
            "def f():\n"
            "    stack = ExitStack()\n"
            "    stack.enterContext(open('a'))\n"
            "    with ExitStack() as es:\n"
            "        es.enterContext(open('b'))\n"
            "    ExitStack().enterContext(open('c'))\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        keys = [f.api for f in findings]
        self.assertNotIn("unittest.TestCase.enterContext", keys)

    def test_self_dot_attribute_enter_context_is_not_flagged(self) -> None:
        # self.stack.enterContext(...) -- the immediate receiver of
        # .enterContext is the Attribute `self.stack`, not the bare Name
        # `self`. Not the unittest.TestCase pattern; must not be flagged.
        source = (
            "from contextlib import ExitStack\n\n"
            "class T:\n"
            "    def __init__(self):\n"
            "        self.stack = ExitStack()\n"
            "    def use(self):\n"
            "        self.stack.enterContext(open('a'))\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        keys = [f.api for f in findings]
        self.assertNotIn("unittest.TestCase.enterContext", keys)

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

    def test_reraising_handler_does_not_suppress(self) -> None:
        # except ImportError: raise provides no actual fallback -- the
        # import still fails identically to no try/except at all -- so it
        # must NOT be treated as a guard.
        source = (
            "try:\n"
            "    import tomllib\n"
            "except ImportError:\n"
            "    raise\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        self.assertEqual([f.api for f in findings], ["tomllib"])

    def test_log_then_reraise_handler_does_not_suppress(self) -> None:
        source = (
            "try:\n"
            "    import tomllib\n"
            "except ImportError:\n"
            "    log.warning('no tomllib')\n"
            "    raise\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        self.assertEqual([f.api for f in findings], ["tomllib"])

    def test_reraise_with_explicit_exception_is_still_not_a_guard(self) -> None:
        # `raise SomeError(...)` (a NEW exception, not a bare re-raise) also
        # doesn't provide a compatible fallback for the gated import -- it
        # just fails differently. Only a body that genuinely handles the
        # error (e.g. sets a fallback value, as in the guarded tests above)
        # counts as a guard.
        source = (
            "try:\n"
            "    import tomllib\n"
            "except ImportError as e:\n"
            "    raise RuntimeError('tomllib required') from e\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        self.assertEqual([f.api for f in findings], ["tomllib"])

    def test_nested_function_import_inside_guarded_try_is_still_flagged(self) -> None:
        # A `def` nested inside a guarded try body only executes when
        # CALLED, not at try-time -- an import inside it is NOT actually
        # protected by the enclosing try/except and must still be flagged.
        source = (
            "try:\n"
            "    def load():\n"
            "        import tomllib\n"
            "        return tomllib\n"
            "except ImportError:\n"
            "    load = None\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        self.assertEqual([f.api for f in findings], ["tomllib"])

    def test_nested_async_function_import_inside_guarded_try_is_still_flagged(self) -> None:
        source = (
            "try:\n"
            "    async def load():\n"
            "        import tomllib\n"
            "        return tomllib\n"
            "except ImportError:\n"
            "    load = None\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        self.assertEqual([f.api for f in findings], ["tomllib"])

    def test_top_level_guarded_import_alongside_nested_function_still_suppressed(self) -> None:
        # Regression guard: excluding nested-function bodies from the
        # guarded-lines collection must not also break suppression for a
        # genuinely top-level guarded import that happens to share a try
        # block with an (unrelated) nested function definition.
        source = (
            "try:\n"
            "    import tomllib\n"
            "    def unrelated():\n"
            "        pass\n"
            "except ImportError:\n"
            "    tomllib = None\n"
        )
        findings = cpvga.scan_source(source, "t.py", FLOOR_310)
        self.assertEqual(findings, [])


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

    def test_enter_context_regex_fallback_direct(self) -> None:
        hits = list(cpvga._detect_enter_context(None, "self.enterContext(open('a'))\n"))
        self.assertEqual(len(hits), 1)

    def test_exitstack_enter_context_regex_fallback_not_flagged(self) -> None:
        # The regex fallback must apply the same self.-only narrowing as the
        # AST path -- a `stack.enterContext(...)` receiver is standard,
        # 3.10-compatible ExitStack usage and must not be flagged even when
        # the file fails to parse under the running interpreter.
        hits = list(cpvga._detect_enter_context(None, "stack.enterContext(open('a'))\n"))
        self.assertEqual(hits, [])


class TestDeclaredMinimumReader(unittest.TestCase):
    def test_reads_real_ci_workflow(self) -> None:
        self.assertEqual(cpvga._read_declared_minimum(), cpvga.FALLBACK_MIN_VERSION)

    def test_regression_live_discovery_actually_succeeds(self) -> None:
        # The drift-detector, strengthened: call the STRICT parser directly
        # and require it not to raise. Merely asserting the wrapper's return
        # value equals FALLBACK_MIN_VERSION (the old form of this test) does
        # NOT distinguish "successfully parsed today's matrix, which happens
        # to floor at the same version as the fallback constant" from
        # "parsing silently failed and fell back" -- both produced the same
        # observable value under the old design. This calls the function
        # that raises on format drift, so a shape change in ci.yml fails
        # THIS test loudly instead of coincidentally still passing.
        parsed = cpvga._parse_declared_minimum(cpvga.CI_WORKFLOW_PATH)
        self.assertEqual(parsed, cpvga.FALLBACK_MIN_VERSION)

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

    def test_missing_file_falls_back_silently(self) -> None:
        # The ONLY benign case: no ci.yml at all (e.g. a stripped checkout).
        missing = Path("/nonexistent/path/ci.yml")
        self.assertEqual(cpvga._read_declared_minimum(missing), cpvga.FALLBACK_MIN_VERSION)

    def test_missing_matrix_key_raises_discovery_error_not_silent_fallback(self) -> None:
        # A workflow file that EXISTS but no longer matches the expected
        # matrix shape is FORMAT DRIFT, not a benign absence -- must raise,
        # never silently return the (possibly now-stale) fallback constant.
        with tempfile.TemporaryDirectory() as tmp:
            workflow = Path(tmp) / "ci.yml"
            workflow.write_text("jobs:\n  build:\n    runs-on: ubuntu-latest\n")
            with self.assertRaises(cpvga.MinVersionDiscoveryError):
                cpvga._parse_declared_minimum(workflow)
            # The fail-soft wrapper must NOT swallow this -- it only
            # swallows OSError (missing file), not a parse-shape failure.
            with self.assertRaises(cpvga.MinVersionDiscoveryError):
                cpvga._read_declared_minimum(workflow)

    def test_empty_version_list_raises_discovery_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow = Path(tmp) / "ci.yml"
            workflow.write_text(
                "jobs:\n  python:\n    strategy:\n      matrix:\n        python: []\n"
            )
            with self.assertRaises(cpvga.MinVersionDiscoveryError):
                cpvga._parse_declared_minimum(workflow)

    def test_main_fails_loud_with_exit_2_on_discovery_error(self) -> None:
        # End-to-end: main() must not silently proceed with a stale floor
        # when the real ci.yml (patched here) fails to parse -- it must
        # exit distinctly (2, not the "findings" exit code 1) with a clear
        # stderr message naming the problem.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow = root / "ci.yml"
            workflow.write_text("jobs:\n  build:\n    runs-on: ubuntu-latest\n")
            clean = root / "clean.py"
            clean.write_text("x = 1\n")
            original = cpvga.CI_WORKFLOW_PATH
            cpvga.CI_WORKFLOW_PATH = workflow
            try:
                exit_code = cpvga.main(["--paths", str(clean)])
            finally:
                cpvga.CI_WORKFLOW_PATH = original
            self.assertEqual(exit_code, 2)


class TestSourceEncodingHandling(unittest.TestCase):
    """A tracked .py file with a non-UTF-8 PEP 263 declared encoding is
    still fully valid, executable Python -- it must be correctly decoded
    (not silently skipped-as-clean) and can still contain a flaggable
    gated API. A genuinely unreadable file must fail CLOSED, not silently
    pass."""

    def test_latin1_declared_file_is_correctly_decoded_and_still_scanned(self) -> None:
        # A PEP 263 encoding cookie + non-ASCII latin-1 content (a comment
        # containing an accented character encodable in latin-1 but not
        # valid as UTF-8 on its own) + an unguarded gated import. The OLD
        # behavior (hardcoded read_text(encoding="utf-8")) would raise
        # UnicodeDecodeError, silently swallow it, and report the file as
        # having no findings -- letting the gated import through unflagged.
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "latin1_source.py"
            content = (
                "# -*- coding: latin-1 -*-\n"
                "# Ren\xe9 wrote this module\n"
                "import tomllib\n"
            )
            fixture.write_bytes(content.encode("latin-1"))
            findings = cpvga.scan_file(fixture, FLOOR_310)
            self.assertEqual([f.api for f in findings], ["tomllib"])

    def test_latin1_declared_file_end_to_end_via_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "latin1_source.py"
            content = (
                "# -*- coding: latin-1 -*-\n"
                "# Ren\xe9 wrote this module\n"
                "import tomllib\n"
            )
            fixture.write_bytes(content.encode("latin-1"))
            exit_code = cpvga.main(
                ["--paths", str(fixture), "--min-version", "3.10"]
            )
            self.assertEqual(exit_code, 1)  # flagged as a finding, not silently clean

    def test_read_source_raises_on_genuine_decode_failure(self) -> None:
        # Bytes that are not valid under EITHER a UTF-8 default NOR any
        # encoding a PEP 263 cookie could declare (raw invalid UTF-8 with
        # no cookie at all) -- a genuine, unrecoverable read failure.
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "broken.py"
            fixture.write_bytes(b"import tomllib\nx = '\xff\xfe invalid utf8'\n")
            with self.assertRaises(cpvga.SourceReadError):
                cpvga._read_source(fixture)

    def test_main_fails_closed_not_silently_clean_on_unreadable_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "broken.py"
            fixture.write_bytes(b"import tomllib\nx = '\xff\xfe invalid utf8'\n")
            exit_code = cpvga.main(
                ["--paths", str(fixture), "--min-version", "3.10"]
            )
            self.assertEqual(exit_code, 1)  # fails closed, not exit 0 "clean"

    def test_missing_file_between_listing_and_reading_is_silently_skipped(self) -> None:
        # The sole benign case: FileNotFoundError (a listing/read race), as
        # opposed to a genuine decode failure on a file that DOES exist.
        missing = Path("/nonexistent/path/gone.py")
        self.assertEqual(cpvga.scan_file(missing, FLOOR_310), [])


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
