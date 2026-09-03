---
name: compose-skills
version: 7.0.2
description: Use when the user says "compose skills," "which skills should I use," "select a recipe," "combine these skills," or "/agent-collab:compose-skills." Also offer this when a task needs multiple lenses and benefits from explicit context, fan-out, authority, and stop-condition limits.
---

# Compose a bounded skill set

Choose the smallest useful set: one primary lens, one supporting lens, and at
most one verifier unless the task demonstrates a larger need. Useful supporting
lenses include `brainstorm`, `context`, `delegate`, and `code-review`.

Recipes select skills, not providers, models, or authority. A runtime request
uses one of the closed semantic actions documented in the plugin README.
Architecture/review/context stay read-only; codegen returns a private patch;
governance remains a distinct authoritative artifact.

Return selected lenses, context each receives, authority, fan-out limit,
execution order, evidence, and stop conditions. Do not load every plausible
skill, turn a recipe into routing policy, or use composition to bypass an
untrusted-source audit.
