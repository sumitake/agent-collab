# PR #3 Third-Review Tripwire Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Converge PR #3 after its third post-hoc review round by preserving
SPDX 2.3 timestamp strictness and closing the GitHub command-file redirect
coverage gap without broadening release behavior.

**Architecture:** Treat the lowercase-`z` suggestion as a specification
adjudication, not a parser expansion: explicitly reject lowercase `z` before
the version-dependent standard-library parser and lock that boundary with a
regression test. Replace the workflow test's narrow local regex with one named,
table-tested matcher that covers every official GitHub command-file variable
and the common unquoted shell redirect spellings while leaving quoted targets
valid.

**Tech Stack:** Python 3.10/3.12/3.14 standard library, `unittest`, regular
expressions, GitHub Actions YAML, SPDX 2.3 JSON.

## Global Constraints

- No production workflow, release archive, license, manifest, or package
  content changes. The only production-code change is an explicit rejection
  of an already-invalid lowercase-`z` timestamp.
- No new dependency; Python standard library only.
- SPDX `creationInfo.created` output remains
  `YYYY-MM-DDThh:mm:ssZ` with uppercase `T` and `Z`.
- Numeric-offset inputs used by `git show --format=%cI` remain accepted and
  normalized to UTC.
- Lowercase `z` remains rejected consistently on Python 3.10, 3.12, and
  3.14.
- Command-file coverage includes `GITHUB_ENV`, `GITHUB_OUTPUT`,
  `GITHUB_PATH`, `GITHUB_STATE`, and `GITHUB_STEP_SUMMARY`.
- Detect unquoted `>` and `>>`, optional whitespace, braced or unbraced
  variables, and an optional shell file-descriptor prefix.
- Do not flag direct single- or double-quoted command-file targets.
- This remains a line-level direct-redirect contract, not general shell taint
  analysis: variable aliases, `eval`, and `tee` are outside this bounded
  change and remain review/actionlint concerns.
- All commits are signed; the PR stays draft until exact-head distinct-family
  review converges and every required check is green.

## Threat and Edge-Case Inventory

- **Parser version skew:** Python 3.10 `datetime.fromisoformat` accepts a
  narrower grammar than later versions; manual uppercase-`Z` normalization
  keeps the supported path consistent.
- **Grammar expansion:** accepting lowercase `z` would exceed the SPDX 2.3
  created-field form rather than repair a valid input.
- **Matcher omissions:** a future workflow could target
  `GITHUB_STEP_SUMMARY` or `GITHUB_STATE`, use `>` instead of `>>`,
  omit whitespace, or use `${...}` braces.
- **Matcher overreach:** quoted targets must remain valid, and the regex must
  not reinterpret every shell data flow as a direct redirect.
- **Liveness:** the contract scans all current `.github/workflows/*.yml`
  files on every test run; no cached allowlist is introduced.
- **Rollback:** the remediation is one isolated commit that can be reverted
  without changing the earlier SPDX/path-safety fixes.

---

### Task 1: Enforce the SPDX Timestamp Boundary Before Parser Dispatch

**Files:**
- Modify: `tests/test_release_evidence.py`
- Modify: `scripts/build_release_evidence.py`

**Interfaces:**
- Consumes: `_normalize_created(value: str) -> str`.
- Produces: a cross-version explicit rejection that lowercase `z` is invalid.

- [ ] **Step 1: Add the failing regression test**

```python
def test_created_timestamp_rejects_lowercase_utc_suffix(self) -> None:
    evidence_builder = _load(
        "agent_collab_evidence_lowercase_utc", EVIDENCE_SCRIPT
    )

    with self.assertRaisesRegex(ValueError, "must use uppercase Z"):
        evidence_builder._normalize_created("2026-07-12T00:00:00z")
```

- [ ] **Step 2: Run the regression test and verify the red state**

Run:

```bash
python3 -m unittest tests.test_release_evidence.ReleaseEvidenceTests.test_created_timestamp_rejects_lowercase_utc_suffix -v
```

Expected: FAIL because the existing parser raises its generic ISO 8601 error
instead of enforcing the uppercase-`Z` boundary before parser dispatch.

- [ ] **Step 3: Add the explicit pre-parser guard**

Insert immediately before the existing uppercase-`Z` normalization:

```python
if candidate.endswith("z"):
    raise ValueError("created timestamp must use uppercase Z for UTC")
if candidate.endswith("Z"):
    candidate = candidate[:-1] + "+00:00"
```

