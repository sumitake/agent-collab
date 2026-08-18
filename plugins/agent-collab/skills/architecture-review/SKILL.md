---
name: architecture-review
version: 6.0.6
description: Self-executed sweep of a codebase for module-deepening opportunities — shallow interfaces, scattered locality, untestable seams — presented as a visual report the user picks a candidate from, then explored interactively. Unlike `architect` (routed consultation) and `code-review` (diff review), this skill is run by the active primary on the whole codebase. Use when the user says "architecture review," "find deepening opportunities," "where is this codebase getting muddy," "improve the architecture," or "/agent-collab:architecture-review." Also offer this proactively when repeated friction in a working session traces to shallow modules — bouncing between many files to follow one concept, or tests that cannot reach behavior through the current interfaces.
---

# Architecture review — find and explore deepening opportunities

Surface architectural friction and propose **deepening opportunities** —
refactors that turn shallow modules into deep ones. The aim is testability and
navigability. This skill is **self-executed by the active primary**: it reads
the codebase directly and produces its own report. It composes with, and does
not replace, the routed skills: for an independent cross-family read on the top
candidates, route them through `architect` afterward.

## Design vocabulary

Use these terms exactly in every suggestion — do not drift into "component,"
"service," "API," or "boundary":

- **Module** — anything with an interface and an implementation; deliberately
  scale-agnostic (a function, class, package, or tier-spanning slice).
- **Interface** — everything a caller must know to use the module correctly:
  types, invariants, ordering constraints, error modes, configuration,
  performance characteristics.
- **Implementation** — what is inside the module.
- **Depth** — leverage at the interface: how much behavior a caller or test can
  exercise per unit of interface learned. **Deep** = small interface, large
  behavior; **shallow** = interface nearly as complex as the implementation.
- **Seam** — a place where behavior can be altered without editing in that
  place; where the interface lives. Placing the seam is its own decision.
- **Adapter** — a concrete thing satisfying an interface at a seam (a role,
  not a substance). One adapter = hypothetical seam; two = real.
- **Leverage** — what callers get from depth: one implementation pays back
  across N call sites and M tests.
- **Locality** — what maintainers get from depth: change, bugs, knowledge, and
  verification concentrate in one place. Fix once, fixed everywhere.
- **Deletion test** — would deleting this module concentrate complexity behind
  a real interface, or just move it? "Concentrates" marks a shallow module
  worth deepening.

## Workflow

### 1. Explore — scope before you scan

Deepening pays off by making future changes easier, so weight the parts of the
codebase that actually change. If the user named a direction — a module, a
subsystem, a pain point — take it. Otherwise walk the commit history
(`git log --oneline`) for hot spots and let those paths pull attention first;
widen the net only if changes are scattered.

Read the project's domain glossary (`CONTEXT.md` or equivalent) and any
architecture decision records in the area first — use the project's own domain
vocabulary in every candidate, and do not re-litigate recorded decisions
unless the friction is real enough to warrant reopening one (then mark the
conflict explicitly in the candidate).

Explore with the host's bounded read-only exploration facility (a read-only
subagent where available; direct reading otherwise). Note where you experience
friction rather than following rigid heuristics: where does understanding one
concept require bouncing between many small modules; where are modules
shallow; where were pure functions extracted for testability while the real
bugs hide in how they are called; which parts are untestable through their
current interface. Apply the deletion test to anything suspect.

### 2. Present candidates as a visual report

Write a **fully self-contained** HTML file to the OS temp directory — resolve
`$TMPDIR` falling back to `/tmp` (`%TEMP%` on Windows), name it
`architecture-review-<timestamp>.html` — and tell the user the absolute path
(open it with the platform opener where available). **Inline all CSS and
hand-drawn SVG; no CDN scripts, no external stylesheets, no remote fonts, no
third-party browser code.** The report must render identically offline.

For each candidate render a card: **Files** involved; **Problem** (why the
current shape causes friction); **Solution** in plain language; **Benefits**
in terms of locality, leverage, and how tests improve; a **before/after
diagram** (inline SVG or styled divs) showing the shallowness and the
deepening; and a **recommendation strength** badge — `Strong`,
`Worth exploring`, or `Speculative`. End with a **Top recommendation** section
naming the candidate to tackle first and why. Do not propose concrete
interfaces yet.

Then ask the user which candidate to explore.

### 3. Explore the picked candidate interactively

Walk the decision tree with the user one question at a time — constraints,
dependencies, the shape of the deepened module, what sits behind the seam,
which tests survive. Use the host's requirements-interview skill when one is
available; otherwise interview inline: look up facts in the codebase, put
every decision to the user, and do not begin implementation until the user
confirms the shared understanding. As decisions crystallize, keep the
project's domain glossary current (add or sharpen terms in `CONTEXT.md` where
the project keeps one), and when the user rejects a candidate for a
load-bearing reason, offer to record the decision so future reviews do not
re-suggest it. For an independent read on a high-stakes candidate, route it
through `architect` (read-only consultation) before committing.

This skill produces analysis and an agreed direction — implementation happens
afterward through the normal change workflow, not inside the review.

## Attribution and license

Derived from `skills/engineering/improve-codebase-architecture/SKILL.md` and
`skills/engineering/codebase-design/SKILL.md` in
[mattpocock/skills](https://github.com/mattpocock/skills) at commit
`2ab958093e83e0ec752e6c1c5932da465bf23e0c`, adapted for this package (inlined
vocabulary, self-contained report assets, host-neutral interviewing,
composition with routed consultation). That material is and remains
MIT-licensed: Copyright (c) 2026 Matt Pocock. Permission is hereby granted,
free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies of the
Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions: The above copyright notice and this
permission notice shall be included in all copies or substantial portions of
the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO
EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
