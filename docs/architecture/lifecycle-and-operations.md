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

For an activation package, the closed management client can report status
without invoking a provider:

```text
python3 "<installed-plugin-root>/runtime_setup.py" status
python3 "<installed-plugin-root>/runtime_setup.py" broker-status
```

Use the exact installed plugin root supplied by the host or migration doctor.
Do not search for provider executables, substitute a binary, or add path/model
overrides. Policy-only packages return typed unavailable for native lifecycle
operations.

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

### Native lifecycle during package update

Package refresh, import, readiness, and route invocation do not silently
install or mutate native lifecycle state. An activation update uses the closed
candidate/proof/commit lifecycle implemented by the package. A candidate is
not a normal routing target, and a previous verified lane is retained until the
new lane is committed and separately drained.

General users should follow the selected release's management output rather
than reconstructing lifecycle commands or paths. A failed update must leave the
previous verified state selected or return a typed lifecycle error.

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
| Safe mode keeps native routes unavailable | Execution is intentionally disabled. | Finish migration and verification, unset safe mode, restart, and re-check readiness. |
| Version in a running session is stale | The host loaded an earlier package snapshot. | Finish the marketplace/package update and start a genuinely new session/task. |

Preserve typed errors. Do not infer failure from response prose, retry a
terminal cleanup/teardown error, or substitute a different provider behind an
explicit target.

## Safe mode and rollback

The normal operational rollback is policy-only safe mode:

1. Set `AGENT_COLLAB_SAFE_MODE=1` in the active host environment.
2. Restart the host.
3. Confirm native model routes return typed unavailable.
4. Run migration and package checks while execution is disabled.
5. Unset safe mode and restart only after the selected state is verified.

Safe mode does not reinstall an older or retired package. It preserves the
public policy boundary while stopping model execution.

If an activation installation has one complete prior verified broker record,
the closed management client also exposes:

```text
python3 "<installed-plugin-root>/runtime_setup.py" rollback-broker
```

That action selects only the verified prior record. It is typed unavailable
when no valid rollback target exists. It is not a general package-version pin,
and it accepts no caller-selected path, socket, provider, model, or binary.

Published release rollback is a release-governance decision. Do not delete and
reuse a published version, detach a shared marketplace clone, or reinstall a
retired package. Prefer a signed revocation where required and a higher patch
release.

## Remove

Remove active lifecycle state before removing an activation package, because
the package contains the only supported management client:

```text
python3 "<installed-plugin-root>/runtime_setup.py" uninstall-broker
```

The command is idempotent when no broker is installed. It removes the exact
active job, socket, configuration, and mutable state while intentionally
retaining immutable version records used for audit/rollback evidence.

Then remove the package.

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

Retired standalone packages map into the unified package:

- `codex-tools →` managed Codex backend in `agent-collab`;
- `glm-worker →` managed OpenCode backend in `agent-collab`; and
- host-specific collaboration packages → dynamic host profiles in
  `agent-collab`.

The exhaustive namespace mapping and cleanup rules live in
[`docs/migration-from-legacy-packages.md`](../migration-from-legacy-packages.md).
Treat names in that document as historical/migration evidence, not active
installation instructions.

For evidence-plane distinctions, read [Status and evidence](status-and-evidence.md).
