# Agent Collab v3.1.0 Source-Available License Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release agent-collab v3.1.0 under PolyForm Strict 1.0.0 with John Osumi as copyright owner, commercial approvals administered by Osumi Consulting LLC, and `AGENTS.md` as the public repository's canonical agent guidance.

**Architecture:** Keep one canonical copy of repository instructions in root `AGENTS.md` and one canonical copy of each legal document at the repository root. Claude receives the same instructions through a minimal `CLAUDE.md` import; the installed plugin receives exact legal-file copies enforced by byte-parity and archive tests. Version, license metadata, contributor-rights governance, deterministic SPDX evidence, checksums, generated skills, marketplaces, documentation, and release automation move together as one policy-only v3.1.0 release.

**Tech Stack:** Markdown, JSON manifests, Python 3.12 standard library, `unittest`, deterministic gzip/tar archives, SPDX 2.3 JSON, GitHub Actions, signed Git tags.

## Global Constraints

- Public license: unmodified PolyForm Strict License 1.0.0.
- Official license source: `https://raw.githubusercontent.com/polyformproject/polyform-licenses/1.0.0/PolyForm-Strict-1.0.0.md` with SHA-256 `9eb48619fbc193ab7bb327b090cfcc703000265b83e670f81f231d0b1c43c56e`.
- Copyright notice: `Copyright (c) 2026 John Osumi. All rights reserved except as expressly granted.`
- Commercial licensing statement: `Commercial licensing is administered by Osumi Consulting LLC.`
- Commercial use requires separate explicit written approval from Osumi Consulting LLC.
- Public plugin manifest identifier: `PolyForm-Strict-1.0.0`.
- SPDX expression: `LicenseRef-PolyForm-Strict-1.0.0`.
- Target package and release version: `agent-collab` `3.1.0`, tag `v3.1.0`.
- Release mode remains `policy-only`; no native runtime is added or activated.
- Root `AGENTS.md` is the only canonical repository-instruction file; root `CLAUDE.md` only imports `@AGENTS.md`.
- No private workspace, provider backend, credential, private path, or retired plugin content may enter the public tree, history, archive, or release evidence.
- External contributions require an operator-confirmed written rights agreement; a DCO alone is insufficient.
- Every third-party GitHub Action reference is pinned to a full 40-character commit SHA.
- Comprehensive CI runs Python 3.10, 3.12, and 3.14 plus repository-contract validation.
- CodeQL uses Python `security-extended` queries on pull request, `main`, weekly schedule, and manual dispatch.
- Secret scanning combines the local scanner, Gitleaks full-history scanning, and GitHub native scanning/push protection.
- README prose names `OpenCode` and `ZCode` separately and contains neither `ZCode/OpenCode` nor `OpenCode/ZCode`.

---

### Task 1: Canonical Agent-Neutral Repository Instructions

**Files:**
- Create: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/public-governance.md`
- Modify: `tests/test_public_distribution_contract.py`
- Modify: `scripts/scaffold-skill-spec.py`
- Modify: `scripts/check_pr_compliance.py`

**Interfaces:**
- Consumes: the existing 65-line repository development guide in `CLAUDE.md`.
- Produces: canonical `AGENTS.md`; exact Claude compatibility loader `# Claude Code compatibility\n\n@AGENTS.md\n`; tests that reject canonical-policy duplication in `CLAUDE.md`.

- [ ] **Step 1: Write the failing instruction-discovery contract tests**

Add to `tests/test_public_distribution_contract.py`:

```python
    def test_agent_neutral_guidance_is_canonical(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

        self.assertIn("# agent-collab development guide", agents)
        self.assertIn("## Source boundaries", agents)
        self.assertEqual(claude, "# Claude Code compatibility\n\n@AGENTS.md\n")
        self.assertNotIn("## Source boundaries", claude)
```

Add `ROOT / "AGENTS.md"` to the public-file sanitation tuple while retaining `CLAUDE.md`.

- [ ] **Step 2: Run the focused test and verify the expected failure**

Run: `python3 -m unittest tests.test_public_distribution_contract.PublicDistributionContractTests.test_agent_neutral_guidance_is_canonical -v`

