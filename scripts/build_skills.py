#!/usr/bin/env python3
"""build_skills.py — generate per-package SKILL.md files from shared specs.

Source of truth: ``skill-specs/<name>.md`` (at the repo root). Each spec is a
package-agnostic Markdown document with ``{{ var }}`` placeholders that the
generator resolves per-package using ``scripts/skill-build-config.json``.

Output: ``plugins/<package>/skills/<name>/SKILL.md`` — a fully-resolved,
self-contained file (no placeholders, no runtime indirection). The shipped
file is what the agent reads via ``view_file`` at invocation time — zero
two-hop latency, zero parameter-translation ambiguity (see workspace
``drafts/antigravity-as-primary-design.md`` §4 + the Phase-2 Gemini cross-
check round 2 verdict ready-to-proceed).

USAGE
  python3 scripts/build_skills.py
      Generate SKILL.md files for every package × every spec.
  python3 scripts/build_skills.py --check
      Generate to a temp dir and diff against the working tree.
      Exit 0 if the working tree matches the generator output, else exit 1
      with the diff. The CI workflow (skill-build-fresh.yml) calls this.
  python3 scripts/build_skills.py --package agent-collab
      Generate only for the named package.
  python3 scripts/build_skills.py --spec second-opinion
      Generate only the named spec (across all configured packages).
  python3 scripts/build_skills.py --list
      Print the (spec, package) pairs that would be generated; do not write.

DESIGN
  * Stdlib-only. No Jinja, no third-party templating — a single ``str.replace``
    per placeholder is sufficient and keeps the build hermetic.
  * Idempotent: re-running with no source changes produces no diff.
  * The active config contains exactly one package: ``agent-collab``.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Iterable

try:
    from scripts.skill_structure import skill_tree_differences, spec_names
except ModuleNotFoundError:  # direct `python3 scripts/build_skills.py`
    from skill_structure import skill_tree_differences, spec_names

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_DIR = REPO_ROOT / "skill-specs"
PLUGINS_DIR = REPO_ROOT / "plugins"
CONFIG_PATH = REPO_ROOT / "scripts" / "skill-build-config.json"
MAX_SKILL_DESCRIPTION_CHARS = 1024
ROUTED_SPECS = frozenset(
    {
        "agent-runtime-status",
        "architect",
        "brainstorm",
        "code-review",
        "debate",
        "delegate",
        "dev-delegate",
        "intent-check",
        "logic-check",
        "long-context",
        "qa-verify",
        "red-team",
        "second-opinion",
        "simulate-user",
    }
)

# Two-brace syntax. Restricted character class so a literal "{{" appearing
# in a code block (e.g., JSON output examples) does NOT accidentally match —
# placeholders are alphanumeric + underscore only.
PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
# Matches the opening ``---`` frontmatter block of a spec.
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
# Matches a ``packages:`` list field inside frontmatter YAML (simple inline or
# block list; we use a lightweight regex rather than a YAML parser to keep the
# build stdlib-only).  Captures the value portion after "packages:".
PACKAGES_FIELD_RE = re.compile(
    r"^packages:\s*\[([^\]]*)\]", re.MULTILINE
)


def load_config() -> dict:
    with open(CONFIG_PATH) as fh:
        return json.load(fh)


def spec_allowed_packages(spec_text: str) -> list[str] | None:
    """Return the ``packages:`` allow-list from a spec's frontmatter, or None.

    If the frontmatter contains ``packages: [pkg1, pkg2]``, only the listed
    package names will receive a generated SKILL.md for this spec.  If the
    field is absent (the common case), returns ``None`` — meaning all active
    packages build the spec (backward-compatible).

    Only the inline bracket form ``packages: [a, b]`` is supported (sufficient
    for the current use-case; block-list YAML would need a real YAML parser).
    """
    m = FRONTMATTER_RE.match(spec_text)
    if not m:
        return None
    fm = m.group(1)
    pm = PACKAGES_FIELD_RE.search(fm)
    if not pm:
        return None
    raw = pm.group(1)
    # Split on commas, strip whitespace and optional quotes around each name.
    names = [
        n.strip().strip("'\"")
        for n in raw.split(",")
        if n.strip().strip("'\"")
    ]
    return names if names else None


def list_specs() -> list[str]:
    """Spec names = filenames under skill-specs/ without the .md extension."""
    return list(spec_names(SPECS_DIR))


def get_effective_config(name: str, config: dict) -> dict:
    """Return the sole package substitution dictionary."""
    return config[name]


def strip_packages_field(rendered: str) -> str:
    """Remove the ``packages:`` build-directive line from rendered frontmatter.

    The ``packages:`` field is a build-time routing directive (consumed by
    ``spec_allowed_packages()`` to decide which packages receive a SKILL.md).
    It must NOT appear in the generated output — it is not a runtime field,
    no other skill has it, and its presence may fail schema validation.

    Only removes the line from inside the opening frontmatter fence (between
    the first ``---`` pair).  Content in the body or in code blocks is never
    touched, so specs that happen to contain the literal text ``packages:``
    in a code example are unaffected.
    """
    m = FRONTMATTER_RE.match(rendered)
    if not m:
        return rendered  # no frontmatter — nothing to strip
    fm_block = m.group(1)
    # Remove any line that starts with "packages:" (optional leading whitespace
    # within the frontmatter block is not expected, but tolerated).
    stripped_fm = re.sub(r"^packages:[^\n]*\n?", "", fm_block, flags=re.MULTILINE)
    # Reconstruct: "---\n" + stripped frontmatter + "\n---\n" + rest of body
    body_after = rendered[m.end():]
    return f"---\n{stripped_fm}\n---\n{body_after}"


def frontmatter_description(rendered: str) -> str | None:
    """Return the generated frontmatter ``description`` value, if present.

    Generated specs keep ``description:`` on one line. The build is stdlib-only,
    so this intentionally handles that supported form rather than importing a
    YAML parser solely for one length guard.
    """
    m = FRONTMATTER_RE.match(rendered)
    if not m:
        return None
    dm = re.search(r"^description:\s*(.*)$", m.group(1), re.MULTILINE)
    if not dm:
        return None
    return dm.group(1).strip()


def validate_description_length(rendered: str, target_rel: Path | str) -> None:
    """Fail the build if a generated skill description exceeds Codex's limit."""
    desc = frontmatter_description(rendered)
    if desc is None:
        return
    length = len(desc)
    if length > MAX_SKILL_DESCRIPTION_CHARS:
        raise ValueError(
            f"{target_rel}: description length {length} exceeds "
            f"{MAX_SKILL_DESCRIPTION_CHARS} characters"
        )


