"""Tests for build-changelog.py — the changelog-fragment compiler.

Stdlib-only (unittest), so CI doesn't need a pytest install.

Tests the pure functions (list_fragments, read_fragments, compile_changelog)
against isolated temp-directory fixtures, plus a few integration tests for
the main() CLI behavior. The CLI tests run main() directly (with sys.argv
monkey-patched) rather than as a subprocess, so they can exercise the
module-level REPO_ROOT/CHANGELOG_PATH/FRAGMENTS_DIR overrides without
needing the script to know about an environment variable.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent

# Load build-changelog.py as a module (the file has a hyphen in its name,
# so we can't `import build-changelog` directly).
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = SCRIPT_DIR / "build-changelog.py"
_spec = importlib.util.spec_from_file_location("build_changelog", SCRIPT_PATH)
build_changelog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_changelog)


BASELINE_CHANGELOG = dedent(
    """\
    # Changelog — agent-collab marketplace

    All notable changes to the marketplace and its hosted plugins.

    ## [Unreleased]

    ### legacy-entry-still-inline 1.0.0 — 2026-05-23

    Preserved unmodified by the fragment compiler.
    """
)


class _RepoCase(unittest.TestCase):
    """Base class: each test gets a fresh tmp_path repo layout with
    REPO_ROOT/CHANGELOG_PATH/FRAGMENTS_DIR monkey-patched onto the
    build_changelog module. Saved attribute values are restored in tearDown.
    """

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)
        (self.tmp_path / "changelog.d").mkdir()
        self._saved = {
            "REPO_ROOT": build_changelog.REPO_ROOT,
            "CHANGELOG_PATH": build_changelog.CHANGELOG_PATH,
            "FRAGMENTS_DIR": build_changelog.FRAGMENTS_DIR,
        }
        build_changelog.REPO_ROOT = self.tmp_path
        build_changelog.CHANGELOG_PATH = self.tmp_path / "CHANGELOG.md"
        build_changelog.FRAGMENTS_DIR = self.tmp_path / "changelog.d"

    def tearDown(self) -> None:
        for k, v in self._saved.items():
            setattr(build_changelog, k, v)
        self._tmpdir.cleanup()

    # ---- helpers ----

    def write_changelog(self, content: str) -> None:
        (self.tmp_path / "CHANGELOG.md").write_text(content)

    def write_fragment(self, name: str, content: str) -> None:
        (self.tmp_path / "changelog.d" / name).write_text(content)

    @contextlib.contextmanager
    def cli(self, *argv: str):
        """Run main() with patched sys.argv + capture stdout/stderr.

        Yields (stdout_text, stderr_text, get_rc). Read after the with-block.
        """
        saved_argv = sys.argv
        sys.argv = ["build-changelog.py", *argv]
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        rc_holder: dict[str, int] = {}
        try:
            with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
                rc_holder["rc"] = build_changelog.main()
            yield out_buf, err_buf, rc_holder
        finally:
            sys.argv = saved_argv


# ---------- list_fragments ----------


class ListFragmentsTests(_RepoCase):
    def test_empty_dir(self) -> None:
        self.assertEqual(build_changelog.list_fragments(), [])

    def test_picks_up_md_files_in_sorted_order(self) -> None:
        self.write_fragment("0002-second.md", "second")
        self.write_fragment("0001-first.md", "first")
        self.write_fragment("0010-tenth.md", "tenth")
        result = build_changelog.list_fragments()
        self.assertEqual(
            [p.name for p in result],
            ["0001-first.md", "0002-second.md", "0010-tenth.md"],
        )

    def test_skips_reserved_names(self) -> None:
        self.write_fragment("README.md", "docs")
        self.write_fragment(".gitkeep", "")
        self.write_fragment(".skip-42", "skip-this-PR")
        self.write_fragment("0001-real-entry.md", "actual content")
        result = build_changelog.list_fragments()
        self.assertEqual([p.name for p in result], ["0001-real-entry.md"])

    def test_skips_non_md_files(self) -> None:
        self.write_fragment("0001-real-entry.md", "content")
        (self.tmp_path / "changelog.d" / "0002-not-a-fragment.txt").write_text("ignored")
        (self.tmp_path / "changelog.d" / "0003-no-extension").write_text("ignored")
        result = build_changelog.list_fragments()
        self.assertEqual([p.name for p in result], ["0001-real-entry.md"])

    def test_handles_missing_dir(self) -> None:
        build_changelog.FRAGMENTS_DIR = self.tmp_path / "nonexistent"
        self.assertEqual(build_changelog.list_fragments(), [])


# ---------- read_fragments ----------


class ReadFragmentsTests(_RepoCase):
    def test_returns_content_in_order(self) -> None:
        self.write_fragment("0001-a.md", "content-a\n")
        self.write_fragment("0002-b.md", "content-b\n")
        fragments = build_changelog.list_fragments()
        self.assertEqual(
            build_changelog.read_fragments(fragments), ["content-a", "content-b"]
        )

    def test_strips_trailing_whitespace_only(self) -> None:
        self.write_fragment("0001.md", "  leading-preserved\ncontent  \n\n\n")
        fragments = build_changelog.list_fragments()
        self.assertEqual(
            build_changelog.read_fragments(fragments),
            ["  leading-preserved\ncontent"],
        )


# ---------- compile_changelog ----------


class CompileChangelogTests(_RepoCase):
    def test_inserts_fragment_block_after_unreleased(self) -> None:
        compiled = build_changelog.compile_changelog(
            BASELINE_CHANGELOG,
            ["### my-fragment 0.1.0 — 2026-05-24\n\nFragment body."],
        )
        self.assertIn(build_changelog.FRAGMENT_BLOCK_START, compiled)
        self.assertIn(build_changelog.FRAGMENT_BLOCK_END, compiled)
        self.assertIn("### my-fragment 0.1.0", compiled)
        self.assertIn("### legacy-entry-still-inline 1.0.0", compiled)
        self.assertLess(
            compiled.index("## [Unreleased]"),
            compiled.index(build_changelog.FRAGMENT_BLOCK_START),
        )
        self.assertLess(
            compiled.index(build_changelog.FRAGMENT_BLOCK_END),
            compiled.index("### legacy-entry-still-inline"),
        )

    def test_with_no_fragments_emits_empty_block(self) -> None:
        compiled = build_changelog.compile_changelog(BASELINE_CHANGELOG, [])
        self.assertIn(build_changelog.FRAGMENT_BLOCK_START, compiled)
        self.assertIn(build_changelog.FRAGMENT_BLOCK_END, compiled)
        start_idx = compiled.index(build_changelog.FRAGMENT_BLOCK_START) + len(
            build_changelog.FRAGMENT_BLOCK_START
        )
        end_idx = compiled.index(build_changelog.FRAGMENT_BLOCK_END)
        self.assertEqual(compiled[start_idx:end_idx].strip(), "")

    def test_idempotent_when_block_already_present(self) -> None:
        first = build_changelog.compile_changelog(
            BASELINE_CHANGELOG, ["### x 0.1.0 — 2026-05-24\n\nbody."]
        )
        second = build_changelog.compile_changelog(
            first, ["### x 0.1.0 — 2026-05-24\n\nbody."]
        )
        self.assertEqual(first, second)

    def test_replaces_existing_block(self) -> None:
        initial = build_changelog.compile_changelog(
            BASELINE_CHANGELOG, ["### old 0.1.0 — 2026-05-24\n\nold."]
        )
        updated = build_changelog.compile_changelog(
            initial, ["### new 0.2.0 — 2026-05-24\n\nnew."]
        )
        self.assertNotIn("### old 0.1.0", updated)
        self.assertIn("### new 0.2.0", updated)
        self.assertEqual(updated.count(build_changelog.FRAGMENT_BLOCK_START), 1)
        self.assertEqual(updated.count(build_changelog.FRAGMENT_BLOCK_END), 1)

    def test_multiple_fragments_concatenated_with_blank_line(self) -> None:
        compiled = build_changelog.compile_changelog(
            BASELINE_CHANGELOG,
            [
                "### a 0.1.0 — 2026-05-24\n\nfirst entry body.",
                "### b 0.2.0 — 2026-05-24\n\nsecond entry body.",
            ],
        )
        self.assertIn("### a 0.1.0", compiled)
        self.assertIn("### b 0.2.0", compiled)
        self.assertLess(
            compiled.index("### a 0.1.0"), compiled.index("### b 0.2.0")
        )
        self.assertIn("first entry body.", compiled)
        self.assertIn("second entry body.", compiled)

    def test_raises_when_no_unreleased_header(self) -> None:
        bad_changelog = "# Changelog\n\nNo Unreleased section here.\n"
        with self.assertRaises(ValueError) as cm:
            build_changelog.compile_changelog(bad_changelog, ["fragment"])
        self.assertIn("[Unreleased]", str(cm.exception))

    def test_preserves_complex_markdown_in_fragments(self) -> None:
        fragment = dedent(
            """\
            ### complex 0.1.0 — 2026-05-24

            Code block:
            ```python
            def foo():
                pass
            ```

            - Bullet
            - Another bullet with `inline code`
            - [Link](https://example.com)

            > Blockquote
            """
        ).rstrip()
        compiled = build_changelog.compile_changelog(BASELINE_CHANGELOG, [fragment])
        self.assertIn("```python", compiled)
        self.assertIn("def foo():", compiled)
        self.assertIn("`inline code`", compiled)
        self.assertIn("[Link](https://example.com)", compiled)
        self.assertIn("> Blockquote", compiled)

    def test_fragment_body_quoting_marker_strings_is_not_matched(self):
        """Regression: a fragment whose BODY mentions the boundary marker
        strings (e.g., in code blocks or backtick quotes describing the
        system itself) MUST NOT be matched by the boundary regex on the
        second compile. Anchoring markers to line-start (^ + re.MULTILINE)
        prevents the bug.
        """
        fragment_with_marker_quotes = (
            "### complex 0.1.0 — 2026-05-24\n\n"
            "This describes the markers: `<!-- changelog-fragments:start (auto-generated by build-changelog.py — do not hand-edit) -->` "
            "and `<!-- changelog-fragments:end -->`. They're for compiler use only.\n"
        )
        # First compile (bootstrap)
        first = build_changelog.compile_changelog(BASELINE_CHANGELOG, [fragment_with_marker_quotes])
        # Second compile must be idempotent (the bug duplicated content)
        second = build_changelog.compile_changelog(first, [fragment_with_marker_quotes])
        self.assertEqual(first, second,
                         "Compile is NOT idempotent when fragment body "
                         "contains marker strings verbatim")


# ---------- CLI integration ----------


class CLITests(_RepoCase):
    def test_check_passes_when_changelog_matches(self) -> None:
        self.write_fragment("0001.md", "### x 0.1.0 — 2026-05-24\n\nbody.")
        compiled = build_changelog.compile_changelog(
            BASELINE_CHANGELOG, ["### x 0.1.0 — 2026-05-24\n\nbody."]
        )
        self.write_changelog(compiled)
        with self.cli("--check") as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 0)

    def test_check_fails_when_changelog_does_not_match(self) -> None:
        self.write_fragment("0001.md", "### x 0.1.0 — 2026-05-24\n\nbody.")
        self.write_changelog(BASELINE_CHANGELOG)
        with self.cli("--check") as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 1)
        self.assertIn("### x 0.1.0", out.getvalue())

    def test_default_mode_writes_compiled_changelog(self) -> None:
        self.write_fragment("0001.md", "### x 0.1.0 — 2026-05-24\n\nbody.")
        self.write_changelog(BASELINE_CHANGELOG)
        with self.cli() as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 0)
        after = (self.tmp_path / "CHANGELOG.md").read_text()
        self.assertIn("### x 0.1.0", after)

    def test_default_mode_idempotent(self) -> None:
        self.write_fragment("0001.md", "### x 0.1.0 — 2026-05-24\n\nbody.")
        self.write_changelog(BASELINE_CHANGELOG)
        # First run: writes
        with self.cli() as (out, err, rc):
            pass
        snap = (self.tmp_path / "CHANGELOG.md").read_text()
        # Second run: no-op
        with self.cli() as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 0)
        self.assertIn("already current", out.getvalue())
        self.assertEqual((self.tmp_path / "CHANGELOG.md").read_text(), snap)

    def test_dry_run_prints_without_writing(self) -> None:
        self.write_fragment("0001.md", "### x 0.1.0 — 2026-05-24\n\nbody.")
        self.write_changelog(BASELINE_CHANGELOG)
        before = (self.tmp_path / "CHANGELOG.md").read_text()
        with self.cli("--dry-run") as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 0)
        self.assertIn("### x 0.1.0", out.getvalue())
        self.assertEqual((self.tmp_path / "CHANGELOG.md").read_text(), before)


if __name__ == "__main__":
    unittest.main()
