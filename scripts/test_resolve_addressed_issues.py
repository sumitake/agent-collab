#!/usr/bin/env python3
"""Deterministic tests for the release issue-resolution marker parser."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve_addressed_issues import (  # noqa: E402
    extract_addressed_issue_numbers,
    scan_pathspec,
    select_actionable,
    _MAX_ISSUES_PER_RUN,
)


class ExtractAddressedTests(unittest.TestCase):
    def test_added_marker_single(self) -> None:
        diff = "+Addressed: #125\n"
        self.assertEqual(extract_addressed_issue_numbers(diff), [125])

    def test_bulleted_and_multiple_on_one_line(self) -> None:
        diff = "+- Addressed: #130, #131 and #7\n"
        self.assertEqual(extract_addressed_issue_numbers(diff), [7, 130, 131])

    def test_case_insensitive_keyword(self) -> None:
        self.assertEqual(extract_addressed_issue_numbers("+addressed: #9\n"), [9])
        self.assertEqual(extract_addressed_issue_numbers("+ADDRESSED: #9\n"), [9])

    def test_dedup_and_sort_across_lines(self) -> None:
        diff = "+Addressed: #5\n+Addressed: #5, #2\n+- Addressed: #9\n"
        self.assertEqual(extract_addressed_issue_numbers(diff), [2, 5, 9])

    def test_removed_lines_are_ignored(self) -> None:
        # A marker being DELETED must never close an issue.
        self.assertEqual(extract_addressed_issue_numbers("-Addressed: #42\n"), [])

    def test_context_lines_are_ignored(self) -> None:
        self.assertEqual(extract_addressed_issue_numbers(" Addressed: #42\n"), [])

    def test_file_header_plus_plus_plus_ignored(self) -> None:
        diff = "+++ b/CHANGELOG.md\n+Addressed: #3\n"
        self.assertEqual(extract_addressed_issue_numbers(diff), [3])

    def test_hash_in_prose_is_not_a_marker(self) -> None:
        # #123 not on an Addressed: line must not be picked up.
        diff = "+Fixed the thing described in #123 (see issue).\n"
        self.assertEqual(extract_addressed_issue_numbers(diff), [])

    def test_marker_must_start_the_line(self) -> None:
        # Trailing 'Addressed:' inside prose should not match (own-line marker).
        diff = "+We finally Addressed: #55 last week\n"
        self.assertEqual(extract_addressed_issue_numbers(diff), [])

    def test_bare_hash_without_number_ignored(self) -> None:
        self.assertEqual(extract_addressed_issue_numbers("+Addressed: nothing\n"), [])

    def test_realistic_fragment_diff(self) -> None:
        diff = (
            "diff --git a/changelog.d/x.md b/changelog.d/x.md\n"
            "+++ b/changelog.d/x.md\n"
            "@@ -0,0 +1,4 @@\n"
            "+### Fixed\n"
            "+- Correct the coordinator timeout_ms validation bound.\n"
            "+\n"
            "+Addressed: #125\n"
        )
        self.assertEqual(extract_addressed_issue_numbers(diff), [125])

    def test_empty_and_no_markers(self) -> None:
        self.assertEqual(extract_addressed_issue_numbers(""), [])
        self.assertEqual(
            extract_addressed_issue_numbers("+### Added\n+- a feature\n"), []
        )


    def test_issue_zero_is_dropped(self) -> None:
        self.assertEqual(extract_addressed_issue_numbers("+Addressed: #0\n"), [])
        self.assertEqual(extract_addressed_issue_numbers("+Addressed: #0, #4\n"), [4])


class ScanPathspecTests(unittest.TestCase):
    def test_excludes_readme_and_archived(self) -> None:
        spec = scan_pathspec()
        self.assertIn("CHANGELOG.md", spec)
        self.assertIn("changelog.d/", spec)
        self.assertIn(":(exclude)changelog.d/README.md", spec)
        self.assertIn(":(exclude)changelog.d/archived/", spec)


class SelectActionableTests(unittest.TestCase):
    def test_passes_through_under_cap(self) -> None:
        nums = list(range(1, 11))
        self.assertEqual(select_actionable(nums), nums)

    def test_at_cap_allowed(self) -> None:
        nums = list(range(1, _MAX_ISSUES_PER_RUN + 1))
        self.assertEqual(select_actionable(nums), nums)

    def test_over_cap_refuses_all(self) -> None:
        nums = list(range(1, _MAX_ISSUES_PER_RUN + 2))
        self.assertEqual(select_actionable(nums), [])


if __name__ == "__main__":
    unittest.main()
