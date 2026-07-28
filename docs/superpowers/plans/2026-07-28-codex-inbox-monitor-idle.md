# Codex Inbox Monitor Idle Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Codex inbox monitor consume zero model turns while idle by
removing its persistent-goal lifecycle and reporting the lack of native event
wake honestly.

**Architecture:** Keep the canonical long-running local monitor process and
session lease, but make its lifecycle independent of Codex goals. A startup
turn performs one bounded proof; later state checks occur only inside a turn
that already exists for a real activation, event, status/stop request, or
concrete failure signal. The distributed skill contract carries a first-empty-
continuation tripwire and a typed `degraded_no_event_wake` state.

**Tech Stack:** Markdown skill specs, Python 3 standard-library `unittest`,
hermetic skill/marketplace generators, JSON package metadata.

## Global Constraints

- Change only the Codex adapter behavior; preserve Claude and Antigravity
  lifecycle behavior.
- Preserve the canonical installed process, 10-second local interval, session
  identity validation, startup proof, kernel lease, and explicit stopped state.
- Do not add automation, a supervisor, a model-level polling loop, a queue-only
  substitute, provider executor source, or native-runtime changes.
- Once Codex startup returns, the monitor lifecycle itself causes zero idle
  model turns.
- Do not create, retain, inspect, or conflict with a Codex goal for monitor
  liveness.
- A first empty legacy monitor continuation performs no exec poll or routine
  status and ends only the positively matching legacy monitor-owned goal.
- `degraded_no_event_wake` means the local monitor is live without a proven
  native model-wake mechanism; it must not be flattened to `armed`.
- `goal_conflict` is removed because the monitor no longer owns the goal slot.
- Package version is 4.5.3, sequenced after broker PR #70's 4.5.2.
- Commit only a unique changelog fragment; never commit generated
  `CHANGELOG.md`.
- All commits are signed. Merge only after PR #70, independent-family
  `PROCEED`, green required checks, and local `MERGE-ELIGIBLE`.
- This side conversation forbids subagents, so implementation remains inline.

---

### Task 1: Lock the Codex Idle-Lifecycle Contract in Red Tests

**Files:**
- Modify: `tests/test_start_inbox_monitor_skill.py`

**Interfaces:**
- Consumes: `read_spec() -> str`.
- Produces: `adapter_section(name: str, next_name: str | None) -> str` and
  deterministic assertions over each host adapter's distributed instructions.

- [ ] **Step 1: Add an adapter-section helper**

```python
def adapter_section(name: str, next_name: str | None = None) -> str:
    text = read_spec()
    start_marker = f"## {name}\n"
    start = text.index(start_marker)
    if next_name is None:
        return text[start:]
    end = text.index(f"## {next_name}\n", start + len(start_marker))
    return text[start:end]
```

- [ ] **Step 2: Replace the old persistent-goal expectations**

Change the shared result contract to require
`degraded_no_event_wake` and no longer require `goal_conflict`. Split the
native-adapter contract so the Codex section requires:

```python
def test_codex_monitor_is_goal_free_and_idle_token_free(self):
    codex = " ".join(adapter_section("Codex", "Claude").split())
    for required in (
        "Do not use Codex goals for monitor liveness",
        "`exec_command`",
        "`degraded_no_event_wake`",
        "zero model turns while idle",
        "first empty monitor-only continuation",
        "perform no exec poll",
        "never recreate",
        "genuine session activation or reactivation",
        "actual monitor or native exec event",
    ):
        self.assertIn(required, codex)
    for forbidden in ("`get_goal`", "`create_goal`", "persistent goal"):
        self.assertNotIn(forbidden, codex)
```

Keep separate assertions that Claude still contains `Monitor`,
`persistent: true`, and `TaskStop`, while Antigravity still contains
`run_command`, `WaitMsBeforeAsync: 100`, and the canonical one-shot command.

- [ ] **Step 3: Run the focused test and verify red**

Run:

```bash
python3 -B -m unittest tests.test_start_inbox_monitor_skill -v
```

Expected: FAIL because the current spec requires `get_goal`/`create_goal`,
contains a persistent goal, lacks `degraded_no_event_wake`, and does not carry
the zero-idle/tripwire contract.

- [ ] **Step 4: Commit the red test**

```bash
git add tests/test_start_inbox_monitor_skill.py
git commit -S -m "test: lock idle-free Codex monitor lifecycle"
```

### Task 2: Replace the Codex Persistent Goal with an Event-Bounded Exec

