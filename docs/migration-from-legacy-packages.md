# Unified agent-collab migration

`agent-collab 3.0.0` replaces every prior public package with one dynamic-host
package. Remove all old packages; they are not dependencies, presets, shims, or
rollback artifacts.

The historically public package IDs `agent-collab-plugin`, `gemini-collab`,
and `grok-collab` are retired aliases too. Remove them if a host reports an
exact installed plugin identity. The current GitHub repository name
`sumitake/agent-collab-plugin` is only the marketplace source and is not a
legacy package selection.

## Namespace and skill mapping

For every row below, all listed old namespaces map to the single new command.

| Old command(s) | New command |
|---|---|
| `/claude-collab:agent-readiness`, `/codex-collab:agent-readiness`, `/antigravity-collab:agent-readiness` | `/agent-collab:agent-readiness` |
| `/claude-collab:agent-runtime-status`, `/codex-collab:agent-runtime-status`, `/antigravity-collab:agent-runtime-status` | `/agent-collab:agent-runtime-status` |
| `/claude-collab:ai-merge-resolve`, `/codex-collab:ai-merge-resolve`, `/antigravity-collab:ai-merge-resolve` | `/agent-collab:ai-merge-resolve` |
| `/claude-collab:autonomy-readiness`, `/codex-collab:autonomy-readiness`, `/antigravity-collab:autonomy-readiness` | `/agent-collab:autonomy-readiness` |
| `/claude-collab:brainstorm`, `/codex-collab:brainstorm`, `/antigravity-collab:brainstorm` | `/agent-collab:brainstorm` |
| `/claude-collab:chain`, `/codex-collab:chain`, `/antigravity-collab:chain` | `/agent-collab:chain` |
| `/claude-collab:chain-configurator`, `/codex-collab:chain-configurator`, `/antigravity-collab:chain-configurator` | `/agent-collab:chain-configurator` |
| `/claude-collab:code-review`, `/codex-collab:code-review`, `/antigravity-collab:code-review` | `/agent-collab:code-review` |
| `/claude-collab:compose-skills`, `/codex-collab:compose-skills`, `/antigravity-collab:compose-skills` | `/agent-collab:compose-skills` |
| `/claude-collab:debate`, `/codex-collab:debate`, `/antigravity-collab:debate` | `/agent-collab:debate` |
| `/claude-collab:delegate`, `/codex-collab:delegate`, `/antigravity-collab:delegate` | `/agent-collab:delegate` |
| `/claude-collab:dev-delegate`, `/codex-collab:dev-delegate`, `/antigravity-collab:dev-delegate` | `/agent-collab:dev-delegate` |
| `/claude-collab:intent-check`, `/codex-collab:intent-check`, `/antigravity-collab:intent-check` | `/agent-collab:intent-check` |
| `/claude-collab:knowledge-compile`, `/codex-collab:knowledge-compile`, `/antigravity-collab:knowledge-compile` | `/agent-collab:knowledge-compile` |
| `/claude-collab:logic-check`, `/codex-collab:logic-check`, `/antigravity-collab:logic-check` | `/agent-collab:logic-check` |
| `/claude-collab:long-context`, `/codex-collab:long-context`, `/antigravity-collab:long-context` | `/agent-collab:long-context` |
| `/claude-collab:orchestrate`, `/codex-collab:orchestrate`, `/antigravity-collab:orchestrate` | `/agent-collab:orchestrate` |
| `/claude-collab:qa-verify`, `/codex-collab:qa-verify`, `/antigravity-collab:qa-verify` | `/agent-collab:qa-verify` |
| `/claude-collab:red-team`, `/codex-collab:red-team`, `/antigravity-collab:red-team` | `/agent-collab:red-team` |
| `/claude-collab:second-opinion`, `/codex-collab:second-opinion`, `/antigravity-collab:second-opinion` | `/agent-collab:second-opinion` |
| `/claude-collab:simulate-user`, `/codex-collab:simulate-user`, `/antigravity-collab:simulate-user` | `/agent-collab:simulate-user` |
| `/claude-collab:teamwork` | `/agent-collab:teamwork` |
| `/claude-collab:ui-to-code`, `/codex-collab:ui-to-code`, `/antigravity-collab:ui-to-code` | `/agent-collab:ui-to-code` |
| `/claude-collab:untrusted-audit`, `/codex-collab:untrusted-audit`, `/antigravity-collab:untrusted-audit` | `/agent-collab:untrusted-audit` |
| `/claude-collab:visual-review`, `/codex-collab:visual-review`, `/antigravity-collab:visual-review` | `/agent-collab:visual-review` |
| `/codex-tools:codex-second-opinion` | `/agent-collab:second-opinion` with `target=codex` |
| `/codex-tools:codex-high-stakes-advisor` | `/agent-collab:governance-review` with `target=codex` |
| `/codex-tools:codex-tiebreaker` | `/agent-collab:second-opinion` with `target=codex`, role `tiebreaker` |
| `/codex-tools:codex-build-coding` | `/agent-collab:dev-delegate` with `target=codex`; typed unavailable until the hardened mutation backend exists, with no advisory fallback |
| `/glm-worker:glm-coding` | `/agent-collab:dev-delegate` with `target=opencode` and model preset `opencode/glm-5.2` |
| `/glm-worker:glm-huge-context` | `/agent-collab:long-context`; central policy selects an advertised read-only long-context route |
| `/grok-worker:grok-build-coding` | `/agent-collab:dev-delegate` with the managed Composer output-only role |
| `/grok-worker:grok-huge-context` | `/agent-collab:long-context` with `target=grok` |
| `/grok-worker:grok-parallel-execution` | `/agent-collab:delegate`; the raw escape hatch has no replacement |
| `/agent-collab-plugin:*`, `/gemini-collab:*`, `/grok-collab:*` | Use the corresponding `/agent-collab:*` command when one exists; otherwise the old alias capability is unavailable |

