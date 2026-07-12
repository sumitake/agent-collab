#!/usr/bin/env python3
"""Verify the agent-collab release version is consistent across every file
that carries it -- and, optionally, that it is monotonic vs a git ref and that
a release tag matches it.

Source of truth: plugins/agent-collab/.claude-plugin/plugin.json -> "version".
The co-packaged Codex manifest must identify the same package and version. The
Claude and Codex marketplace surfaces contain exactly this one package; no
aliases are releaseable.

Checked surfaces (the canonical marketplace entry):
  - CHANGELOG.md / changelog.d       topmost "### <plugin> X.Y.Z" heading or a committed
                                     changelog fragment mentions each bumped entry
  - README.md                        "**<plugin>** (vX.Y.Z)" summary line for each
                                     and "## What's new - vX.Y.Z" heading
  - plugins/<plugin>/README.md       "Current: **X.Y.Z**" in the Version section

Modes (combinable):
  (default)            consistency check across the files above
  --against-ref REF    additionally assert plugin.json version >= REF's version
  --tag TAG            additionally assert TAG resolves to the plugin.json version

Exit: 0 = all checks passed, 1 = drift / missing anchor.

Stdlib-only by design -- runs on a bare CI runner with no pip install. The
Markdown-version extractors are the brittle surface; they are pinned by
scripts/test_check_release_consistency.py, which CI runs before this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

PLUGIN = "agent-collab"
_SEMVER = r"(\d+\.\d+\.\d+)"
_PLUGIN_JSON = f"plugins/{PLUGIN}/.claude-plugin/plugin.json"
MANIFEST_LICENSE = "PolyForm-Strict-1.0.0"
MARKETPLACE_LICENSE = "LicenseRef-PolyForm-Strict-1.0.0"
LICENSE_SHA256 = "9eb48619fbc193ab7bb327b090cfcc703000265b83e670f81f231d0b1c43c56e"
NOTICE_TEXT = (
    "Copyright (c) 2026 John Osumi. All rights reserved except as expressly "
    "granted.\nCommercial licensing is administered by Osumi Consulting LLC.\n"
)
LEGAL_FILES = ("LICENSE", "NOTICE", "COMMERCIAL-LICENSING.md")


def repo_root() -> Path:
    """Repo root = the current git working tree root (worktree-aware).

    Uses `git rev-parse --show-toplevel` so that when this script runs as a
    pre-commit hook from a git worktree, it reads the worktree's files rather
    than the main repo's (the hook CWD is the worktree root, so
    --show-toplevel returns the worktree path regardless of where __file__
    resolves). Falls back to the parent of this script's scripts/ directory
    when git is unavailable (e.g., in tests invoked outside a git tree).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path(__file__).resolve().parents[1]


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def license_contract_errors(root: Path, version: str) -> list[str]:
    """Return deterministic licensing drift errors for one release tree."""
    errors: list[str] = []
    plugin_root = root / "plugins" / PLUGIN
    for label, path in (
        ("Claude", plugin_root / ".claude-plugin" / "plugin.json"),
        ("Codex", plugin_root / ".codex-plugin" / "plugin.json"),
    ):
        text = _read(path)
        try:
            manifest = json.loads(text) if text is not None else {}
        except (TypeError, ValueError):
            manifest = {}
        if manifest.get("version") != version:
            errors.append(f"{label} manifest version is not {version}")
        if manifest.get("license") != MANIFEST_LICENSE:
            errors.append(
                f"{label} manifest license is not {MANIFEST_LICENSE}"
            )

    marketplace_text = _read(root / ".claude-plugin" / "marketplace.json")
    try:
        marketplace = (
            json.loads(marketplace_text) if marketplace_text is not None else {}
        )
        entries = marketplace.get("plugins", [])
        entry = entries[0] if isinstance(entries, list) and len(entries) == 1 else {}
    except (AttributeError, TypeError, ValueError):
        entry = {}
    if entry.get("license") != MARKETPLACE_LICENSE:
        errors.append(f"marketplace license is not {MARKETPLACE_LICENSE}")

    for name in LEGAL_FILES:
        root_bytes = _read_bytes(root / name)
        plugin_bytes = _read_bytes(plugin_root / name)
        if root_bytes is None or plugin_bytes is None:
            errors.append(f"{name} is missing from the root or plugin")
        elif root_bytes != plugin_bytes:
            errors.append(f"{name} byte parity failed")

    license_bytes = _read_bytes(root / "LICENSE")
    if (
        license_bytes is None
        or hashlib.sha256(license_bytes).hexdigest() != LICENSE_SHA256
    ):
        errors.append("LICENSE does not match the pinned PolyForm Strict text")
    notice = _read(root / "NOTICE")
    if notice != NOTICE_TEXT:
        errors.append("NOTICE owner or commercial administrator drifted")

    commercial = _read(root / "COMMERCIAL-LICENSING.md") or ""
    for token in (
        "PolyForm Strict License 1.0.0",
        "explicit written approval",
        "Osumi Consulting LLC",
        "Repository access",
        "installation",
        "GitHub interaction",
        "acceptance of a contribution",
    ):
        if token not in commercial:
            errors.append(f"COMMERCIAL-LICENSING.md is missing {token!r}")

    for label, path in (
        ("root README", root / "README.md"),
        ("plugin README", plugin_root / "README.md"),
    ):
        text = _read(path) or ""
        for token in (
            "PolyForm Strict License 1.0.0",
            "Osumi Consulting LLC",
            "](LICENSE)",
            "[NOTICE](NOTICE)",
            "[COMMERCIAL-LICENSING.md](COMMERCIAL-LICENSING.md)",
        ):
            if token not in text:
                errors.append(f"{label} is missing {token!r}")
        for combined in ("ZCode/OpenCode", "OpenCode/ZCode"):
            if combined in text:
                errors.append(f"{label} combines distinct hosts as {combined}")

    changelog_parts = [_read(root / "CHANGELOG.md") or ""]
    fragments_dir = root / "changelog.d"
    if fragments_dir.is_dir():
        changelog_parts.extend(
            _read(path) or ""
            for path in sorted(fragments_dir.glob("*.md"))
            if path.name != "README.md"
        )
    changelog = "\n".join(changelog_parts)
    for token in (
        f"agent-collab {version}",
        "PolyForm Strict License 1.0.0",
        "`AGENTS.md`",
        "Osumi Consulting LLC",
    ):
        if token not in changelog:
            errors.append(f"changelog licensing entry is missing {token!r}")
    return errors


