# Lifecycle and operations

< [Architecture handbook index](README.md)

This guide covers the public user lifecycle. It uses portable placeholders and
host-supported plugin commands; it does not expose operator-specific paths or
private provider invocation details.

## Before installing

Confirm these boundaries:

- The repository is source-available under PolyForm Strict. Installation does
  not grant redistribution, derivative-work, or commercial-use rights.
- The package currently ships native host manifests for Claude Code and Codex.
  Other hosts need a compatible plugin surface; do not recreate a retired
  host- or provider-specific shim.
- Managed native execution currently targets the platform described by the
  selected release manifest. Skills and migration can still be present when a
  native route is unavailable.
- Supported provider CLIs and authentication remain external prerequisites.
  Install and authenticate them only through vendor-supported interfaces.

## Install

### Claude Code

From Claude Code:

```text
/plugin marketplace add sumitake/agent-collab
/plugin install agent-collab@agent-collab
```

Start a new session, then run:

```text
/agent-collab:migration-doctor
```

### Codex CLI/app

From a terminal with Codex installed:

```text
codex plugin marketplace add sumitake/agent-collab
codex plugin add agent-collab@agent-collab
```

Start a new Codex task, then invoke the `agent-collab:migration-doctor` skill.
The repository tests pin `codex plugin add`; `codex plugin install` is not the
current command.

### Other hosts

Use the same single package only if the host has a compatible, supported
plugin manager. If it cannot load the package and preserve the closed request
boundary, treat it as unsupported. Do not copy skills into a provider-specific
package or rebuild a raw provider route.

## Verify

Installation, selection, and readiness are separate checks.

1. **Package inventory:** confirm the host reports
   `agent-collab@agent-collab` and the expected version.
2. **Fresh load:** start a new session/task; a running session can retain the
   previously loaded plugin.
3. **Migration doctor:** remove every active or installed retired package it
   reports, then run the doctor again.
4. **Runtime status:** invoke `agent-runtime-status` for a provider-free typed
   snapshot. A listed route is not proof of readiness.
5. **Bounded smoke test:** invoke one low-risk read-only workflow, such as a
   second opinion on a short draft, and verify the returned family is eligible
   and independent.

For an activation package, the installed package can report status without
model inference. Run the provider-free doctor and the single readiness
snapshot:

```text
python3 "<installed-plugin-root>/migration_doctor.py" --json
printf '%s\n' '{"operation":"readiness","request_id":"runtime-status-1","quality_profile":"frontier","effort_class":"maximum","timeout_ms":120000}' | python3 "<installed-plugin-root>/coordinator.py"
```

Use the exact installed plugin root supplied by the host or migration doctor.
Do not search for provider executables, substitute a binary, or add path/model
overrides. Policy-only packages return typed unavailable for native actions.

## Use

Invoke the skills in normal language or by their host command. Examples:

```text
/agent-collab:second-opinion Review this architecture decision.
/agent-collab:code-review Review the current diff against the task.
/agent-collab:qa-verify Verify the completed work against these acceptance criteria.
/agent-collab:delegate Split this read-only research list with an independent reviewer.
/agent-collab:agent-runtime-status
```

The primary should always:

- provide bounded context and an explicit expected output;
- treat delegated output as untrusted until reviewed;
- preserve the returned typed status and provenance;
- run local tests before claiming completion; and
- keep merge, deployment, secret, and destructive decisions within the user's
  and repository's authority boundaries.

`project-estimation` is offline and read-only by default. The packaged v6.2.4
source contains an explicit bootstrap prior: enhancement duration is
descriptive, greenfield may return `no_compatible_prior`, and absent token
evidence returns `unavailable_no_token_prior` rather than zero. Persist an
estimate only with the request's explicit consent, and do not interpret
bootstrap presence as a release, installation, activation, or promoted
calibration claim.

## Update

### Claude Code

Refresh the marketplace, update the package, then restart Claude Code:

```text
claude plugin marketplace update agent-collab
claude plugin update agent-collab@agent-collab
```

After restart, verify the reported version and re-run
`/agent-collab:migration-doctor`. Reloading an already-running session is not a
substitute for applying a pending package version.

### Codex CLI/app

Refresh the configured Git marketplace and start a new task:

```text
codex plugin marketplace upgrade agent-collab
codex plugin list --json
```

Read only the `agent-collab@agent-collab` version from local inventory; avoid
publishing the full output because host inventories can include local paths. If
the refreshed snapshot is not installed, use the current remove/add commands:

```text
codex plugin remove agent-collab@agent-collab --json
codex plugin add agent-collab@agent-collab --json
```

Then start a new task and re-run migration doctor and runtime status.

### Antigravity

Import the exact host-resolved Claude package root, verify the imported
manifest version, and start a fresh Antigravity session:

```text
agy plugin install "<absolute-Claude-plugin-root>"
agy plugin list --json
```

The import inventory identifies the package but does not currently report its
version. Read `.claude-plugin/plugin.json` beneath the host-resolved
Antigravity import root and require the intended version before running
migration doctor and runtime status.

