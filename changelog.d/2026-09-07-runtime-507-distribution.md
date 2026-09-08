### Fixed

- agent-collab 7.0.5 distributes signed provider runtime 5.0.7 for both macOS architectures. Native Claude, Agy, and ACP output remains available when final-answer extraction finds no content, including bytes observed at completion and during cleanup. The caller interprets retained output separately from native execution status.
- Normal Agy invocation and migration-doctor JSON/text reporting are included. The carrier matrix is unchanged: Claude remains on its admitted document-intent route, Agy handles Google routes, Codex uses its native app-server, and Grok/OpenCode retain their native transports. No alternate provider path or replay is introduced.
- The two architecture bundles form one activation set. Wire schema 12 and its descriptor digest, runtime protocol 5, and native contract 4 are unchanged.
