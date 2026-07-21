### Fixed

- Runtime: the dispatcher bridge document (`runtime_client._dispatcher_bridge_document`)
  now emits the canonical seven-key schema for every protocol version, instead of
  over-sending the request reservation (`execution_key` / `request_size` /
  `request_sha256`) for v2. The receiving bridge validator (workspace
  `provider_runtime._validate_dispatcher_bridge_document`, and its tests) accepts
  exactly seven keys and derives the reservation from `request` itself, so the
  over-send made a fresh selector-v2 dispatcher fail its first bridge exchange with
  "dispatcher bridge document is invalid". The reservation still crosses the trust
  boundary on the wire hello frame (where the bridge's freshly computed values are
  used); echoing it in the same-trust-domain bridge document added no integrity
  value. Fixes fresh v2 dispatcher activation.