**Files:**
- Modify: `skill-specs/start-inbox-monitor.md`
- Generate: `plugins/agent-collab/skills/start-inbox-monitor/SKILL.md`

**Interfaces:**
- Consumes: canonical monitor command, startup-line proof, session stop-state
  helper, and the shared kernel lease.
- Produces: the `degraded_no_event_wake` Codex lifecycle and first-empty-turn
  tripwire.

- [ ] **Step 1: Correct the shared result contract**

Remove `goal_conflict`. Add:

```markdown
- `degraded_no_event_wake`: Codex's canonical local process is positively live,
  but no host-native event mechanism has been proven to wake the model; the
  adapter created no recurring model continuation.
```

Keep `armed` for a host whose native startup and event-driven wake are both
positively observed, and keep all other shared results unchanged.

- [ ] **Step 2: Replace the Codex section**

Retain the existing command and five-line startup proof, but replace the goal
lifecycle with these operative rules:

```markdown
Codex uses one long-running `exec_command` session plus the canonical process
lease. Do not use Codex goals for monitor liveness.

Inspect or adopt monitor state only when a real turn already exists because of
an explicit start/status/stop request, genuine session activation or
reactivation, an actual monitor or native exec event delivered by the host, or
concrete evidence that the retained exec failed. The startup turn may perform
one bounded exec observation to prove the complete startup set. After that,
perform no timer-driven or empty-continuation liveness polls.
```

Classify a complete local startup as `degraded_no_event_wake` unless the current
host independently proves an event-driven model wake bound to that exec. A
clean busy lease remains `already_armed`; unsafe or ambiguous startup remains
`startup_failed`.

Add the explicit idle contract and tripwire:

```markdown
After startup returns, this lifecycle must cause zero model turns while idle.
The script's 10-second local filesystem poll remains allowed because it does
not invoke a model.

On the first empty monitor-only continuation from a legacy monitor-owned
lifecycle, perform no exec poll and emit no routine status. End only the
positively matching legacy monitor goal or task, never recreate it, and leave
the lease-owning local process untouched. This tripwire permits at most one
empty model wake.
```

Keep explicit stop-state handling and one-attempt lease adoption after
compaction. Do not edit the Claude or Antigravity sections.

- [ ] **Step 3: Generate the focused skill output**

Run:

```bash
python3 -B scripts/build_skills.py --spec start-inbox-monitor
```

- [ ] **Step 4: Run the focused test and verify green**

Run:

```bash
python3 -B -m unittest tests.test_start_inbox_monitor_skill -v
python3 -B scripts/build_skills.py --check
```

Expected: all focused tests pass and generated skill parity is clean.

- [ ] **Step 5: Commit the lifecycle change**

```bash
git add \
  skill-specs/start-inbox-monitor.md \
  plugins/agent-collab/skills/start-inbox-monitor/SKILL.md
git commit -S -m "skill: make Codex monitor idle-token free"
```

### Task 3: Publish the 4.5.3 Policy-Surface Update

**Files:**
- Modify: `scripts/skill-build-config.json`
- Modify: `.claude-plugin/marketplace.base.json`
- Modify: `README.md`
- Modify: `plugins/agent-collab/README.md`
- Generate: `.claude-plugin/marketplace.json`
- Generate: `plugins/agent-collab/.claude-plugin/plugin.json`
- Generate: `plugins/agent-collab/.codex-plugin/plugin.json`
- Generate: the existing `plugins/agent-collab/skills/` tree's version
  frontmatter as enumerated by `python3 scripts/build_skills.py --list`
- Create: `changelog.d/2026-07-28-codex-monitor-idle.md`

**Interfaces:**
- Consumes: package version 4.5.2 from the broker PR base.
- Produces: one internally consistent 4.5.3 public package with unchanged
  native-runtime bytes.

- [ ] **Step 1: Bump both generator inputs to 4.5.3**

Set `skill_version` in `scripts/skill-build-config.json` and
`metadata.version` in `.claude-plugin/marketplace.base.json` to `4.5.3`.

- [ ] **Step 2: Add user-facing release notes**

Update the repository and package READMEs from 4.5.2 to 4.5.3 where they
identify the current source/package. Add a repository `What's new - v4.5.3`
entry explaining that Codex keeps its local monitor process but no longer
creates a persistent model goal, reports `degraded_no_event_wake` without a
native wake surface, and incurs zero model turns while idle.

Create this fragment:

```markdown
### agent-collab 4.5.3 — 2026-07-28

#### Changed

- The Codex inbox-monitor adapter no longer creates or retains a persistent
  goal. Its canonical leased local process continues at the existing 10-second
  interval, but liveness checks occur only on real activation, event, status,
  stop, or failure turns, so idle monitoring causes zero model turns.
- Codex reports `degraded_no_event_wake` when the local process is live without
  a proven host-native model wake, and a first-empty-continuation tripwire
  prevents a legacy goal from producing repeated no-event turns.
- Claude and Antigravity monitor lifecycles are unchanged.
```

- [ ] **Step 3: Regenerate all distributed surfaces**

Run:

```bash
python3 -B scripts/build_skills.py
python3 -B scripts/build_marketplace.py
```

- [ ] **Step 4: Run metadata and release consistency checks**

Run:

```bash
python3 -B scripts/build_skills.py --check
python3 -B scripts/build_marketplace.py --check
python3 -B scripts/build-changelog.py --dry-run
python3 -B scripts/check_release_consistency.py
```

Expected: all commands exit zero; `CHANGELOG.md` remains unchanged.

- [ ] **Step 5: Commit the package surfaces**

```bash
git add \
  .claude-plugin/marketplace.base.json \
  .claude-plugin/marketplace.json \
  README.md \
  changelog.d/2026-07-28-codex-monitor-idle.md \
  plugins/agent-collab/.claude-plugin/plugin.json \
  plugins/agent-collab/.codex-plugin/plugin.json \
  plugins/agent-collab/README.md \
  plugins/agent-collab/skills \
  scripts/skill-build-config.json
git commit -S -m "release: prepare idle-free monitor policy 4.5.3"
```

### Task 4: Verify, Review, and Self-Merge After the Broker PR

**Files:**
- Verify all files changed by Tasks 1-3 plus the design and this plan.
- Do not alter native runtime artifacts or generated `CHANGELOG.md`.

**Interfaces:**
- Consumes: exact 4.5.3 candidate head and merged broker PR #70.
- Produces: one governed, cross-family-reviewed, green, self-merged PR.

- [ ] **Step 1: Run the complete local gate bundle**

```bash
python3 -B scripts/build_skills.py --check
python3 -B scripts/build_marketplace.py --check
python3 -B scripts/build-changelog.py --dry-run
python3 -B -m unittest discover -s tests -t . -v
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
python3 -B scripts/check_release_consistency.py
python3 -B scripts/secret_scan.py
python3 -B scripts/check-public-export-safety.py --active-tree
git diff --check
```

Run history mode in a disposable full clone of the exact public candidate,
because the shared clone may retain obsolete refs:

```bash
python3 -B scripts/check-public-export-safety.py --active-tree --history
```

Expected: every gate exits zero.

- [ ] **Step 2: Verify exact scope and commit signatures**

Confirm:

- the semantic diff changes only the Codex monitor lifecycle;
- the Claude and Antigravity sections are byte-identical to the 4.5.2 base
  except generated version frontmatter;
- no runtime artifact bytes changed;
- every branch commit reports a good signature; and
- the branch is based on the final merged PR #70 head.

- [ ] **Step 3: Push and open a Tier-2 PR**

Use a PR body containing the required public compliance trace, explicit
generated/version/changelog/validation checklists, and an in-flight
independent-family review state. Set the PR base to PR #70's branch if #70 is
still open; after #70 merges, rebase onto `origin/main` and retarget to `main`.

- [ ] **Step 4: Obtain independent-family exact-head review**

Wait until the broker owner's reserved managed-review slot is released. Then
request one bounded read-only review from a non-OpenAI family over the exact
candidate diff. Integrate material findings, rerun affected tests, and update
the compliance trace only after the final exact-head verdict is `PROCEED`.

- [ ] **Step 5: Wait for required CI and run the merge gate**

```bash
pr_number="$(gh pr view dev/codex/codex-monitor-idle \
  --repo sumitake/agent-collab --json number --jq .number)"
python3 -B scripts/check_pr_compliance.py "$pr_number" \
  --repo sumitake/agent-collab
```

Expected: `MERGE-ELIGIBLE`.

- [ ] **Step 6: Squash-merge and verify remote main**

Merge without admin bypass. Verify the PR is `MERGED`, fetch `origin/main`, and
confirm the merge commit contains version 4.5.3, the corrected Codex section,
the tests, and the changelog fragment.

- [ ] **Step 7: Stop at the source-merge boundary**

Do not tag a release, update the installed plugin, restart Codex, or mutate the
live monitor in this task. Report those as separate activation follow-up
because source merge is not release or loaded-version evidence.