# --- version extractors (brittle surface -- unit-tested) ---------------------

def extract_plugin_json_version(text: str) -> str | None:
    try:
        v = json.loads(text).get("version")
    except (ValueError, AttributeError):
        return None
    return str(v) if v else None


def extract_changelog_version(text: str) -> str | None:
    """Topmost '### <canonical-plugin> X.Y.Z' heading (kept for unit-test back-compat;
    run_consistency reads marketplace.json's plugin list directly and validates each
    entry's mention in the topmost header, so this single-plugin extractor is
    vestigial but still useful for spot-checks)."""
    m = re.search(rf"^###\s+{re.escape(PLUGIN)}\s+{_SEMVER}", text, re.M)
    return m.group(1) if m else None


def extract_root_summary_version(text: str) -> str | None:
    """'**<canonical-plugin>** (vX.Y.Z)' marketplace summary line (vestigial; see
    extract_changelog_version note above — run_consistency validates each entry
    from marketplace.json directly)."""
    m = re.search(rf"\*\*{re.escape(PLUGIN)}\*\*\s*\(v{_SEMVER}\)", text)
    return m.group(1) if m else None


def extract_whatsnew_version(text: str) -> str | None:
    """'## What's new - vX.Y.Z' heading (hyphen / en-dash / em-dash tolerated)."""
    m = re.search(rf"^##\s+What's new\s*[-–—]\s*v{_SEMVER}", text, re.M)
    return m.group(1) if m else None


