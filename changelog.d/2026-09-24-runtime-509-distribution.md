### agent-collab 7.0.8 — runtime 5.0.9

- Pair runtime 5.0.9 with the coordinator's request-repair reporting. Both
  macOS architectures must pass the coordinated signing, import and staged
  qualification gates before publication.
- A request whose effort is below an action's required floor is now raised to
  the lowest admitted class instead of failing before any provider starts;
  the raised effort, when it happens, is reported in the terminal result. An
  unsupported explicitly named provider now reports a distinct, stable
  reason instead of a generic failure.
- The coordinator now repairs a small class of request-construction mistakes
  before dispatch and reports each repair it made. A read-only repository
  action whose request omits the caller's repository is now bound to the
  caller's own repository (or a linked worktree of it that the request
  names); a request that names only some other directory is rejected before
  dispatch rather than silently redirected.
- Keep wire schema 12, protocol 5, native contract 4, 12 logical actions,
  eight logical agents and wire digest
  `a675807e0ff5f0544d7cc9d659914ce2dadac9be8efd0fb56635815e5c3e842a`
  unchanged. Bind the new release-exact manifest schema to the signed
  producer.
- Retain caller-owned independent-review checks, advisory results when
  evidence is missing, all-author reviewer selection and a nonrenewable
  corrected-review allowance.