Expected: FAIL because root `AGENTS.md` does not exist.

- [ ] **Step 3: Move policy into `AGENTS.md` and reduce `CLAUDE.md` to an import**

Copy the complete current `CLAUDE.md` development guide byte-for-byte into `AGENTS.md`, then replace `CLAUDE.md` with:

```markdown
# Claude Code compatibility

@AGENTS.md
```

Change `docs/public-governance.md` to identify `AGENTS.md` as the authoritative source. Reword active script comments and scaffolding guidance so public repository policy points to `AGENTS.md` or to the named trigger/governance contract rather than a private workspace directive.

- [ ] **Step 4: Run focused tests and reference scan**

Run:

```bash
python3 -m unittest tests.test_public_distribution_contract -v
rg -n 'CLAUDE\.md.*(defines|authoritative|directive)|project CLAUDE\.md|workspace CLAUDE\.md' AGENTS.md CLAUDE.md README.md docs scripts tests
```

Expected: tests PASS; scan returns no active statement treating public `CLAUDE.md` as canonical.

- [ ] **Step 5: Commit the instruction-source change**

```bash
git add AGENTS.md CLAUDE.md docs/public-governance.md tests/test_public_distribution_contract.py scripts/scaffold-skill-spec.py scripts/check_pr_compliance.py
git commit -S -m "docs: make AGENTS the canonical repository guide"
```

### Task 2: Canonical Legal Documents and Plugin Archive Parity

**Files:**
- Create: `LICENSE`
- Create: `NOTICE`
- Create: `COMMERCIAL-LICENSING.md`
- Create: `plugins/agent-collab/LICENSE`
- Create: `plugins/agent-collab/NOTICE`
- Create: `plugins/agent-collab/COMMERCIAL-LICENSING.md`
- Modify: `scripts/build_plugin_archive.py`
- Modify: `tests/test_plugin_archive.py`
- Modify: `tests/test_public_distribution_contract.py`

**Interfaces:**
- Consumes: the official PolyForm text and approved ownership/approval terms.
- Produces: three root legal documents, exact plugin copies, mandatory archive members, and byte-parity enforcement.

- [ ] **Step 1: Write failing legal-file and archive tests**

Add constants in `tests/test_plugin_archive.py`:

```python
LEGAL_FILES = ("LICENSE", "NOTICE", "COMMERCIAL-LICENSING.md")
```

Extend the policy-only archive test to assert all three names exist and each archived file equals both the root and plugin copy. Add:

```python
    def test_packaged_legal_files_match_repository_canonicals(self) -> None:
        for name in LEGAL_FILES:
            self.assertEqual(
                (PLUGIN / name).read_bytes(),
                (ROOT / name).read_bytes(),
                name,
            )
```

Add a public-distribution test asserting the notice contains the exact copyright and administrator statements and the commercial document states that repository access, installation, GitHub interaction, and contribution acceptance do not grant commercial approval.

- [ ] **Step 2: Run the legal-file tests and verify expected failures**

Run:

```bash
python3 -m unittest tests.test_plugin_archive.PluginArchiveTests.test_packaged_legal_files_match_repository_canonicals -v
python3 -m unittest tests.test_public_distribution_contract -v
```

Expected: FAIL because the legal files are absent.

- [ ] **Step 3: Add the approved legal documents**

Create root `LICENSE` from the official tagged PolyForm Strict file without changing its text. Verify its digest:

```bash
shasum -a 256 LICENSE
```

Expected: `9eb48619fbc193ab7bb327b090cfcc703000265b83e670f81f231d0b1c43c56e  LICENSE`.

Create `NOTICE` with exactly:

```text
Copyright (c) 2026 John Osumi. All rights reserved except as expressly granted.
Commercial licensing is administered by Osumi Consulting LLC.
```

Create `COMMERCIAL-LICENSING.md` explaining:

- the public grant is PolyForm Strict 1.0.0;
- commercial use requires explicit written approval from Osumi Consulting LLC;
- approval must identify the licensee and permitted scope;
- access, installation, GitHub activity, and accepted contributions are not approval;
- commercial inquiries use the repository security/contact channel without publishing confidential terms.

