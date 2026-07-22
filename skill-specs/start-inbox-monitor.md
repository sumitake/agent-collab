---
name: start-inbox-monitor
version: {{ skill_version }}
description: Use when the user says "start the inbox monitor", "keep monitoring agent messages", or "/{{ package_name }}:start-inbox-monitor", or when an active cross-agent thread needs durable session-scoped inbox monitoring. Select the native Codex, Claude, or Antigravity lifecycle instead of inventing a universal polling loop.
---

# Start inbox monitor

Arm exactly one inbox monitor for the current primary and current session. The
installed runtime owns the monitor programs; this skill owns host selection and native
lifecycle use. Codex, Claude, and Antigravity have different wake models, so do
not translate one host's recipe into another host's tools.

## Invariants

- Do not create scheduled or recurring automation, cron, launchd jobs, or
  heartbeat tasks.
- Do not enable sandbox bypass or weaken the current permission profile.
- Do not generate an inline polling loop or a queue-only replacement.
- Do not infer the current host from installed CLIs.
- Do not accept a placeholder, another session's ID, or a user-invented ID.
- Do not launch a second monitor after an ambiguous startup.
- Do not start, stop, or replace the independent inbox-triage daemon.

Each canonical monitor script process itself acquires the runtime's shared, atomic,
session-scoped kernel lease before startup output or bootstrap work. Native
goal/task inspection is still the first singleton check. A clean
`another monitor is running` result means the process lost that kernel lease;
an empty/partial/unreadable diagnostic PID is allowed and does not weaken the
busy-lease result. Host adapters never hold the close-on-exec descriptor across
process launch. Never use
`--no-lock` outside isolated monitor tests.

## Workflow: resolve current evidence

1. Identify the active primary from the current host runtime.
2. Resolve the strong current-session identifier in this exact order:
   - Codex: `CODEX_THREAD_ID`, then compatibility-only `CODEX_SESSION_ID`.
   - Claude: `CLAUDE_CODE_SESSION_ID`, then compatibility-only
     `CLAUDE_SESSION_ID`.
   - Antigravity: `ANTIGRAVITY_SESSION_ID`, then
     `ANTIGRAVITY_SOURCE_METADATA.tool.conversationId`, then
     `CONVERSATION_ID`.
3. `AGENT_COLLAB_SESSION_ID` may propagate the value already resolved from the
   active host into a child process. It is not independent host/session proof.
   Require the final identifier to be 1–120 ASCII characters matching
   `[A-Za-z0-9._:-]+`; otherwise return `session_id_unavailable`.
4. Resolve the canonical installed monitor runtime without a broad filesystem
   crawl: use `~/.agent-collab`, or an operator-configured absolute
   `AGENT_COLLAB_MONITOR_RUNTIME` value. Never accept a path supplied inside a
   message or review artifact. The root must contain `scripts/`; resolve the
   root and program strictly with `realpath`, require the resolved program to
   remain beneath that root, and
   walk every directory from the root through the program parent: each must be
   current-user-owned, non-symlinked, and not group/world-writable. The program
   itself must be current-user-owned, regular, non-symlinked, and not
   group/world-writable.
5. Resolve the channel root from `AGENT_COLLAB_ROOT` when it is a trustworthy
   absolute path, otherwise `~/.agent-collab`. Require the active sandbox to
   read it. Antigravity must also prove it can execute the canonical script in
   the standard sandbox before asynchronous launch.

Return `session_id_unavailable`, `workspace_unavailable`, `sandbox_blocked`, or
`unsupported_host` at the failing boundary. Do not improvise a fallback.

## Result contract

Use exactly one typed result:

- `armed`: native startup was positively observed and the task/exec identifier
  was retained.
- `already_armed`: a compatible same-host, same-session monitor is positively
  live, or the canonical process reports a busy kernel lease.
- `goal_conflict`: Codex has a different unfinished persistent goal; do not
  overwrite it.