def extract_plugin_readme_version(text: str) -> str | None:
    """'Current: **X.Y.Z**' in the plugin README Version section."""
    m = re.search(rf"Current:\s*\*\*{_SEMVER}\*\*", text)
    return m.group(1) if m else None


def changelog_fragment_mentions(root: Path, expected_mention: str) -> bool:
    """Return True when any committed changelog fragment mentions a release.

    PRs commit ``changelog.d/`` fragments, not the generated CHANGELOG body.
    Release consistency therefore accepts either the compiled topmost
    CHANGELOG heading (post-release) or a fragment mention (PR-time).
    """
    fragments_dir = root / "changelog.d"
    if not fragments_dir.is_dir():
        return False
    for path in sorted(fragments_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        text = _read(path)
        if text and expected_mention in text:
            return True
    return False


def semver_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".")[:3])


def parse_tag_full(tag: str) -> tuple[str | None, str | None]:
    """Resolve a release tag into (plugin_name, version).

    Accepts:
      - 'vX.Y.Z'              -> (None, 'X.Y.Z')  -- canonical default plugin
                                                     (agent-collab; see PLUGIN constant)
      - 'v-<plugin>-X.Y.Z'    -> ('<plugin>', 'X.Y.Z')

    Returns (None, None) if the tag doesn't match either form (or is None /
    empty / whitespace).

    The plugin_name slot lets `run_tag_check` validate a release tag against
    the correct plugin's plugin.json (e.g., `v-agent-collab-1.0.0` against
    plugins/agent-collab/.claude-plugin/plugin.json, not the canonical
    agent-collab one). Prior to this split (Phase 1b release-tag follow-up,
    2026-05-25) the script hardcoded agent-collab as the source-of-truth,
    which caused per-plugin release builds to FAIL by comparing the plugin's
    version against agent-collab's plugin.json. (Historical: first surfaced
    in the historical multi-package release flow.)

    Regex robustness: the version sub-pattern is inlined (`(\\d+\\.\\d+\\.\\d+)`)
    rather than reusing the module-level `_SEMVER` constant. This decouples
    parse_tag_full's group-index logic from any future change to `_SEMVER`'s
    capture-group structure (e.g., switching to non-capturing or multi-group
    semver). Localized robustness; `_SEMVER` is still used elsewhere.
    """
    if not tag:
        return (None, None)
    tag = tag.strip()
    if not tag:
        return (None, None)
    m = re.fullmatch(r"v-([a-z0-9-]+)-(\d+\.\d+\.\d+)", tag)
    if m:
        return (m.group(1), m.group(2))
    m = re.fullmatch(r"v(\d+\.\d+\.\d+)", tag)
    if m:
        return (None, m.group(1))
    return (None, None)


def parse_tag(tag: str) -> str | None:
    """Resolve a release tag to its X.Y.Z version (plugin name discarded).

    Backward-compat wrapper around `parse_tag_full`; existing callers that
    only need the version (e.g., `cut_release.py`'s truthiness check on tag
    well-formedness) keep working unchanged. New callers needing the plugin
    name should use `parse_tag_full` directly.
    """
    _, version = parse_tag_full(tag)
    return version


# --- checks ------------------------------------------------------------------

def plugin_json_path(plugin: str) -> str:
    """Repo-relative path to a plugin's .claude-plugin/plugin.json."""
    return f"plugins/{plugin}/.claude-plugin/plugin.json"


def plugin_version(root: Path, plugin: str) -> str | None:
    """Read the version field of any plugin's plugin.json. Returns None if
    the file doesn't exist or has no parseable version."""
    text = _read(root / plugin_json_path(plugin))
    return extract_plugin_json_version(text) if text is not None else None