Copy all three root documents exactly into `plugins/agent-collab/`.

- [ ] **Step 4: Require legal documents in every archive**

Add `LICENSE`, `NOTICE`, and `COMMERCIAL-LICENSING.md` to `REQUIRED_ROOTS` in `scripts/build_plugin_archive.py`. Keep symlink rejection and existing source-byte parity unchanged.

- [ ] **Step 5: Run focused archive tests**

Run: `python3 -m unittest tests.test_plugin_archive -v`

Expected: all archive tests PASS and the policy-only archive contains all legal documents but no runtime.

- [ ] **Step 6: Commit legal documents and archive enforcement**

```bash
git add LICENSE NOTICE COMMERCIAL-LICENSING.md plugins/agent-collab/LICENSE plugins/agent-collab/NOTICE plugins/agent-collab/COMMERCIAL-LICENSING.md scripts/build_plugin_archive.py tests/test_plugin_archive.py tests/test_public_distribution_contract.py
git commit -S -m "legal: adopt PolyForm Strict licensing"
```

### Task 3: License Metadata, Version 3.1.0, and Generated Surfaces

**Files:**
- Modify: `plugins/agent-collab/.claude-plugin/plugin.json`
- Modify: `plugins/agent-collab/.codex-plugin/plugin.json`
- Modify: `plugins/agent-collab/marketplace-fragment.json`
- Modify: `.claude-plugin/marketplace.base.json`
- Modify: `.claude-plugin/marketplace.json` (generated)
- Modify: `.agents/plugins/marketplace.json` (generated only if generator output changes)
- Modify: `scripts/build_marketplace.py`
- Modify: `scripts/skill-build-config.json`
- Modify: `skill-specs/governance-review.md`
- Modify: `skill-specs/migration-doctor.md`
- Modify: `skill-specs/route.md`
- Modify: `skill-specs/worker.md`
- Modify: `plugins/agent-collab/skills/*/SKILL.md` (generated)
- Modify: `tests/test_build_marketplace.py`
- Modify: `tests/test_codex_native_packaging.py`
- Modify: `tests/test_public_distribution_contract.py`

**Interfaces:**
- Consumes: manifest license `PolyForm-Strict-1.0.0`, marketplace SPDX expression `LicenseRef-PolyForm-Strict-1.0.0`, version `3.1.0`.
- Produces: matching Claude/Codex manifests, one licensed marketplace entry, and generated skills at v3.1.0.

- [ ] **Step 1: Write failing metadata tests**

In `tests/test_codex_native_packaging.py`, require both manifests to contain the same `license` value and assert it equals `PolyForm-Strict-1.0.0`.

In `tests/test_build_marketplace.py`, include `license: PolyForm-Strict-1.0.0` in both fixture manifests and `license: LicenseRef-PolyForm-Strict-1.0.0` in the fragment, then assert the generated Claude marketplace entry uses the SPDX `LicenseRef`.

In `tests/test_public_distribution_contract.py`, update expected distributed versions to `3.1.0` and assert all generated skill frontmatter uses `version: 3.1.0`.

- [ ] **Step 2: Run focused metadata tests and verify expected failures**

Run:

```bash
python3 -m unittest tests.test_build_marketplace tests.test_codex_native_packaging tests.test_public_distribution_contract -v
```

Expected: FAIL on missing license fields and the still-current `3.0.1` version.

- [ ] **Step 3: Implement manifest and marketplace license propagation**

Set both plugin manifests to version `3.1.0` and license `PolyForm-Strict-1.0.0`. Set the marketplace fragment license to `LicenseRef-PolyForm-Strict-1.0.0`. Update `scripts/build_marketplace.py` so the generated entry takes the explicit fragment `license` and rejects absent or unexpected manifest/fragment license mappings.

Set `.claude-plugin/marketplace.base.json` metadata version and `scripts/skill-build-config.json` `skill_version` to `3.1.0`. Replace the four hardcoded skill-spec versions with `{{ skill_version }}`.

- [ ] **Step 4: Regenerate skills and marketplaces**

Run:

```bash
python3 scripts/build_skills.py
python3 scripts/build_marketplace.py
```