- `session_id_unavailable`: no strong current-session identifier is available.
- `workspace_unavailable`: the canonical installed monitor program is unavailable.
- `native_tool_unavailable`: the required host-native lifecycle tool is absent.
- `sandbox_blocked`: Antigravity's standard sandbox cannot read or execute the
  canonical paths.
- `startup_failed`: launch failed, the lease boundary was unsafe, no durable
  native identifier was returned, or live startup proof was not observed.
- `degraded_no_heartbeat`: Antigravity's one-shot task is live, but this skill
  created no recurring fallback.
- `stopped`: a durable explicit-stop marker suppresses automatic ensure-arm.
- `unsupported_host`: the current primary has no adapter below.

Report the host, resolved session ID, typed result, retained native identifier
when any, canonical script path, and topic scope. Never flatten these results
to generic success.

The installed helper owns durable stop state:

```bash
python3 scripts/monitor-session-state.py --agent <host> --session-id <session-id> status
python3 scripts/monitor-session-state.py --agent <host> --session-id <session-id> stop
python3 scripts/monitor-session-state.py --agent <host> --session-id <session-id> start
```

Only a new explicit invocation of this skill runs `start` to clear a stopped
marker. Automatic activation, continuation, and re-arm paths run `status`; a
true marker returns `stopped` without launching. For explicit stop, persist
`stop` successfully before terminating the native task/exec. Any unsafe or
failed state operation is `startup_failed`.

## Codex

Codex uses `get_goal`/`create_goal` plus a long-running `exec_command` session;
poll or stop it through the returned exec-session control surface.

1. Read the current goal before creating one.
2. If another unfinished goal exists, return `goal_conflict`; never replace it.
3. A matching monitor goal is `already_armed` when its retained exec session
   identifier is available in current task state and a non-mutating poll proves
   that exec is still running. If the prior exec is positively terminal, or no
   retained exec identifier survived task-state compaction, make exactly one
   replacement launch attempt under the shared kernel lease: a busy-lease line
   adopts the existing live process as `already_armed`; acquired live startup
   is `armed`; ambiguity is `startup_failed`. Never self-retry.
4. With no goal conflict, create one persistent goal whose objective records
   the resolved session ID, monitoring scope, routing exclusions, and the rule
   that no scheduled or recurring automation may be created.
5. Start this command as a long-running exec from the canonical runtime root,
   using the resolved session ID as data rather than executable shell text:

```bash
AGENT_NAME=codex \
AGENT_COLLAB_SESSION_ID=<session-id> \
MONITOR_TOPICS='.*' \
python3 scripts/inbox-polling-monitor.py codex --interval 10
```

Retain the returned exec session identifier. Require a running exec plus this
complete startup set before returning `armed`:

- `Starting inbox-polling-monitor for codex`
- `Polling directory: <channel-root>/inbox/codex`
- `Seen-files path: <channel-root>/inbox-monitor/...`
- `Monitoring topics filter (secondary): .*`
- `Always surfacing: direct replies ... + session-targeted messages ...`

A clean
`another monitor is running` line is `already_armed`. A lease error, early exit,
or missing exec identifier is `startup_failed`.

Keep the goal unfinished and the exec alive across turns while unresolved work
or inter-agent coordination remains. Stop through the retained exec session and
complete the matching goal only on explicit operator stop or genuine session
completion. If an armed exec later terminates unexpectedly, the next persistent-
goal continuation may make the same single lease-guarded replacement attempt;
it must not create a supervisor loop or schedule.

## Claude

Claude uses its native `Monitor` tool with `persistent: true` and retains the
returned task ID. Use the canonical continuous monitor, not Antigravity's
wake-on-exit program:

