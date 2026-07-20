### agent-collab 4.1.1 — 2026-07-20

#### Fixed

- Make `broker-status` use the same canonical selector view as request routing,
  so a valid selector-v1 selected dispatcher is no longer misclassified as an
  obsolete single-broker installation.
- Require the selected immutable lane, launchd job, socket, and closed liveness
  exchange to pass before broker status is ready. Migration-doctor `READY` now
  requires this executable proof as well as the signed runtime manifest.
- Require the one-shot launchd job to return idle and every retained fallback
  lane to remain independently verifiable before status can claim executable
  readiness, matching the topology that request routing will actually accept.
- Treat a selectorless legacy broker as installed but unavailable even when its
  old socket responds, because current request routing cannot capture an
  executable lane without the same canonical selector proof.
- Keep liveness compatible with a verified dispatcher-v1 selected lane while a
  dispatcher-v2 candidate is staged, so the previous lane remains executable
  until the new lane is fully proved and atomically selected.
- Preserve typed timeout, output-limit, and teardown results after a dispatcher
  accepts a request instead of collapsing those local completion failures into
  a misleading `protocol_error`; accepted work still never retries another lane.
- Wait for a selected dispatcher-v1 one-shot job to return idle before exposing
  its response to the next caller, closing the launchd teardown window without
  serializing the concurrent dispatcher-v2 scheduler.
- Bound that dispatcher-v1 idle proof by the request's existing absolute broker
  deadline, so teardown verification cannot silently start a fresh timeout.
- Resolve Codex Desktop's active OpenAI model from its exact current rollout
  when `CODEX_ACTIVE_MODEL` is absent. The reader is fixed-root, bounded,
  no-follow, same-owner, single-file, and fail-closed on ambiguous, writable,
  linked, malformed, oversized, or conflicting identity evidence.

#### Verification

- Added RED/GREEN regressions for selector-v1 projection, legacy selected-lane
  liveness, selectorless legacy false-positive rejection, one-shot idle
  completion, invalid retained-lane rejection,
  accepted-request timeout typing and no-fallback behavior, legacy one-shot
  response teardown and deadline reuse, failed dispatcher ping, manifest-only
  doctor readiness, safe Codex rollout identity, and ambiguous or unsafe
  rollout rejection.