def current_version(root: Path) -> str | None:
    """Canonical plugin's version (agent-collab). Thin wrapper kept for
    backward compatibility with run_consistency / run_monotonicity callers."""
    return plugin_version(root, PLUGIN)


def run_consistency(root: Path) -> tuple[bool, list[str]]:
    """Assert host manifests, marketplaces, changelog, and READMEs agree."""
    expected = current_version(root)
    if not expected:
        return False, [f"FAIL  cannot read a version from {_PLUGIN_JSON}"]
    lines = [f"source of truth: {_PLUGIN_JSON} version = {expected}"]
    ok = True

    licensing_errors = license_contract_errors(root, expected)
    if licensing_errors:
        ok = False
        lines.extend(f"FAIL  licensing: {error}" for error in licensing_errors)
    else:
        lines.append(
            "PASS  PolyForm Strict legal files, metadata, and README notices match"
        )

    codex_manifest_path = (
        root / "plugins" / PLUGIN / ".codex-plugin" / "plugin.json"
    )
    codex_manifest_text = _read(codex_manifest_path)
    if codex_manifest_text is None:
        ok = False
        lines.append("FAIL  Codex plugin manifest: cannot read file")
    else:
        try:
            codex_manifest = json.loads(codex_manifest_text)
            codex_name = codex_manifest.get("name")
            codex_version = codex_manifest.get("version")
            if codex_name != PLUGIN or codex_version != expected:
                ok = False
                lines.append(
                    "FAIL  Codex plugin manifest: "
                    f"name={codex_name!r} version={codex_version!r}, expected "
                    f"name={PLUGIN!r} version={expected!r}"
                )
            else:
                lines.append(
                    "PASS  Codex plugin manifest matches Claude package "
                    f"({PLUGIN} {expected})"
                )
        except (ValueError, AttributeError) as error:
            ok = False
            lines.append(f"FAIL  Codex plugin manifest: failed to parse: {error}")

    # 1. Check marketplace.json metadata and entries
    m_path = root / ".claude-plugin" / "marketplace.json"
    m_text = _read(m_path)
    if m_text is None:
        ok = False
        lines.append("FAIL  marketplace.json: cannot read file")
    else:
        try:
            m_data = json.loads(m_text)
            m_version = m_data.get("metadata", {}).get("version")
            if m_version != expected:
                ok = False
                lines.append(f"FAIL  marketplace.json: metadata.version is {m_version}, expected {expected}")
            else:
                lines.append(f"PASS  marketplace.json: metadata.version = {m_version}")

            plugins_list = m_data.get("plugins", [])
            for p_entry in plugins_list:
                p_name = p_entry.get("name")
                p_version = p_entry.get("version")
                p_json_path = root / "plugins" / p_name / ".claude-plugin" / "plugin.json"
                p_json_text = _read(p_json_path)
                if p_json_text is None:
                    ok = False
                    lines.append(f"FAIL  {p_name}/plugin.json: cannot read file")
                else:
                    found_p_version = extract_plugin_json_version(p_json_text)
                    if found_p_version != p_version:
                        ok = False
                        lines.append(f"FAIL  {p_name}: marketplace version {p_version} differs from plugin.json version {found_p_version}")
                    else:
                        lines.append(f"PASS  {p_name}: marketplace version matches plugin.json version ({p_version})")
        except Exception as e:
            ok = False
            lines.append(f"FAIL  marketplace.json: failed to parse: {e}")

    # 2. Check the Codex-native marketplace surface.
    codex_marketplace_path = root / ".agents" / "plugins" / "marketplace.json"
    codex_marketplace_text = _read(codex_marketplace_path)
    if codex_marketplace_text is None:
        ok = False
        lines.append("FAIL  Codex marketplace: cannot read file")
    else:
        try:
            codex_marketplace = json.loads(codex_marketplace_text)
            entries = codex_marketplace.get("plugins", [])
            expected_source = {
                "source": "local",
                "path": f"./plugins/{PLUGIN}",
            }
            if (
                codex_marketplace.get("name") != PLUGIN
                or not isinstance(entries, list)
                or len(entries) != 1
                or not isinstance(entries[0], dict)
                or entries[0].get("name") != PLUGIN
                or entries[0].get("source") != expected_source
            ):
                ok = False
                lines.append(
                    "FAIL  Codex marketplace: expected exactly one local "
                    f"{PLUGIN} entry"
                )
            else:
                lines.append(
                    f"PASS  Codex marketplace contains only {PLUGIN}"
                )
        except (ValueError, AttributeError) as error:
            ok = False
            lines.append(f"FAIL  Codex marketplace: failed to parse: {error}")

    # 3. Check CHANGELOG.md for topmost header
    changelog_path = root / "CHANGELOG.md"
    changelog_text = _read(changelog_path)
    if changelog_text is None:
        ok = False
        lines.append("FAIL  CHANGELOG.md: cannot read file")
    else:
        first_h3 = None
        in_fragments = False
        for line in changelog_text.splitlines():
            if "<!-- changelog-fragments:start" in line:
                in_fragments = True
                continue
            if "<!-- changelog-fragments:end" in line:
                in_fragments = False
                continue
            if in_fragments:
                continue
            if line.startswith("### "):
                first_h3 = line
                break
        if first_h3 is not None:
            lines.append(f"Found topmost CHANGELOG header: '{first_h3}'")
        if m_text is not None:
            try:
                m_data = json.loads(m_text)
                for p_entry in m_data.get("plugins", []):
                    p_name = p_entry.get("name")
                    p_version = p_entry.get("version")
                    expected_mention = f"{p_name} {p_version}"
                    if first_h3 is not None and expected_mention in first_h3:
                        lines.append(
                            "PASS  CHANGELOG.md: topmost header mentions "
                            f"'{expected_mention}'"
                        )
                    elif changelog_fragment_mentions(root, expected_mention):
                        lines.append(
                            f"PASS  changelog.d fragment mentions '{expected_mention}'"
                        )
                    else:
                        ok = False
                        lines.append(
                            "FAIL  CHANGELOG.md topmost header and changelog.d "
                            f"fragments do not mention '{expected_mention}'"
                        )
            except Exception:
                pass

    # 4. Check README.md at root for summary lines
    root_readme_path = root / "README.md"
    root_readme_text = _read(root_readme_path)
    if root_readme_text is None:
        ok = False
        lines.append("FAIL  root README.md: cannot read file")
    else:
        whatsnew = extract_whatsnew_version(root_readme_text)
        if whatsnew != expected:
            ok = False
            lines.append(f"FAIL  root README.md: whatsnew version is {whatsnew}, expected {expected}")
        else:
            lines.append(f"PASS  root README.md: whatsnew version = {whatsnew}")

        if m_text is not None:
            try:
                m_data = json.loads(m_text)
                for p_entry in m_data.get("plugins", []):
                    p_name = p_entry.get("name")
                    p_version = p_entry.get("version")
                    pat = rf"\*\*{re.escape(p_name)}\*\*\s*\(v{re.escape(p_version)}\)"
                    if not re.search(pat, root_readme_text):
                        ok = False
                        lines.append(f"FAIL  root README.md: summary line for '{p_name}' at version 'v{p_version}' not found")
                    else:
                        lines.append(f"PASS  root README.md: summary line for '{p_name}' matches v{p_version}")
            except Exception:
                pass

    # 5. Check each plugin's README.md Current: **X.Y.Z** version
    if m_text is not None:
        try:
            m_data = json.loads(m_text)
            for p_entry in m_data.get("plugins", []):
                p_name = p_entry.get("name")
                p_version = p_entry.get("version")
                p_readme_path = root / "plugins" / p_name / "README.md"
                p_readme_text = _read(p_readme_path)
                if p_readme_text is not None:
                    found = extract_plugin_readme_version(p_readme_text)
                    if found is not None:
                        if found != p_version:
                            ok = False
                            lines.append(f"FAIL  {p_name}/README.md: Current: **{found}**, expected **{p_version}**")
                        else:
                            lines.append(f"PASS  {p_name}/README.md: Current: **{found}** matches plugin version")
        except Exception:
            pass

    return ok, lines


