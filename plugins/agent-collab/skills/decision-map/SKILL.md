---
name: decision-map
version: 6.2.2
description: Plan an effort too large for one session as a shared map of decision tickets on the repo's issue tracker, then resolve them one per session until the way to the destination is clear. Use when the user says "decision map," "chart this effort," "map out this project," "break this fog into tickets," "work the map," or "/agent-collab:decision-map." Also offer this proactively when a request is a loose multi-session idea whose route is not yet visible — where the open questions outnumber the known steps and a single planning pass would either stall or guess.
---

# Decision map — multi-session planning on the issue tracker

A loose idea has arrived — too big for one session, and wrapped in fog: the way
from here to the **destination** is not visible yet. This skill charts the way
as a **shared map** on the repo's issue tracker, then works its **decision
tickets** — questions whose resolution is a decision, not slices of a build to
execute — one at a time until the route is clear.

The destination varies per effort, and naming it is the first act of charting.
It might be a spec to hand off, a decision to lock before implementation
planning starts, or a change made in place. The map is domain-agnostic.

## Plan, don't do

Each ticket resolves a decision; the map is done when nothing is left to decide
before someone goes and does the thing. The pull to just do the work is usually
the signal you have reached the edge of the map and it is time to hand off. An
effort can override this in its Notes — carrying execution into the map — but
absent that, produce decisions, not deliverables.

## Refer by name

Every map and ticket is an issue, so it has a name — its title. In everything
the human reads, refer to it by that name, never by a bare id or number; the id
and URL ride inside the name as a link, never stand in for it.

## Tracker resolution and the write gate

Resolve the tracker in this order; never assume one:

1. **Whatever the project's own docs designate**: when the repository's
   documentation records a tracker workflow (an issue-tracker doc, a
   contributing guide naming Jira/Linear/GitLab, or equivalent), follow that
   documentation — it wins even when a GitHub remote exists.
2. **GitHub Issues via the `gh` CLI** when the repo has a GitHub remote and no
   documented tracker says otherwise. Feature-detect sub-issue and dependency
   support (`gh issue create --parent`, `gh issue edit --blocked-by`) before
   relying on it; on older CLI versions fall back to a `Blocked by: #N` body
   convention and a task-list of child links in the map body.
3. **Local markdown** when neither applies: the map at
   `.scratch/<effort>/map.md`, tickets as sibling files, blocking edges as
   body text.

**Write gate:** tracker issues are shared, outward-facing state. Before
creating, editing, assigning, commenting on, or closing any tracker item,
present the exact set of writes (titles, bodies, edges) and get the user's
confirmation — unless the user in this conversation already explicitly asked to
publish or update the map. Local-markdown mode needs no confirmation.

## The map

The map is one issue labelled `decision-map:map`; its tickets are child issues.
The map is an **index**, not a store: it gists each closed decision in one line
and links the ticket that holds the detail. Open tickets are not listed — they
are found by query. The map body carries four sections:

- **Destination** — what reaching the end looks like, one or two lines; every
  session orients to it before choosing a ticket.
- **Notes** — domain, skills every session should consult, standing preferences.
- **Decisions so far** — one line per closed ticket: `[title](link) — gist`.
- **Not yet specified** and **Out of scope** — see below.

Each ticket's body is one question, sized to a single session. A session
**claims** a ticket by assigning it before any work — the assignee is the
claim. A ticket is unblocked when every ticket blocking it is closed; the
**frontier** is the open, unblocked, unclaimed children.

## Ticket types

Every ticket is either **HITL** — worked with a human who speaks for
themselves — or **AFK**, driven by the agent alone. A HITL ticket only resolves
through that live exchange; the agent never stands in for the human's side.

- **Research** (AFK): read documentation, third-party APIs, or local knowledge
  bases to surface a fact a decision waits on. Delegate to a bounded read-only
  research subagent when the host provides one; otherwise research inline.
  Capture findings as a cited markdown note linked from the ticket.
- **Prototype** (HITL): raise the fidelity of the discussion with a cheap
  concrete artifact to react to — via the `prototype` skill in this package
  where code is called for. Link the artifact from the ticket.
- **Interview** (HITL): the default. Work the question with the user one
  question at a time, resolving dependent decisions in order. Use the host's
  requirements-interview or brainstorming skill when one is available;
  otherwise interview inline. Either way: look up **facts** in the environment
  rather than asking, put every **decision** to the human and wait, and do not
  act on the outcome until the user confirms shared understanding.
- **Task** (HITL or AFK): manual work that must happen before a decision can be
  made — provisioning access, moving data so its shape can be seen. It earns
  its place by unblocking a decision, not by delivering the destination.

## Fog of war and out of scope

Do not chart what you cannot yet see. **Not yet specified** holds the dim view
of questions you can tell are coming but cannot yet phrase sharply; resolving
tickets graduates patches of it into fresh tickets. The test for fog vs.
ticket is whether the question can be stated precisely now — not whether it can
be answered now. **Out of scope** holds work consciously ruled beyond the
destination; it never graduates. When an existing ticket turns out to sit past
the destination, close it and leave one line here with the reason.

## Workflow

Two modes. Either way, resolve at most one non-research ticket per session.

**Chart the map** (user arrives with a loose idea): (1) pin the destination via
an interview; (2) interview again breadth-first to surface the open decisions —
if no fog surfaces, the effort fits one session and needs no map: say so and
stop; (3) draft the map and the tickets you can specify now; (4) pass the write
gate, then create the map and tickets, wiring blocking edges in a second pass;
(5) kick off research tickets; (6) stop — charting is one session's work.

**Work the map** (user arrives with a map reference): (1) load the map body
only; (2) take the named ticket, or the first frontier ticket — claim it
first; (3) resolve it, zooming into related tickets on demand; (4) record the
answer as a resolution comment, close the ticket, append the one-line gist to
Decisions so far; (5) graduate any fog the answer sharpened, and rule anything
the answer exposed as beyond the destination out of scope. Expect concurrent
sessions to be editing the tracker; the claim discipline is what keeps them
from colliding.

## Attribution and license

Derived from `skills/engineering/wayfinder/SKILL.md` in
[mattpocock/skills](https://github.com/mattpocock/skills) at commit
`2ab958093e83e0ec752e6c1c5932da465bf23e0c`, adapted for this package
(tracker resolution, write gate, host-neutral sub-skill references). That
material is and remains MIT-licensed: Copyright (c) 2026 Matt Pocock.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions: The above copyright
notice and this permission notice shall be included in all copies or
substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS",
WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
THE USE OR OTHER DEALINGS IN THE SOFTWARE.