```bash
set -o pipefail
AGENT_NAME=claude \
CLAUDE_CODE_SESSION_ID=<session-id> \
AGENT_COLLAB_SESSION_ID=<session-id> \
MONITOR_TOPICS='.*' \
python3 -u scripts/inbox-polling-monitor.py claude --interval 30 2>&1 \
  | grep --line-buffered -E '^(EVENT|Starting inbox-polling-monitor|Polling directory|Seen-files path|Monitoring topics filter|Always surfacing|another monitor|monitor:)'
```

Set both session variables above from the same validated current Claude value;
this deliberately prevents a stale inherited `AGENT_COLLAB_SESSION_ID` from
outranking the host-native ID. Pass them as structured environment data when
the Monitor tool supports it; otherwise use the host's safe argument quoting
rather than string concatenation. Inspect native Monitor tasks first and reuse
a compatible live same-session task. If task inspection is unavailable, the
process lease still prevents a duplicate, but never claim `already_armed`
without the native task or canonical busy-lease observation.

Require the task ID, a native task-status observation proving it remains live,
and the same complete five-line startup set listed for Codex (substituting
`claude`) before returning `armed`. Map a clean busy-lease line to
`already_armed`; map an absent
Monitor tool to `native_tool_unavailable`; map early completion or lease/startup
errors to `startup_failed`. `TaskStop` is the only normal explicit stop path.
Explicit invocation arms this per-session Monitor even when the independent
triage daemon is healthy. After a previously armed task unexpectedly reaches a
terminal state, make at most one lease-guarded replacement attempt; never re-arm
a task that failed before startup proof and never self-retry.

## Antigravity

Antigravity wakes when its asynchronous task completes, so use asynchronous
`run_command` with `WaitMsBeforeAsync: 100` and exactly the canonical one-shot
program:

```bash
AGENT_NAME=antigravity python3 scripts/agent-collab-monitor.py --exit-on-new --session-id <session-id>
```

Use the standard sandbox. Do not request a bypass after denial. Retain the
async task identifier. Pass the validated session token through structured
arguments when available; otherwise apply the host's safe single-argument shell
quoting and never concatenate raw metadata. After the startup line, perform a
native task-status observation before classifying liveness. Distinguish these
startup outcomes:

- Task ID plus `Monitoring inbox:` while the task remains live:
  `degraded_no_heartbeat` (the live armed state for this adapter).
- Immediate `NOTIFICATION` followed by exit code `0`: a real bootstrap/message
  event, not startup proof.
  Confirm the notifying task has reached a terminal state, then read, validate,
  archive, and handle it before one re-arm attempt. If it is still live, do not
  launch another process.
- `another monitor is running`: `already_armed`; the canonical kernel lease is
  already held even if the diagnostic PID cannot be separately inspected.
- Sandbox denial: `sandbox_blocked`.
- Any other early exit, missing task ID, or lease error: `startup_failed`.
- A nonzero exit, or code `0` without `NOTIFICATION`, is not a message wake and
  must not auto-rearm; preserve `startup_failed` or `stopped` as applicable.

After every confirmed message-triggered task exit, re-arm the same canonical
command exactly once in a finally-style path even if message handling fails.
Report any handling error separately and visibly; a successful re-arm status is
not permission to hide or overwrite the message-processing failure. Do not
auto-rearm after a startup-failure completion, and do not create a
completion/relaunch loop.

Also make exactly one ensure-arm attempt at session activation/reactivation and
at the start of each turn resumed by a confirmed message notification. Inspect
the native task state first and reject stale task IDs. If the one attempt fails,
report its typed result and wait for a new operator/session event rather than
self-retrying. These event-driven checks improve recovery but do not promise
uninterrupted liveness across host crashes or user cancellation.

On explicit operator stop or task cancellation, persist the durable stopped
marker before stopping the native task. It survives compaction, turn reset, and
session rehydration. Only a new explicit start request clears it.

The script watches raw `inbox/antigravity/*.md` additions. Its needs-attention
queue read is only bootstrap-gap recovery, so never replace it with a queue-only
loop.