Expected: 26 generated skills at v3.1.0 and one Claude/Codex marketplace package.

- [ ] **Step 5: Run focused metadata and generator checks**

Run:

```bash
python3 -m unittest tests.test_build_marketplace tests.test_codex_native_packaging tests.test_public_distribution_contract -v
python3 scripts/build_skills.py --check
python3 scripts/build_marketplace.py --check
```

Expected: all tests and checks PASS.

- [ ] **Step 6: Commit versioned licensed metadata**

```bash
git add plugins/agent-collab/.claude-plugin/plugin.json plugins/agent-collab/.codex-plugin/plugin.json plugins/agent-collab/marketplace-fragment.json .claude-plugin/marketplace.base.json .claude-plugin/marketplace.json .agents/plugins/marketplace.json scripts/build_marketplace.py scripts/skill-build-config.json skill-specs plugins/agent-collab/skills tests/test_build_marketplace.py tests/test_codex_native_packaging.py tests/test_public_distribution_contract.py
git commit -S -m "release: set licensed v3.1.0 metadata"
```

### Task 4: Contributor Rights Governance

**Files:**
- Modify: `.github/PULL_REQUEST_TEMPLATE.md`
- Modify: `.github/workflows/compliance-trace.yml`
- Modify: `docs/public-governance.md`
- Modify: `scripts/check_pr_compliance.py`
- Modify: `scripts/test_check_pr_compliance.py`

**Interfaces:**
- Consumes: existing compliance-trace parsing.
- Produces: required `contributor_rights` evidence with documented `OWNER-AUTHORED` and `OPERATOR-CONFIRMED` states.

- [ ] **Step 1: Add failing local compliance tests**

Add `contributor_rights` to test fixtures and assert:

```python
    def test_missing_contributor_rights_is_rejected(self):
        _, errors = cpc.parse_trace_block(_make_body(contributor_rights=None))
        self.assertTrue(any("contributor_rights" in error for error in errors))

    def test_owner_authored_contributor_rights_is_valid(self):
        _, errors = cpc.parse_trace_block(
            _make_body(contributor_rights="OWNER-AUTHORED")
        )
        self.assertEqual(errors, [])
```

- [ ] **Step 2: Run focused compliance tests and verify expected failure**

Run: `python3 -m unittest scripts.test_check_pr_compliance.TestParseTraceBlock -v`

Expected: FAIL because `contributor_rights` is not required yet.

- [ ] **Step 3: Implement and document the contributor-rights field**

Add `contributor_rights` to `REQUIRED_KEYS` in the local checker and the workflow-inline parser. Add it to the PR template:

```text
contributor_rights: OWNER-AUTHORED | OPERATOR-CONFIRMED
```

Document that `OPERATOR-CONFIRMED` means John Osumi or Osumi Consulting LLC has verified a separate written agreement granting sufficient rights to use, modify, distribute, sublicense, and commercially relicense the contribution. State that automation verifies only presence/form; operator review verifies the agreement.

- [ ] **Step 4: Run local and workflow-contract tests**

Run:

```bash
python3 scripts/test_check_pr_compliance.py
python3 -m unittest tests.test_ci_test_coverage -v
```

Expected: PASS.

- [ ] **Step 5: Commit contribution governance**

```bash
git add .github/PULL_REQUEST_TEMPLATE.md .github/workflows/compliance-trace.yml docs/public-governance.md scripts/check_pr_compliance.py scripts/test_check_pr_compliance.py
git commit -S -m "governance: require contributor rights evidence"
```

### Task 5: Deterministic Checksum and SPDX Release Evidence

**Files:**
- Create: `scripts/build_release_evidence.py`
- Create: `tests/test_release_evidence.py`
- Modify: `.github/workflows/release.yml`
- Modify: `tests/test_release_runtime_gate.py`

**Interfaces:**
- Consumes: verified `.plugin` archive, version `3.1.0`, commit-derived UTC creation timestamp.
- Produces: `<archive>.sha256` and `agent-collab-v3.1.0.spdx.json`; SPDX file inventory contains `LICENSE`, `NOTICE`, and `COMMERCIAL-LICENSING.md` and embeds the extracted PolyForm text under `LicenseRef-PolyForm-Strict-1.0.0`.

