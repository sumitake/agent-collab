# Claude participation

< [Architecture handbook index](README.md)

Claude can host the plugin, act as the resident primary, and serve selected
managed actions through its official CLI. Host-owned asynchronous coordination
requires separate authorization.

## Managed actions

Runtime 5.1.0 admits Claude for four read-only actions. Use
`architecture.conceptual` for a design question supplied as text,
`context.documents.intent` for intent comparison, `context.documents.extract`
for extraction, and `context.documents.reason` for reasoning over supplied
documents. The caller reads the returned content and checks it against the
inputs. Repository access, managed review, governance, and code generation
remain outside Claude's managed authority.

Set `explicit_target` to `claude` to select it. Automatic planning places
Claude after the existing eligible routes for these actions. Live authentication
and execution are checked separately for the selected route.

On the signed 7.1.0 package, Claude passed one fresh case for each new
action at each of three quality levels. Grok answered the same architecture
cases and Gemini answered the same document cases. The first installed
extraction reached the native subscription's five-hour limit. The release
record distinguishes provider access at invocation from package installation.
[Qualification and installed results](https://github.com/sumitake/agent-collab/issues/162)

## Provider and credential boundary

The route uses the provider's own installed CLI. The package does not extract
subscription credentials, reuse them in another client, or convert them into
API credentials. Authentication and CLI currency remain owned by the official
tool. The runtime preserves native results and available content separately;
the caller determines whether the response satisfies the requested action.

Native transport and lifecycle controls may be parsed, but provider prose or
structured-output shape does not establish document evidence or gate bounded
opaque-content recovery. The invocation has one owned process lifecycle and
separate cleanup evidence. There is no interactive screen-scraping completion
heuristic, credential fallback, or automatic replay.

The 7.0.5 host qualification explicitly deferred restoration of local Claude
subscription access and live Claude intent qualification. That deferral does
not enable another Claude action and is not a passed native inference check.

During the 7.0.6 follow-up, one fresh admitted document-intent attempt returned
an organization subscription-access denial. Package installation and
provider-free readiness did not establish inference access. At that release, additional Claude
profiles remained unqualified in [#162](https://github.com/sumitake/agent-collab/issues/162);
the attempt was not replayed, and no billing or credential change was made.

For 7.0.7, the supported Claude package update succeeded and every released
file matched the published artifact. Managed Claude inference remains
explicitly excepted under the operator's absence/authentication decision; no
new Claude inference qualification or existing-session reload is claimed.

For 7.0.8, the supported Claude package update again succeeded with every
released file matched. Managed Claude inference (`context.documents.intent`,
its sole admitted action) was qualified twice: during pre-publication staged
live qualification (one consumed canary against a disposable fixture,
substantive fixture-marker-correct answer, confirmed cleanup), and again on
the installed unit via a separately-run, explicitly-targeted
(`explicit_target: "claude"`) request against the installed cache
(`selected_logical_agent: claude`, `native_model_identity.model:
claude-opus-5-5`, `execution_status: ok`, confirmed cleanup, correct
fixture-marker answer). No existing-session reload is claimed, and no other
Claude action is admitted.

For 7.0.9, all 184 released files again match the supported host installation.
A fresh installed document-intent request returned the exact new fixture value
with native success, one observed attempt, zero replays, and confirmed cleanup.
Current publisher and capability metadata also passed the separate zero-model
readiness probe. The staged document-intent case passed before publication.
No additional Claude action or existing-session reload is claimed; earlier
release-specific deferrals and incomplete attempts above remain historical.

## Host and resident-primary role

Claude Code remains a fully supported host: the package installs natively,
every `/agent-collab:*` skill can be selected, and a Claude session may act as
the trusted resident primary. The primary interprets the user's objective,
authors and integrates work, adjudicates cross-family feedback, runs
verification, and owns landing decisions within operator authority.

Managed text actions carry advisory authority. When the
active primary is Anthropic-family, the
primary and repository/skill workflow must exclude same-family evidence where
an independent family is required. Conversely, when another family is primary,
Claude can provide text input to a review. Independent approval requires an
admitted governance reviewer.

## Asynchronous participation

Host-owned asynchronous coordination remains a separate, explicitly
authorized surface. Host tooling owns addressability checks; the public coordinator does
not report async readiness or send async messages. An async response keeps the authority of that
coordination channel and does not become managed runtime evidence merely
because Claude also has managed native routes.
