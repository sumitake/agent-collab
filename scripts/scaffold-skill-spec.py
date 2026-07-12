#!/usr/bin/env python3
"""scaffold-skill-spec.py — create a new skill-spec skeleton from a template.

Reduces the boilerplate cost of adding a new skill to the marketplace
(M7 of the 2nd-round meta-improvement cycle). The generated file has
TODO markers showing where the author needs to fill in, follows the
discipline rules in `skill-specs/_AUTHORING_BRIEF.md`, and is ready
to be edited + run through `python3 scripts/build_skills.py --spec <name>`.

USAGE
  python3 scripts/scaffold-skill-spec.py <name>
      Create `skill-specs/<name>.md` from the default template.

  python3 scripts/scaffold-skill-spec.py <name> --verifier-independence YES
      Force-include the verifier-independence block.

  python3 scripts/scaffold-skill-spec.py <name> --verifier-independence NO
      Force-omit the verifier-independence block.

  python3 scripts/scaffold-skill-spec.py <name> --default-tier flash
      Suggest `flash` as the default tier (default: `pro`; see § 4 below).

  python3 scripts/scaffold-skill-spec.py <name> --dry-run
      Print the skeleton to stdout instead of writing.

  python3 scripts/scaffold-skill-spec.py <name> --force
      Overwrite an existing spec (default: refuse with exit 1).

  python3 scripts/scaffold-skill-spec.py <name> --out PATH
      Write to PATH instead of `skill-specs/<name>.md`.

DESIGN
  * Stdlib-only (argparse, pathlib, sys).
  * Auto-detection (overridable):
      - Verifier-independence block included by default for skills in the
        YES list per `_AUTHORING_BRIEF.md` § 10:
            second-opinion, debate, code-review, qa-verify, logic-check,
            red-team, ai-merge-resolve
        Omitted by default for skills in the explicit NO list:
            brainstorm, long-context, simulate-user, delegate, dev-delegate,
            chain, chain-configurator
        Unclassified names default to INCLUDED with a TODO note (safer
        default — easier to delete a block than to remember to add it).
      - Default tier: `flash` for throughput/binary tasks (qa-verify,
        brainstorm, simulate-user); else `pro`.
  * Refuses to overwrite without --force; emits a clear pointer at the
    existing file's path.
  * Skill name validated against `[a-z][a-z0-9-]*` (matches the build
    system's discovery glob — see `build_skills.py:discover_specs`).

EXIT CODES
  0  success (file written / printed; or --dry-run completed)
  1  refused (file exists; use --force)
  2  invalid arguments (bad name, etc.)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_DIR = REPO_ROOT / "skill-specs"

# Per `_AUTHORING_BRIEF.md` § 10 — verifier-independence classification.
VERIFIER_INDEPENDENCE_YES = frozenset({
    "second-opinion",
    "debate",
    "code-review",
    "qa-verify",
    "logic-check",
    "red-team",
    "ai-merge-resolve",
})
VERIFIER_INDEPENDENCE_NO = frozenset({
    "brainstorm",
    "long-context",
    "simulate-user",
    "delegate",
    "dev-delegate",
    "chain",
    "chain-configurator",
})

# Default-tier heuristic — `flash` for throughput/binary tasks.
DEFAULT_TIER_FLASH = frozenset({
    "qa-verify",
    "brainstorm",
    "simulate-user",
})

# Validation pattern — must match the build system's spec discovery.
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


# ---------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------


VERIFIER_INDEPENDENCE_BLOCK = """<!-- verifier-independence:start -->
## Verifier independence (functional contract)

A cross-check is *independent* only when the verifier and the author come from different model families. The families this platform recognizes:

- **Anthropic**: Claude.
- **Google**: Gemini, Antigravity.

Before invoking, identify who authored the artifact under review:

- **Authored by {{ primary_agent }}** (this package's primary, in the {{ primary_family }} family) — {{ verifier_agent }} sits in the {{ verifier_family }} family and is therefore cross-family. The cross-check is independent. Proceed normally.
- **Authored by a model in the {{ verifier_family }} family** (the verifier's own family) — a {{ verifier_agent }} review here is same-family and shares correlated training biases. It is **not** an independent verification. The independent reviewer in this case is a model from the {{ primary_family }} family: **{{ primary_agent }} performs the critique itself, without delegating to {{ verifier_agent }}.** {{ verifier_agent }} may still be consulted, but its output is filed as a clearly-labelled supplementary, non-independent view — never as, nor instead of, the independent verification.
- **Author unclear** — ask the user one question before sending.

This rule mirrors the orchestrator's Router (`route_cross_check`), which refuses a verifier whose `model_family` equals the artifact author's. Skipping it produces an audit-log entry that looks like cross-checking but cannot bear the weight of the decisions downstream consumers may make from it.
<!-- verifier-independence:end -->"""


def render_template(
    name: str,
    *,
    include_verifier_independence: bool,
    default_tier: str,
    classification_hint: Optional[str] = None,
) -> str:
    """Render the spec skeleton for `name`.

    `classification_hint` is shown to the author at the top of the file as
    a comment ("auto-detected YES / NO / UNCLASSIFIED") so they can decide
    whether the auto choice was right.
    """
    display_name = name.replace("-", " ").title()
    pretty_tier_other = "flash" if default_tier == "pro" else "pro"

    verifier_block = (
        VERIFIER_INDEPENDENCE_BLOCK
        if include_verifier_independence
        else "<!-- This skill does NOT make a verifier-independence claim "
        "(per _AUTHORING_BRIEF.md § 10). The verifier-independence block "
        "is intentionally omitted. -->"
    )

    classification_comment = ""
    if classification_hint:
        classification_comment = (
            f"<!-- scaffold note: verifier-independence "
            f"auto-detected as {classification_hint}. "
            f"Override with --verifier-independence YES|NO if needed. -->\n\n"
        )

    return f"""---
name: {name}
version: 0.1.0
description: TODO — write a one-sentence description containing BOTH (a) explicit user phrases like "<trigger phrase>", "<another trigger phrase>" AND (b) at least one situational trigger clause like "or when <situation>". Both halves are mandatory per workspace CLAUDE.md project directive #1; a description with only one half won't trigger reliably across deliberate and proactive invocation paths.
---

{classification_comment}# {display_name} — TODO tagline

TODO: 1-2 sentence opener — what the skill is, what its core job is, and the single most important thing to know about it. Write this from a position of clarity, not aspiration; if you can't compress the skill's purpose into two sentences here, the spec is not yet ready.

## When to use

Use this skill when one or more of the following are true:

- **The user explicitly asks for it** — "<trigger phrase 1>", "<trigger phrase 2>", "<trigger phrase 3>".
- **<situational trigger 1>** — TODO short description.
- **<situational trigger 2>** — TODO short description.

## When to skip

Skip this skill when:

- The artifact is a routine TODO; invoke `{{{{ mcp_tool_ask_short }}}}` (or the relevant direct tool) instead.
- TODO additional skip conditions specific to this skill.
- The cost of being wrong is trivially recoverable. The framing overhead is not worth it.

{verifier_block}

## Procedure

### 1. TODO first-step name

TODO: prose. What does the agent do first when invoking this skill? Pin down the inputs, the stakes, the success criterion. If the user has given vague input, ask ONE clarifying question rather than guessing.

### 2. Call the verifier

Invoke `{{{{ mcp_tool_ask }}}}` with `model: '{default_tier}'`. The `{default_tier}` tier resolves on this side to `{{{{ tier_{default_tier}_resolves_to }}}}`, which is the tier configured for TODO (slow skeptical analysis / fast throughput). The `{pretty_tier_other}` tier is the wrong choice for this skill because TODO.

Use this prompt template — the numbered sections are a **functional contract**, not stylistic suggestion. Downstream tooling (parity tests, audit logs, chain runners) keys on them:

```
TODO: full prompt template here. Include the literal section anchors that downstream consumers will parse.

1. SECTION_ONE_ANCHOR: <description>
2. SECTION_TWO_ANCHOR: <description>
3. ...

--- ARTIFACT ---
[paste the full artifact verbatim]
```

**Retry-on-malformed.** If the response does not contain all required sections, retry exactly once with:

> Previous response did not include all required sections. Re-emit strictly per the template above, no preamble.

If the second attempt is also malformed, surface that explicitly when you report back — do not silently paper over the format failure with a fabricated structure. A malformed cross-check is itself a signal worth reporting.

### 3. Adjudicate, then close

TODO: synthesis step — what does the agent do with the verifier's output? How does it relay to the user? What template (if any) does it use for the user-facing summary?

## Default tier

`{default_tier}` — TODO justification. Use `{pretty_tier_other}` only when TODO condition.

## Examples across domains

The skill is domain-agnostic. A representative sample of where it pays off:

| Domain | Artifact / context | What this skill typically surfaces |
|---|---|---|
| Product management | TODO example | TODO outcome |
| Software architecture | TODO example | TODO outcome |
| Clinical research | TODO example | TODO outcome |
| Finance | TODO example | TODO outcome |
| Legal | TODO example | TODO outcome |
| Systems engineering | TODO example | TODO outcome |
| Operations | TODO example | TODO outcome |
| Research methodology | TODO example | TODO outcome |

When picking the right example to share with the user mid-invocation, match the user's domain — not the operator's. The skill works the same way regardless of subject matter.

## Anti-patterns

- **TODO misuse pattern 1** — what goes wrong, and why.
- **TODO misuse pattern 2** — what goes wrong, and why.
- **Using this for tasks the underlying tool handles directly** — call `{{{{ mcp_tool_ask_short }}}}` instead. The framing overhead is not worth it for routine queries.
- **Skipping the retry on malformed output** — if the verifier returns a wall of prose without the structured sections, parity tests and audit logs cannot consume it. Retry once; if it fails again, report the failure rather than fabricating structure around the prose.
"""


# ---------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------


def classify_verifier_independence(name: str) -> tuple[bool, str]:
    """Return (include_block, hint_label) for the given skill name."""
    if name in VERIFIER_INDEPENDENCE_YES:
        return True, "YES (explicit YES list)"
    if name in VERIFIER_INDEPENDENCE_NO:
        return False, "NO (explicit NO list)"
    return True, "UNCLASSIFIED — defaulting to INCLUDED (safer default; delete the block if not applicable)"


def classify_default_tier(name: str) -> str:
    return "flash" if name in DEFAULT_TIER_FLASH else "pro"


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="scaffold-skill-spec",
        description="Create a new skill-spec skeleton from a template (M7).",
    )
    p.add_argument(
        "name",
        help='Skill name (must match "[a-z][a-z0-9-]*"; e.g. "code-review").',
    )
    p.add_argument(
        "--verifier-independence",
        choices=["YES", "NO", "AUTO"],
        default="AUTO",
        help='Include the verifier-independence block? Default AUTO classifies by name per _AUTHORING_BRIEF.md § 10.',
    )
    p.add_argument(
        "--default-tier",
        choices=["pro", "flash", "AUTO"],
        default="AUTO",
        help='Default tier suggestion in the spec. Default AUTO heuristically picks flash for throughput/binary tasks (qa-verify, brainstorm, simulate-user); else pro.',
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path. Default: skill-specs/<name>.md",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rendered skeleton to stdout instead of writing.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing spec (default: refuse).",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    name = args.name.strip()
    if not NAME_PATTERN.match(name):
        print(
            f"ERROR: skill name {name!r} does not match {NAME_PATTERN.pattern!r}. "
            f"Use lowercase letters, digits, and hyphens; start with a letter.",
            file=sys.stderr,
        )
        return 2

    # Verifier-independence resolution
    if args.verifier_independence == "AUTO":
        include_vi, hint = classify_verifier_independence(name)
    elif args.verifier_independence == "YES":
        include_vi, hint = True, "YES (explicit --verifier-independence YES)"
    else:
        include_vi, hint = False, "NO (explicit --verifier-independence NO)"

    # Default-tier resolution
    default_tier = (
        classify_default_tier(name)
        if args.default_tier == "AUTO"
        else args.default_tier
    )

    body = render_template(
        name,
        include_verifier_independence=include_vi,
        default_tier=default_tier,
        classification_hint=hint,
    )

    if args.dry_run:
        sys.stdout.write(body)
        return 0

    out_path = args.out if args.out is not None else SPECS_DIR / f"{name}.md"

    if out_path.exists() and not args.force:
        print(
            f"ERROR: {out_path} already exists. Use --force to overwrite, "
            f"or pick a different name.",
            file=sys.stderr,
        )
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body)

    next_steps_tier = "pro" if default_tier == "pro" else "flash"
    print(f"OK: scaffolded {out_path}")
    print(f"  verifier-independence: {'INCLUDED' if include_vi else 'OMITTED'} ({hint})")
    print(f"  default tier: {next_steps_tier}")
    print()
    print("Next steps:")
    print(f"  1. Edit {out_path} — fill in every TODO marker.")
    print(f"  2. python3 scripts/build_skills.py --spec {name}    # generate SKILL.md per package")
    print(f"  3. python3 scripts/build_skills.py --check         # idempotency check")
    print(f"  4. git add skill-specs/{name}.md plugins/*/skills/{name}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