class GitReadError(RuntimeError):
    """A comparison ref or an existing version file could not be read."""


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitReadError("git comparison command failed") from exc


def _git_show_version(root: Path, ref: str, plugin: str | None = None) -> str | None:
    """Read plugin.json version at a proven ref.

    None means only that the ref was readable and the path was proven absent;
    every command, ref, existing-file, or parse failure raises GitReadError.
    Defaults to the canonical PLUGIN when plugin is None or
    omitted (backward-compat with the pre-cycle-2 signature
    `_git_show_version(root, ref)`).

    The `plugin` parameter (added 2026-05-25 Phase 1b release-tag follow-up
    cycle 2; addresses Gemini cross-check concern #2 from PR #67) lets
    `run_monotonicity` assert non-regression on the *specific* plugin a
    release tag targets, instead of always agent-collab. Without this,
    `v-agent-collab-X.Y.Z` would always monotonicity-check agent-collab
    (correct as a canonical invariant, but misses the per-plugin assertion
    a release-tagger would want).

    Defensive None-handling (per Gemini cross-check concern #2 on this
    follow-up PR): an explicit `plugin=None` falls back to PLUGIN rather
    than propagating None into `plugin_json_path` and raising. This makes
    `_git_show_version` safe for future callers regardless of how they
    construct the kwarg.

    `git -C <root> show <ref>:<path>` requires `<path>` to be repo-relative
    (NOT absolute); `plugin_json_path` returns `plugins/<plugin>/.claude-plugin/plugin.json`
    which is the correct form (matches the pre-cycle-2 `_PLUGIN_JSON` constant
    semantics).
    """
    resolved_plugin = plugin if plugin else PLUGIN
    pj_path = plugin_json_path(resolved_plugin)
    target = f"{ref}:{pj_path}"
    shown = _run_git(root, "show", target)
    if shown.returncode == 0:
        version = extract_plugin_json_version(shown.stdout)
        if version is None:
            raise GitReadError(f"existing version file at {target} is invalid")
        return version

    verified = _run_git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if verified.returncode != 0:
        raise GitReadError(f"comparison ref is unavailable: {ref}")
    tree = _run_git(root, "ls-tree", "--name-only", ref, "--", pj_path)
    if tree.returncode != 0:
        raise GitReadError(f"comparison tree is unreadable: {ref}")
    if not tree.stdout.strip():
        return None
    raise GitReadError(f"existing version file could not be read: {target}")


