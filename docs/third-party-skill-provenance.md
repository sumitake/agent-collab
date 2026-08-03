# Third-party skill provenance — mattpocock/skills (MIT)

Three skills in this package are derived from Matt Pocock's
[mattpocock/skills](https://github.com/mattpocock/skills) repository,
MIT-licensed (Copyright (c) 2026 Matt Pocock). The derived portions remain
MIT-licensed; the PolyForm Strict License 1.0.0 governs only the rest of this
package. Each derived generated skill carries the full MIT permission notice
in its own `SKILL.md` (§ Attribution and license), so the notice travels with
every archive — policy-only and activation — that ships the skills tree.

Pinned upstream commit: `2ab958093e83e0ec752e6c1c5932da465bf23e0c`
Upstream license file: `LICENSE` (blob `f1dd2c09108dde1a5f56097cee8461b3ea834499`)

## File map (local ← upstream @ 2ab9580)

| Local (spec → generated) | Upstream path | Upstream blob SHA |
|---|---|---|
| `skill-specs/decision-map.md` → `plugins/agent-collab/skills/decision-map/SKILL.md` | `skills/engineering/wayfinder/SKILL.md` | `42e3644cc57e41a1b87482754f25b4d9462d4bbc` |
| `skill-specs/prototype.md` → `plugins/agent-collab/skills/prototype/SKILL.md` | `skills/engineering/prototype/SKILL.md` | `e75d5331ceffd9b2c5a9554c3db124d848afa054` |
| (same, inlined) | `skills/engineering/prototype/LOGIC.md` | `fe9a2c29f77b9b7182ad7fa4bd251f27e506b7d9` |
| (same, inlined) | `skills/engineering/prototype/UI.md` | `76c0f6012b016af04d6105fa696a9a0e29dfa53a` |
| `skill-specs/architecture-review.md` → `plugins/agent-collab/skills/architecture-review/SKILL.md` | `skills/engineering/improve-codebase-architecture/SKILL.md` | `b56969e92f0705d70700f908b8ec929a1edfa782` |
| (same, inlined vocabulary) | `skills/engineering/codebase-design/SKILL.md` | `16620c24528b737408e78d95dd6a0e01a98d3d63` |
| `skill-specs/code-review.md` → `plugins/agent-collab/skills/code-review/SKILL.md` (adapted portions only; mixed `PolyForm AND MIT` member) | `skills/engineering/code-review/SKILL.md` | `2a0b5240731b927caa9ac0bf43c3e2af9dc3f0a7` |
| `skill-specs/orchestrate.md` → `plugins/agent-collab/skills/orchestrate/SKILL.md` (adapted portions only; mixed member) | `skills/engineering/to-tickets/SKILL.md` | `96deac51d4391a3f691478d48f85f43261516c08` |
| `skill-specs/teamwork.md` → `plugins/agent-collab/skills/teamwork/SKILL.md` (adapted portions only; mixed member) | `skills/engineering/to-tickets/SKILL.md` | `96deac51d4391a3f691478d48f85f43261516c08` |

## Adaptations applied (this package is not a verbatim mirror)

- `decision-map` (from `wayfinder`): renamed; tracker resolved at run time
  (GitHub `gh` with feature detection → local markdown → project-documented
  workflow) instead of a setup-skill config file; an explicit user-approval
  write gate added before any tracker mutation; upstream sub-skill references
  (`/grilling`, `/domain-modeling`, `/research`, `/setup-matt-pocock-skills`)
  replaced with host-neutral equivalents.
- `prototype`: upstream `LOGIC.md`/`UI.md` companion files inlined (this
  package's generated skill directories are `SKILL.md`-only); isolated
  worktree/branch requirement and a production-safe gate on the whole UI
  variant mechanism added; no auto-commit to the caller's branch.
- `architecture-review` (from `improve-codebase-architecture` +
  `codebase-design`): renamed; deep-module vocabulary inlined; report changed
  from CDN Tailwind/Mermaid to fully self-contained inline CSS/SVG; grilling
  replaced with host-neutral interviewing; composition with this package's
  routed `architect` consultation documented.

Re-pin procedure: when refreshing from upstream, update the pinned commit and
every blob SHA above in the same change, and re-verify the adaptations list.

## Adapted-portion (mixed-license) files

- `code-review` (adapted portions, v4.8.0): the two-axis spec-fidelity
  reporting structure and the Fowler smell-baseline treatment are adapted;
  spec materialization/ambiguity/trust rules, the JSONL contract extension
  (`Spec`/`Smell` severities, `spec_ref`), and everything else in that skill
  are package-original. Per-file SPDX for this member is
  `LicenseRef-PolyForm-Strict-1.0.0 AND MIT`.
- `orchestrate` + `teamwork` (adapted portions, v4.9.0): the conditional
  tracer-bullet slice rules and expand–contract sequencing are adapted from
  upstream `to-tickets`; the conditionality boundaries (feature-work-only,
  codemoddable-batch alternative, coexistence-required trigger) and the rest
  of both skills are package-original. Per-file SPDX for both members is
  `LicenseRef-PolyForm-Strict-1.0.0 AND MIT`.
