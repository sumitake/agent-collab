---
name: prototype
version: 6.2.1
description: Build a throwaway prototype that answers one design question — an interactive terminal app to pressure-test a state model or logic shape, or several radically different UI variants on one route. Use when the user says "prototype this," "sanity-check this state model," "show me a few options for this page," "mock up some variations," or "/agent-collab:prototype." Also offer this proactively when a design conversation is circling a question that a runnable artifact would settle in minutes — how a state machine handles an awkward case, or which of several layouts actually works with real data.
---

# Prototype — throwaway code that answers a question

A prototype is **throwaway code that answers a question**. The question decides
the shape:

- **"Does this logic or state model feel right?"** → a tiny interactive
  terminal app that pushes the state machine through cases that are hard to
  reason about on paper.
- **"What should this look like?"** → several radically different UI variants
  on a single route, switchable in the browser.

Getting the branch wrong wastes the whole prototype. If the question is
ambiguous and the user is not reachable, default to whichever branch better
matches the surrounding code — a backend module suggests logic, a page or
component suggests UI — and state the assumption at the top of the prototype.

## Workflow rules that apply to both branches

1. **Isolate the prototype from the caller's work.** Build it on an isolated
   worktree or a clearly named throwaway branch. Never commit to, rebase, or
   otherwise alter the branch the user was on without their explicit approval.
2. **Throwaway from day one, and clearly marked as such.** Name files and
   routes so a casual reader sees "prototype," and follow the project's
   existing conventions rather than inventing new top-level structure.
3. **One command to run**, registered with the project's existing task runner
   (`package.json` scripts, `Makefile`, `justfile`, `pyproject.toml`); if there
   is none, put the command at the top of the prototype's README.
4. **No persistence by default.** State lives in memory; persistence is the
   thing a prototype checks, not something it depends on. If the question
   explicitly involves a database, use a scratch store with a clear
   "PROTOTYPE — wipe me" name.
5. **Skip the polish.** No tests, no error handling beyond runnability, no
   abstractions. The point is to learn something fast.
6. **Surface the state.** After every action (logic) or on every variant switch
   (UI), show the full relevant state so the user sees what changed.
7. **Capture it when done.** Fold the validated decision into the real code;
   keep the prototype itself as a primary source on its throwaway branch with a
   context pointer from the relevant issue or commit. The main branch keeps
   only the validated decision.

## Logic branch — interactive terminal app

State the question first — one paragraph at the top of the file or README; a
logic prototype that answers the wrong question is pure waste. Then:

1. **Use the host project's language and tooling.** No new runtimes or package
   managers for a prototype.
2. **Isolate the logic behind a small pure interface** that could be lifted
   into the real codebase later — a pure reducer `(state, action) → state`, an
   explicit state machine when "which actions are legal right now" is part of
   the question, a set of pure functions over a plain data type, or a module
   with a clear method surface when the logic genuinely owns ongoing state.
   Pick the shape that fits the question, not the one easiest to wire to a
   terminal. No I/O or terminal code inside the logic module.
3. **Wrap it in the smallest terminal shell that exposes the state**: on every
   action, clear the screen and re-render one stable frame — current state
   pretty-printed, then the keyboard shortcuts (`[a] add  [t] tick  [q] quit`).
   Read one keystroke, dispatch, re-render, loop until quit.
4. **Hand the run command to the user.** The interesting moments are "wait,
   that shouldn't be possible" — bugs in the idea, which is the point. Add
   actions as they ask.
5. **On resolution**, the validated logic module lifts into the real code; the
   terminal shell rides along to the throwaway branch as a primary source.

Anti-patterns: adding tests; wiring to the real database; generalizing for
futures the question does not ask about; blurring logic and shell so the
module is no longer portable; shipping the shell toward production.

## UI branch — radically different variants on one route

Default to **3 variants**; more than 5 is noise. Two sub-shapes; strongly
prefer the first:

- **Adjustment to an existing page** (preferred): render variants on the
  existing route, gated by a `?variant=` URL parameter — the page's real data,
  auth, and surroundings stay, only the rendering swaps. A new section that
  would naturally live inside an existing page is still this sub-shape.
- **A new page** (last resort): only when the surface genuinely has no home.
  Follow the project's routing conventions and name the route so it is
  obviously a prototype.

Variants must be **structurally different** — different layout, information
hierarchy, primary affordance — not different colors. If two drafts come out
similar, redo one with explicit counter-guidance. Use the project's existing
component and styling system. A floating bottom bar switches variants.

**Production-safe gate:** the entire variant mechanism — variant components,
switcher bar, and the `?variant=` handling — must be unreachable in production
builds: compile it out via the project's dev-mode conditionals, an explicitly
non-production route guard, or by keeping the prototype on its throwaway
branch. Gating only the switcher UI is not enough.

## Attribution and license

Derived from `skills/engineering/prototype/` (`SKILL.md`, `LOGIC.md`,
`UI.md`) in [mattpocock/skills](https://github.com/mattpocock/skills) at
commit `2ab958093e83e0ec752e6c1c5932da465bf23e0c`, adapted for this package
(worktree isolation, production-safe gating, inlined references). That
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
