---
name: visual-review
version: 3.4.0
defaults:
  tier: Advanced
  effort: high

description: Review a screenshot, mockup, slide, chart, diagram, photograph, or marketing asset for hierarchy, readability, density, consistency, accessibility, and brand fit. Use when the user says "review this design," "look at this screenshot," "design feedback," "accessibility review," "is this on-brand," or "compare these variants," or when a visual artifact is about to ship. The unified plugin currently has no managed cross-family image transport, so this skill provides an honest primary-only visual pass or reports independent visual review unavailable; it never fabricates a verifier call.
---

# Visual review

Provide a specific, prioritized critique of a visual artifact without claiming
an independent reviewer was used when the managed transport cannot carry the
image.

## Current availability boundary

The public coordinator protocol accepts bounded UTF-8 prompts, text documents,
and exact text artifact snapshots. It has no image, media-type, or binary
attachment field. Therefore managed cross-family visual review is
**temporarily unavailable** in this release.

Never:

- encode image bytes into a text document or prompt;
- pass a local path and assume the native runtime will read it;
- add an undocumented coordinator field;
- discover or invoke a provider CLI directly;
- describe a primary-only read as independent or cross-family.

If the workflow requires governance-grade reviewer independence, return typed
unavailable and state that a signed typed image contract is required.

## Workflow

1. Inspect the image using the active host's native visual capability.
2. State once that this is a primary-only visual read and is not an independent
   cross-family review.
3. Select one or two lenses that match the user's request: hierarchy and flow,
   readability, information density, consistency, accessibility, brand and
   tone, or comparative judgment.
4. Return the top three findings ranked by severity. For each, name the exact
   element, the problem, and one concrete fix.
5. For a comparison, pick one winner against the user's stated criteria and
   name one element worth borrowing from the other variant.

When only OCR text, alt text, or a user-authored textual description is in
scope, that text may be reviewed through an advisory route. Label the result a
**textual-description review**, not a visual review.

## Output

Use this compact form:

```text
Availability: PRIMARY-ONLY | MANAGED VISUAL REVIEW UNAVAILABLE
1. [Critical|High|Medium] <element and issue> — Fix: <concrete fix>
2. [Critical|High|Medium] <element and issue> — Fix: <concrete fix>
3. [Critical|High|Medium] <element and issue> — Fix: <concrete fix>
```

Avoid generic praise, unsupported pixel measurements, invented contrast
ratios, or claims about image details the active primary cannot actually see.
