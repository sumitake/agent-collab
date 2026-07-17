### agent-collab 4.0.3 — dispatcher lifecycle control protocol

- Send lifecycle ping and lock-probe control messages on the sealed dispatcher
  protocol-v1 contract so a staged dispatcher can be proven before activation.
- Keep typed lifecycle failures on runtime protocol v2 and reject swapped,
  malformed, or extra-field success and failure responses.
