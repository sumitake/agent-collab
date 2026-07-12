# Public repository governance

This is the self-contained contribution and merge contract for
`sumitake/agent-collab`. Contributors need no access to a private repository or
build system. Private infrastructure owns only native-runtime implementation,
credentials, signing, and notarization; this repository owns public policy,
skills, client behavior, contribution rules, and release-safety gates.

## Authoritative local surfaces

- `AGENTS.md` defines source boundaries and required validation.
- `.github/PULL_REQUEST_TEMPLATE.md` defines the evidence contributors record.
- `.github/workflows/compliance-trace.yml` validates the trace schema in CI.
- `scripts/check_pr_compliance.py` is the local pre-merge form check.
- `SECURITY.md` defines private vulnerability reporting.

When prose and automation disagree, fail closed and do not merge until they
agree. Automation verifies evidence form and presence, not whether a review was
genuine; reviewers and the operator remain responsible for substance.

## Change tiers

- **Tier 1:** documentation, comments, or cosmetic metadata with no executable,
  policy, security, packaging, or release effect. A reasoned `N/A` cross-check
  is permitted.
- **Tier 2:** user-visible behavior, skills, tests, ordinary CI, dependencies,
  or compatible policy changes. Record an independent cross-family review.
- **Tier 3:** routing authority, family independence, provenance, sandboxing,
  authentication, signing, runtime verification, release supply chain, or
  governance gates. Record an independent cross-family review; operator-reserved
  paths also require the operator to merge.

The reviewer family must differ from the artifact author or active agent family.
Unknown-family evidence cannot establish governance-grade independence. A
multi-round trace records the final operative verdict.

## Pull-request contract

Every pull request contains exactly one compliance-trace block with these
non-empty keys: `author`, `standing_directives`, `tier`, `cross_check`,
`post_condition`, `mcp_coverage_gap`, and `operator_reserved`.

`mcp_coverage_gap` remains the stable schema name. Record `NONE` when no
external capability gap exists, or `FILED: <public issue URL>` when follow-up is
required. Tier 2 and Tier 3 cannot use a bare `N/A` cross-check. In-flight states
may keep a PR open, but only a converged `PROCEED` makes it merge-eligible.

Before merge, run:

```text
python3 scripts/check_pr_compliance.py <pr-number> --repo sumitake/agent-collab
```

The verdict is a point-in-time form check. Required CI, CODEOWNERS, review state,
and operator decisions still govern the actual merge.

## Public-source and release boundary

Every active path, reachable ref, and release archive must stay free of provider
executor source, raw provider invocation recipes, private absolute paths,
credentials, retired package trees, and unreviewed native artifacts. PR CI uses
GitHub-hosted runners and receives no private build/sign credentials.

Policy-only releases contain an empty runtime manifest. An activation release
may import only a final signed and notarized runtime plus the public verification
metadata. Public contributors never build or inspect the private implementation.

Run the gates in `README.md`, including:

```text
python3 scripts/check-public-export-safety.py --active-tree --history
python3 scripts/secret_scan.py
git diff --check
```

Suspected source-boundary or secret exposure is a security incident. Stop
publication and use `SECURITY.md`; do not preserve suspect material in a public
issue, PR body, fixture, or log.