- [ ] **Step 4: Rerun the regression test**

Run:

```bash
python3 -m unittest tests.test_release_evidence.ReleaseEvidenceTests.test_created_timestamp_rejects_lowercase_utc_suffix -v
```

Expected: PASS.

- [ ] **Step 5: Record the adjudication in the inline review thread**

Reply with the exact contract evidence: SPDX 2.3 Clause 6.9 requires
`YYYY-MM-DDThh:mm:ssZ`; the builder already normalizes valid uppercase `Z`
and numeric-offset inputs to that form. Resolve the thread only after the
characterization test passes.

### Task 2: Cover Every Direct GitHub Command-File Redirect

**Files:**
- Modify: `tests/test_ci_security_contract.py`

**Interfaces:**
- Produces:
  `UNQUOTED_GITHUB_COMMAND_REDIRECT_RE: re.Pattern[str]`.
- Consumes: every line from `_workflow_texts()`.

- [ ] **Step 1: Add a failing table-driven matcher test**

```python
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
```

- [ ] **Step 2: Run the new test and verify the red state**

Run:

```bash
python3 -m unittest tests.test_ci_security_contract.CiSecurityContractTests.test_command_file_redirect_matcher_covers_official_files_and_syntaxes -v
```

Expected: ERROR because
`UNQUOTED_GITHUB_COMMAND_REDIRECT_RE` is not yet defined.

- [ ] **Step 3: Add the bounded matcher and use it in the live scan**

Add near `FULL_SHA_RE`:

```python
GITHUB_COMMAND_FILE_NAMES = (
    r"GITHUB_(?:ENV|OUTPUT|PATH|STATE|STEP_SUMMARY)"
)
UNQUOTED_GITHUB_COMMAND_REDIRECT_RE = re.compile(
    rf">>?\s*(?![\"'])(?:"
    rf"\$(?:{GITHUB_COMMAND_FILE_NAMES})\b|"
    rf"\$\{{(?:{GITHUB_COMMAND_FILE_NAMES})\}}"
    rf")"
)
```

Then replace the local three-variable `pattern` in
`test_github_command_file_redirects_are_quoted`:

```python
for name, text in self._workflow_texts().items():
    for lineno, line in enumerate(text.splitlines(), 1):
        if UNQUOTED_GITHUB_COMMAND_REDIRECT_RE.search(line):
            unsafe.append(f"{name}:{lineno}:{line.strip()}")
```

- [ ] **Step 4: Run focused tests and verify green**

Run:

```bash
python3 -m unittest tests.test_ci_security_contract tests.test_release_evidence -v
```

Expected: all tests pass; current quoted workflow redirects remain accepted.

### Task 3: Verify, Commit, and Re-enter the Review Gate

**Files:**
- Verify the three implementation/test files from Tasks 1-2 plus this plan.

**Interfaces:**
- Consumes: completed characterization and matcher tests.
- Produces: one signed remediation commit and a new exact-head review request.

- [ ] **Step 1: Run the complete local gate bundle**

```bash
python3 -m unittest discover -s tests -t . -v
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/build_skills.py --check
python3 scripts/build_marketplace.py --check
python3 scripts/build-changelog.py --dry-run >/dev/null
python3 scripts/check_release_consistency.py
python3 scripts/secret_scan.py
python3 scripts/check-public-export-safety.py --active-tree --history
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 2: Rehearse release evidence and validate SPDX 2.3**

Build into a fresh temporary directory, verify the SHA-256 sidecar, parse the
JSON, and run SPDX Tools with `--version SPDX-2.3`.

Expected: archive build, checksum verification, JSON parse, and SPDX validation
all exit 0.

- [ ] **Step 3: Commit and push**

```bash
git add \
  docs/superpowers/plans/2026-07-12-pr3-review-tripwire-remediation.md \
  scripts/build_release_evidence.py \
  tests/test_release_evidence.py \
  tests/test_ci_security_contract.py
git commit -S -m "release: close final review edge cases"
git push origin HEAD:dev/codex/source-available-license
```

- [ ] **Step 4: Re-enter exact-head review**

Answer the two current threads, request a new Gemini Code Assist review, and
keep `cross_check` pending. Merge remains prohibited until that exact-head
review introduces no new material concern, all threads are resolved, and every
required check is green.
