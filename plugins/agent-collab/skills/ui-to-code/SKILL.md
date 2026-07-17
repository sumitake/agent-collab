---
name: ui-to-code
version: 4.0.3
defaults:
  tier: Advanced
  effort: high

description: Turn a UI mockup, screenshot, or wireframe into code in the active primary's project context. Use when the user says "turn this into code," "build this UI," "implement this mockup," "code this screenshot," or "extract a UI spec." Also offer this proactively when implementation is about to start from a visual artifact. The unified plugin currently has no managed cross-family image transport, so the active primary performs the visual extraction and implementation while explicitly reporting that independent visual extraction is unavailable; never claim a second visual read occurred.
---

# UI to code

Implement a visual design in the user's actual stack while preserving an
honest boundary around reviewer independence.

## Current availability boundary

The coordinator has no image or binary attachment contract. Managed
cross-family structural extraction is **temporarily unavailable**. Do not pass
paths, base64 image bytes, invented media fields, or raw provider commands.
When the user requires an independent visual extraction as a governance gate,
return typed unavailable and stop that gate.

## Workflow

1. Inspect the image using the active host's native visual capability.
2. State that the structural read is primary-only; do not call it a two-read or
   cross-family result.
3. Extract a working spec: layout regions, elements, visible text, hierarchy,
   approximate spacing and colors, interaction hints, responsive behavior, and
   accessibility requirements.
4. Inspect the project before writing. Reuse its framework, components, design
   tokens, naming conventions, tests, and accessibility patterns.
5. Implement in the trusted primary's normal mutation boundary. This public
   skill does not grant a provider backend file-write, shell, test, commit, PR,
   merge, or deploy authority.
6. Run project-appropriate verification and compare the rendered result against
   the source image. Record assumptions where the image is ambiguous.

If the caller supplies an independently authored **textual** design spec, an
advisory route may review that text with the exact artifact snapshot and author
model. That is a text-spec review, not image analysis.

## Guardrails

- Do not invent the user's framework or component library.
- Prefer existing design tokens over hardcoded values.
- Add semantic HTML, keyboard behavior, focus states, and accessible labels
  even when the static mockup cannot depict them.
- Do not reuse working element identifiers blindly; map them to project
  conventions.
- Do not claim pixel precision for values that were visually estimated.
- Do not claim independent verification until a signed typed image contract is
  advertised by the native runtime.
