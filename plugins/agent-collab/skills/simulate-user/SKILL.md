---
name: simulate-user
version: 7.0.3
defaults:
  quality_profile: economical
  effort_class: minimal

description: Cast the reviewer into a strict roleplay as a user persona or stakeholder reacting to an artifact (draft email, pitch deck, UI flow, policy memo, marketing copy, instructional text). The output is an in-character reaction — not a review — that shows how the artifact lands. Use when the user says "simulate a skeptical engineer," "simulate an impatient executive," "how would a non-technical user react to this," "play a confused customer reading this," "roleplay a skeptical engineer responding to this proposal," "what would a compliance officer say about this," "have the reviewer pretend to be a specific persona," or any cast-into-roleplay framing. Also offer this proactively when the active primary is about to ship a draft (email, deck, copy, instructions) to an audience where framing matters and the audience is non-technical, time-pressed, skeptical, hostile, or otherwise different from the author's defaults.
---

## Unified runtime invocation

Resolve the **plugin root** from this loaded file: `SKILL.md` is at `<plugin-root>/skills/<skill-name>/SKILL.md`. Invoke only `python3 "<plugin-root>/coordinator.py"` and send one bounded JSON routing request on EOF-delimited stdin, without a PTY. Use the Python invocation example in the **Routing request** section in `<plugin-root>/README.md` and the co-packaged manifest's signed `wire_contract`; never invent fields or provider actions. Supply one caller-defined work unit per independently useful deliverable, with this skill's logical action and a bounded opaque payload. Use `depends_on` only for actual dependencies. Set `explicit_target` only when the operator names a provider. Choose quality and effort for the workload; include context/output token estimates when known. Read the current manifest digest and actual cwd device/inode; do not copy example values. The runtime owns its timeout; do not wrap it in a shorter fixed timeout. Repository identity, source-head verification, disposable copies, patch capture, and cleanup remain caller-owned where applicable. The shim runs standalone from the installed plugin and transports the routing client's bounded result without semantic interpretation. Never discover a provider executable, reconstruct a raw command, or replay, retry, or fail over a consumed work unit. Provider status, terminal records, receipts, telemetry, and other structured fields are optional diagnostics; none is a content-availability gate. Preserve every returned content record or recovered partial response and interpret it with ordinary model reasoning. Never synthesize approval, authority, or a receipt from process exit or missing diagnostics. A planning-only request sets `dispatch_requested=false`; a live request sets it true and consumes at most one provider attempt per work unit.
Planning reports route eligibility, not live availability or authentication. Report a caller/client failure at that layer; provider state remains unknown unless native evidence establishes it. Content availability and each work unit's `execution_status` are separate facts.

# Simulate-user — in-character persona reaction to an artifact

Unlike `second-opinion` or `code-review`, this skill is not an analytical critique. It is a **strict in-character roleplay**: the verifier becomes a specific persona reading the artifact and reacts as that persona would — confused, impatient, suspicious, enthusiastic, missing the ask, snagging on a phrase — without breaking character to deliver a "review." The point is to see how the artifact lands with the intended audience, not how a model thinks about the artifact in the abstract.

Cross-family does not have the verifier-independence semantics it has in cross-check skills; this is collaborative roleplay. the reviewer (independent family) can inhabit personas the active primary (resolved family) would not naturally inhabit, which is part of the value, but no formal independence rule applies.

## When to use

- **The user explicitly asks for it** — "simulate a skeptical engineer," "simulate an impatient board member," "how would a non-technical user react to this," "test this pitch on an executive," "play a confused customer reading this," "roleplay a skeptical engineer responding to this proposal," "what would a compliance officer say about this," "have the reviewer pretend to be a specific persona."
- **A draft is about to ship to a specific audience** — email, pitch, deck, marketing copy, instructional text, policy memo, internal announcement — and the framing matters.
- **The audience is materially different from the author's defaults** — non-technical readers, time-pressed executives, skeptical engineers, hostile reviewers, regulated-industry compliance, non-native-language readers.
- **A UI flow or set of instructions** needs a "first-time user with no context" pass to find where users will get stuck.

## When to skip

- **The artifact has no specific audience** — internal notes, draft brainstorms, things the user is thinking through privately.
- **The persona is too generic** ("simulate a user") — produces generic output. Either narrow to a specific persona or use `second-opinion` for general critique.
- **The user wants critique**, not roleplay. Use `second-opinion` (analytic) or `visual-review` (visual) instead.
- **The artifact is at draft-of-draft stage** — wait for enough committed framing to have something concrete to react to.

## Procedure

### 1. Identify the artifact and the persona

If the user said "test this email" without naming a persona, ask one short question: "Who should the reviewer pretend to be? An impatient executive, a confused customer, a skeptical engineer, a regulatory reviewer, a non-native-language reader?"

A specific persona produces a specific reaction. Generic personas produce generic reactions; that defeats the skill.

### 2. Frame the prompt strictly

Instruct the verifier to stay entirely in character and **not break the fourth wall**. Specifically:

- No meta-commentary ("As an executive, I would...")
- No phrase-by-phrase critique ("The third paragraph is unclear because...")
- No "review" framing
- Show internal monologue if confused / bored / annoyed — that is the signal
- React exactly as the persona would in real life, with the constraints the persona actually has (time pressure, attention, background, motivation)

### 3. Call the verifier

