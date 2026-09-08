# Capabilities and workflows

< [Architecture handbook index](README.md)

The unified package exposes 53 generated skills under the
`agent-collab` namespace. A skill is a workflow contract: it defines when to
use the capability, what evidence to gather, which authority is acceptable,
and when to stop. It is not a promise that every managed route is currently
available on every host.

The definitive low-level inventory remains the
[package reference](../../plugins/agent-collab/README.md#skills); this page
organizes that inventory by user outcome.

## Capability map

| User job | Skills | Typical outcome |
| --- | --- | --- |
| Identity, routing, and readiness | `agent-readiness`, `agent-runtime-status`, `migration-doctor`, `route`, `start-inbox-monitor`, `teamwork` | Establish which host, family, route, or async target is eligible before relying on it. |
| Planning, architecture, and estimation | `architect`, `brainstorm`, `compose-skills`, `intent-check`, `project-estimation`, `second-opinion` | Clarify a design, widen options, select workflows, obtain an independent read, or forecast agent-led delivery. |
| Governance and assurance | `autonomy-readiness`, `code-review`, `governance-review`, `logic-check`, `qa-verify`, `red-team`, `untrusted-audit` | Test correctness, independence, security, provenance, and completion evidence. |
| Deliberation and stakeholder lenses | `debate`, `simulate-user` | Expose conflicting arguments or test a proposal against a persona. |
| Delegation and implementation | `delegate`, `dev-delegate`, `worker` | Analyze supplied sources or return a development artifact for the primary to integrate. |
| Context and knowledge work | `context`, `knowledge-compile`, `project-knowledge` | Extract or synthesize bounded documents/repositories, or maintain an explicit project knowledge layer, with provenance. |
| Reproducible workflows | `chain`, `chain-configurator`, `orchestrate` | Define and execute repeatable multi-step coordination. |
| Integration and conflict handling | `merge-resolve` | Analyze and resolve a bounded merge conflict while preserving intent. |
| Visual guidance | `ui-to-code`, `visual-review` | Guide primary-only visual work when typed image transport is absent; never invent a managed attachment path. |
| Language expertise | `rust-engineer`, `go-engineer`, `elixir-engineer`, `sql-engineer` | Apply domain-specific engineering practices. |
| Infrastructure and reliability | `kubernetes-specialist`, `terraform-engineer`, `sre-engineer`, `incident-responder` | Design, review, or troubleshoot operational systems. |
| Data and AI | `mlops-engineer`, `llm-architect`, `postgres-engineer`, `data-engineer` | Apply data, model, database, and pipeline expertise. |
| Evaluation and writing quality | `eval-engineer`, `prompt-regression-tester`, `hallucination-investigator`, `ai-writing-auditor` | Evaluate model-backed behavior, prompt drift, factual failure, or prose quality. |
| Engineering process | `decision-map`, `prototype`, `architecture-review` | Create decision tickets, answer one design question with a throwaway prototype, or sweep module boundaries. |

## Execution shapes

### Managed synchronous routes

Routed review, context, planning, governance, and worker workflows submit a
bounded request through the installed package's public coordinator. Policy
selects an eligible managed route and preserves one of the authorities defined
in [Governance and authority](governance-and-authority.md).

Current repository route contracts cover:

- Claude read-only document-intent work through the official native CLI,
  cost-last after eligible Gemini and Grok routes;
- Gemini advisory, governance, and bounded context work;
- Codex advisory, governance, and output-only code-generation work;
- OpenCode planning and output-only build work;
- Grok read-only architecture, governance, bounded context, and output-only
  code generation.

The route list is a **current repository contract**, not installed/active
evidence. Readiness is resolved immediately before use, including for the
output-only Codex code-generation route.

### Primary-executed workflows

Some skills guide the active primary directly rather than selecting a managed
provider. The engineering-process pack is explicitly self-executed. Visual
skills also remain primary-only where the current protocol has no typed image
or binary-media transport. These workflows can still require local tools,
tests, or user approval; “primary-executed” is not “unchecked.”

### Async coordination

Claude and Antigravity participation can use host-owned asynchronous transport
after the exact target identity, family, session, and current readiness are
observed through host tooling. The public coordinator neither reports async
readiness nor sends async messages. Async coordination is separate from Claude's narrow managed
`context.documents.intent` route, and an async reply is not independent
governance merely because it arrived. [Claude participation](claude-participation.md)
explains the action-scoped boundary.

### Reproducible composition

- `chain` executes a versioned YAML-defined sequence of skill invocations.
- `chain-configurator` helps create a chain definition interactively.
- `orchestrate` coordinates a dependency graph with bounded tasks and explicit
  gates.
- `teamwork` coordinates role-based milestones and stop conditions.

Composition does not erase the authority of individual steps. A read-only
review inside a chain remains read-only, and a worker artifact still returns to
the primary for integration.

## Common workflows

### Code review and independent approval

1. Identify the artifact, primary, authors and whether the task requires
   independent approval.
2. Use the appropriate review skill. For required independence, verify a
   reviewer outside the primary and author families and bind that selection to
   the live call. Verify observed reviewer lineage and exact source afterward.
3. For ordinary code review, an available Gemini reviewer can still help when
   no distinct-family reviewer is available. Label same-family or unknown
   lineage as advisory; leave any independent approval requirement unmet.
4. Preserve and adjudicate the raw findings. Do not infer independence from
   routing, role names or a subscription, repeatedly attempt an unavailable
   provider, or replay a consumed request to repair formatting or evidence.

This is caller-owned behavior in the [released code-review
skill](../../skill-specs/code-review.md). The routing request has no dynamic
primary/artifact-author lineage exclusion fields.

### Bounded delegation

The primary keeps objective interpretation and integration ownership. Ordinary
`delegate` work analyzes supplied bounded documents or an exact sealed
repository through an admitted context action. A list of names, links or topics
alone is not a document corpus, and this route does not promise source discovery.
Each worker receives the relevant sources, scope and stop condition. Results
remain advisory; multiple workers do not imply multiple model families.

Development delegation uses the separate admitted code-generation actions.
The caller supplies a disposable repository or copy, captures any returned
patch, and reviews and tests it before application. A worker does not gain
permission to apply output or make landing decisions through successful routing.

### Architecture and planning

Use `brainstorm` to widen the option space, `architect` for an additional
read-only architecture consultation, `architecture-review` for a primary-led
codebase sweep, `intent-check` for an advisory task-interpretation comparison, and
`decision-map` when the effort is too large for one session.

`project-estimation` adds a deterministic delivery forecast once a formal
design or plan has a concrete completion boundary, phases, dependencies,
roles, and material gates. The skill description supports situational
auto-selection, while package-owned `architect`, `orchestrate`, and `teamwork`
workflows explicitly compose the checkpoint before final presentation. A host
without contextual skill selection uses explicit invocation and reports that
the automatic checkpoint was unavailable. See
[Project estimation](project-estimation.md) for modes, examples, output
semantics, and the published v7.0.6 maintenance evidence.

The packaged prior is currently an explicit bootstrap: enhancement duration is
descriptive, bootstrap confidence cannot be high, and unsupported greenfield,
token-cost, wait, rework, quota-delay, and cash metrics remain typed omissions
rather than zeros or workflow failures.

### Large-context work

Use `knowledge-compile` when multiple sources must become a durable cited
dossier. Use `context` for a bounded managed document or repository extraction
or reasoning request, and `project-knowledge` for an explicit project-owned
knowledge layer. Context transport does not grant governance or mutation
authority.

## Host and package support

| Surface | Public package evidence | User expectation |
| --- | --- | --- |
| Claude Code | Claude-compatible plugin manifest and marketplace metadata. | Native package install and `/agent-collab:*` skills. The official native CLI may serve read-only document intent when action-scoped readiness passes; Claude is not eligible for managed review, governance, repository, or code-generation actions (see [Claude participation](claude-participation.md)). |
| Codex CLI/app | Codex-native manifest and generated Codex marketplace. | Native package install and the same skill namespace. Start a new task after install/update. |
| Antigravity | Compatible plugin import, logical Gemini managed routes, and separate host-owned async coordination; no separate package. | Gemini repository review uses the co-packaged coordinator and action-scoped readiness. Async readiness is a different surface; neither host name nor reviewer role proves independence. |
| OpenCode and ZCode | Dynamic host/model policy and managed OpenCode routes; no separate package. | A compatible host/plugin surface is required. OpenCode is a transport; the selected model supplies family lineage. |
| Custom host | Explicit primary identity fields and the closed package contract. | If the host cannot load the package safely, it is unsupported; do not recreate provider-specific shims. |

## Availability rules

A capability is usable only when all applicable gates pass:

- the unified package is installed and selected;
- no active retired package blocks migration;
- primary identity is complete enough for the requested authority;
- the requested family is eligible and independent where required;
- the manifest advertises the exact route/action contract;
- the native boundary and provider-free readiness checks pass; and
- provider authentication, quota, and request execution succeed.

Runtime and planning diagnostics describe the attempted route; they do not
perform the caller's family-exclusion check or establish provider-wide failure.
Missing independent-review evidence leaves that requirement unmet. Preserve
available advisory content without claiming broader authority, silently
substituting an operator-named target, or replaying a consumed request.

For installation and recovery, continue to
[Lifecycle and operations](lifecycle-and-operations.md).
