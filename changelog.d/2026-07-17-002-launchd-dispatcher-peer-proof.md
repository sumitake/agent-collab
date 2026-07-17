### agent-collab 3.5.2 — launchd dispatcher peer readiness

- Distinguish the root-owned launchd listener credential from the
  operator-owned sealed runtime process when authenticating a staged
  dispatcher on macOS.
- Retry only the exact root-plus-pid-1 launchd handoff sentinel under the
  existing handshake deadline, with capped exponential sleeps and immediate
  failure for malformed state or socket errors.
- Re-prove the stable process start identity, exact executable, signed
  artifact, socket identity, and final kernel peer PID before sending hello.