def inject_runtime_invocation(spec_name: str, rendered: str) -> str:
    """Add the one canonical standalone invocation contract to routed skills."""
    if spec_name not in ROUTED_SPECS:
        return rendered
    match = FRONTMATTER_RE.match(rendered)
    if not match:
        raise ValueError(f"{spec_name}: routed skill is missing frontmatter")
    block = (
        "\n## Unified runtime invocation\n\n"
        "Resolve the **plugin root** from this loaded file: `SKILL.md` is at "
        "`<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only "
        "`python3 \"<plugin-root>/coordinator.py\"` and send one bounded JSON "
        "request on stdin. Before constructing it, read the **Coordinator "
        "request schema** in `<plugin-root>/README.md`; never invent fields or "
        "route/action pairs. The public "
        "coordinator re-observes the active host/model, captures artifact "
        "provenance, excludes same-family routes, and verifies the co-packaged "
        "native manifest. It runs standalone from the installed plugin. Never "
        "discover a provider executable or reconstruct a raw command. "
        "Frontmatter `tier` is a routing recommendation, never a coordinator "
        "request field. For a review, cross-check, tiebreaker, or fallback over "
        "an authored artifact, capture its exact UTF-8 content and observed "
        "author model in the optional `artifact` object even when governance is "
        "false; never paste it into the prompt as a provenance substitute.\n"
    )
    return rendered[: match.end()] + block + rendered[match.end() :]


def render_spec(spec_text: str, substitutions: dict[str, str]) -> str:
    """Resolve every ``{{ var }}`` placeholder. Unknown placeholders raise."""
    missing: list[str] = []

    def _sub(match: re.Match) -> str:
        name = match.group(1)
        if name not in substitutions:
            missing.append(name)
            return match.group(0)
        return str(substitutions[name])

    out = PLACEHOLDER_RE.sub(_sub, spec_text)
    if missing:
        raise ValueError(
            f"unresolved placeholders: {sorted(set(missing))} "
            "(add to scripts/skill-build-config.json or remove from spec)"
        )
    return out


def target_path(package: str, spec_name: str) -> Path:
    return PLUGINS_DIR / package / "skills" / spec_name / "SKILL.md"


def iter_pairs(packages: Iterable[str], specs: Iterable[str]):
    for pkg in packages:
        for spec in specs:
            yield pkg, spec