- [ ] **Step 1: Write failing release-evidence tests**

Create tests that build the canonical policy-only archive, call `build_evidence(...)`, and assert:

```python
self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
self.assertEqual(sbom["dataLicense"], "CC0-1.0")
self.assertEqual(sbom["packages"][0]["versionInfo"], "3.1.0")
self.assertEqual(
    sbom["packages"][0]["licenseDeclared"],
    "LicenseRef-PolyForm-Strict-1.0.0",
)
self.assertTrue(
    {"LICENSE", "NOTICE", "COMMERCIAL-LICENSING.md"}
    <= {item["fileName"] for item in sbom["files"]}
)
```

Also assert the extracted license text equals root `LICENSE`, every file checksum matches archive bytes, and the checksum sidecar equals the archive SHA-256 plus two spaces and the archive filename.

- [ ] **Step 2: Run the evidence test and verify expected failure**

Run: `python3 -m unittest tests.test_release_evidence -v`

Expected: import/error failure because `scripts/build_release_evidence.py` does not exist.

- [ ] **Step 3: Implement the standard-library evidence generator**

Implement:

```python
def build_evidence(
    archive: Path,
    *,
    version: str,
    created: str,
    sbom_output: Path,
    checksum_output: Path,
) -> None:
    """Validate a canonical archive and write deterministic SPDX/checksum evidence."""
```

The implementation must reject unsafe/duplicate archive names, missing legal members, root/plugin legal-byte drift, non-`3.1.0` semantic versions, and a license whose SHA-256 differs from the pinned official hash. Use stable sorted file order and `json.dumps(..., indent=2, sort_keys=True) + "\n"`.

- [ ] **Step 4: Add release-workflow evidence generation and assets**

After building the archive, derive the creation time with:

```bash
CREATED="$(git show -s --format=%cI HEAD)"
python3 scripts/build_release_evidence.py \
  --archive "/tmp/$ARCHIVE" \
  --version "${{ steps.meta.outputs.version }}" \
  --created "$CREATED" \
  --sbom "/tmp/agent-collab-v${{ steps.meta.outputs.version }}.spdx.json" \
  --checksum "/tmp/$ARCHIVE.sha256"
```

Pass the archive, checksum, and SPDX JSON paths to `gh release create`.

- [ ] **Step 5: Run release-evidence and workflow tests**

Run:

```bash
python3 -m unittest tests.test_release_evidence tests.test_release_runtime_gate -v
python3 scripts/build_plugin_archive.py --output '/tmp/agent-collab v3.1.0.plugin'
python3 scripts/build_release_evidence.py --archive '/tmp/agent-collab v3.1.0.plugin' --version 3.1.0 --created '2026-07-12T00:00:00Z' --sbom /tmp/agent-collab-v3.1.0.spdx.json --checksum '/tmp/agent-collab v3.1.0.plugin.sha256'
```

Expected: tests PASS; evidence command writes both files and reports success.

- [ ] **Step 6: Commit release evidence**

```bash
git add scripts/build_release_evidence.py tests/test_release_evidence.py .github/workflows/release.yml tests/test_release_runtime_gate.py
git commit -S -m "release: publish licensed SPDX evidence"
```

### Task 6: Release Documentation, Changelog, and Consistency Gates

**Files:**
- Modify: `README.md`
- Modify: `plugins/agent-collab/README.md`
- Modify: `docs/migration-from-legacy-packages.md`
- Create: `changelog.d/2026-07-12-v3.1.0-source-available-license.md`
- Modify: `scripts/check_release_consistency.py`
- Modify: `scripts/test_check_release_consistency.py`

**Interfaces:**
- Consumes: legal/version/agent-neutral contracts from Tasks 1-5.
- Produces: user-facing v3.1.0 licensing guidance and release gates that reject legal/version drift.

- [ ] **Step 1: Write failing release-consistency tests**

Extend release-consistency fixtures and checks to require:

- matching manifest licenses;
- root/plugin legal-file byte parity;
- exact copyright and commercial-administrator notices;
- README `agent-collab` summary, package table, What's New heading, and plugin README at `3.1.0`;
- a `agent-collab 3.1.0` changelog fragment mentioning PolyForm Strict, `AGENTS.md`, and commercial approval.

