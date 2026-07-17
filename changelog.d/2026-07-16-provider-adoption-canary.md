### agent-collab 3.5.0 — authenticated dispatcher canaries

- Add exact Darwin dispatcher peer proof and a request-free, digest-bound
  hello/ready handshake before any green provider request is sent.
- Add a token-gated internal `adoption_canary` coordinator operation bound to
  one candidate tuple and route allowlist without exposing a user-selectable
  provider path, model, auth root, or policy route.
- Keep the selector legacy-blue by default. Apply a separate local bound to the
  request-free handshake so a proven pre-request green failure retains time for
  independently proven blue without shortening the original request deadline;
  a failure at or after request send never retries another lane.