def resolve_packages(config: dict, requested: str | None) -> list[str]:
    """Resolve the only supported package, optionally named explicitly."""
    package_names = [
        name
        for name, cfg in config.items()
        if isinstance(cfg, dict) and "primary_agent" in cfg
    ]
    if package_names != ["agent-collab"]:
        raise SystemExit(
            "skill-build-config.json must define exactly one active package: "
            "agent-collab"
        )
    if requested:
        if requested != "agent-collab":
            raise SystemExit(f"unknown package: {requested!r}")
        return [requested]
    return package_names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="diff-only mode; exit 1 if working tree differs from generator output",
    )
    parser.add_argument(
        "--package", default=None,
        help="generate only for the named package (skip the _active filter)",
    )
    parser.add_argument(
        "--spec", default=None,
        help="generate only the named spec (across configured packages)",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="print (package, spec) pairs and exit",
    )
    args = parser.parse_args()

    if not SPECS_DIR.is_dir():
        print(f"no skill-specs/ directory at {SPECS_DIR}; nothing to do.",
              file=sys.stderr)
        return 0

    config = load_config()
    packages = resolve_packages(config, args.package)
    if not packages:
        print("no active packages configured; nothing to do.", file=sys.stderr)
        return 0

    all_specs = list_specs()
    if args.spec:
        if args.spec not in all_specs:
            raise SystemExit(
                f"unknown spec: {args.spec!r}; available: {all_specs}"
            )
        specs = [args.spec]
    else:
        specs = all_specs

    if not specs:
        print("no specs found; nothing to do.", file=sys.stderr)
        return 0

    if args.list:
        for pkg, spec in iter_pairs(packages, specs):
            spec_path = SPECS_DIR / f"{spec}.md"
            spec_text = spec_path.read_text()
            allowed = spec_allowed_packages(spec_text)
            if allowed is not None and pkg not in allowed:
                continue
            print(f"{pkg}\t{spec}\t{target_path(pkg, spec).relative_to(REPO_ROOT)}")
        return 0

    any_diff = False
    written = 0
    for pkg, spec in iter_pairs(packages, specs):
        spec_path = SPECS_DIR / f"{spec}.md"
        with open(spec_path) as fh:
            spec_text = fh.read()
        # Per-spec package allow-list: if the spec's frontmatter declares
        # ``packages: [pkg1, pkg2]``, skip packages not in the list.  Absent
        # field means all active packages build the spec (backward-compatible).
        allowed_pkgs = spec_allowed_packages(spec_text)
        if allowed_pkgs is not None and pkg not in allowed_pkgs:
            continue
        effective_cfg = get_effective_config(pkg, config)
        rendered = render_spec(spec_text, effective_cfg)
        # Strip the ``packages:`` build-directive from the rendered frontmatter.
        # This field is for build-time routing only; it must not ship in
        # generated SKILL.md files (no other skill has it; may fail schema
        # validation).  strip_packages_field is a no-op for specs without it.
        rendered = strip_packages_field(rendered)
        rendered = inject_runtime_invocation(spec, rendered)
        target = target_path(pkg, spec)
        target_rel = target.relative_to(REPO_ROOT)
        validate_description_length(rendered, target_rel)

        if args.check:
            current = target.read_text() if target.exists() else ""
            if current != rendered:
                any_diff = True
                print(f"DIFF: {target_rel}")
                for line in difflib.unified_diff(
                    current.splitlines(keepends=True),
                    rendered.splitlines(keepends=True),
                    fromfile=str(target_rel) + " (working tree)",
                    tofile=str(target_rel) + " (generator output)",
                ):
                    sys.stdout.write(line)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text() != rendered:
            target.write_text(rendered)
            written += 1

    if args.spec is None:
        for pkg in packages:
            differences = skill_tree_differences(PLUGINS_DIR / pkg / "skills", SPECS_DIR)
            if differences:
                any_diff = True
                for difference in differences:
                    print(f"DIFF: plugins/{pkg}/skills/{difference}")

    if args.check:
        if any_diff:
            print(
                "\nERROR: generated SKILL.md files diverge from source specs. Run "
                "`python3 scripts/build_skills.py` (without --check) to "
                "regenerate, or edit skill-specs/<name>.md and re-run.",
                file=sys.stderr,
            )
            return 1
        print("OK: all generated SKILL.md files match source specs.")
        return 0

    if any_diff:
        print(
            "ERROR: generated skill tree contains missing, unexpected, or unsafe members.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: {written} SKILL.md file(s) "
        f"{('written' if written else 'unchanged')}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