- [ ] **Step 2: Run the consistency tests and verify expected failure**

Run: `python3 scripts/test_check_release_consistency.py`

Expected: FAIL because v3.1.0 docs and legal consistency checks are not implemented.

- [ ] **Step 3: Update public documentation**

Update both READMEs with a concise License section linking `LICENSE`, `NOTICE`, and `COMMERCIAL-LICENSING.md`; state that source visibility is not an open-source grant, noncommercial use follows PolyForm Strict, and commercial use requires explicit written approval from Osumi Consulting LLC. Update version and What's New content to v3.1.0, including canonical `AGENTS.md`, contributor-rights gating, legal archive members, checksum, and SPDX evidence.

Update migration guidance to v3.1.0 without changing the legacy package mapping or runtime authority model.

Replace all four combined README references as follows:

```text
Claude, Codex, Antigravity, OpenCode, ZCode, and custom primary hosts
Model changes during an OpenCode or ZCode session
Antigravity, OpenCode, ZCode, and custom hosts
a strong live OpenCode or ZCode model observation
```

Add a regression assertion that neither `ZCode/OpenCode` nor `OpenCode/ZCode`
appears in active README or plugin documentation.

Create the changelog fragment:

```markdown
### agent-collab 3.1.0 — source-available licensing and neutral guidance

- License the public repository and installed package under the unmodified
  PolyForm Strict License 1.0.0. Copyright remains with John Osumi; commercial
  use requires explicit written approval administered by Osumi Consulting LLC.
- Make `AGENTS.md` the sole canonical public repository guide and retain
  `CLAUDE.md` only as an `@AGENTS.md` compatibility loader.
- Require contributor-rights evidence and package exact legal documents,
  SHA-256 evidence, and an SPDX 2.3 SBOM in the policy-only release.
```

- [ ] **Step 4: Implement and run consistency gates**

Run:

```bash
python3 scripts/test_check_release_consistency.py
python3 scripts/check_release_consistency.py
python3 scripts/build_changelog.py --dry-run
```

Expected: all commands PASS and dry-run displays the v3.1.0 fragment without modifying `CHANGELOG.md`.

- [ ] **Step 5: Commit release documentation and gates**

```bash
git add README.md plugins/agent-collab/README.md docs/migration-from-legacy-packages.md changelog.d/2026-07-12-v3.1.0-source-available-license.md scripts/check_release_consistency.py scripts/test_check_release_consistency.py
git commit -S -m "docs: document v3.1.0 licensing"
```

### Task 7: Comprehensive CI, CodeQL, and Secret Scanning

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `.github/workflows/backend-tests.yml`
- Modify: `.github/workflows/changelog-fragments-validate.yml`
- Modify: `.github/workflows/codeql.yml`
- Modify: `.github/workflows/compliance-trace.yml`
- Modify: `.github/workflows/regression-test-skills.yml`
- Modify: `.github/workflows/release-consistency.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `.github/workflows/secret-scan.yml`
- Modify: `.github/workflows/skill-build-fresh.yml`
- Modify: `.github/workflows/validate-skills.yml`
- Modify: `CODEOWNERS`
- Create: `tests/test_ci_security_contract.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: existing deterministic test/generator commands, CodeQL Python configuration, local secret scanner, release archive/evidence builders.
- Produces: SHA-pinned public CI/security workflows, stable `CI` aggregate context, `Gitleaks` context, explicit sensitive-file ownership, and a post-merge repository-settings contract.

- [ ] **Step 1: Write failing workflow-security contract tests**

Create `tests/test_ci_security_contract.py` with tests that:

```python
WORKFLOWS = ROOT / ".github" / "workflows"
PINNED_USE = re.compile(r"^\s*-?\s*uses:\s*[^\s@]+@[0-9a-f]{40}(?:\s+#.*)?$", re.M)
UNPINNED_USE = re.compile(r"^\s*-?\s*uses:\s*[^\s@]+@(?![0-9a-f]{40}(?:\s|$))", re.M)
```

