# Claude participation

< [Architecture handbook index](README.md)

Claude participates in three distinct roles: as a supported host and resident
primary, through separately authorized host-owned asynchronous coordination,
and through one narrow managed native route. Keeping those roles separate
prevents a valid document-intent route from being mistaken for review,
governance, repository, or code-generation authority.

## The managed route

The signed runtime descriptor admits Claude only for
`context.documents.intent`. The selected carrier invokes the locally installed
official Claude CLI and returns bounded opaque content with separate execution
diagnostics. The caller supplies and verifies the document inputs; a response
does not prove every document was read or establish a `context_text` artifact.
No general Claude transport is exposed in the routing request.

Routing is deliberately cost-last: eligible Gemini and Grok document-intent
routes precede Claude. Claude becomes a candidate only within the same sealed
request after those higher-priority routes are ineligible before provider
execution. This is route selection, not replay or a second invocation.

The boundary is action- and source-specific:

- allowed: document intent under `context.documents.intent`;
- not allowed: document extraction or general document reasoning;
- not allowed: repository or conceptual-prompt sources; and
- not allowed: review, governance, architecture, planning, delegation, or
  code generation.

Planning can select Claude only for its admitted action. A route decision
does not prove authentication, enable another action, or establish the
availability of the whole family.

## Provider and credential boundary

The route uses the provider's own installed CLI. The package does not extract
subscription credentials, reuse them in another client, or convert them into
API credentials. Authentication and CLI currency remain owned by the official
tool. The runtime preserves native results and available content separately;
the caller determines whether the requested intent comparison completed.

Native transport and lifecycle controls may be parsed, but provider prose or
structured-output shape does not establish document evidence or gate bounded
opaque-content recovery. The invocation has one owned process lifecycle and
separate cleanup evidence. There is no interactive screen-scraping completion
heuristic, credential fallback, or automatic replay.

The 7.0.5 host qualification explicitly deferred restoration of local Claude
subscription access and live Claude intent qualification. That deferral does
not enable another Claude action and is not a passed native inference check.

## Host and resident-primary role

Claude Code remains a fully supported host: the package installs natively,
every `/agent-collab:*` skill can be selected, and a Claude session may act as
the trusted resident primary. The primary interprets the user's objective,
authors and integrates work, adjudicates cross-family feedback, runs
verification, and owns landing decisions within operator authority.

The native document-intent route does not change independence rules. When the
active primary or artifact author is Anthropic-family, the primary and repository/skill workflow must exclude
same-family evidence where an independent family is required. Conversely,
when another family is primary, Claude document intent remains context only;
it cannot satisfy a review or governance evidence contract.

## Asynchronous participation

Host-owned asynchronous coordination remains a separate, explicitly
authorized surface. Host tooling owns addressability checks; the public coordinator does
not report async readiness or send async messages. An async response keeps the authority of that
coordination channel and does not become managed runtime evidence merely
because Claude also has a native document-intent route.

The accurate summary is therefore action-scoped: Claude is a fully supported
host and resident primary, may participate through separately authorized async
coordination, and is a managed native carrier only for read-only document
intent. No one of those roles silently widens either of the others.
