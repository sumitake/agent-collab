### agent-collab 7.0.6

- Correct review skills and their scaffold to require caller-owned primary,
  artifact-author, and observed reviewer family verification. Routing success
  alone does not establish independent evidence; unknown lineage stays unknown,
  and a consumed review is never replayed to repair its evidence.
- Regenerate skill instructions while retaining signed provider runtime 5.0.7,
  its manifest, and the routing wire unchanged.