- reject any external `uses:` reference not pinned to 40 hexadecimal characters;
- require `ci.yml` to contain Python `3.10`, `3.12`, and `3.14`, full repository/script test discovery, generator checks, release consistency, archive/evidence rehearsal, public-export safety, Actionlint `v1.7.12`, `git diff --check`, and a final job named `CI`;
- require `codeql.yml` to contain pull-request, `main`, weekly, and dispatch triggers, `security-extended`, Python analysis, and only GitHub-hosted execution;
- require `secret-scan.yml` to run both `scripts/secret_scan.py` and pinned `gitleaks/gitleaks-action`, fetch full history, and expose schedule/dispatch triggers;
- require every workflow to omit `self-hosted`;
- require explicit CODEOWNERS entries for `/.github/workflows/`, `/SECURITY.md`, `/LICENSE`, `/NOTICE`, `/COMMERCIAL-LICENSING.md`, `/AGENTS.md`, `/CLAUDE.md`, and `/CODEOWNERS`;
- reject `ZCode/OpenCode` and `OpenCode/ZCode` in active README/plugin documentation.

- [ ] **Step 2: Run the workflow contract and verify expected failure**

Run: `python3 -m unittest tests.test_ci_security_contract -v`

Expected: FAIL because `ci.yml` and Gitleaks are absent and action references still use mutable major-version tags.

- [ ] **Step 3: Add comprehensive Python and repository-contract CI**

Create `.github/workflows/ci.yml` with PR, `main`, and manual triggers; `contents: read`; per-ref concurrency; and:

```yaml
  python:
    name: Python ${{ matrix.python }}
    strategy:
      fail-fast: false
      matrix:
        python: ["3.10", "3.12", "3.14"]
```

Each matrix leg runs both unittest discovery commands. A `Repository Contracts`
job runs generator checks, changelog dry-run, release consistency, active-tree
public-export safety, local secret scan, archive/evidence rehearsal, JSON
validation, Actionlint v1.7.12, and `git diff --check`. A final `CI` job uses
`if: always()` and fails unless both preceding job results are `success`.

- [ ] **Step 4: Pin every GitHub Action and harden CodeQL**

Replace active action references with these reviewed pins:

```text
actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd # v5
actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6
actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4
actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093 # v4
github/codeql-action/init@1ad29ea4a422cce9a242a9fae469541dcd08addc # v4
github/codeql-action/analyze@1ad29ea4a422cce9a242a9fae469541dcd08addc # v4
```

Keep CodeQL Python-only, `security-extended`, weekly, PR, `main`, and manual.
Retain least-privilege `actions: read`, `contents: read`,
`security-events: write`, and `packages: read` permissions.

- [ ] **Step 5: Add full-history Gitleaks alongside the local scanner**

Extend `secret-scan.yml` with weekly/manual triggers and a second job:

```yaml
  gitleaks:
    name: Gitleaks
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - name: Check out full history
        uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd # v5
        with:
          fetch-depth: 0
      - name: Scan repository history
        uses: gitleaks/gitleaks-action@ff98106e4c7b2bc287b24eaf42907196329070c7 # v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Keep the existing local scanner as a separate fail-closed job.

- [ ] **Step 6: Add explicit sensitive-file ownership and documentation**

Add exact CODEOWNERS entries for every sensitive path listed in Step 1. Add a
README section describing CI, CodeQL, local/Gitleaks/native secret detection,
full-SHA action pinning, Dependabot, GitHub-hosted runners, and release evidence.

- [ ] **Step 7: Run workflow and full deterministic tests**

Run:

```bash
python3 -m unittest tests.test_ci_security_contract -v
python3 -m unittest discover -s tests -t . -v
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/secret_scan.py
git diff --check
```

Expected: all commands PASS.

- [ ] **Step 8: Commit CI and security hardening**

```bash
git add .github/workflows CODEOWNERS tests/test_ci_security_contract.py README.md
git commit -S -m "ci: harden public repository security gates"
```

### Task 8: Full Verification, Pull Request, Merge, Repository Settings, and v3.1.0 Release

**Files:**
- Verify all changed files.
- Release assets generated under `/tmp`; no generated release artifact is committed.

**Interfaces:**
- Consumes: completed Tasks 1-6.
- Produces: reviewed and merged v3.1.0 source, signed tag `v3.1.0`, GitHub release with archive/checksum/SBOM, and post-release verification.

- [ ] **Step 1: Run deterministic generators and complete test suites**

Run:

```bash
python3 scripts/build_skills.py --check
python3 scripts/build_marketplace.py --check
python3 -m unittest discover -s tests -t . -v
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/check_release_consistency.py
python3 scripts/check-public-export-safety.py --active-tree --history
python3 scripts/secret_scan.py
git diff --check
```

Expected: every command exits 0; no generated drift, secret, unsafe history, or test failure.

- [ ] **Step 2: Rehearse and inspect the release archive and evidence**

Run:

```bash
rm -f '/tmp/agent-collab v3.1.0.plugin' '/tmp/agent-collab v3.1.0.plugin.sha256' /tmp/agent-collab-v3.1.0.spdx.json
python3 scripts/build_plugin_archive.py --output '/tmp/agent-collab v3.1.0.plugin'
python3 scripts/build_release_evidence.py --archive '/tmp/agent-collab v3.1.0.plugin' --version 3.1.0 --created '2026-07-12T00:00:00Z' --sbom /tmp/agent-collab-v3.1.0.spdx.json --checksum '/tmp/agent-collab v3.1.0.plugin.sha256'
tar -tzf '/tmp/agent-collab v3.1.0.plugin'
shasum -a 256 -c '/tmp/agent-collab v3.1.0.plugin.sha256'
python3 -m json.tool /tmp/agent-collab-v3.1.0.spdx.json >/dev/null
```

Expected: archive lists `LICENSE`, `NOTICE`, and `COMMERCIAL-LICENSING.md`, contains no `runtime/`, checksum verifies, and SBOM is valid JSON.

- [ ] **Step 3: Run release dry-run and verify branch state**

Run:

```bash
python3 scripts/cut_release.py --dry-run
git status --short --branch
git log --show-signature -7 --oneline
```

Expected: dry-run selects policy-only `3.1.0`; worktree is clean; all task commits are signed.

- [ ] **Step 4: Push and open the governed pull request**

Push `dev/codex/source-available-license` and open a PR to `main` with tier 3, independent cross-family review evidence, `contributor_rights: OWNER-AUTHORED`, and links to the design and plan.

- [ ] **Step 5: Verify CI, review state, and merge eligibility**

Run the repository compliance checker against the PR, inspect every required check and review/comment surface, and merge only after all gates are green and operator-reserved requirements are satisfied.

- [ ] **Step 6: Apply and verify GitHub-native security and branch settings**

After the new workflow contexts have completed on merged `main`, use the GitHub
API to enable secret scanning, push protection, non-provider patterns, validity
checks, and Dependabot security updates where supported. Update branch
protection to strict current-branch checks including `CI`, `Analyze Python`,
`Gitleaks`, `scan`, and `validate-trace`; retain the existing specialized
required checks; require one code-owner/last-push approval with stale-review
dismissal; disable admin enforcement so the operator can release owner-authored
changes; retain linear history; and keep force pushes/deletions disabled.

Read back both repository `security_and_analysis` and branch-protection JSON.
Treat an unsupported optional native setting as explicitly unavailable rather
than reporting it enabled.

- [ ] **Step 7: Create the signed release from clean merged `main`**

From a clean current `main`, run:

```bash
python3 scripts/cut_release.py
```

Expected: creates and pushes signed annotated tag `v3.1.0`; release workflow builds the policy-only archive, checksum, and SPDX SBOM.

- [ ] **Step 8: Verify the public release**

Verify through GitHub that:

- tag `v3.1.0` is signed and targets merged `main`;
- release title is `agent-collab v3.1.0`;
- assets include `agent-collab v3.1.0.plugin`, its `.sha256`, and `agent-collab-v3.1.0.spdx.json`;
- downloaded checksum verifies;
- downloaded archive contains exact legal documents and no runtime;
- repository license/readme/manifests report the approved licensing model;
- no `v3.0.0` release or tag exists.