def run_monotonicity(root: Path, ref: str, plugin: str | None = None) -> tuple[bool, list[str]]:
    """Assert that the (named) plugin's version at HEAD is >= its version at
    the given git ref. Defaults to the canonical PLUGIN when `plugin` is
    None or omitted (preserves pre-Phase-1b behavior of `--against-ref REF`
    on the canonical plugin).

    Plugin-qualified call sites (added 2026-05-25 Phase 1b release-tag
    follow-up cycle 2; Gemini cross-check concern #2 from PR #67): when
    `main()` is invoked with both `--tag v-<plugin>-X.Y.Z` and
    `--against-ref REF`, the plugin parsed from the tag is forwarded here
    so monotonicity asserts non-regression on the *tagged plugin* rather
    than always agent-collab.
    """
    target_plugin = plugin if plugin else PLUGIN
    current = plugin_version(root, target_plugin)
    if not current:
        return False, [
            f"FAIL  monotonicity: cannot read current version for '{target_plugin}' "
            f"({plugin_json_path(target_plugin)})"
        ]
    try:
        base = _git_show_version(root, ref, target_plugin)
    except GitReadError as exc:
        return False, [
            f"FAIL  monotonicity ({target_plugin}): cannot read {ref}: {exc}"
        ]
    if base is None:
        return True, [
            f"SKIP  monotonicity ({target_plugin}): ref is readable and has no "
            f"plugin.json at {ref}"
        ]
    if semver_tuple(current) >= semver_tuple(base):
        return True, [f"PASS  monotonicity ({target_plugin}): {current} >= {base} (on {ref})"]
    return False, [
        f"FAIL  monotonicity ({target_plugin}): {current} < {base} (on {ref}) - version regressed"
    ]


