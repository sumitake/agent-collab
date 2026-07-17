---
name: chain-configurator
version: 4.0.2
defaults:
  tier: Standard
  effort: medium

description: Interactive Q&A meta-skill that guides the user through generating a YAML chain definition for the `chain` orchestrator — either specializing an existing template (audit-cross-systems, validate-release-candidate, validate-calculation, validate-decision, etc.) or building a chain from scratch step-by-step. Use when the user says "help me configure a chain," "generate a chain for X," "set up a chain," "create a new chain," "configure audit-<topic>," "build a chain from scratch," or describes a repeating multi-step workflow that would benefit from chain formalization but hasn't yet written the YAML. Also offer this proactively when the active primary has just walked through a multi-step verification workflow that the user is likely to repeat — capturing it as a chain up-front turns one-off ad-hoc work into a versioned, audited, reproducible artifact.
---

# Chain-configurator — interactive YAML generator for the `chain` orchestrator

This skill **writes a chain YAML**; it does not execute one. Lead the user through batched Q&A to produce a draft chain spec under `drafts/sample-chains/<name>.yaml`, then hand off to the `chain` skill (or `python3 -m orchestrator` for the workspace-side runtime) for execution and validation.

Use only the closed chain fields documented by the installed `chain` skill.
Do not require or disclose an external private schema.

## When to use

Use this skill when one or more of the following are true:

- **The user explicitly asks for it** — "help me configure a chain," "generate a chain for X," "set up a chain," "create a new chain," "configure audit-<topic>," "build a chain from scratch," "scaffold a chain for me."
- **The user wants to formalize a repeating workflow** but has not written chain YAML before.
- **The user wants to adapt an existing chain template** (audit-cross-systems, validate-release-candidate, validate-calculation, validate-decision, etc.) to their specific domain.
- **The user has a workflow described in natural language** and wants it captured as a verifiable chain.
- **A first-time chain author needs scaffolding + sanity-checking.**

## When to skip

- **The user already has a chain YAML draft** and just wants validation — read the file directly + reference the chain-spec format doc; no Q&A overhead needed.
- **One-shot work that won't be repeated** — use ad-hoc skill invocation; don't formalize as a chain.
- **The user is editing an existing chain** — use the Edit tool directly; no Q&A regeneration needed.
- **The user knows the spec well** — Q&A becomes friction; let them write the YAML directly and review.

## Procedure (overview)

The full Q&A scripts for each template + the from-scratch flow are documented inside the skill at runtime invocation. The high-level shape:

### 1. Identify intent (one batched question)

Ask the user ONE consolidated question that determines the path:

1. **Specialize existing template** vs **build from scratch**?
2. **What workflow** does the chain run (one sentence)?
3. **Roughly how many steps**?

If the user says "I don't know" on #1, default to (a) — show the existing templates and let them pick the closest:

| Template | Pattern |
|---|---|
| `audit-cross-systems` | Multi-system state audit → optimization proposals → safety review → finalize |
| `validate-release-candidate` | Code-review + red-team + qa-verify + synthesis for a code change |
| `validate-calculation` | Independent re-derivation + reconcile + framing-review for a math/financial calc |
| `validate-decision` | Debate + decide + cross-check + optional persona-check + finalize for a binary decision |

When no current-project template exists, build the minimal YAML from scratch.

### 2. If specializing an existing template

Ask the template-specific questions in a batched form. For each template, the questions correspond 1:1 with the template's `inputs:` section. Walk through them in order.

Use the existing template's structure as the scaffold; the user's answers populate the inputs. Leave the template's `steps:`, `gates:`, `outputs:` untouched unless the user explicitly asks to modify them.

### 3. If building from scratch

Walk through the chain-spec sections one at a time, batching related questions:

- **Batch A — metadata + inputs**: chain name (lowercase-hyphen), one-line description, declared inputs (per input: name, type, required, default, description).
- **Batch B — per step** (iterate for each step the user identified): step ID, runner (`skill` vs `<primary>`), skill reference (for `skill` runner) or instruction text (for `<primary>` runner), input map (referencing prior steps or chain inputs), output schema (text / json / jsonl / structured-text with anchor), retry policy, on_failure policy, gates (optional but recommended for any step that asserts a side effect).
- **Batch C — outputs**: which step's output(s) become the chain's final output? Render templates.
- **Batch D — audit + cost budget** (optional): audit log path, cost budget limit + on_exceed policy.

