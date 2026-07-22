### agent-collab 4.2.3 — 2026-07-21

#### Fixed
- **Notarization tri-state typing at consumer activation (issue #36, Phase 1).**
  On a host that is online but cannot reach Apple's notarization service
  (enterprise firewalls blocking `*.apple.com` / CloudKit, Apple notary outages,
  restrictive allowlists), `runtime_client.py` no longer mis-reports the runtime
  as a corrupted `SIGNATURE_ERROR`. `codesign … --check-notarization` returns the
  same `rc != 0` for an unreachable notary and a genuinely-unnotarized binary, so
  an independent notary-reachability probe (`_apple_notary_reachable`, a
  system-trust TLS handshake to Apple's notary/CloudKit hosts that never raises
  into its caller) now disambiguates the two: an unreachable notary — and a
  transient `TimeoutExpired`/`OSError` — is typed as the retryable
  `RuntimeStatus.UNAVAILABLE` with an actionable message, while a genuine
  not-notarized negative (notary confirmed reachable) stays `SIGNATURE_ERROR`.
  Activation still gates on `status == OK`, so no non-OK outcome can ever execute
  the runtime — only the reporting and retryability change. `migration-doctor`
  now surfaces the specific reason instead of a bare "typed unavailable".

#### Notes
- Scope is Phase 1 (consumer-activation path) per the operator's phased decision.
  The broker-verification path (`_verify_published_version`) exhibits the same
  defect (typed `INTEGRITY_ERROR`) and is tracked as a bounded follow-up. Full
  offline activation (a committed Apple-signed notarization ticket verified
  offline against the entrypoint CDHash) remains a separately-scoped Tier-3
  effort gated on a feasibility spike; a bare Mach-O cannot be stapled, so that
  path is not turnkey.
