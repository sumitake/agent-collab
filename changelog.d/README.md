# `changelog.d/` — changelog fragment directory

This directory holds **per-PR changelog fragments** that compile into `CHANGELOG.md` at build / release time. The fragment-based approach (Towncrier-style) eliminates the top-of-CHANGELOG.md merge-conflict class that historically caused geometric rebase cost on deep PR stacks (empirically: ~30 min of pure CHANGELOG conflict resolution during the 2026-05-24 Phase 2 16-spec burst).

## How to add a fragment

1. **Create a file in this directory** named `<sortable-id>-<short-slug>.md`. Examples:
   - `0001-m1-changelog-fragments.md`
   - `0042-fix-marketplace-json-bump.md`
   - `0099-agent-collab-v3.0.1.md`

   The `<sortable-id>` is anything that sorts lexically the way you want entries to appear (most projects use zero-padded incrementing IDs, PR numbers, or ISO date prefixes). **Use a unique filename** (prefer your PR number or an ISO date + sequence) — two PRs creating the *same* fragment filename is the only remaining way to collide on `changelog.d/`, so distinct names make conflicts structurally impossible.

2. **Write the entry content** in standard CHANGELOG section format:

   ```markdown
   ### <plugin-name> <version> — <YYYY-MM-DD>

   <body — typical sections: #### Added / #### Changed / #### Cross-check / #### Compliance trace / etc.>
   ```

   The fragment IS the entry. No frontmatter is required (no YAML preamble). The compile script just concatenates fragments — formatting is your responsibility.

3. **Commit ONLY the fragment — do NOT commit `CHANGELOG.md`** (convention changed 2026-06-14). The generated `CHANGELOG.md` is compiled from fragments at **release time**, not in PRs — that is what keeps concurrent PRs from conflicting on the shared `[Unreleased]` block. Preview your entry with `python3 scripts/build-changelog.py --dry-run` (writes nothing); if you ran the compiler in write mode locally, `git restore CHANGELOG.md` before committing so it stays out of your PR. CI validates fragment-only PRs with `--dry-run` (the compiler must succeed) and enforces strict `--check` parity only on a PR that actually edits `CHANGELOG.md` (e.g. a release PR).

## How fragments compile into `CHANGELOG.md`

`scripts/build-changelog.py` is the compiler:

- **Build mode** (default): reads `changelog.d/*.md` in sorted order, concatenates content, inserts the result into the `## [Unreleased]` section of `CHANGELOG.md`. Idempotent.
- **Check mode** (`--check`): builds to a temp file and diffs against the current `CHANGELOG.md`. Exit 0 if they match; exit 1 with diff if they don't. CI uses this mode.
- **Dry-run mode** (`--dry-run`): prints what would be compiled without writing.

```bash
# Preview what fragments will look like compiled into CHANGELOG
python3 scripts/build-changelog.py --dry-run

# Compile fragments into CHANGELOG.md
python3 scripts/build-changelog.py

# CI-style check (fails if fragments don't match CHANGELOG.md)
python3 scripts/build-changelog.py --check
```

## When NOT to add a fragment

Trivial PRs that don't warrant a CHANGELOG entry — pure typo fixes in comments, internal-only refactors with no user-visible behavior, CI workflow tweaks that don't change product behavior — can skip the fragment. CI's `validate-changelog-fragments` workflow allows opting out with the label `no-changelog` on the PR, or by adding a sentinel file `changelog.d/.skip-<PR-number>` (empty or with a one-line justification).

## Why fragments

Each PR adding to `## [Unreleased]` at the same anchor position creates a guaranteed merge conflict against every other PR doing the same. Fragments distribute the additions across separate files, so two PRs adding fragments never conflict on CHANGELOG.md (they conflict only if they both edit the SAME fragment file, which is rare by construction).

Reference: workspace `docs/multi-agent-coordination.md` § "Phase 2 merge-cycle learnings" Improvement M1 (formerly L10); originally proposed 2026-05-24 after the Phase 2 burst surfaced the cost empirically.

## Reserved filenames and paths

- `README.md` (this file) — not treated as a fragment.
- `.gitkeep` — not treated as a fragment.
- `.skip-<PR-number>` (or `.skip-<topic>`) — not treated as a fragment; signals that the PR explicitly opts out of having a CHANGELOG entry. Optional one-line body explains why.
- `archived/` subdirectory — fragments for already-released content moved here at release time (e.g., when promoting `[Unreleased]` to a versioned section in `CHANGELOG.md`). Files here are not picked up by the `*.md` glob that the compiler uses.

Anything else with a `.md` extension at this level (not in a subdirectory) is processed as a fragment.
