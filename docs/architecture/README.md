# agent-collab architecture handbook

This handbook explains the public architecture of `agent-collab` for users,
contributors, reviewers, and release maintainers. It describes stable
boundaries and public contracts. It does not reproduce private runtime
implementation, build credentials, operator-specific paths, or machine state.

The handbook is descriptive. Source, tests, manifests, release evidence, and
the contribution contract remain authoritative for their respective claims.
When two generations differ, use the status vocabulary below instead of
silently treating them as the same thing.

## Read this handbook in order

1. [System context](system-context.md) explains what the project is, what it is
   not, its actors, and its public/private boundary.
2. [Capabilities and workflows](capabilities-and-workflows.md) maps the skill
   surface to common user jobs and explains availability limits.
3. [Project estimation](project-estimation.md) explains deterministic delivery
   forecasting, reconciliation, pricing and quota semantics, privacy-safe
   priors, planning checkpoints, and release maintenance.
4. [Governance and authority](governance-and-authority.md) explains family
   independence, sealed authority, review evidence, and operator control.
5. [Lifecycle and operations](lifecycle-and-operations.md) covers installation,
   verification, use, updates, troubleshooting, safe mode, rollback, and
   removal.
6. [Repository and release architecture](repository-and-release.md) maps the
   public package, generated sources, validation, and release flow.
7. [Status and evidence](status-and-evidence.md) defines the binding lifecycle
   labels and records the dated evidence snapshot used by this documentation.
8. [Claude participation](claude-participation.md) explains Claude's three
   distinct roles: fully supported host and resident primary, optional async
   participant, and action-scoped managed document-intent carrier.

Historical and design material is indexed separately in
[`docs/design/README.md`](../design/README.md). It is not automatically the
current runtime contract.

## Status vocabulary

| Label | Meaning | Appropriate evidence |
| --- | --- | --- |
| **current** | The behavior or contract is present in the checked-out public repository baseline and covered by current source, manifests, or tests. | Merged source plus focused tests or generated-manifest checks. |
| **repository-only** | The implementation or artifact exists in the repository, but no cited release and host observation proves it is installed and selected. | Repository source or artifact identity only. |
| **staged** | Material is prepared for a later compilation, publication, activation, or selection step. | A changelog fragment, candidate artifact, tag input, or generated release input. |
| **installed/active** | A specific version has been positively observed as installed, selected, and ready on a specific host. | Host package inventory plus provider-free readiness evidence. |
| **proposed** | A design or change has not become the current merged contract. | Draft, branch, issue, or unmerged design. |
| **historical** | Retained evidence explains earlier decisions but does not define current behavior. | Changelog, superseded design, or past review record. |
| **retired** | The public source explicitly removes or blocks the old surface. | Migration policy, absence tests, and clean-package checks. |

These labels are deliberately narrower than words such as “released” or
“available.” A manifest can advertise a route while a host still reports it
unavailable. A tag can exist without a GitHub release. A repository version can
be newer than both. See [Status and evidence](status-and-evidence.md).

## Architectural invariants

The public repository and package preserve these invariants:

1. There is one installable package, `agent-collab`, not one plugin per host or
   provider.
2. Callers select a skill or logical collaboration job. They do not receive a
   raw provider-execution escape hatch.
3. Governance review requires a model family independent of the active primary
   and the reviewed artifact's known author family.
4. Route authorities are closed. Read-only, output-only, and unavailable
   actions do not promote themselves because another route failed.
5. Provider output is an artifact for the trusted primary to inspect. It does
   not merge, deploy, or change policy by returning successfully.
6. Native execution is optional at the package level and fail-closed. A listed
   skill or advertised contract does not prove current host readiness.
7. The public package may contain only the final reviewed native bundle and
   closed manifest metadata. Native implementation and build/sign credentials
   remain outside this repository.
8. Retired packages are migration evidence, not rollback targets.

## Sanitization contract

Architecture documentation is public only when it records portable boundaries
rather than one operator's environment. These pages therefore:

- use repository-relative paths and generic roles;
- omit personal account names, host names, network details, tokens,
  credentials, local cache paths, and private repository locations;
- describe managed provider roles without publishing raw provider invocation
  recipes or discovery commands;
- distinguish public artifact-verification requirements from the private
  systems that produce those artifacts; and
- label uncertainty instead of inferring installed or active state.

Do not add copied diagnostic output, private build identifiers, notarization
submission identifiers, environment dumps, or secret-bearing examples to this
handbook. Suspected exposure follows [the security policy](../../SECURITY.md),
not a public issue or pull request.

## Source map

| Question | Start here | Authoritative public evidence |
| --- | --- | --- |
| What does the package install? | [System context](system-context.md) | Host manifests, generated marketplaces, package tree, and distribution tests. |
| Which workflows exist? | [Capabilities and workflows](capabilities-and-workflows.md) | `skill-specs/`, generated skills, package reference, and skill-contract tests. |
| How are agent projects estimated? | [Project estimation](project-estimation.md) | Public request/result schemas, deterministic helper, released v6.2.3 maintenance evidence, skill checkpoints, maintenance verifier, producer-byte compatibility fixtures, and focused tests. |
| Who may review, write, or merge? | [Governance and authority](governance-and-authority.md) | Host policy, coordinator, public governance contract, PR template, and compliance checks. |
| Is a route usable now? | [Status and evidence](status-and-evidence.md) | Installed version plus provider-free readiness on that host. Repository presence alone is insufficient. |
| How do I install or recover? | [Lifecycle and operations](lifecycle-and-operations.md) | Current host CLI, migration doctor, runtime-management surface, and migration policy. |
| How is a release produced? | [Repository and release architecture](repository-and-release.md) | Release scripts, workflows, signed-tag contract, archive checks, and release evidence. |
| Where may Claude participate? | [Claude participation](claude-participation.md) | Signed action/source targeting, official structured-CLI boundary, async coordination, and host-support statements in this handbook. |

## Maintenance rule

Update the relevant architecture page in the same change when a public
component, authority boundary, host surface, route contract, lifecycle state,
or release boundary changes. Keep each claim tied to repository-relative source
and focused evidence. If delivery evidence lags source, keep both observations
and label them; do not “fix” the discrepancy by declaring one generation
active everywhere.
