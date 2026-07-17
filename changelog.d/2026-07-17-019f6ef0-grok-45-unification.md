### agent-collab 4.0.0 — Grok 4.5 model and effort unification

- **Breaking:** advance the fixed public/native runtime protocol to v2. Older
  public clients and signed runtimes now reject each other instead of silently
  using the retired Composer model or an outdated request shape.
- Route Grok architecture, governance, huge-context, and compatibility codegen
  through the same `xai/grok-4.5` author model. `composer/codegen` remains a
  public compatibility route with output-only authority, not a separate model.
- Seal review effort from the task: architecture and governance use high,
  huge-context synthesis uses medium, and callers cannot override those review
  profiles. Codegen requires `simple_codegen`, `standard_codegen`, or
  `complex_codegen`, with respective low, medium, and high effort floors.
- Keep all model, tool, sandbox, credential, environment, filesystem, and
  application authority out of the public codegen row. The trusted primary
  still owns applying output, integration review, testing, git, and release.
