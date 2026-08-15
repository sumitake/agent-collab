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
`post_condition`, `mcp_coverage_gap`, `contributor_rights`, and
`operator_reserved`.

`mcp_coverage_gap` remains the stable schema name. Record `NONE` when no
external capability gap exists, or `FILED: <public issue URL>` when follow-up is
required. Tier 2 and Tier 3 cannot use a bare `N/A` cross-check. In-flight states
may keep a PR open, but only a converged `PROCEED` makes it merge-eligible.
An anchored `OPERATOR-BYPASSED` state may record an explicit operator-authorized
admin/bypass path without making the trace-form check red. It is valid evidence
form only: it is not a reviewer verdict, does not establish cross-family
convergence, and never grants ordinary agent self-merge eligibility. The
`operator_reserved` field must begin with `yes` and identify the
operator-controlled action.

Coordinator `provider_error` and `teardown_error` results are attempt-local.
They invalidate that attempt's artifact and evidence, but do not establish
provider or route unavailability, quarantine the route, or block unrelated
repository work. Never automatically replay the failed request; a later
caller-authorized request is a distinct attempt whose eligibility is evaluated
from fresh readiness. Where governance evidence is still required, use an
eligible documented alternative or record an explicit operator-authorized path
honestly; never fabricate reviewer convergence.

Set `contributor_rights` to `OWNER-AUTHORED` only when John Osumi authored the
change. For any external contribution, use `OPERATOR-CONFIRMED` only after John
Osumi or Osumi Consulting LLC has verified a separate written agreement that
grants sufficient rights to use, modify, distribute, sublicense, and
commercially relicense the contribution. A Developer Certificate of Origin is
not a substitute. Automation verifies the field's presence and form; the
operator verifies the actual agreement.

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
may import only a final signed and notarized standalone bundle, its closed
schema-4/runtime-protocol-3/native-contract-4 manifest, the canonical generated
wire descriptor and hash, per-member verification metadata, and required
third-party license evidence. Public contributors never build or inspect the
private implementation.

Run the gates in `README.md`, including:

```text
python3 scripts/check-public-export-safety.py --active-tree --history
python3 scripts/secret_scan.py
git diff --check
```

### Scope of history mode

`--history` inspects every ref reachable in the *local* clone, not live remote
state. A clone that retains pre-rewrite refs therefore fails this gate even when
the canonical remote is clean. Run the gate on a disposable full clone of the
canonical remote and record the commit and refs it checked.

A large `legacy_history` or `legacy_release_ref` wall naming retired package
trees is consistent with retained pre-rewrite refs, but violation kind and volume
carry no provenance. A clean disposable-clone comparison is evidence only about
the snapshot it recorded. It does not clear the failing clone, the current
publication candidate, refs the comparison did not fetch, or the possibility of
prior public exposure.

Stop publication and use `SECURITY.md` when the publication candidate itself
fails, a canonical fetched ref fails, credential material appears, prior exposure
is possible, or provenance stays uncertain. Scanner output is not safe to paste
publicly: `FAIL` lines carry paths, object identifiers, and ref names.

Suspected source-boundary or secret exposure is a security incident. Stop
publication and use `SECURITY.md`; do not preserve suspect material in a public
issue, PR body, fixture, or log.