Invoke `python3 "<plugin-root>/coordinator.py"` with `quality_profile='economical'` and `effort_class='minimal'`
(economical quality with minimal effort through the fastest eligible independent reviewer allowed by central policy — the skill default; raise both closed profiles for nuanced personas — short
in-character responses do not need depth). Use frontier/maximum only for
personas requiring nuanced reasoning, such as a litigator parsing a contract
clause or a detail-focused engineer reading a specification.

Prompt template:

```
You are [specific, opinionated persona — title, background, current context, mood, time pressure]. You have [time/attention budget — "2 minutes between meetings," "skimming on a phone on the bus," "reading aloud to your team," etc.] to read this [artifact type].

React IN CHARACTER. [Word limit, e.g., "Under 150 words"]. No "review," no "As a {persona}..." preambles, no meta-commentary, no critique-mode. If you get confused, bored, distracted, irritated, or excited — show that as internal monologue. Respond exactly as you would in real life.

--- ARTIFACT ---
[paste the artifact verbatim]
```

**Out-of-character artifact.** If the response slips out of character
(delivers a "review" instead of a reaction; says "As {persona}, I would..."),
Surface the out-of-character simulation as incomplete. Do not issue a second
provider request or ask the verifier to repair the artifact. A later
caller-authorized request is a new attempt. If the caller authorizes one,
include the stricter persona framing in that new request. The
failure-to-inhabit is itself information.

### 4. Surface the in-character reaction, then synthesize

Present the verifier's in-character response to the user **as-is**, framed as the persona's reaction. Then **step out of character yourself** and offer a one-paragraph synthesis: what the simulation revealed, what concrete change to the artifact follows from it. Examples:

- "The executive completely ignored the third paragraph because the bottom line was buried. The ask should move to the top."
- "The confused customer got stuck on the word 'provision' — they thought it meant 'food allotment' rather than 'configure.' Reword to 'set up.'"
- "The skeptical engineer immediately challenged the latency number without seeing the source. Add the benchmark methodology inline."

The simulation is the raw data; the synthesis is what the user can act on.

## Examples across domains

| Domain | Artifact | Persona to simulate | What the simulation typically reveals |
|---|---|---|---|
| Executive comms | Quarterly board-update email | Impatient board member with 2 minutes between meetings | Bottom line buried; ask not explicit; bullet structure required |
| Customer support | Knowledge-base article on resetting 2FA | Frustrated customer locked out of account, mobile phone, on hold | Step 3 assumes a setting they can't reach; "if you don't see X" path missing |
| Engineering | RFC for a new architecture | Skeptical principal engineer who has seen this fail twice before | Trade-offs not surfaced; missing benchmark/sizing; doesn't address the obvious objection |
| Marketing | Paid-social ad copy variant | The target demographic (specific age, region, prior brand awareness) | Brand voice off; CTA ambiguous; assumes context the audience doesn't have |
| Legal | Contract clause draft | Counterparty's lawyer reviewing the redline | Term that looks neutral has worst-case interpretation favoring us; will trigger redline |
| Clinical | Patient-facing medication instruction | A 70-year-old reading the printed sheet without their glasses on, on a kitchen counter, distracted | Font assumption breaks; "take as needed" ambiguous; warning unfamiliarly worded |
| Compliance | New-policy announcement to staff | A line-manager who hates new policies and will skim, then field questions | What changes for them isn't surfaced in the first paragraph; the "why" feels like cover |
| Sales | Outbound prospecting email | A VP at a target ICP company, on a flight, skim-reading on phone | Subject line doesn't promise a benefit; opener references the company in a way that reads like a mail-merge |
| Product / UX | New-feature onboarding tooltip series | First-time user who has never used the product before | Tooltip 2 assumes a UI state the user doesn't have yet; words like "schema" don't land |
| Education | Instructions for a science-class experiment | A 12-year-old reading aloud to a 9-year-old partner | Step 4 assumes lab safety knowledge they don't have; reagent name unfamiliar |

The pattern is constant: name a specific, opinionated, time-budgeted persona; cast strictly; capture the in-character reaction; synthesize what to change.

## Anti-patterns

- **Letting the verifier slip into "polite critique" mode.** "I think this could be improved by..." defeats the skill. Surface the current artifact as incomplete; do not replay it automatically.
- **Simulating a generic "user"** instead of a specific opinionated persona. Generic personas produce generic reactions. Always name the persona's title, context, mood, time budget.
- **Skipping the synthesis step.** The raw in-character reaction is data; the user wants the actionable change. The skill is not done until the synthesis is delivered.
- **Using frontier/maximum reflexively.** Short in-character reactions favor economical/minimal; frontier/maximum is for nuanced-reasoning personas (litigator, detail engineer, or compliance officer parsing a regulation).
- **Simulating personas the verifier may have content-policy issues inhabiting** (hostile, prejudiced, criminal personas). If the persona's reaction is the actual question, frame the persona's *role* (e.g., "skeptical adversarial reviewer") rather than the persona's *identity*; or use `second-opinion` framed adversarially instead.
- **Treating the simulation as ground truth for the actual audience.** It is a *prediction* of audience reaction, not a focus-group result. For high-stakes audiences, run a real focus group or A/B test in addition.
- **Running the same persona simulation 3 times without changing the artifact.** No new information; the verifier saturates.
- **Mixing simulate-user and visual-review on the same artifact in one call.** Roleplay is fundamentally different from analytic critique; mixing produces neither cleanly. Two separate calls.