## Migration sequence

1. Install `/agent-collab` from this marketplace.
2. Run `/agent-collab:migration-doctor`.
3. Remove every installed or active legacy package reported by the doctor. Its
   observations preserve the source host, including Codex
   `[plugins."name@marketplace"]` entries from `~/.codex/config.toml`, so each
   uninstall command targets the package manager that owns the residue.
4. Re-run the doctor; provider routing remains blocked until duplicate state is
   absent.
5. Configure unknown/custom primaries explicitly with primary id, family,
   active model, host runtime, and session identifier.

## Safe-mode rollback

Policy-only safe mode returns typed unavailable for native Gemini, Codex,
OpenCode, Grok 4.5, and Composer roles. An async inbox remains eligible only
when the host explicitly observes its transport available; the public
coordinator exposes non-governance readiness only and never sends. Without that
observation the inbox is typed unavailable too. Safe mode is the operational
rollback. Reinstalling an old package is never a rollback path.

Set `AGENT_COLLAB_SAFE_MODE=1` in the active host runtime environment and
restart to enter safe mode. Unset it and restart after the migration doctor and
eligible-route checks pass.

The active package intentionally contains no unsigned runtime placeholder. Every
model route therefore remains temporarily unavailable until the signed private
runtime advertises the complete Gemini, Codex, OpenCode, Grok, and Composer
route/action matrix. A policy-only release requires an empty runtime manifest
and archive; it installs the migration and policy surface while every native
route stays typed unavailable. An activation release requires the complete
contracts plus commit-bound macOS signing/notarization evidence. No raw launcher
is a migration fallback.

The runtime manifest does not control signer trust. The operator-owned Apple
Team ID must be pinned independently in `plugins/agent-collab/signing_policy.py`;
activation verification rejects an empty anchor, a manifest mismatch, or a
different `codesign` TeamIdentifier. Until that reviewed anchor and matching
Developer ID/notarization credentials exist, native activation is typed
unavailable. This does not block an explicitly policy-only release whose
manifest and archive contain no runtime.

## Public-release history gate

Deleted provider and preset sources remain in this private repository's git
history until the separately authorized history rewrite is performed. Do not
change repository visibility or export this clone directly. A public release
must come from an audited clean-history export that passes both active-tree and
history modes of `scripts/check-public-export-safety.py` after the primary
performs the backup, rewrite, branch/tag/release cleanup, and GitHub residual
audit. History mode reads every reachable blob as bytes, scans archive members
and renamed executor markers, and rejects symlinks or other unsafe git tree
modes. It also inspects all refs, annotated-tag objects and messages, direct
blob/tree refs, release-tag form and target, and provider-backend directories
inside recursively nested archives. Cumulative archive depth, member count,
per-member size, and decompressed-size limits fail closed; static Python argv
construction is scanned semantically rather than by raw substrings alone. This
document does not authorize those destructive operations.

## Native package and artifact contract

The unified package has one Claude-compatible manifest and one Codex-native
manifest. `.claude-plugin/marketplace.json` and
`.agents/plugins/marketplace.json` are generated from the same package and may
contain no legacy preset or provider package.

Governance plus applicable review, fallback, and worker requests bind the
artifact separately from the prompt. The native protocol receives exact
captured bytes as base64 with
SHA-256, size, author model, and derived family; it must decode and verify those
fields before dispatch. Conflicting active-model family signals resolve to
unknown even when a stale asserted family is present. Unknown provenance fails
governance closed and warns on otherwise permitted non-governance delegation.
