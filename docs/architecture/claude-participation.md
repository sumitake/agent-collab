# Claude participation

< [Architecture handbook index](README.md)

Claude participates in three distinct roles: as a supported host and resident
primary, through separately authorized host-owned asynchronous coordination,
and through one narrow managed native route. Keeping those roles separate
prevents a valid document-intent route from being mistaken for review,
governance, repository, or code-generation authority.

## The managed route

The signed runtime descriptor admits Claude only for
`context.documents.intent` with document source. The runtime invokes the
locally installed official Claude CLI through its structured interface and
returns the existing read-only `context_text` artifact with all-document-read
evidence. It does not expose provider credentials, a raw CLI escape hatch, or
a general Claude transport to callers.

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

Readiness reports Claude only for the compatible action/source pair. A ready
Claude CLI does not make Claude eligible elsewhere, and an unavailable Claude
candidate does not make the family globally unavailable.

## Provider and credential boundary

The route uses the provider's own installed CLI and its supported structured
output surface. The package does not extract or reuse Claude subscription
credentials in another client, translate them into an API credential, or
publish a provider invocation recipe. Authentication and CLI currency remain
owned by the official tool; the signed adapter observes readiness and returns
typed failures without weakening the request contract.

This distinction matters. Driving an interactive terminal UI by screen
scraping would create an unversioned, brittle completion heuristic and could
not produce the runtime's structured evidence. The managed route does not do
that: it uses a bounded structured CLI contract, one fresh process for the
sealed request, typed output validation, and deterministic cleanup.

Provider terms and the official CLI contract remain authoritative. If either
withdraws the structured surface, readiness fails closed for this route rather
than substituting a raw command, another credential mechanism, or broader
authority.

## Host and resident-primary role

Claude Code remains a fully supported host: the package installs natively,
every `/agent-collab:*` skill can be selected, and a Claude session may act as
the trusted resident primary. The primary interprets the user's objective,
authors and integrates work, adjudicates cross-family feedback, runs
verification, and owns landing decisions within operator authority.

The native document-intent route does not change independence rules. When the
active primary or artifact author is Anthropic-family, policy still excludes
same-family evidence where an independent family is required. Conversely,
when another family is primary, Claude document intent remains context only;
it cannot satisfy a review or governance evidence contract.

## Asynchronous participation

Host-owned asynchronous coordination remains a separate, explicitly
authorized surface. The public coordinator may report its readiness but does
not send async messages. An async response keeps the authority of that
coordination channel and does not become managed runtime evidence merely
because Claude also has a native document-intent route.

The accurate summary is therefore action-scoped: Claude is a fully supported
host and resident primary, may participate through separately authorized async
coordination, and is a managed native carrier only for read-only document
intent. No one of those roles silently widens either of the others.
