### Fixed

- **Broker-verification notarization tri-state (issue #36 path-2).** Extend the Phase-1
  consumer-activation notarization tri-state to the broker-verification / lifecycle path in
  `runtime_client.py`. A transient *online-but-notary-unreachable* outage during a broker
  operation (install, status, stage/commit/abort, rollback, drain, recover, uninstall) is now
  reported as a retryable `RuntimeStatus.UNAVAILABLE` instead of a mis-typed hard
  `INTEGRITY_ERROR` / `PROVIDER_ERROR` / `PROTOCOL_ERROR`. Genuine integrity failures
  (signature, digest, membership) keep their hard status unchanged; activation continues to
  gate on `status == OK`, so re-typing changes reporting and retryability only, never whether an
  unverified runtime is adopted or spawned. Implemented via a `_BrokerNotarizationUnavailable`
  marker re-typed at the single `_verify_published_version` source flatten, a `retryable` field
  threaded through `_BrokerMutationFailure` (rollback still runs), and earlier
  `except _BrokerNotarizationUnavailable` handlers at the broker terminals. The dispatcher-bridge
  probe path (non-authoritative for adoption) and dead code are out of scope.
