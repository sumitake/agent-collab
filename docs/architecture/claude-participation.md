# Claude participation

< [Architecture handbook index](README.md)

A frequently asked question from users of this package: why does Claude not
participate as a routed managed agent in the multi-agent workflow, when the
model family is fully capable and well qualified for exactly this work? Other
handbook pages state the fact ("Claude model participation remains
async-only"); this page explains it.

The short answer: **capability is not the constraint; authorization is.** The
boundary is a provider policy about how Claude subscription credentials may be
used, not a design judgment by this project about Claude's quality. Policy
facts on this page were last verified 2026-08-18; Anthropic's current published
terms are authoritative if they have changed since.

## The provider policy boundary

Anthropic restricts Claude subscription credentials (the OAuth tokens behind
Free, Pro, and Max plans) to use within its own interactive surfaces: the
Claude Code application and claude.ai. In February 2026 Anthropic clarified
that using subscription OAuth tokens from third-party tools violates its terms
of use, and effective April 4, 2026 subscriptions no longer cover usage
through third-party tools at all. Metered API keys are the provider's
designated path for programmatic and third-party use.

The managed provider runtime this package coordinates is precisely a
third-party automation surface: it invokes provider CLIs non-interactively,
one fresh process per sealed request, and validates structured artifacts and
execution receipts. Under the current policy there is no authorized way for it
to invoke Claude headlessly on a subscription, so no synchronous Claude route
exists, and readiness reporting for Claude covers async coordination only.

Two properties of the boundary are worth stating plainly:

- It is a **credential-authorization** rule, not a technical gap. The
  runtime's adapter pattern could support a Claude backend the same way it
  supports the other provider families if an authorized programmatic
  credential were configured for it.
- It is **provider-enforced**, not merely declarative. Anthropic has deployed
  technical countermeasures against third-party use of subscription
  authentication and has suspended violating accounts.

## What Claude does in this workflow

The restriction removes one role, not the family. Claude Code is a fully
supported **host**: the package installs natively, every `/agent-collab:*`
skill runs, and a Claude session acts as a **resident primary**, the
highest-authority seat in the workflow. The primary authors work, runs the
governed process, adjudicates cross-family feedback, and integrates results.
Interactive use under a subscription is the provider's sanctioned mode, so
nothing about the primary role is affected. Claude also participates in
host-owned **async coordination** where readiness is observed (see
[Capabilities and workflows](capabilities-and-workflows.md)).

What the policy removes is Claude as a **callable managed leg**: a routed
cross-check consultant, reviewer, or worker that another primary's sealed
request can select synchronously. Family-independence requirements are met by
the other enabled lineages.

For users choosing a primary host by familiarity: running a non-Claude primary
does not strand a Claude subscription, and choosing Claude Code as your host
does not cost you anything in this workflow. The subscription's value here is
the resident-primary seat itself; the only gap is that *other* primaries
cannot call Claude as a managed service.

## Why not drive the CLI through a pseudo-terminal?

An obvious-looking workaround exists: host the official Claude Code CLI inside
a pseudo-terminal, have the runtime type prompts into the interactive session,
and read answers back from the screen, the way terminal-cockpit orchestrators
host CLI agents for a human operator. This was formally assessed in August
2026 and rejected. The distinction that matters:

- **Supervised cockpits are fine.** When a human is on the other end of every
  terminal, the CLI is being used interactively, which is what the
  subscription authorizes.
- **Unattended routing is not.** The same mechanics driven by an automated
  runtime become machine-to-machine automation presented to the provider as
  interactive use, the exact pattern the policy change was made to stop.

The rejection was also structural, not just contractual. A terminal UI has no
machine contract: completion must be inferred from screen heuristics (so
"still thinking" and "hung" are indistinguishable), the screen layout is an
unversioned auto-updating surface, interactive dialogs stall unattended
sessions, and the route cannot produce the truthful execution receipts and
evidence this project's governance requires. It fails the project's
reliability, simplicity, and honesty baselines even before the terms are
considered, and detection risk would fall on the operator's own subscription,
removing the compliant interactive role along with the workaround.

## What would restore a routed Claude agent

1. **A metered API-key route.** The provider's documented programmatic
   surface, authorized by a metered API key, is compliant and fits the managed
   runtime's adapter contract like the other provider families: structured
   artifacts, genuine receipts, typed failures. Enabling it is a cost decision
   for each deployment's operator, and the spend can be bounded by scoping the
   route to narrow high-value actions.
2. **A provider terms change.** If Anthropic later offers a sanctioned
   programmatic tier for subscriptions, enabling Claude routes becomes a
   registry configuration change on machinery that already exists.

Until then, the accurate summary is: Claude is absent from managed routing
because the provider's subscription terms authorize no compliant headless
invocation, the one feasible workaround fails this project's reliability
baseline and would put the operator's own Claude access at risk, and the
project chooses the honest configuration over a fragile circumvention.
