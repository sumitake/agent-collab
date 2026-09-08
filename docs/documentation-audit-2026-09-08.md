# Documentation audit — 2026-09-08

The inspected remote-main baseline is `fb13fc5`, the v7.0.6 documentation
closeout. The previous closeout was `77d061f` for v7.0.5. Between them,
`c03af78` corrects caller-owned review independence across skill instructions,
`fc8d66b` compiles the release changelog, and `fb13fc5` records the resulting
release and installation evidence. The signed v7.0.6 tag identifies
`fc8d66b3978dc1f2a177e9447b45915bb3486f84`; its runtime remains 5.0.7.

The audit examined unchanged descriptions as well as that release delta.
All nine architecture handbook pages were checked against public source,
generated inventories, contract tests, and the existing dated release record.

| Surface | Disposition |
| --- | --- |
| Root README | Verified the 7.0.6 summary and sole latest-release showcase. Added the supported-host lifecycle pointer and use changelog dry-run for a branch carrying fragments. |
| Architecture index | Verified ownership, source map, lifecycle labels, and sanitization contract. |
| System context | Corrected the order: public client verifies the bundle, then the signed runtime selects descriptor-admitted routes. Removed the nonexistent setup-module description. |
| Capabilities/workflows | Added the missing `learning-loop` skill, corrected OpenCode's four-lineage context/governance coverage, and clarified caller-owned repository and identity verification. |
| Governance/authority | Verified caller-owned lineage and source checks, opaque-content acceptance, separate evidence and merge decisions, and no inferred independence from routing. |
| Lifecycle/operations | Verified supported host install/update commands against this repository's maintained host contract, doctor and planning distinctions, recovery boundaries, and fresh-session loading caveat. |
| Repository/release | Corrected public transport versus compiled admission ownership; made staged and installed native qualification visible in the lifecycle alongside provider-free readiness. |
| Status/evidence | Verified current release identity against the immutable tag and published release; retained dated installation claims and earlier canaries as historical evidence. No new host qualification is claimed. |
| Project estimation | Verified current receipt-bound bootstrap, source inventory, private/public boundary, unknown metrics, maintenance validation, and release gates. |
| Claude participation | Verified intent-only admission and the dated 7.0.6 subscription denial; host, resident, async, and managed roles remain separate. |
| Package technical README and skill-specs README | Checked current counts and wire/manifest/client boundaries; corrected the source-spec count to 53, excluding authoring material. |
| Supporting current docs, design index, governance, migration, licensing/provenance, and changelog | Checked owning source links and current/historical status. Retained historical designs, release snapshots, and generated history with their original identities. |

The README's latest-release-only rule remains automated by
`scripts/check_release_consistency.py` and its regression suite in
`scripts/test_check_release_consistency.py`. Exactly one heading must name the current
package version; missing, duplicate, and stale headings fail. Older releases
belong in `CHANGELOG.md`, not additional README showcases.

This audit changes repository documentation only. It does not regenerate
skills, alter package/runtime bytes or policy, move tags, or claim a new release.
Private producer identifiers, local paths, credentials, and native invocation
recipes are excluded. Validation and review evidence are recorded in the PR.
