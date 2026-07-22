### agent-collab 4.2.3 — 2026-07-21

#### Fixed
- **Notarization outage no longer mis-typed as a corrupted runtime (issue #36, Phase 1).**
  On a host that is online but cannot confirm notarization with Apple (enterprise
  firewall blocking `*.apple.com` / CloudKit, Apple notary outage, restrictive
  allowlist), consumer activation no longer reports the runtime as a corrupted
  `SIGNATURE_ERROR`. Any nonzero result from `codesign … --check-notarization` — a
  transient `TimeoutExpired`/`OSError`, or any `rc != 0` — is now typed as the
  retryable `RuntimeStatus.UNAVAILABLE` (new `_RuntimeNotarizationUnavailable`,
  a sibling of `_RuntimeSignatureError`) with an actionable, retryable message.
  Activation still gates on `status == OK`, so a runtime whose notarization cannot
  be confirmed never executes — only the reporting and retryability change.
  `migration-doctor` now surfaces the specific reason rather than a bare
  "typed unavailable".
- The consumer does not attempt to distinguish "genuinely unnotarized" from
  "notary unreachable": `codesign --check-notarization` returns the same nonzero
  for both, and a frontend TLS handshake cannot confirm the notary lookup itself
  (per the Codex review of PR #39). The authoritative genuine-not-notarized check
  remains at the release gate (`verify_runtime_release.py`), which runs on a fresh,
  online CI host where the lookup is reliable.

#### Notes
- Scope is Phase 1 (consumer-activation path) per the operator's phased decision.
  The broker-verification path (`_verify_published_version`) exhibits the same
  defect typed as `INTEGRITY_ERROR`; an audit found its true surface spans the
  broker lifecycle (≈14 status-mappers + load-bearing exception flatteners), so it
  is tracked as its own focused follow-up. Full offline activation (a committed
  Apple-signed notarization ticket verified offline against the entrypoint CDHash)
  remains a separately-scoped Tier-3 effort gated on a feasibility spike (a bare
  Mach-O cannot be stapled, so it is not turnkey).
