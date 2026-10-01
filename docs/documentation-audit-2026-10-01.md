# Documentation audit — 2026-10-01

This is a descriptive audit of current remote `main`, not a release or runtime
change. The inspected public baseline is
`86b883aac18346992e3665e136714e05d7b8726c`. The preceding comprehensive
documentation correction completed on 2026-09-08; later 7.0.7 and 7.0.8 release
closeouts are part of the current evidence and were rechecked against source.

## Changes since the previous documentation audit

Since the 2026-09-08 audit, the repository shipped 7.0.7 and 7.0.8. The current
published release is 7.0.8 and carries provider runtime 5.0.9. The manifest
remains schema 4 / runtime protocol 5 / native contract 4 / wire schema 12,
with 12 logical actions, eight logical agents, and two Darwin artifacts.

The implementation delta includes bounded coordinator request repairs,
caller-repository binding for omitted read-only repository cwd, effort-floor
raising in the signed runtime, the distinct `target_agent_unsupported` result,
bounded native-output recovery, and the 7.0.8 project-estimation maintenance
handoff. Later repository-only work corrected stale build-script comments and
advanced a pinned release-workflow action SHA without changing the package or
runtime contract.

## Current documentation verification

The root README, all nine architecture-handbook pages, `AGENTS.md`,
`docs/public-governance.md`, the package technical reference,
`skill-specs/README.md`, migration guidance, release/change tooling, and
current dated evidence were checked against current source and manifests.

| Surface | Determination |
| --- | --- |
| Root README | **verified current** — public source and release are 7.0.8 / runtime 5.0.9; exactly one `What's new` showcase names v7.0.8. |
| Architecture index | **verified current** — current release identity, status vocabulary, ownership split, and sanitization boundary remain accurate. |
| System context | **verified current** — public coordinator/client, caller-owned repository/integration duties, host-owned async coordination, and private producer boundary match source. |
| Capabilities and workflows | **verified current** — 53 generated skills and 12 logical actions remain correctly grouped. |
| Governance and authority | **verified current** — routing eligibility is not independent approval; lineage/source evidence and merge authority remain separate. |
| Lifecycle and operations | **verified current** — supported host update paths, doctor/readiness limits, no-daemon/no-broker runtime shape, and recovery boundaries match current behavior. |
| Repository and release | **verified current** — source/generated ownership, signed artifact admission, staged versus installed evidence, maintenance, changelog compilation, and documentation closeout remain aligned. |
| Status and evidence | **verified current** — v7.0.8 is current; older releases remain explicitly historical. |
| Project estimation | **verified current** — the 7.0.8 receipt remains bootstrap maintenance evidence, not promoted calibration. |
| Claude participation | **verified current** — Claude remains admitted only for `context.documents.intent`; observed evidence stays scoped to named attempts. |
| Package technical README | **verified current at the signed tag** — intentionally retained as the immutable release-time snapshot rather than rewritten with later postpublication facts. |

No current architecture page requires a behavioral correction in this audit.
The package README's prepublication wording is part of the immutable tagged
package snapshot. Current postpublication facts belong in the root README and
architecture handbook.

## README release-showcase invariant

The root README contains one current release showcase,
`## What's new - v7.0.8`. Earlier release history remains in
`CHANGELOG.md` and dated evidence.

`scripts/check_release_consistency.py` keeps this invariant automated. Its
regression suite in `scripts/test_check_release_consistency.py` rejects
missing and duplicate `What's new` headings and a heading whose version
disagrees with the current package. This audit does not weaken that enforcement.

## Scope

The audit changes documentation only. It does not alter package/runtime bytes,
policy, tags, or release state. Validation and merge evidence belong to the
pull request.
