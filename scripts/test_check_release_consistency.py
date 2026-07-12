#!/usr/bin/env python3
"""Unit tests for the version-extraction logic in check_release_consistency.py.

Parsing versions out of Markdown is the brittle surface of the release-
consistency check; these tests pin every extractor against known-good and
known-bad inputs so a regex regression fails loudly here, not silently in
production. CI runs this before trusting the consistency check itself.

Run: python scripts/test_check_release_consistency.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_release_consistency as crc  # noqa: E402


class TestPluginJsonVersion(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(crc.extract_plugin_json_version('{"version": "1.2.3"}'), "1.2.3")

    def test_missing_field(self):
        self.assertIsNone(crc.extract_plugin_json_version('{"name": "x"}'))

    def test_not_json(self):
        self.assertIsNone(crc.extract_plugin_json_version("definitely not json"))


class TestHostManifestConsistency(unittest.TestCase):
    def setUp(self):
        import json
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        plugin = self.root / "plugins" / "agent-collab"
        for host, version in ((".claude-plugin", "3.0.0"), (".codex-plugin", "2.9.0")):
            directory = plugin / host
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "plugin.json").write_text(
                json.dumps({"name": "agent-collab", "version": version}),
                encoding="utf-8",
            )
        (plugin / "README.md").write_text("Current: **3.0.0**\n", encoding="utf-8")
        claude_marketplace = self.root / ".claude-plugin"
        claude_marketplace.mkdir()
        (claude_marketplace / "marketplace.json").write_text(
            json.dumps(
                {
                    "metadata": {"version": "3.0.0"},
                    "plugins": [{"name": "agent-collab", "version": "3.0.0"}],
                }
            ),
            encoding="utf-8",
        )
        codex_marketplace = self.root / ".agents" / "plugins"
        codex_marketplace.mkdir(parents=True)
        (codex_marketplace / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "agent-collab",
                    "plugins": [
                        {
                            "name": "agent-collab",
                            "source": {
                                "source": "local",
                                "path": "./plugins/agent-collab",
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (self.root / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
        fragments = self.root / "changelog.d"
        fragments.mkdir()
        (fragments / "entry.md").write_text(
            "- agent-collab 3.0.0 release\n", encoding="utf-8"
        )
        (self.root / "README.md").write_text(
            "**agent-collab** (v3.0.0)\n## What's new - v3.0.0\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_release_consistency_rejects_codex_manifest_version_drift(self):
        ok, lines = crc.run_consistency(self.root)
        self.assertFalse(ok)
        self.assertTrue(
            any("Codex plugin manifest" in line and "2.9.0" in line for line in lines),
            lines,
        )


class TestLicenseContract(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        plugin = self.root / "plugins" / "agent-collab"
        for host in (".claude-plugin", ".codex-plugin"):
            directory = plugin / host
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "plugin.json").write_text(
                json.dumps(
                    {
                        "name": "agent-collab",
                        "version": "3.1.0",
                        "license": "PolyForm-Strict-1.0.0",
                    }
                ),
                encoding="utf-8",
            )
        marketplace = self.root / ".claude-plugin"
        marketplace.mkdir()
        (marketplace / "marketplace.json").write_text(
            json.dumps(
                {
                    "plugins": [
                        {
                            "name": "agent-collab",
                            "version": "3.1.0",
                            "license": "LicenseRef-PolyForm-Strict-1.0.0",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        license_bytes = (Path(__file__).resolve().parents[1] / "LICENSE").read_bytes()
        notice = (
            "Copyright (c) 2026 John Osumi. All rights reserved except as "
            "expressly granted.\nCommercial licensing is administered by "
            "Osumi Consulting LLC.\n"
        ).encode()
        commercial = (
            "PolyForm Strict License 1.0.0\nexplicit written approval\n"
            "Osumi Consulting LLC\nRepository access\ninstallation\n"
            "GitHub interaction\nacceptance of a contribution\n"
        ).encode()
        for name, data in (
            ("LICENSE", license_bytes),
            ("NOTICE", notice),
            ("COMMERCIAL-LICENSING.md", commercial),
        ):
            (self.root / name).write_bytes(data)
            (plugin / name).write_bytes(data)
        (self.root / "README.md").write_text(
            "PolyForm Strict License 1.0.0\nOsumi Consulting LLC\n"
            "[LICENSE](LICENSE) [NOTICE](NOTICE) "
            "[COMMERCIAL-LICENSING.md](COMMERCIAL-LICENSING.md)\n",
            encoding="utf-8",
        )
        (plugin / "README.md").write_text(
            "PolyForm Strict License 1.0.0\nOsumi Consulting LLC\n"
            "[LICENSE](LICENSE) [NOTICE](NOTICE) "
            "[COMMERCIAL-LICENSING.md](COMMERCIAL-LICENSING.md)\n",
            encoding="utf-8",
        )
        fragments = self.root / "changelog.d"
        fragments.mkdir()
        (fragments / "entry.md").write_text(
            "### agent-collab 3.1.0\nPolyForm Strict License 1.0.0\n"
            "`AGENTS.md`\nOsumi Consulting LLC\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _errors(self):
        self.assertTrue(
            hasattr(crc, "license_contract_errors"),
            "license_contract_errors must enforce release licensing",
        )
        return crc.license_contract_errors(self.root, "3.1.0")

    def test_canonical_license_contract_passes(self):
        self.assertEqual(self._errors(), [])

    def test_manifest_license_drift_is_rejected(self):
        path = self.root / "plugins/agent-collab/.codex-plugin/plugin.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["license"] = "MIT"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(any("Codex manifest license" in e for e in self._errors()))

    def test_packaged_legal_file_drift_is_rejected(self):
        (self.root / "plugins/agent-collab/NOTICE").write_text("changed\n")
        self.assertTrue(any("NOTICE byte parity" in e for e in self._errors()))

    def test_changelog_licensing_drift_is_rejected(self):
        (self.root / "changelog.d/entry.md").write_text(
            "### agent-collab 3.1.0\n",
            encoding="utf-8",
        )
        self.assertTrue(any("changelog" in e for e in self._errors()))


class TestChangelogVersion(unittest.TestCase):
    SAMPLE = (
        "# Changelog - agent-collab marketplace\n\n"
        "## [Unreleased]\n\n"
        "### Marketplace (repo-level)\n- some repo change\n\n"
        "### agent-collab 0.11.0 - 2026-05-21\nnotes\n\n"
        "### agent-collab 0.10.0 - 2026-05-21\nolder\n"
    )

    def test_topmost_wins(self):
        self.assertEqual(crc.extract_changelog_version(self.SAMPLE), "0.11.0")

    def test_marketplace_heading_ignored(self):
        self.assertIsNone(crc.extract_changelog_version("### Marketplace (repo-level)\n"))

    def test_empty(self):
        self.assertIsNone(crc.extract_changelog_version(""))


class TestRootReadmeVersions(unittest.TestCase):
    def test_summary(self):
        self.assertEqual(
            crc.extract_root_summary_version("- **agent-collab** (v0.11.0) - 15 skills"),
            "0.11.0")

    def test_summary_no_version(self):
        self.assertIsNone(crc.extract_root_summary_version("- **agent-collab** - 15 skills"))

    def test_whatsnew_emdash(self):
        self.assertEqual(crc.extract_whatsnew_version("## What's new — v0.11.0\n"), "0.11.0")

    def test_whatsnew_hyphen_tolerated(self):
        self.assertEqual(crc.extract_whatsnew_version("## What's new - v0.11.0\n"), "0.11.0")

    def test_whatsnew_absent(self):
        self.assertIsNone(crc.extract_whatsnew_version("## Something else\n"))


class TestPluginReadmeVersion(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(
            crc.extract_plugin_readme_version("Current: **0.11.0** - the server"), "0.11.0")

    def test_unbolded(self):
        self.assertIsNone(crc.extract_plugin_readme_version("Current: 0.11.0"))


class TestChangelogFragments(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "changelog.d").mkdir()
        (self.root / "changelog.d" / "README.md").write_text("fragment docs\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_fragment_mention_detected(self):
        (self.root / "changelog.d" / "2026-06-28-demo.md").write_text(
            "### Added\n- agent-collab 2.9.0 adds workflow skills.\n"
        )

        self.assertTrue(
            crc.changelog_fragment_mentions(self.root, "agent-collab 2.9.0")
        )

    def test_readme_fragment_ignored(self):
        (self.root / "changelog.d" / "README.md").write_text(
            "### Added\n- agent-collab 2.9.0 adds workflow skills.\n"
        )

        self.assertFalse(
            crc.changelog_fragment_mentions(self.root, "agent-collab 2.9.0")
        )


class TestTagParsing(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(crc.parse_tag("v1.2.3"), "1.2.3")

    def test_plugin_qualified(self):
        # v-<plugin>-X.Y.Z works for any plugin name; canonical agent-collab and
        # deprecation aliases agent-collab-plugin / gemini-collab are all valid.
        self.assertEqual(crc.parse_tag("v-agent-collab-1.2.3"), "1.2.3")
        self.assertEqual(crc.parse_tag("v-agent-collab-plugin-1.2.3"), "1.2.3")
        self.assertEqual(crc.parse_tag("v-gemini-collab-1.2.3"), "1.2.3")

    def test_two_part_rejected(self):
        self.assertIsNone(crc.parse_tag("v1.2"))

    def test_no_v_prefix_rejected(self):
        self.assertIsNone(crc.parse_tag("1.2.3"))

    def test_garbage_rejected(self):
        self.assertIsNone(crc.parse_tag("garbage"))


class TestTagParsingWithPlugin(unittest.TestCase):
    """parse_tag_full additionally returns the plugin name parsed from the tag
    (added 2026-05-25 Phase 1b release-tag follow-up). Plain `vX.Y.Z` returns
    None for the plugin slot so the caller can default to the canonical plugin.
    """

    def test_plain_returns_none_plugin(self):
        self.assertEqual(crc.parse_tag_full("v1.2.3"), (None, "1.2.3"))

    def test_named_plugin(self):
        self.assertEqual(
            crc.parse_tag_full("v-sample-plugin-1.0.0"),
            ("sample-plugin", "1.0.0"))

    def test_other_named_plugin(self):
        self.assertEqual(
            crc.parse_tag_full("v-other-plugin-2.0.0"),
            ("other-plugin", "2.0.0"))

    def test_canonical_explicit(self):
        # `v-agent-collab-X.Y.Z` is equivalent to bare `vX.Y.Z` (both validate
        # against agent-collab/plugin.json), but the explicit form preserves
        # the plugin name in parse_tag_full's first slot for symmetry.
        self.assertEqual(
            crc.parse_tag_full("v-agent-collab-1.2.3"),
            ("agent-collab", "1.2.3"))

    def test_generic_named_tags(self):
        self.assertEqual(
            crc.parse_tag_full("v-sample-plugin-1.2.3"),
            ("sample-plugin", "1.2.3"))
        self.assertEqual(
            crc.parse_tag_full("v-other-plugin-1.2.3"),
            ("other-plugin", "1.2.3"))

    def test_garbage_returns_none_pair(self):
        self.assertEqual(crc.parse_tag_full("garbage"), (None, None))

    def test_two_part_semver_rejected(self):
        self.assertEqual(crc.parse_tag_full("v1.2"), (None, None))

    def test_no_v_prefix_rejected(self):
        self.assertEqual(crc.parse_tag_full("1.2.3"), (None, None))

    def test_empty_string_returns_none_pair(self):
        # Defensive guard (Gemini cross-check concern 5): an empty or
        # whitespace-only tag (e.g., a missing env var that produced "") must
        # not raise; it should fail-soft as not-a-release-tag.
        self.assertEqual(crc.parse_tag_full(""), (None, None))
        self.assertEqual(crc.parse_tag_full("   "), (None, None))

    def test_none_input_returns_none_pair(self):
        # Defensive guard (Gemini cross-check concern 5): a None tag (e.g., a
        # missing-arg path that bypassed argparse) must fail-soft, not
        # AttributeError on tag.strip().
        self.assertEqual(crc.parse_tag_full(None), (None, None))

    def test_parse_tag_backcompat_with_full(self):
        """`parse_tag` is the v-version-only wrapper around parse_tag_full.
        Both should agree on the version slot for every valid tag form."""
        for tag in ("v1.2.3", "v-agent-collab-1.0.0", "v-sample-plugin-2.0.0"):
            with self.subTest(tag=tag):
                _, full_version = crc.parse_tag_full(tag)
                self.assertEqual(crc.parse_tag(tag), full_version)


class TestPluginJsonPath(unittest.TestCase):
    """Per-plugin plugin.json path construction (added 2026-05-25 Phase 1b
    release-tag follow-up). Used by run_tag_check to find the right plugin's
    plugin.json based on the plugin name parsed from the tag.
    """

    def test_canonical(self):
        self.assertEqual(
            crc.plugin_json_path("agent-collab"),
            "plugins/agent-collab/.claude-plugin/plugin.json")

    def test_named_plugin(self):
        self.assertEqual(
            crc.plugin_json_path("sample-plugin"),
            "plugins/sample-plugin/.claude-plugin/plugin.json")

    def test_other_plugin(self):
        self.assertEqual(
            crc.plugin_json_path("other-plugin"),
            "plugins/other-plugin/.claude-plugin/plugin.json")


class TestRunTagCheckPerPlugin(unittest.TestCase):
    """Integration tests for run_tag_check's plugin-aware dispatch. These tests
    create a minimal fake repo tree with plugin.json files for two plugins at
    different versions, then verify the right plugin.json is consulted based on
    the tag form (added 2026-05-25 Phase 1b release-tag follow-up).
    """

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # Canonical agent-collab at 2.0.0 plus two named plugin fixtures.
        # The fake repo only needs the plugin.json files run_tag_check reads.
        for plugin, version in (
            ("agent-collab", "2.0.0"),
            ("sample-plugin", "1.0.0"),
            ("other-plugin", "2.0.0"),
        ):
            d = self.root / "plugins" / plugin / ".claude-plugin"
            d.mkdir(parents=True)
            (d / "plugin.json").write_text(f'{{"name": "{plugin}", "version": "{version}"}}')

    def tearDown(self):
        self._tmp.cleanup()

    def test_canonical_bare_tag_passes(self):
        # `v2.0.0` (no plugin) defaults to agent-collab; agent-collab is at 2.0.0
        ok, lines = crc.run_tag_check(self.root, "v2.0.0")
        self.assertTrue(ok, msg=f"unexpected failure: {lines}")
        self.assertTrue(any("agent-collab" in line for line in lines))

    def test_named_plugin_tag_passes(self):
        # A named tag looks up that named plugin's plugin.json.
        # This was the exact failure mode that motivated Phase 1b's release-tag
        # follow-up (pre-fix: compared the version to agent-collab's version -> FAIL).
        ok, lines = crc.run_tag_check(self.root, "v-sample-plugin-1.0.0")
        self.assertTrue(ok, msg=f"unexpected failure: {lines}")
        self.assertTrue(any("sample-plugin" in line and "1.0.0" in line for line in lines))

    def test_other_plugin_tag_passes(self):
        ok, lines = crc.run_tag_check(self.root, "v-other-plugin-2.0.0")
        self.assertTrue(ok, msg=f"unexpected failure: {lines}")
        self.assertTrue(any("other-plugin" in line for line in lines))

    def test_version_mismatch_fails_with_named_plugin(self):
        # Tag version doesn't match the named plugin's plugin.json -> FAIL,
        # and the failure message names the actual plugin (not the canonical
        # default) so the operator can diagnose without re-reading the workflow.
        ok, lines = crc.run_tag_check(self.root, "v-sample-plugin-9.9.9")
        self.assertFalse(ok)
        self.assertTrue(any("sample-plugin" in line and "9.9.9" in line and "1.0.0" in line
                            for line in lines), msg=f"expected named-plugin diagnostic, got: {lines}")

    def test_unknown_plugin_fails_with_path_diagnostic(self):
        # Tag names a plugin that doesn't exist in the repo -> FAIL with a
        # diagnostic pointing at the missing plugin.json path.
        ok, lines = crc.run_tag_check(self.root, "v-bogus-plugin-1.0.0")
        self.assertFalse(ok)
        self.assertTrue(any("bogus-plugin" in line and "plugin.json" in line
                            for line in lines), msg=f"expected path diagnostic, got: {lines}")

    def test_garbage_tag_fails(self):
        ok, lines = crc.run_tag_check(self.root, "garbage")
        self.assertFalse(ok)
        self.assertTrue(any("not a release-tag form" in line for line in lines))


class TestPluginVersion(unittest.TestCase):
    """plugin_version is the per-plugin reader run_tag_check delegates to.
    Mirrors the path construction tests above with read-side coverage."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        d = self.root / "plugins" / "agent-collab" / ".claude-plugin"
        d.mkdir(parents=True)
        (d / "plugin.json").write_text('{"name": "agent-collab", "version": "1.0.0"}')

    def tearDown(self):
        self._tmp.cleanup()

    def test_reads_named_plugin(self):
        self.assertEqual(crc.plugin_version(self.root, "agent-collab"), "1.0.0")

    def test_missing_plugin_returns_none(self):
        self.assertIsNone(crc.plugin_version(self.root, "not-a-plugin"))


