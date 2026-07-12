<!--
This template surfaces the procedural traces required by:
  - the global standing directive (~/.claude/CLAUDE.md "WORKFLOW LAYER" — pre-flight, branch, validation, CHANGELOG, version bump, restart), and
  - the workspace project standing-directive additions (agent-collab-workspace/CLAUDE.md):
      #1 Trigger-phrase verification
      #2 Cloud Run / local-plugin functional sync (MCP coverage gap evaluation)
      #3 .plugin archive distribution (post-merge release tag)

Fill in each section. For checkbox items, prefer richness over rote ticking — state the outcome
in a sentence. "N/A — reason" is acceptable; silent ticking is not.

Anti-pattern: ticking a box without performing the check. The check is the point;
the trace is the audit log.
-->

## Summary

<!-- What changed and why, in 2–3 sentences. -->

## Cross-repo coordination

<!-- "N/A" if standalone. Otherwise: companion PR link in agent-collab-workspace, merge order,
and justification if the default order ("workspace first") is reversed (e.g., when the plugin
references a workspace path that's being changed). -->

## Verification

<!-- What you ran locally, what passed, what the CI is expected to confirm. -->

## Plugin-specific procedural traces (workspace project additions)

### Addition #1 — Trigger-phrase verification (SKILL.md description-field changes)

State the outcome, do not leave blank:

- [ ] **Description field changed** in this PR. Both explicit user-phrase triggers AND at least one situational ("or when X happens") trigger are present in the new description. Verified by re-reading the description against `agent-collab-workspace/CLAUDE.md` addition #1.
- OR
- [ ] **N/A** — this change does not modify any SKILL.md `description:` field. Triggers are unchanged; they continue to fire correctly.

### Addition #2 — Cloud Run / local-plugin functional sync (every skill change)

The directive's exact words: *"Evaluate is not optional — make a positive determination ('no gap' or 'gap filed')."*

- [ ] **MCP tool coverage gap: NONE** — this change does not add, remove, or modify any MCP tool capability (no new tool, no new parameter, no new response field). No TODO needs to be filed in `agent-mcp-server`.
- OR
- [ ] **MCP tool coverage gap: FILED** at `<link to specific section in https://github.com/sumitake/agent-mcp-server/blob/main/TODO.md>` — describes what the parked Cloud Run server would need to implement to mirror this plugin change.

### Addition #3 — `.plugin` archive distribution (post-merge release tag)

- [ ] **`plugin.json` version was bumped** in this PR. The post-merge tag step is documented in the test plan below.
- OR
- [ ] **N/A** — `plugin.json` version was NOT bumped (e.g., repo-level meta change, or doc fix with no user-visible effect). No release tag step needed.

## Global standing-directive compliance

- [ ] **Pre-flight conflict check** — `gh pr list --state open` scanned in this repo AND `agent-collab-workspace`; no conflicting work
- [ ] **Branch naming** follows `dev/<agent>/<short-topic>`
- [ ] **Edited in working repo** (NOT the runtime cache `~/.claude/plugins/cache/`, NOT the deprecated `~/.claude/marketplaces/personal/`)
- [ ] **Local validation** — state which (frontmatter lint, skill description rendering, trigger-phrase mental simulation, etc.)
- [ ] **`changelog.d/` fragment** added; `plugin.json` version bumped if user-visible (generated `CHANGELOG.md` changes only in a release PR)
- [ ] **Gemini cross-check** completed — state outcome (H/M/L confidence + plan-change yes/no), OR document why exempt (narrow exception class only)
- [ ] **Memory file refresh** applicable? (state where, or "no — substance not memory-worthy")

## Test plan

- [ ] CI checks, including skill validation, deterministic tests, secret scan,
      CodeQL, release consistency, and export safety, pass
- [ ] Merge this PR
- [ ] **Post-merge release tag** (only if `plugin.json` version was bumped — see addition #3):
  ```bash
  cd <agent-collab-plugin-checkout>
  git checkout main && git pull origin main
  # First prove clean reachable history and integrate every required signed
  # native-runtime capability. The release workflow fails closed without both.
  git tag -s v<X.Y.Z> -m "agent-collab v<X.Y.Z>"  # signed annotated tag
  git push origin v<X.Y.Z>  # triggers the gated single-package release
  ```
- [ ] **Restart the active host runtime** so the marketplace clone refreshes (skill changes are not picked up mid-session)

## Compliance trace

An agent fills this block in and runs `python3 scripts/check_pr_compliance.py <pr#> --repo <owner/repo>` (the tool lives in the `agent-collab-workspace` repo) before self-merging this PR, per directive #6 ("Agent merge authority").

<!-- compliance-trace:start -->
author: <Claude | Codex | Antigravity | ZCode | custom | operator>
standing_directives: <directives followed, comma-separated>
tier: <1 | 2 | 3 — formal tier declaration; Tier 2/3 REQUIRE a real cross_check verdict (a bare "N/A" is valid only at Tier 1)>
cross_check: <e.g. "2 rounds; round 2 VERDICT: PROCEED" — or, ONLY at Tier 1, "N/A — <why workflow-exempt>">
post_condition: <result, or N/A>
mcp_coverage_gap: <NONE | FILED: issue-link>
operator_reserved: <yes | no>
<!-- compliance-trace:end -->
