### agent-collab 7.0.6

- Correct review skills and their scaffold to require caller-owned primary,
  artifact-author, and observed reviewer family verification. Routing success
  alone does not establish independent evidence; unknown lineage stays unknown,
  and a consumed review is never replayed to repair its evidence.
- Regenerate skill instructions while retaining signed provider runtime 5.0.7,
  its manifest, and the routing wire unchanged.

- Clarify compatible macOS caller execution when a native command sandbox cannot nest beneath the caller sandbox, preserving native permissions and consumed-attempt boundaries.

- Allow ordinary Gemini code review when no eligible distinct-family reviewer is available, explicitly label same-family or unverified advisory results, preserve required independent approval gates, and stop repeated attempts against unavailable providers.

- Bind a caller-verified independent reviewer to the live request using the existing target field, respecting operator selection and avoiding unbound planning-to-dispatch changes.

- Align injected invocation text with reviewer binding, keep shared quality descriptions neutral for creative work, and remove fictional family and role-switch independence claims from complete generated skills.

- Keep intent comparison and delegated work advisory without automatic family-exclusion claims, while preserving observed-lineage requirements for independent review and governance.