class TestRunMonotonicityPerPlugin(unittest.TestCase):
    """Per-plugin monotonicity (added 2026-05-25 Phase 1b release-tag follow-up
    cycle 2; integrates Gemini cross-check concern #2 from PR #67). The
    `plugin` parameter lets `run_monotonicity` assert non-regression on the
    specific plugin a release tag targets, instead of always agent-collab.

    These tests mock `_git_show_version` to avoid needing a real git repo;
    the function-under-test is `run_monotonicity`'s decision logic, not git
    plumbing (which is already covered by the file-system fixtures elsewhere).
    """

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for plugin, version in (
            ("agent-collab", "2.0.0"),
            ("sample-plugin", "1.0.0"),
            ("other-plugin", "2.0.0"),
        ):
            d = self.root / "plugins" / plugin / ".claude-plugin"
            d.mkdir(parents=True)
            (d / "plugin.json").write_text(f'{{"name": "{plugin}", "version": "{version}"}}')
        # Monkeypatch _git_show_version to return canned per-plugin/per-ref versions
        self._saved_git_show = crc._git_show_version

        def fake_git_show(root, ref, plugin=crc.PLUGIN):
            # Pretend the previous ref had the same versions; bumps tested via
            # explicit overrides in individual tests when needed.
            return {
                "agent-collab": "1.3.0",
                "sample-plugin": "0.9.9",  # < 1.0.0 → forward bump
                "other-plugin": "1.3.0",
            }.get(plugin)
        crc._git_show_version = fake_git_show

    def tearDown(self):
        crc._git_show_version = self._saved_git_show
        self._tmp.cleanup()

    def test_default_canonical(self):
        # No plugin arg → uses canonical (agent-collab 2.0.0 >= ref 1.3.0)
        ok, lines = crc.run_monotonicity(self.root, "HEAD~1")
        self.assertTrue(ok, msg=f"unexpected failure: {lines}")
        self.assertTrue(any("agent-collab" in line and "2.0.0" in line and "1.3.0" in line
                            for line in lines))

    def test_explicit_canonical(self):
        # Explicit plugin="agent-collab" must match default behavior
        ok, lines = crc.run_monotonicity(self.root, "HEAD~1", plugin="agent-collab")
        self.assertTrue(ok, msg=f"unexpected failure: {lines}")

    def test_none_plugin_falls_back_to_canonical(self):
        # plugin=None must also fall back to canonical (preserves
        # `run_monotonicity(root, ref)` legacy invocation signature)
        ok, lines = crc.run_monotonicity(self.root, "HEAD~1", plugin=None)
        self.assertTrue(ok, msg=f"unexpected failure: {lines}")
        self.assertTrue(any("agent-collab" in line for line in lines))

    def test_named_plugin_forward(self):
        ok, lines = crc.run_monotonicity(self.root, "HEAD~1", plugin="sample-plugin")
        self.assertTrue(ok, msg=f"unexpected failure: {lines}")
        self.assertTrue(any("sample-plugin" in line and "1.0.0" in line and "0.9.9" in line
                            for line in lines))

    def test_other_plugin_forward(self):
        ok, lines = crc.run_monotonicity(self.root, "HEAD~1", plugin="other-plugin")
        self.assertTrue(ok, msg=f"unexpected failure: {lines}")

    def test_regression_fails_with_named_plugin(self):
        # Simulate a regression for a named plugin.
        def fake_git_show_regression(root, ref, plugin=crc.PLUGIN):
            return {"sample-plugin": "2.0.0"}.get(plugin)
        crc._git_show_version = fake_git_show_regression
        ok, lines = crc.run_monotonicity(self.root, "HEAD~1", plugin="sample-plugin")
        self.assertFalse(ok)
        # Failure must name the actual plugin so the operator can diagnose
        self.assertTrue(any("sample-plugin" in line and "regressed" in line
                            for line in lines), msg=f"expected plugin-named regression diagnostic, got: {lines}")

    def test_missing_plugin_json_fails(self):
        ok, lines = crc.run_monotonicity(self.root, "HEAD~1", plugin="bogus-plugin")
        self.assertFalse(ok)
        self.assertTrue(any("bogus-plugin" in line and "plugin.json" in line
                            for line in lines), msg=f"expected path diagnostic, got: {lines}")

    def test_skip_when_ref_proves_no_plugin_json(self):
        # None is reserved for a successfully-read ref whose tree proves this
        # plugin path did not exist yet.
        def fake_git_show_none(root, ref, plugin=None):
            return None
        crc._git_show_version = fake_git_show_none
        ok, lines = crc.run_monotonicity(self.root, "HEAD~1", plugin="sample-plugin")
        self.assertTrue(ok)
        self.assertTrue(any("SKIP" in line and "sample-plugin" in line for line in lines))

    def test_ref_read_error_fails_closed(self):
        def fake_git_show_error(root, ref, plugin=None):
            raise crc.GitReadError("unreadable ref")
        crc._git_show_version = fake_git_show_error
        ok, lines = crc.run_monotonicity(
            self.root, "origin/main", plugin="sample-plugin"
        )
        self.assertFalse(ok)
        self.assertTrue(any("cannot read" in line for line in lines), lines)