### Grok

An install pinned to a release tag remains pinned: `grok plugin update` reports
that fact and does not advance it. Preserve plugin data while replacing only
the pinned package code, then verify the new inventory and start a fresh Grok
session:

```text
grok plugin uninstall agent-collab --confirm --keep-data
grok plugin install "sumitake/agent-collab@vX.Y.Z#plugins/agent-collab" --trust
grok plugin list --json
```

Require the registry's `git_ref`, resolved commit, and package version to match
the signed release tag. Do not convert a pinned install into an unreviewed
moving branch merely to make the generic update command advance it.

### Co-packaged runtime during update

Version 6 has no separately installed broker, daemon, socket, selector, lane,
or setup lifecycle. The signed runtime bundle and its manifest are members of
the plugin package. Updating the package therefore updates one closed unit;
readiness verifies that unit before any semantic request.

The governed release build refreshes the supported provider CLI catalog and
compatibility evidence before signing, even when the verification host has not
yet auto-updated. A normal vendor-managed CLI update covered by that release is
admitted automatically. Qualification selects a compatibility profile; it is
not a governance label for the vendor binary and must not reduce caller
authority or functionality. If a later executable falls outside the published
evidence, record the typed readiness result and refresh the next plugin build;
do not call the vendor release defective, roll it back merely to match a stale
profile, or substitute a raw binary.

If an update is incomplete or incompatible, keep the typed unavailable or
protocol result, inspect the package inventory and migration doctor, and start
a fresh session only after the host reports the intended package version. Do
not reconstruct a lifecycle path, copy a runtime out of another package, or
fall back to a retired provider-specific plugin.

## Troubleshoot

| Symptom or status | Meaning | Safe response |
| --- | --- | --- |
| Skill is missing | The package may not be installed, enabled, or loaded in this session. | Check host plugin inventory, then start a new session/task. |
| `duplicate_blocked` or migration conflict | A retired package remains active or installed. | Run migration doctor, apply only its host-specific removal actions, and run it again. |
| `unavailable` | The route, runtime, provider prerequisite, or observed readiness is not currently usable. | Run runtime status and migration doctor; check supported vendor authentication separately. Do not use a raw-provider fallback. |
| `same_family_blocked` | The requested reviewer/worker is not independent from the primary or artifact author. | Select an eligible different family or treat the review as non-independent. |
| `unknown_family` | Current identity or artifact lineage cannot establish governance independence. | Correct the supported host identity signals; do not guess from a model nickname or installation path. |
| `config_error` | Request fields, host identity, or route/action pairing violate the closed schema. | Use the installed skill/package reference; remove unsupported fields rather than widening the schema. |
| `auth_error` or `quota_error` | The managed provider prerequisite failed after routing. | Use the provider's supported login/account interface or wait for quota. Keep the same authority. |
| Output-only worker made no caller-worktree changes | Expected behavior. | Review the returned artifact and apply it through the trusted primary if appropriate. |
| Governance call refuses partial identity | Expected fail-closed behavior. | Establish all required current-session identity fields or use a non-governance workflow with its warning. |
| Version in a running session is stale | The host loaded an earlier package snapshot. | Finish the marketplace/package update and start a genuinely new session/task. |

Preserve typed errors. Do not infer failure from response prose, retry a
terminal cleanup/teardown error, or substitute a different provider behind an
explicit target.

## Fail closed and release correction

The direct runtime fails typed when the selected package, manifest, bundle,
provider prerequisite, source boundary, or cleanup proof is not usable. It
does not silently choose a wider authority, restore a retired package, or
replay the whole request through another provider.

A published release correction is a release-governance decision. Do not move
or reuse a published tag, detach a shared marketplace clone, copy a runtime
between packages, or reinstall a retired package. Publish a signed revocation
when required and a higher patch release for corrected bytes. Until then,
leave the affected semantic action unused or remove the package through the
host manager.

Local activation-release preflight also needs macOS code-signing trust-service
access. A managed execution sandbox can make the same notarized bytes return
`notarization_not_confirmed`; that result is neither artifact rejection nor
permission to proceed. Keep the verified tree and tag state unchanged, then
run the complete preflight with authorized trust-service access. Only a full
pass permits creation of the immutable tag; never weaken the notarization gate
or substitute a hand-run partial check.

## Remove

Version 6 has no separately installed broker or native lifecycle state to
remove. Remove the package through the host manager.

Claude Code:

```text
claude plugin uninstall -s user -y agent-collab@agent-collab
```

Codex:

```text
codex plugin remove agent-collab@agent-collab --json
```

If the `agent-collab` marketplace is no longer needed, remove it through that
host's marketplace command. Start a new session/task and confirm the skills are
absent. Package removal does not authorize manual deletion of unknown host
paths or credential state.

## Legacy migration

The namespace changes and cleanup rules live in
[`docs/migration-from-legacy-packages.md`](../migration-from-legacy-packages.md).
Treat names in that document as historical/migration evidence, not active
installation instructions.

For evidence-plane distinctions, read [Status and evidence](status-and-evidence.md).
