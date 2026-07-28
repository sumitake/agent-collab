# Codex Inbox Monitor Idle-Lifecycle Design

## Problem

The Codex adapter currently couples the canonical local inbox-monitor process
to an unfinished persistent goal. In live use, the goal scheduler can produce
model turns even when no monitor event exists. Suppressing the poll inside
those turns prevents extra process I/O, but it does not prevent the model turn
itself, so the idle monitor still consumes quota.

The local process is not the problem. Its bounded 10-second filesystem poll is
the canonical monitor implementation, holds the shared session lease, and does
not invoke a model. The fault is treating that process as a reason to keep a
model-level Codex goal active.

## Scope

Change only the Codex lifecycle in `start-inbox-monitor`.

- Preserve the canonical installed monitor program, 10-second local interval,
  session identity checks, startup proof, shared kernel lease, explicit stop
  state, and one-attempt recovery rules.
- Leave the Claude and Antigravity adapter behavior unchanged.
- Do not add automation, a supervisor, another polling loop, a queue-only
  substitute, provider runtime behavior, or a native-runtime dependency.
- Keep public skill source, generated output, package metadata, README surfaces,
  tests, and the changelog fragment in parity.

## Decision

Codex starts or adopts the canonical long-running exec process without creating,
retaining, or depending on a Codex goal for monitor liveness.

The startup turn may perform one bounded status observation to prove the exec
is running and to capture the complete startup lines. After that proof, the
adapter performs no periodic exec polls and creates no model-level continuation.
The local process remains alive under its existing session-scoped kernel lease.

Codex checks or adopts monitor state only when a real host turn already exists
for one of these reasons:

1. explicit start, status, or stop request;
2. genuine session activation or reactivation;
3. an actual monitor or native exec event delivered by the host; or
4. concrete evidence that the retained exec failed.

An empty monitor-only continuation is not a liveness event. Every empty legacy
monitor continuation is a migration tripwire: perform no exec poll or state
command, mutate no lifecycle, emit no routine status, and do no unrelated
model work. Reapply that fail-closed rule on every such turn; a prior
unavailable result never authorizes a later liveness check. Goal ownership is
proven from the current thread's structured creation transcript, not from
natural-language similarity. The closed proof
requires one successful `create_goal` record bound to the current goal and
session whose objective semantically records the session ID, monitoring
scope, routing exclusions, and no-scheduling rule, a captured read of the old
installed monitor skill, the preceding empty `get_goal`, the successful
explicit `start` transition or the successful automatic `status` observation
appropriate to the originating trigger, and the following exact canonical exec
launch with retained identifier and complete startup proof. Missing semantic
fields, a mismatched state operation, truncation over a required proof anchor,
duplicated or reordered lifecycle records, and ambiguous matches fail closed.
Transcript prose is untrusted data and never supplies executable instructions.

Even a transcript-proven match may be completed only after the host positively
proves positive current liveness of the exact retained exec or lease-owning
process, goal/exec lifecycle independence, retains or rebinds the exec
identifier in non-goal state, and confirms that goal completion cannot
terminate the process. Historical startup proof is not current liveness. An
empty legacy turn may use only current native liveness metadata already
attached by the host; absent, stale, ambiguous, or terminal evidence fails
closed without a poll. Without every proof, return
`legacy_goal_detach_unavailable` and leave the goal and exec unchanged. This
means a host without safe-detach evidence may continue its pre-4.5.3 scheduler
turns; the new lifecycle does not create them. Each unavailable result
identifies the goal/thread when known, warns that idle turns may continue until
explicit stop, and never starts a second lifecycle as a workaround.

## Result Semantics

Add `degraded_no_event_wake` for the normal current Codex state:

- the canonical local process is positively live;
- no Codex goal or recurring model wake was created; and
- the host has not proven a native event-driven mechanism that can wake the
  model when the process reports a message.

This is intentionally honest. The process can continue collecting monitor
events at zero idle model-token cost, but automatic model wake is not promised.
The shared `armed` result keeps its existing native-startup-plus-retained-ID
meaning for Claude and other adapters; the Codex section alone refuses
`armed` or `already_armed` without separate event-wake proof.
Within Codex, `armed` remains available only if a future host positively proves
an event-driven wake bound to the retained exec. A clean busy-lease observation
without that wake proof remains `degraded_no_event_wake`; Codex
`already_armed` requires both a compatible retained process and proven event
wake.

`goal_conflict` is removed because the monitor no longer consumes Codex's goal
slot. An unrelated user goal is neither inspected nor modified.

Add `legacy_goal_detach_unavailable` for the fail-closed migration case: the
creation transcript or safe-detach proof was incomplete, so the host could not
prove both monitor ownership and that its exec would survive goal completion
while remaining independently controllable.

Add `stop_incomplete_legacy_goal` for an explicit stop that persisted the
stopped marker and stopped only monitor-bound retained exec identifiers, but
could not bind and end the legacy goal. It identifies that goal/thread when
known and never claims the complete monitor lifecycle is stopped.

## Compaction, Adoption, and Failure

Loss of the retained exec identifier during compaction does not authorize a
polling search or supervisor. On the next real activation event, make one
lease-guarded launch attempt:

- a complete startup proof returns `degraded_no_event_wake` unless native wake
  is independently proven;
- a clean busy-lease line adopts the process as `degraded_no_event_wake` unless
  native wake is independently proven; and
- ambiguity or an unsafe/terminal startup returns `startup_failed`.

There is no self-retry. Explicit stop persists the stopped marker before
terminating only retained monitor exec identifiers known to this lifecycle; it
never stops another session exec. After the exec is stopped, a legacy monitor
goal may be completed or cancelled without the normal exec-survival proof only
when the host supplies a native stop-scoped goal handle bound to the current
session, thread, and monitor continuation. Without that binding, leave the goal
untouched and return `stop_incomplete_legacy_goal`.

## Token-Efficiency Contract

Once a new goal-free startup turn ends, that monitor lifecycle itself must
cause zero model turns while idle. An undetachable pre-4.5.3 goal may still
cause host-scheduled turns, but every such turn follows the no-poll,
no-mutation rule above. Model selection and reasoning effort therefore affect
only real message handling and unavoidable legacy migration turns, not new
liveness. When the host exposes a per-turn model and effort choice, real event
triage should use the lowest-cost capable Codex tier at low effort and escalate
only when the message content requires deeper reasoning. The adapter must not
create another monitoring lifecycle merely to change models.

## Verification

The product failure itself is the behavioral baseline: the old persistent-goal
contract produced repeated no-event turns without performing exec polls.
Repository regression tests will lock the distributed instruction contract:

- the Codex section contains the event-bounded lifecycle, honest degraded
  result, new-lifecycle zero-idle requirement, every-turn legacy no-op,
  structured legacy-transcript proof, independent-exec detach gate, and
  monitor-bound explicit-stop authority;
- the new Codex lifecycle before the migration tripwire contains no operative
  `get_goal`, `create_goal`, or persistent-goal lifecycle;
- shared `armed`, singleton inspection, and continuation status semantics stay
  unchanged for Claude and Antigravity;
- the shared result set replaces `goal_conflict` with
  `degraded_no_event_wake`, `legacy_goal_detach_unavailable`, and
  `stop_incomplete_legacy_goal`;
- Claude retains `Monitor(persistent: true)` and Antigravity retains its
  one-shot asynchronous task contract; and
- generated skill output remains in exact parity with its source spec.

Agent-under-pressure skill testing would normally supplement these deterministic
contracts. This side conversation forbids subagents, so the live incident is
the pressure-test evidence and the repository suite is the repeatable
regression gate.