def run_tag_check(root: Path, tag: str) -> tuple[bool, list[str]]:
    """Validate a release tag against the named plugin's plugin.json.

    Tag forms (parse_tag_full handles both):
      - 'vX.Y.Z'              -> validates against the canonical plugin
                                 (the PLUGIN constant; currently `agent-collab`,
                                 the canonical-default for bare-version tags
                                 cut via `gh release create vX.Y.Z`).
      - 'v-<plugin>-X.Y.Z'    -> validates against
                                 plugins/<plugin>/.claude-plugin/plugin.json
                                 (where <plugin> is any plugin in the marketplace).

    The plugin-name-in-tag dispatch (added 2026-05-25 Phase 1b release-tag
    follow-up) is what makes per-plugin release builds work — without it, a
    tag like `v-agent-collab-1.0.0` was checked against agent-collab's
    plugin.json (currently 2.0.0) and always failed.

    Default-dispatch invariant: a bare `vX.Y.Z` tag must always validate
    against the canonical PLUGIN's plugin.json, preserving the pre-Phase-1b
    `gh release create v<X.Y.Z>` workflow for canonical releases.
    """
    plugin_in_tag, resolved = parse_tag_full(tag)
    if resolved is None:
        return False, [f"FAIL  tag '{tag}': not a release-tag form (vX.Y.Z or v-<plugin>-X.Y.Z)"]
    target_plugin = plugin_in_tag if plugin_in_tag else PLUGIN
    target_version = plugin_version(root, target_plugin)
    if not target_version:
        return False, [
            f"FAIL  tag '{tag}': cannot read plugin.json for '{target_plugin}' "
            f"({plugin_json_path(target_plugin)})"
        ]
    if resolved != target_version:
        return False, [
            f"FAIL  tag '{tag}' -> {resolved}, but {target_plugin}/plugin.json is {target_version}"
        ]
    return True, [f"PASS  tag '{tag}' matches {target_plugin}/plugin.json version {target_version}"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="agent-collab release-version consistency check (canonical + deprecation aliases)")
    ap.add_argument("--against-ref", metavar="REF",
                    help="also assert plugin.json version >= REF's version")
    ap.add_argument("--tag", metavar="TAG",
                    help="also assert TAG resolves to the plugin.json version")
    args = ap.parse_args(argv)

    root = repo_root()
    ok, lines = run_consistency(root)
    # Cross-flag composition (added 2026-05-25 Phase 1b release-tag follow-up
    # cycle 2): when BOTH --tag and --against-ref are provided, the tag's
    # plugin name flows into run_monotonicity so non-regression is asserted
    # on the same plugin the tag targets — instead of always agent-collab.
    # When only --against-ref is provided (no tag), keep the pre-existing
    # canonical-default behavior so legacy invocations don't change.
    monotonicity_plugin = None
    if args.tag:
        plugin_in_tag, _ = parse_tag_full(args.tag)
        monotonicity_plugin = plugin_in_tag  # None for bare vX.Y.Z (-> canonical)
    if args.against_ref:
        m_ok, m_lines = run_monotonicity(root, args.against_ref, plugin=monotonicity_plugin)
        ok &= m_ok
        lines += m_lines
    if args.tag:
        t_ok, t_lines = run_tag_check(root, args.tag)
        ok &= t_ok
        lines += t_lines

    print("\n".join(lines))
    print("RESULT:", "OK - release versions are consistent"
          if ok else "FAIL - release-version drift detected")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
