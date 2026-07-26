<!-- release: agent-collab 4.5.1 -->
### Changed

- Rebuild the darwin-arm64 provider runtime from final workspace `1.0.823`
  commit `d08b6382710d6d5910d64cf011bcac873a2e1c03`, Developer-ID sign it, and
  notarize it through Apple submission
  `c6d29dec-5351-467d-883e-0b862734567d`.
- Replace the policy-only placeholder with a closed activation manifest that
  pins the complete standalone bundle at SHA-256
  `2cea10cff2030d0238661667cf8d1b83cf9885dc6f4a03b0db4365e891b04f47`.
  The rebuilt runtime includes the v4.5.1 provider-agnostic containment,
  canonical-user-HOME authentication, private request workspace, bounded
  execution/teardown/cleanup, OpenCode Go, output conformance, and lifecycle
  continuity repairs from the final merged workspace.

### Tests

- Verify the imported handoff byte-for-byte, re-run the Developer ID,
  hardened-runtime, secure-timestamp, Apple-notarization, Mach-O, contract,
  member-inventory, and whole-bundle gates, then build and reopen the canonical
  activation archive.