class TestGitShowVersionDefensive(unittest.TestCase):
    """Defensive None-handling in _git_show_version (added 2026-05-25 cycle 2
    per Gemini cross-check concern #2 on this PR): an explicit `plugin=None`
    must fall back to PLUGIN rather than propagating None into
    `plugin_json_path` (which would interpolate `"plugins/None/.claude-plugin/plugin.json"`
    and fail confusingly at the git-show step).

    `run_monotonicity` already maps None → PLUGIN before calling
    `_git_show_version`, but the defensive guard is still appropriate so
    future callers can't accidentally pass None directly. Test is structural:
    we monkeypatch subprocess.run to capture the path argument and assert
    PLUGIN's path is used (not "plugins/None/...").
    """

    def test_none_plugin_falls_back_to_canonical_path(self):
        # Monkeypatch subprocess.run to capture the path argument
        import subprocess as _subprocess
        captured = []

        class _CaptureResult:
            def __init__(self):
                self.returncode = 0
                self.stdout = '{"version": "1.0.0"}'

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return _CaptureResult()
        saved_run = _subprocess.run
        _subprocess.run = fake_run
        crc.subprocess.run = fake_run  # reset module-level reference too
        try:
            crc._git_show_version(Path("/tmp"), "HEAD", plugin=None)
        finally:
            _subprocess.run = saved_run
            crc.subprocess.run = saved_run

        # Assert the captured command's tree-ish argument names the canonical
        # plugin's path, not "plugins/None/..."
        self.assertTrue(captured, msg="subprocess.run was not invoked")
        cmd = captured[0]
        tree_ish = cmd[-1]  # last arg is "HEAD:plugins/<plugin>/.claude-plugin/plugin.json"
        self.assertIn(crc.PLUGIN, tree_ish,
                      msg=f"expected canonical PLUGIN in tree-ish, got: {tree_ish}")
        self.assertNotIn("plugins/None/", tree_ish,
                         msg=f"plugin=None must NOT propagate into the path: {tree_ish}")


