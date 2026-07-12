"""Public CI, CodeQL, secret-scan, and workflow supply-chain contract."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
GITHUB_COMMAND_FILE_NAMES = (
    r"GITHUB_(?:ENV|OUTPUT|PATH|STATE|STEP_SUMMARY)"
)
UNQUOTED_GITHUB_COMMAND_REDIRECT_RE = re.compile(
    rf">>?\s*(?![\"'])(?:"
    rf"\$(?:{GITHUB_COMMAND_FILE_NAMES})\b|"
    rf"\$\{{(?:{GITHUB_COMMAND_FILE_NAMES})\}}"
    rf")"
)


class CiSecurityContractTests(unittest.TestCase):
    def _workflow_texts(self) -> dict[str, str]:
        return {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(WORKFLOWS.glob("*.yml"))
        }

    def test_every_external_action_is_pinned_to_a_full_commit(self) -> None:
        unpinned: list[str] = []
        for name, text in self._workflow_texts().items():
            for lineno, line in enumerate(text.splitlines(), 1):
                match = re.match(r"^\s*-?\s*uses:\s*([^\s#]+)", line)
                if not match:
                    continue
                target = match.group(1).strip("'\"")
                if target.startswith("./"):
                    continue
                _repository, separator, revision = target.rpartition("@")
                if not separator or FULL_SHA_RE.fullmatch(revision) is None:
                    unpinned.append(f"{name}:{lineno}:{target}")
        self.assertEqual(unpinned, [])

    def test_github_command_file_redirects_are_quoted(self) -> None:
        unsafe: list[str] = []
        for name, text in self._workflow_texts().items():
            for lineno, line in enumerate(text.splitlines(), 1):
                if UNQUOTED_GITHUB_COMMAND_REDIRECT_RE.search(line):
                    unsafe.append(f"{name}:{lineno}:{line.strip()}")
        self.assertEqual(unsafe, [])

    def test_command_file_redirect_matcher_covers_official_files_and_syntaxes(
        self,
    ) -> None:
        unsafe = (
            "echo x >> $GITHUB_OUTPUT",
            "echo x >>$GITHUB_ENV",
            "echo x > ${GITHUB_PATH}",
            "echo x 2>>${GITHUB_STEP_SUMMARY}",
            "echo x >> ${GITHUB_STATE}",
        )
        safe = (
            'echo x >> "$GITHUB_OUTPUT"',
            "echo x >> '$GITHUB_ENV'",
            'echo x >>"${GITHUB_PATH}"',
            "echo x >>'${GITHUB_STEP_SUMMARY}'",
        )
        for line in unsafe:
            with self.subTest(line=line):
                self.assertIsNotNone(
                    UNQUOTED_GITHUB_COMMAND_REDIRECT_RE.search(line)
                )
        for line in safe:
            with self.subTest(line=line):
                self.assertIsNone(
                    UNQUOTED_GITHUB_COMMAND_REDIRECT_RE.search(line)
                )

    def test_comprehensive_ci_covers_supported_python_and_contracts(self) -> None:
        path = WORKFLOWS / "ci.yml"
        self.assertTrue(path.is_file(), "comprehensive ci.yml must exist")
        text = path.read_text(encoding="utf-8")
        for token in (
            "pull_request:",
            "workflow_dispatch:",
            "branches: [main]",
            'python: ["3.10", "3.12", "3.14"]',
            "python3 -m unittest discover -s tests -t . -v",
            "python3 -m unittest discover -s scripts -p 'test_*.py' -v",
            "python3 scripts/build_skills.py --check",
            "python3 scripts/build_marketplace.py --check",
            "python3 scripts/build-changelog.py --dry-run",
            "python3 scripts/check_release_consistency.py",
            "python3 scripts/build_plugin_archive.py",
            "python3 scripts/build_release_evidence.py",
            "python3 scripts/check-public-export-safety.py --active-tree",
            "python3 scripts/secret_scan.py",
            "github.com/rhysd/actionlint/cmd/actionlint@v1.7.12",
            "git diff --check",
            "name: Repository Contracts",
            "name: CI",
            "if: always()",
        ):
            self.assertIn(token, text)

    def test_codeql_is_scheduled_extended_python_analysis(self) -> None:
        text = (WORKFLOWS / "codeql.yml").read_text(encoding="utf-8")
        for token in (
            "pull_request:",
            "push:",
            "schedule:",
            "workflow_dispatch:",
            "languages: python",
            "queries: security-extended",
            "security-events: write",
        ):
            self.assertIn(token, text)

    def test_secret_scan_combines_local_and_full_history_scanners(self) -> None:
        text = (WORKFLOWS / "secret-scan.yml").read_text(encoding="utf-8")
        for token in (
            "schedule:",
            "workflow_dispatch:",
            "python scripts/secret_scan.py",
            "fetch-depth: 0",
            "name: Gitleaks",
            "gitleaks/gitleaks-action@ff98106e4c7b2bc287b24eaf42907196329070c7",
        ):
            self.assertIn(token, text)

    def test_public_workflows_never_select_self_hosted_runners(self) -> None:
        for name, text in self._workflow_texts().items():
            with self.subTest(workflow=name):
                runner_lines = [
                    line.lower()
                    for line in text.splitlines()
                    if re.match(r"^\s*runs-on:", line)
                ]
                self.assertTrue(runner_lines, f"{name} has no runner declaration")
                self.assertFalse(
                    any("self-hosted" in line for line in runner_lines),
                    runner_lines,
                )

    def test_sensitive_repository_surfaces_have_explicit_owners(self) -> None:
        text = (ROOT / "CODEOWNERS").read_text(encoding="utf-8")
        for path in (
            "/.github/workflows/",
            "/SECURITY.md",
            "/LICENSE",
            "/NOTICE",
            "/COMMERCIAL-LICENSING.md",
            "/AGENTS.md",
            "/CLAUDE.md",
            "/CODEOWNERS",
        ):
            self.assertRegex(text, rf"(?m)^{re.escape(path)}\s+@sumitake$")

    def test_readme_documents_security_layers_and_distinct_hosts(self) -> None:
        readmes = "\n".join(
            (
                (ROOT / "README.md").read_text(encoding="utf-8"),
                (ROOT / "plugins/agent-collab/README.md").read_text(
                    encoding="utf-8"
                ),
            )
        )
        for token in (
            "GitHub-hosted runners",
            "CodeQL",
            "Gitleaks",
            "secret scanning",
            "full commit SHA",
            "Dependabot",
        ):
            self.assertIn(token, readmes)
        self.assertNotIn("ZCode/OpenCode", readmes)
        self.assertNotIn("OpenCode/ZCode", readmes)


if __name__ == "__main__":
    unittest.main()
