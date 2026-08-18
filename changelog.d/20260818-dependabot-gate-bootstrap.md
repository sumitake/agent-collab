### Changed

- Document the one-time bootstrap requirement in `dependabot-gate.yml`: the
  branch-protection preflight refuses to pin a context with no prior check-run,
  so the gate must run on at least one PR before `dependabot-gate` is pinned
  required. This PR is that first run, enabling activation on the plugin repo.
