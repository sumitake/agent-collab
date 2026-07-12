"""Tests for scaffold-skill-spec.py — skill-spec skeleton generator.

Stdlib-only (unittest). Loads the script via importlib since the filename
has a hyphen.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

# Load scaffold-skill-spec.py as a module.
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = SCRIPT_DIR / "scaffold-skill-spec.py"
_spec = importlib.util.spec_from_file_location("scaffold", SCRIPT_PATH)
scaffold = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scaffold)


class _CLICase(unittest.TestCase):
    """Common setup: temp output dir for scaffold writes."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @contextlib.contextmanager
    def cli(self, *argv: str):
        """Run main() with argv + capture stdout/stderr."""
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        rc_holder: dict[str, int] = {}
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            rc_holder["rc"] = scaffold.main(list(argv))
        yield out_buf, err_buf, rc_holder


# ---------- classify_verifier_independence ----------


class ClassifyVerifierIndependenceTests(unittest.TestCase):
    def test_yes_list(self):
        for name in scaffold.VERIFIER_INDEPENDENCE_YES:
            include, hint = scaffold.classify_verifier_independence(name)
            self.assertTrue(include, f"{name} should default to INCLUDED")
            self.assertIn("YES", hint)

    def test_no_list(self):
        for name in scaffold.VERIFIER_INDEPENDENCE_NO:
            include, hint = scaffold.classify_verifier_independence(name)
            self.assertFalse(include, f"{name} should default to OMITTED")
            self.assertIn("NO", hint)

    def test_unclassified_defaults_to_included(self):
        include, hint = scaffold.classify_verifier_independence("brand-new-skill")
        self.assertTrue(include, "unclassified names should default to INCLUDED")
        self.assertIn("UNCLASSIFIED", hint)


# ---------- classify_default_tier ----------


class ClassifyDefaultTierTests(unittest.TestCase):
    def test_flash_for_throughput(self):
        for name in scaffold.DEFAULT_TIER_FLASH:
            self.assertEqual(scaffold.classify_default_tier(name), "flash")

    def test_pro_for_reasoning_heavy(self):
        # Sample reasoning-heavy skills
        for name in ("second-opinion", "debate", "code-review", "red-team", "ai-merge-resolve"):
            self.assertEqual(scaffold.classify_default_tier(name), "pro")

    def test_pro_for_unclassified(self):
        self.assertEqual(scaffold.classify_default_tier("brand-new-skill"), "pro")


# ---------- render_template ----------


class RenderTemplateTests(unittest.TestCase):
    def test_includes_frontmatter(self):
        body = scaffold.render_template(
            "test-skill",
            include_verifier_independence=False,
            default_tier="pro",
        )
        self.assertTrue(body.startswith("---\n"))
        self.assertIn("name: test-skill", body)
        self.assertIn("version: 0.1.0", body)
        self.assertIn("description: TODO", body)

    def test_includes_verifier_block_when_requested(self):
        body = scaffold.render_template(
            "test-skill",
            include_verifier_independence=True,
            default_tier="pro",
        )
        self.assertIn("<!-- verifier-independence:start -->", body)
        self.assertIn("<!-- verifier-independence:end -->", body)
        self.assertIn("Verifier independence", body)

    def test_omits_verifier_block_when_not_requested(self):
        body = scaffold.render_template(
            "test-skill",
            include_verifier_independence=False,
            default_tier="pro",
        )
        self.assertNotIn("<!-- verifier-independence:start -->", body)
        self.assertNotIn("<!-- verifier-independence:end -->", body)
        # The "this skill does NOT make a verifier-independence claim" comment is there
        self.assertIn("does NOT make a verifier-independence claim", body)

    def test_default_tier_pro_threads_through(self):
        body = scaffold.render_template(
            "test-skill",
            include_verifier_independence=False,
            default_tier="pro",
        )
        self.assertIn("model: 'pro'", body)
        self.assertIn("{{ tier_pro_resolves_to }}", body)
        self.assertIn("The `flash` tier is the wrong choice", body)

    def test_default_tier_flash_threads_through(self):
        body = scaffold.render_template(
            "test-skill",
            include_verifier_independence=False,
            default_tier="flash",
        )
        self.assertIn("model: 'flash'", body)
        self.assertIn("{{ tier_flash_resolves_to }}", body)
        self.assertIn("The `pro` tier is the wrong choice", body)

    def test_placeholders_preserved(self):
        """The build system will substitute these; the template must
        emit them in `{{ var }}` form (not interpolate them)."""
        body = scaffold.render_template(
            "test-skill",
            include_verifier_independence=True,
            default_tier="pro",
        )
        for placeholder in (
            "{{ primary_agent }}",
            "{{ primary_family }}",
            "{{ verifier_agent }}",
            "{{ verifier_family }}",
            "{{ mcp_tool_ask }}",
            "{{ mcp_tool_ask_short }}",
            "{{ tier_pro_resolves_to }}",
        ):
            self.assertIn(placeholder, body, f"missing placeholder: {placeholder}")

    def test_classification_hint_appears_in_body(self):
        body = scaffold.render_template(
            "test-skill",
            include_verifier_independence=True,
            default_tier="pro",
            classification_hint="YES (explicit)",
        )
        self.assertIn("scaffold note: verifier-independence", body)
        self.assertIn("YES (explicit)", body)

    def test_display_name_titlecased(self):
        body = scaffold.render_template(
            "code-review",
            include_verifier_independence=True,
            default_tier="pro",
        )
        self.assertIn("# Code Review", body)