After each batch, summarize what the user said back as YAML-ready notes. Only render the final YAML after all batches complete.

### 4. Render the YAML

Emit the chain YAML to the operator-selected current-project path. Validate its
closed fields against the installed `chain` skill and surface specific errors.

### 5. Hand off

Present the user with:

- The path to the new draft.
- A one-line command to validate + dry-run the chain: e.g., `python3 -m orchestrator validate drafts/sample-chains/<name>.yaml && python3 -m orchestrator run drafts/sample-chains/<name>.yaml --mock`.
- A note that the chain is in `drafts/sample-chains/`, not `chains/`, until the user has validated it on real inputs and is ready to promote it.

## Anti-patterns

- **Skipping the batched-Q&A discipline.** Asking 12 separate questions one by one is friction; batch related questions and wait for the user to answer all of them in one turn.
- **Writing the YAML before the user has answered the metadata + inputs batch.** Premature rendering misleads — the user sees a YAML they haven't committed to.
- **Inventing unsupported chain fields.** Stay within the installed skill's
  closed format and report when the requested feature is unavailable.
- **Promoting the draft to `chains/` automatically.** Drafts go to `drafts/sample-chains/`; promotion to `chains/` is a separate operator-mediated step after real-input validation.
- **Failing to validate the generated YAML before handing off.** A malformed draft wastes the user's first run. Validate before presenting.
- **Skipping cross-family routing on cross-check steps.** When the user requests a cross-check step in the chain, ensure the spec routes it to a different-family verifier (per the chain-spec's family-aware routing rule). Don't let the user accidentally configure a same-family cross-check.
- **Forcing the user into the "from scratch" path** when an existing template is a 90% match. Specialize the template; save the user time.
- **Asking the user to specify gates / output_schema / retry policy** when they're a first-time author and don't yet have a workflow that surfaces those choices. Default to sensible values (e.g., `output_schema: text` if uncertain, `retry: 1`, no `gates:` initially) and prompt the user to revisit after the first chain run surfaces the need.

## Examples across domains

| Domain | Workflow user describes | Template / from-scratch decision |
|---|---|---|
| Engineering | "Validate every PR for security + edge cases + performance before merge" | Specialize `validate-release-candidate` |
| Finance | "Audit a multi-tier cap table calculation against the term-sheet constraints" | Specialize `validate-calculation` |
| Product strategy | "Decide whether to build, buy, or partner for a new feature each quarter" | Specialize `validate-decision` (binary at first; iterate to three-way later) |
| Operations | "Monthly TLS-certificate audit across 8 services with snapshot-and-renew" | Specialize `audit-cross-systems` (8-system list, audit focus = TLS health) |
| Clinical | "Validate a chemotherapy dosing calc against weight + age brackets + max-dose ceiling" | Specialize `validate-calculation` (clinical-specific constraints) |
| Compliance | "Quarterly review of new data-processing flows for PHI/PII exposure" | Build from scratch (specific to the org's compliance categories) |
| Research methodology | "For each new paper draft, validate methodology + cite-check + reproducibility-claims" | Build from scratch (paper-specific gates) |
| Legal | "For each new vendor contract: triage + counsel review + signature routing" | Build from scratch (uses both `triage-nda` and the org's contract-review skill) |
| Sales | "For each enterprise prospect: account research → outreach draft → cross-check → personalize" | Specialize `validate-decision` (decide whether to advance the prospect) |
| HR / talent | "Final-round candidate evaluation: panel synthesis → cross-check → calibration" | Build from scratch (panel-specific inputs) |

## Limitations

This skill **writes** a chain YAML; it does not execute one. Run the result via
the installed `chain` skill.

The draft is saved to `drafts/sample-chains/<name>.yaml` — **not** `chains/`. Promotion to `chains/` is a separate operator-mediated step that happens after the chain has been validated on real inputs.
