### agent-collab 5.0.0

- Breaking: replace provider route/action requests with 11 semantic actions,
  replace `long-context` with the source-grounded `context` skill, and invoke
  the co-packaged native runtime directly without broker, dispatcher, lane,
  launchd, or provider-specific proof compatibility paths.

- Runtime policy now derives agent, transport, source-mode, artifact, and
  authority membership from one co-packaged wire descriptor. Provider CLI and
  model identities remain observed diagnostics and are never release pins.

- Accept an owned, non-symlink runtime bundle directory with ordinary child
  link counts while retaining the single-link rule for executable and manifest
  files, so a freshly installed production bundle resolves before invocation.

- Derive every repository/document/conceptual source mode from the signed wire
  descriptor, including repository context actions whose semantic names do not
  end in `.repository`.

- Preserve the public contribution boundary under the PolyForm Strict License
  1.0.0, with `AGENTS.md` as the local operating contract and commercial-use
  approval administered by Osumi Consulting LLC.