# ---------- CLI ----------


class CLITests(_CLICase):
    def test_invalid_name_rejected(self):
        with self.cli("Bad_Name") as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 2)
        self.assertIn("does not match", err.getvalue())

    def test_uppercase_name_rejected(self):
        with self.cli("BadName") as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 2)

    def test_starts_with_digit_rejected(self):
        with self.cli("1skill") as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 2)

    def test_dry_run_prints_skeleton_no_write(self):
        out_path = self.tmp_path / "test-skill.md"
        with self.cli("test-skill", "--out", str(out_path), "--dry-run") as (
            out, err, rc
        ):
            pass
        self.assertEqual(rc["rc"], 0)
        self.assertIn("name: test-skill", out.getvalue())
        self.assertFalse(out_path.exists())

    def test_writes_to_default_path(self):
        # Override the SPECS_DIR via --out (avoids touching the real specs dir)
        out_path = self.tmp_path / "my-skill.md"
        with self.cli("my-skill", "--out", str(out_path)) as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 0)
        self.assertTrue(out_path.exists())
        self.assertIn("name: my-skill", out_path.read_text())
        self.assertIn("OK: scaffolded", out.getvalue())

    def test_refuses_existing_file_without_force(self):
        out_path = self.tmp_path / "existing.md"
        out_path.write_text("existing content")
        with self.cli("existing", "--out", str(out_path)) as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 1)
        self.assertIn("already exists", err.getvalue())
        # File contents must be preserved
        self.assertEqual(out_path.read_text(), "existing content")

    def test_force_overwrites_existing_file(self):
        out_path = self.tmp_path / "existing.md"
        out_path.write_text("existing content")
        with self.cli("existing", "--out", str(out_path), "--force") as (
            out, err, rc
        ):
            pass
        self.assertEqual(rc["rc"], 0)
        self.assertIn("name: existing", out_path.read_text())

    def test_explicit_verifier_independence_yes(self):
        out_path = self.tmp_path / "x.md"
        with self.cli(
            "brainstorm", "--out", str(out_path), "--verifier-independence", "YES"
        ) as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 0)
        body = out_path.read_text()
        self.assertIn("<!-- verifier-independence:start -->", body)

    def test_explicit_verifier_independence_no(self):
        out_path = self.tmp_path / "x.md"
        with self.cli(
            "second-opinion", "--out", str(out_path), "--verifier-independence", "NO"
        ) as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 0)
        body = out_path.read_text()
        self.assertNotIn("<!-- verifier-independence:start -->", body)

    def test_auto_verifier_independence_for_yes_listed(self):
        out_path = self.tmp_path / "x.md"
        with self.cli("second-opinion", "--out", str(out_path)) as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 0)
        body = out_path.read_text()
        self.assertIn("<!-- verifier-independence:start -->", body)
        self.assertIn("YES (explicit YES list)", body)

    def test_auto_verifier_independence_for_no_listed(self):
        out_path = self.tmp_path / "x.md"
        with self.cli("brainstorm", "--out", str(out_path)) as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 0)
        body = out_path.read_text()
        self.assertNotIn("<!-- verifier-independence:start -->", body)

    def test_explicit_default_tier_flash(self):
        out_path = self.tmp_path / "x.md"
        with self.cli(
            "second-opinion", "--out", str(out_path), "--default-tier", "flash"
        ) as (out, err, rc):
            pass
        self.assertEqual(rc["rc"], 0)
        body = out_path.read_text()
        self.assertIn("model: 'flash'", body)

    def test_help_includes_design_rationale(self):
        """--help should at least not crash."""
        with self.assertRaises(SystemExit) as cm:
            scaffold.parse_args(["--help"])
        self.assertEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