class TestMainCrossFlagComposition(unittest.TestCase):
    """When `main()` is invoked with BOTH `--tag` and `--against-ref`, the
    plugin name parsed from the tag must flow into `run_monotonicity` so
    non-regression is asserted on the right plugin. Tests the integration
    seam between `parse_tag_full` and `run_monotonicity` via `main`'s
    argparse plumbing (added 2026-05-25 Phase 1b release-tag follow-up
    cycle 2).
    """

    def setUp(self):
        # Capture run_monotonicity invocations so we can assert the `plugin`
        # arg matches expectations. Tests don't need a real git ref.
        self._captured = []
        self._saved_run_monotonicity = crc.run_monotonicity

        def fake_run_monotonicity(root, ref, plugin=None):
            self._captured.append({"root": root, "ref": ref, "plugin": plugin})
            return True, [f"PASS  fake monotonicity (plugin={plugin})"]
        crc.run_monotonicity = fake_run_monotonicity

        # Stub run_consistency + run_tag_check so we exercise just main()
        # composition without real file-system / git assertions.
        self._saved_run_consistency = crc.run_consistency
        crc.run_consistency = lambda root: (True, ["PASS  fake consistency"])
        self._saved_run_tag_check = crc.run_tag_check
        crc.run_tag_check = lambda root, tag: (True, [f"PASS  fake tag check ({tag})"])

    def tearDown(self):
        crc.run_monotonicity = self._saved_run_monotonicity
        crc.run_consistency = self._saved_run_consistency
        crc.run_tag_check = self._saved_run_tag_check

    def test_tag_and_ref_with_canonical_default(self):
        # Bare `v2.0.0` tag + --against-ref → monotonicity_plugin=None
        # (run_monotonicity falls back to canonical agent-collab)
        rc = crc.main(["--tag", "v2.0.0", "--against-ref", "HEAD~1"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(self._captured), 1)
        self.assertIsNone(self._captured[0]["plugin"],
                          msg="bare vX.Y.Z tag should pass plugin=None (canonical default)")

    def test_tag_and_ref_with_plugin_qualified(self):
        # `v-agent-collab-1.0.0` tag → monotonicity_plugin="agent-collab"
        # (run_monotonicity asserts non-regression on agent-collab specifically)
        rc = crc.main(["--tag", "v-agent-collab-1.0.0", "--against-ref", "HEAD~1"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(self._captured), 1)
        self.assertEqual(self._captured[0]["plugin"], "agent-collab",
                         msg="v-agent-collab-X.Y.Z tag should forward 'agent-collab' to run_monotonicity")

    def test_ref_only_preserves_canonical(self):
        # --against-ref WITHOUT --tag → monotonicity_plugin=None
        # (legacy invocation signature; preserves pre-cycle-2 behavior)
        rc = crc.main(["--against-ref", "HEAD~1"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(self._captured), 1)
        self.assertIsNone(self._captured[0]["plugin"],
                          msg="legacy --against-ref alone should pass plugin=None")

    def test_tag_only_skips_monotonicity(self):
        # --tag without --against-ref → run_monotonicity not invoked at all
        rc = crc.main(["--tag", "v-agent-collab-1.0.0"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(self._captured), 0,
                         msg="--tag alone should NOT invoke run_monotonicity")


class TestSemverOrdering(unittest.TestCase):
    def test_greater(self):
        self.assertGreaterEqual(crc.semver_tuple("0.11.0"), crc.semver_tuple("0.10.0"))

    def test_equal(self):
        self.assertEqual(crc.semver_tuple("1.0.0"), crc.semver_tuple("1.0.0"))

    def test_lesser(self):
        self.assertLess(crc.semver_tuple("0.10.0"), crc.semver_tuple("0.11.0"))


if __name__ == "__main__":
    unittest.main()
