# agent-collab

`agent-collab` is the single dynamic-host collaboration package: the
installable half of the governed multi-agent engineering model described in
the [repository README](../../README.md) — cross-family review independence,
verifiable compliance evidence, and operator final-say, delivered as one
package for every supported host. This document is the package's technical
reference; the repository README carries the purpose and governance narrative.

Current: **4.7.0**

It resolves `primary_id`, `primary_family`, `active_model`, `host_runtime`, and
`session_identifier` from the current host or explicit configuration. On a
Claude Code host the active model is observed from the live session's own
transcript, because that host does not export it to the environment; the
observation is bounded, fails closed, and cannot reassign the host-derived
family.
ZCode model changes are re-observed before routing; OpenCode is a runtime, while the
selected model determines artifact family. The current
`opencode-go/glm-5.2` preset therefore records **Zhipu** provenance. Kimi
models record **Moonshot** provenance. Exact provider/model segments produce
lineage; conflicting family signals or incidental substrings resolve to
unknown and fail the applicable independence check.

Governance requires a complete trustworthy primary identity: current
`primary_id`, `primary_family`, `active_model`, `host_runtime`, and
`session_identifier` must all be present and mutually consistent. Explicit
configuration may fill signals the host cannot observe, but conflicting
current-session and explicit identity is a configuration error for every
route. Partial or unknown identity is allowed only for non-governance work and
always carries an independence warning.

Codex Desktop may expose a thread identifier without an active model. For an
exact lowercase-UUID thread, the policy reads one same-owner, non-writable,
non-linked rollout from the fixed Codex sessions tree with bounded no-follow
I/O, validates its session metadata, and accepts only the newest complete,
internally consistent OpenAI turn model. Ambiguous, unsafe, malformed, or
conflicting rollout evidence fails governance closed instead of inventing
model metadata.

## License

This package uses the unmodified
[PolyForm Strict License 1.0.0](LICENSE). Copyright is owned by John Osumi;
commercial use requires separate, explicit written approval administered by
Osumi Consulting LLC. Source visibility and package installation do not grant
commercial rights. See [NOTICE](NOTICE) and
[COMMERCIAL-LICENSING.md](COMMERCIAL-LICENSING.md) for the exact ownership and
approval boundary.

When the signed native runtime is activated, the archive also includes
`THIRD-PARTY-NOTICES.txt` and `third-party-licenses/` for CPython 3.13.14,
Nuitka 4.1.3 runtime material, and incorporated dependencies. Those exact files
are digest-pinned by the archive builder and remain outside policy-only
archives, which contain none of the corresponding runtime components.

Exception to the PolyForm boundary: the `decision-map`, `prototype`, and
`architecture-review` skills contain material derived from the MIT-licensed
[mattpocock/skills](https://github.com/mattpocock/skills) repository
(Copyright (c) 2026 Matt Pocock). Those portions are and remain MIT-licensed;
each derived `SKILL.md` carries the full MIT permission notice, release SPDX
evidence declares those members `MIT`, and
[docs/third-party-skill-provenance.md](../../docs/third-party-skill-provenance.md)
records the pinned upstream commit, per-file blob SHAs, and adaptations.

## Runtime and safe mode

The package may contain a privately built signed native standalone bundle only
at the platform path declared by `runtime-manifest.json`. Native manifest schema
3 and contract 3 close the bundle path, entrypoint, signed provider-runtime and
route-contract anchor, sorted member list,
per-member role/mode/size/hash/Mach-O facts, signing profile, and
domain-separated whole-bundle identity. `runtime_client.py` rejects overrides,
links, aliases, extra members, parent traversal, writable modes, wrong
platform/architecture, wrong size/hash, the wrong signing team, or failed
notarization. It inspects every member as thin arm64 Mach-O and requires exactly
one macOS `LC_BUILD_VERSION` with minimum macOS 14.0 instead of trusting those
manifest labels. The broker transport and provider protocol are both version 2.
The package
carries both `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`; both
identify this same 4.7.0 package.

Codex, Gemini, OpenCode, Grok, and Composer are broker-only contracts. Their sealed requests cross a
mode-`0600`, digest-bound per-user launchd Unix socket; launchd starts the exact
signed runtime for one request, and the broker exits after its single bounded
response. The plist has no keepalive, run-at-load, polling, interval, calendar,
or resident-process trigger. At idle, launchd retains only its job registration
and one mode-`0600` Unix listening socket; the immutable bundle consumes disk,
but there is no provider process, polling CPU, provider memory, or network
traffic. A missing or stale broker is a typed failure—these routes never fall
back to the direct entrypoint path. Only local runtime management retains fixed
direct exact-entrypoint execution.

The client preserves selector-v1 bytes and maintains a parallel selector-v2
document with independent selected, retained, candidate, and lifecycle roles.
Normal routing tries selected and then retained; candidate is never a normal
route. Exact committed schema-2/runtime-2 dispatcher-1 and historical broker-2
lanes remain viable, while schema-2/runtime-1 broker is lifecycle-only. New
candidates require schema 3, runtime 2, and dispatcher 2.
Lifecycle ping and lock-probe requests, and their successful replies, use the
closed dispatcher control protocol v1. Typed lifecycle failures remain on the
runtime protocol v2. Each response shape is validated against its own protocol,
so swapped or malformed protocol pairings fail closed.
The separate sealed provider-adoption operation also enters on the public
protocol-v2 coordinator contract and is translated to the dispatcher protocol
v1 only at the installed runtime-client boundary. Dispatcher success and typed
failure replies must use protocol v1; public protocol v2 at that internal
boundary is rejected.
Green label,
socket, state, and plist paths are derived from its signed artifact and manifest
digests; callers cannot supply them. Missing, malformed, unsafe, unproven, or
unreachable selected state leaves a proven retained lane usable through the
protocol-specific pre-consumption boundary: dispatcher 2 until authenticated
READY is accepted, and historical dispatcher 1 until a request-bearing frame
is sent. Dispatcher protocol 2 proves Darwin peer credentials, the
exact published dispatcher executable, and a request-free
nonce/deadline/lane-bound hello/ready exchange that reserves the canonical
request digest, size, and execution key. An accepted READY consumes fallback
eligibility. Its local I/O bound preserves
time for blue without shortening the original request deadline. A failure at
or after request send never retries another lane. The selector remains
legacy-blue by default;
staging green or invoking the token-gated internal `adoption_canary` operation
does not select it for normal traffic. That operation binds one exact
provider/candidate/worker/generation/route tuple and is not a public policy
route or model selector. Mutating broker lifecycle commands are unavailable from
the Codex seatbelt at both packaged entrypoints; read-only `broker-status`
remains available and reports ready only after the canonical selected lane,
immutable artifact and manifest, launchd job, socket, and a closed liveness
exchange are all proven stable.
The broker strips the Codex Desktop outer-Seatbelt marker before dispatch:
socket activation does not inherit that client sandbox, so every brokered Grok
and Composer attempt independently validates its own nested read-only sandbox.
Provider children receive closed backend-specific environment allowlists,
canonical passwd HOME for reliable authenticated state, and fresh private
temporary/cwd roots. Grok uses real serialized `~/.grok`; OpenCode keeps
private XDG roots and selected-provider auth; Codex keeps a sealed per-call
`CODEX_HOME`, SQLite, and XDG overlay. A provider-specific policy overlay may
narrow credentials or tools without replacing process HOME. Broker transport cannot invoke local `status`,
`prepare`, or `grok_login` management authority.
The runtime resolves that canonical user HOME from passwd for provider
authentication while keeping the caller checkout read-only by default. Every
request receives a private temporary workspace where the provider may clone or
copy inputs, edit, build, use tools, and reason agentically. Only explicit
provider-state paths are writable outside that workspace, in-request binary
auto-update is disabled, execution is bounded, descendants are reaped, and
temporary cleanup is positively verified. OpenCode build is sealed output-only:
its private-workspace changes are returned for trusted-primary review and
application rather than written into the caller checkout.
Canonical HOME is not a deny-all-read confidentiality boundary: providers
operate under explicit same-UID read trust so authenticated CLIs,
loaders, and tools remain reliable. The structural boundary confines writes,
execution/lifecycle, provider-state access, protected paths, and request
cleanup; provider-specific overlays may narrow reads further.

A blocked access attempt inside an established boundary is containment success,
not an invocation failure. Structural containment failure is reserved for a
boundary that cannot be established before launch or positive evidence that a
write escaped allowed paths or changed protected source/credentials.
Authentication, protocol/output, timeout, provider, teardown, and cleanup
failures remain orthogonal; `rc=0`, empty output, or stderr wording never
manufacture a containment result. Direct CLI use is not a normal reliability
fallback for a managed route.
Client disconnect propagates cancellation through every managed provider
route, reaps provider child groups, and discards partial
output. Disconnect cancellation is never retried; a deadline below the managed
setup reserve returns typed `timeout` before provider setup.
Gemini uses the managed agy backend with canonical passwd HOME, a mandatory
controlling PTY, serialized shared state, and write containment. Its separate
`governance` action emits complete artifact-bound broker proof; advisory and
long-context results are explicitly non-governance evidence. The public client
accepts exactly provider runtime `2.0.0` with governance proof contract `2`;
those proof-domain versions remain separate from public bundle manifest
contract `3`. Governance response provenance must identify that same compatible
runtime version; legacy, crossed, or mixed-provenance tuples fail closed. This
is a response-consistency check inside the broker transport trust boundary, not
a separate provenance-attestation mechanism. Its hash is not a signature: a
process able to rewrite the verified runtime, its memory, or its anonymous
stdout pipe is already inside the native-runtime trust domain and could forge
either complete schema. The client rechecks the selected executable identity
immediately before direct child launch and has no external response-ingest
path, so a runtime rewrite fails before that private pipe opens. Within this
explicit boundary, complete legacy v1 remains intentionally acceptable for
retained-lane rollback continuity; any received v2 discriminator selects only
v2. Dual-version callers use `GEMINI_GOVERNANCE_PROOF_KEYSETS`; the legacy
`GEMINI_GOVERNANCE_PROOF_KEYS` alias remains v1-only. Containment is
version-scoped by exact raw case-sensitive string: v1 admits exactly
`write_contained_shared_home` (`GEMINI_GOVERNANCE_V1_CONTAINMENTS`), while v2
admits exactly that mode or the producer's access-only
`nonwriteback_ephemeral_home` (`GEMINI_GOVERNANCE_V2_CONTAINMENTS`), and a v2
result's containment must equal the independently supplied proof containment
exactly - dual set membership without equality fails closed, as do mixed,
hybrid, unknown, or non-string values. Governance readiness recognizes either
exact mode as capability-only; readiness never authorizes execution.

This 4.5.4 source tree retains the rebuilt darwin-arm64 activation artifact
from final workspace `1.0.823` commit
`d08b6382710d6d5910d64cf011bcac873a2e1c03`. Its manifest pins the complete
standalone bundle at SHA-256
`2cea10cff2030d0238661667cf8d1b83cf9885dc6f4a03b0db4365e891b04f47`;
the bundle is Developer-ID signed and Apple-notarized under submission
`c6d29dec-5351-467d-883e-0b862734567d`. Native **Gemini
advisory/governance/long-context**, **Codex advisory/governance**,
**OpenCode plan/build**, and **Grok 4.5 read-only architecture consultation,
governance review, huge-context ingestion, and output-only code/patch
generation through the `composer/codegen` compatibility route** become
available only after the installed lifecycle has positively proven the exact
artifact, manifest, dispatcher, broker, and provider tuple. Safe mode or an
unproven host still returns typed unavailable. A host inbox is eligible only
after a current availability observation, and the public coordinator exposes
readiness only rather than a send primitive. Reinstalling a retired plugin is
never a rollback.

To enter rollback mode, set `AGENT_COLLAB_SAFE_MODE=1` in the active host
runtime environment and restart the host. Unset it and restart only after the
migration doctor and route checks pass.

Codex build (`target=codex`) remains resolvable as a distinct mutation-capable
request, but it always returns typed unavailable until a separate hardened
mutation backend is integrated. It never falls back to or widens Codex
advisory.

Each signed artifact must advertise its exact route/action contracts. The
public `coordinator.py` captures immutable primary and artifact snapshots,
applies family exclusion, and seals one route, action, and authority
combination before `runtime_client.py` will launch. The client requires the response to
return matching artifact-author model/family provenance. It cannot use an
advisory role as a worker or silently turn output-only Grok 4.5 compatibility
codegen into filesystem mutation.

For governance plus applicable review, fallback, and worker roles, the
artifact remains separate from the prompt. The sealed native document carries
exact captured bytes as base64
with SHA-256, byte size, author model, and derived author family. The client
decodes and verifies size/hash before launch; prompt duplication is neither
required nor accepted as an artifact substitute.

## Independence and authority

Governance review fails closed unless the primary identity is complete and
trustworthy and the artifact-author family is known. Non-governance delegation
with a partial or unknown primary may continue only with an independence
warning. The active primary and immutable artifact-author families are excluded
from every review panel, tiebreaker, worker selection, and fallback.

Claude and Antigravity use **async inbox** targets only. There is no synchronous
Claude route, and Claude is never invoked headlessly. The coordinator accepts
only non-governance `inbox/async` readiness with an explicit target identity and
session after `primary.async_inbox` or `AGENT_COLLAB_ASYNC_INBOX` reports the
host-owned transport available. It never sends; execute/governance inbox calls
are configuration errors. A Claude target must be Anthropic-family, an
Antigravity target must be Google-family, and a target from the current
primary's family is blocked in either direction.

Explicit `target=gemini`, `target=codex`, `target=opencode`, `target=grok`, and
`target=composer` requests are fail-closed. A target is never silently
replaced. Automatic general **advisory** routing may try only eligible
Gemini/Codex routes. Automatic architecture may also try the corresponding
sealed Grok action. Automatic governance maps Gemini and Grok to their explicit
`governance` actions while Codex retains its sealed advisory action, preserving read-only authority and
attempting each target once. Automatic worker routing is temporarily unavailable; worker
requests require an explicit managed target. Read-only, output-only, and
mutation-capable authority never promote or demote into one another.

## Central role mapping

| Request | Authority | Managed route |
|---|---|---|
| `target=gemini` review or advisory | Read-only | Gemini advisory |
| `target=gemini` governance review | Read-only | Gemini `governance` with artifact-bound broker proof |
| `target=gemini` large-corpus extraction | Read-only | Gemini long-context |
| `target=codex` second opinion, high-stakes advice, or tiebreaker | Read-only | Codex advisory |
| `target=codex` bounded implementation | Mutation-capable worker | Typed unavailable pending hardened mutation backend; no advisory fallback |
| `target=opencode` analysis or implementation plan | Read-only | OpenCode plan |
| `target=opencode` implementation | Output-only worker | OpenCode build with tools in a private temporary workspace; trusted primary applies the returned material |
| `target=grok` architecture consultation | Read-only | Grok 4.5 `architecture` action |
| `target=grok` governance review | Read-only | Grok 4.5 `governance` action |
| `target=grok` large-corpus extraction | Read-only | Grok 4.5 huge-context ingestion |
| `target=composer` constrained patch/code generation | Output-only | Grok 4.5 through the `composer/codegen` compatibility route; trusted primary applies and verifies |

Grok prose succeeds only on an explicit `EndTurn` terminal. Exact `Cancelled`
is a typed non-success with no retained assistant text; the managed broker may
retry it once only when more than ten seconds remain under the original
deadline. Grok and Composer enforce an inclusive 1,048,576-byte final UTF-8
input ceiling before authentication or spawn and return typed `input_limit`
above it.

Non-trivial Grok 4.5 compatibility codegen starts from a comprehensive architectural coding
packet: scope, invariants, authority boundaries, exact files and symbols, error
taxonomy, lifecycle, tests, and acceptance criteria. The primary architect owns
that packet, an eligible distinct-family synchronous frontier architect is the
adversarial complement, and `composer/codegen` is implementation-only. Claude and Codex
frontier primaries are the strongest default architecture seats; Grok 4.5 is
the qualified near-peer architecture/governance complement. Async inbox review
is fallback-only when no eligible synchronous complement is available.

## Skills

All skills share the same coordinator, family-exclusion policy, sealed authority
contracts, and managed runtime boundary. Availability is resolved at invocation
time; a listed skill does not imply that its native route is currently active.

| Group | Skills |
|---|---|
| Identity, routing, and readiness | `agent-readiness`, `agent-runtime-status`, `migration-doctor`, `route`, `start-inbox-monitor`, `teamwork` |
| Planning and architecture | `architect`, `brainstorm`, `compose-skills`, `intent-check`, `second-opinion` |
| Governance and assurance | `autonomy-readiness`, `code-review`, `governance-review`, `logic-check`, `qa-verify`, `red-team`, `untrusted-audit` |
| Deliberation and stakeholder lenses | `debate`, `simulate-user` |
| Delegation and implementation | `delegate`, `dev-delegate`, `worker` |
| Large-context and knowledge work | `knowledge-compile`, `long-context` |
| Reproducible workflows | `chain`, `chain-configurator`, `orchestrate` |
| Integration and conflict handling | `merge-resolve` |
| Visual guidance | `ui-to-code`, `visual-review` |
| Domain expertise - languages (pack, v4.4.0) | `rust-engineer`, `go-engineer`, `elixir-engineer`, `sql-engineer` |
| Domain expertise - infrastructure and reliability (pack, v4.4.0) | `kubernetes-specialist`, `terraform-engineer`, `sre-engineer`, `incident-responder` |
| Domain expertise - data and AI (pack, v4.4.0) | `mlops-engineer`, `llm-architect`, `postgres-engineer`, `data-engineer` |
| Domain expertise - LLM evaluation and writing quality (pack, v4.4.0) | `eval-engineer`, `prompt-regression-tester`, `hallucination-investigator`, `ai-writing-auditor` |
| Engineering process (pack, v4.7.0; MIT-derived) | `decision-map`, `prototype`, `architecture-review` |

The sixteen domain-expertise skills were authored for this repository. Their
scope selection was informed by two MIT-licensed VoltAgent reference corpora,
reviewed as untrusted input at pinned commits and fully re-authored (zero
copied passages, verified by shingle comparison): awesome-claude-code-subagents
(commit 947b44ca) and awesome-codex-subagents (commit 5605c9c1).

The three engineering-process skills are self-executed by the active primary
(no coordinator route) and are derived from the MIT-licensed
[mattpocock/skills](https://github.com/mattpocock/skills) repository at pinned
commit `2ab95809`, adapted for this package. Those portions remain
MIT-licensed; each derived `SKILL.md` carries the full MIT permission notice,
and the file-level provenance map is
[docs/third-party-skill-provenance.md](../../docs/third-party-skill-provenance.md).
`architecture-review` is the self-executed sweep; `architect` remains the
routed read-only consultation the sweep can hand its top candidates to.

`visual-review` and `ui-to-code` currently provide primary-only guidance because
the managed protocol does not accept image attachments. They never reinterpret
binary images as long-context text. Mutation-capable skills still require an
explicit compatible backend and never borrow advisory authority.

## Migration doctor

Run `/agent-collab:migration-doctor` after install/update. It uses no provider:
it inventories installed and cache-selected old packages, including enabled or
installed-disabled Codex entries under `~/.codex/config.toml`; records the
source host for each observation; resolves the current host profile; checks the
runtime manifest; proves the selected broker lane with a closed liveness
exchange; blocks routing while any retired package remains installed or active
or the executable broker path is unproven; and prints exact manager-specific
install, verify, and uninstall actions.

## Signed runtime setup

After installing an activation release, resolve this installed plugin root and
use the closed management client only:

```text
python3 "<plugin-root>/runtime_setup.py" status
python3 "<plugin-root>/runtime_setup.py" prepare
python3 "<plugin-root>/runtime_setup.py" install-broker
python3 "<plugin-root>/runtime_setup.py" broker-status
python3 "<plugin-root>/runtime_setup.py" login-grok
```

`status` is read-only, `prepare` creates only signed-runtime-managed state, and
`login-grok` starts the bounded interactive device flow. The client accepts no
provider, model, path, environment, binary, tool, or arbitrary argument
options. It verifies the same co-packaged signed artifact as normal routing,
keeps the child environment scrubbed, reports only a closed host-context enum,
and never exposes private provider recipes. Codex and OpenCode still require
their exact supported external CLIs and standard authenticated host state;
install and authenticate those through their vendor-supported interfaces.
Policy-only releases return typed `unavailable` for runtime-dependent commands.
Broker installation is explicit; import, readiness, and invocation never
install or mutate launchd state. `install-broker` publishes only the verified
manifest-listed bundle members and manifest into an immutable
artifact-plus-manifest digest directory,
atomically activates a closed plist, proves the job/socket and one-request
process exit, and retains one verified prior record. Failed updates restore the
complete prior state; same-version reactivation preserves its rollback target,
and an unverified version is never recorded as rollback-safe. `broker-status`
is read-only and emits no prompt, credential, provider output, or private path.
Before the exact selected-lane ping may prove callability, the live launchd
job's closed transcript must contain one valid top-level `properties =` line
and no `KeepAlive`, `RunAtLoad`, or structured event-trigger evidence. Any
event-trigger block is intentionally persistence-like: ambiguous lifecycle
configuration blocks readiness rather than being mislabeled socket-only.
`persistence_state` reports `nonpersistent`, `persistent`, or `unproven`; the
matching `persistent_process` value is `false`, `true`, or `null`, and an
unproven diagnostic format fails readiness closed. A separate optional
one-second quiescence observation reports `process_idle=true|false` only after
that probe runs; otherwise it is null, meaning unmeasured rather than idle.
Bounded request activity or post-request grace therefore does not masquerade
as configured persistence. Both new status observations are additive and
optional for rolling-upgrade consumers. Lifecycle mutations never use either
observation and still require their full idle proof. Bounded `launchctl`
collection failures remain typed and auditable.

Use the closed rollback/removal actions only when needed:

```text
python3 "<plugin-root>/runtime_setup.py" rollback-broker
python3 "<plugin-root>/runtime_setup.py" uninstall-broker
```

Rollback switches to the one complete prior verified record. Uninstall removes
the exact job, socket, plist, and mutable state while retaining immutable
version directories. On a machine where the broker was never installed,
uninstall is an idempotent success and rollback is typed unavailable. No
lifecycle command accepts a caller-selected path, label, socket, environment,
provider, model, or raw argument.

## Standalone invocation and local threat limit

Every routed skill resolves this installed plugin root from its own `SKILL.md`
path and sends one bounded JSON object to:

```text
python3 "<plugin-root>/coordinator.py"
```

## Coordinator request schema

The coordinator reads exactly one JSON object from stdin. Unknown fields,
non-integer protocol/timeout values, unsupported pairs, and row-shape drift are
`config_error`; provider arguments, tools, binary paths, and model overrides
outside the row contract are never accepted.

Every request contains exactly `protocol_version`, `request_id`, `operation`,
`route`, `action`, `timeout_ms`, `governance`, `primary`, and `row`.
`protocol_version` is integer `2`; `request_id` matches
`[A-Za-z0-9._:-]{1,128}`; `operation` is `readiness` or `execute`; and
`timeout_ms` is an integer from 1 through 600000 and is one end-to-end
coordinator budget. Policy resolution and every automatic candidate consume
that same monotonic deadline; a fallback receives only the remaining sealed
milliseconds. Timeout and teardown-unproven results are terminal because
accepted-request cleanup is not safe to overlap with another provider. An
`execute` request also has
`prompt`. A governance request has `prompt` plus `artifact`, exactly
`{"content":"...","author_model":"..."}`; both values must be nonblank. It may
use only a read-only governance-review contract: `gemini/governance`,
`codex/advisory`, or `grok/governance`.
An execute request for `opencode/plan`, `opencode/build`, `composer/codegen`, `codex/build`,
`auto/worker`, `auto/advisory`, `auto/architecture`, `auto/governance`, or an
applicable explicit Gemini/Codex/OpenCode/Grok review action may
optionally carry that same exact `artifact` snapshot. No other
non-governance request accepts it. The captured artifact-author family is
excluded from every applicable review, fallback, and worker selection.

A successful `execute` response must contain substantive string
`result.text`. Empty, whitespace-only, Unicode-invisible/filler-only,
replacement-glyph-only, terminal-control-only, malformed-terminal, missing,
and non-string text fail closed as `protocol_error`; provider stderr cannot
turn empty stdout into success. Exact CSI byte-class ordering and a closed
OSC/C1 matrix reject malformed control residue. A co-packaged,
content-addressed contract supplies the frozen Unicode-16 blankness table, so
host Unicode updates cannot silently change classification. The public client
enforces this independently of the signed runtime so a stale runtime cannot
manufacture a false-positive result. The canonical archive ships the contract
as `runtime_client.py`'s sibling and verifies byte identity. Direct and broker
response parsing retain the original absolute request deadline; a large
blank/control stream that consumes the remaining budget returns typed
`timeout`. `readiness`
responses keep their route-specific shape and are exempt. Typed native
failures such as `containment_error`, `timeout`, and `teardown_error` are
mapped before success validation and are never reclassified by this rule.
Automatic route selection may fall back only after a pre-acceptance
`unavailable`; an invalid-success `protocol_error` is terminal.

The coordinator captures `artifact.content` as exact UTF-8 bytes and seals it
separately from `prompt`. Its private native-protocol representation is:

```json
{
  "artifact": {
    "encoding": "base64",
    "content": "<exact bytes>",
    "sha256": "<64 lowercase hex characters>",
    "size": 123,
    "author_model": "<observed model>",
    "author_family": "<derived family>"
  }
}
```

The native runtime must base64-decode and verify `size` and `sha256`, then pass
the exact bytes to its role separately from the prompt. Artifact presence is
derived only from captured nonblank bytes, never from model metadata. A model
without nonblank content is `config_error`. Blank or unknown author-model
lineage fails governance closed; otherwise permitted non-governance use of
nonblank content continues with an independence warning.

`primary` is an object containing any subset of the string fields
`primary_id`, `primary_family`, `active_model`, `host_runtime`,
`session_identifier`, `opencode_model`, and `async_inbox`. **Send `{}` and let
the host be observed.** Supply an explicit field only when the host genuinely
cannot expose that signal, and only for that one field. Strong observed session
identity, model, family, runtime, and session identifier are authoritative.
Explicit values may fill
missing signals only; conflicting current-session and explicit identity is a
configuration error rather than an override. Complete explicit configuration
is governance-eligible only when its id, family, active-model lineage, runtime,
and session identifier are mutually consistent.

**Never invent a `session_identifier`.** A caller cannot know a session
identifier the host did not expose, so a constructed value is invented rather
than observed. Where the identifier IS observed, an invented one does not
override it: it registers as an identity conflict and turns every route into a
configuration error. If a governance route reports incomplete identity, do not
assemble an identity to satisfy it -- fix the missing observed signal, or let
the route fail closed. This does not withdraw complete explicit configuration
for a host that genuinely cannot be observed; it forbids fabricating a signal
the caller does not have.

**On a detected Claude host, identity is observation-only.** Every Claude
identity field is recorded non-empty, so none of `primary_id`,
`primary_family`, `active_model`, `host_runtime`, or `session_identifier` can be
supplied through `AGENT_COLLAB_*` or an explicit `primary`; a supplied value
that disagrees registers as a conflict rather than an override. The active model
is observed from the live session transcript, and only a resolved transcript
yields a governance-ready Claude profile. This scoping is specific to that host
and does not change the fill behavior of the other host runtimes.

Exact row contracts are:

| Contract | Exact `row` shape |
|---|---|
| `gemini/advisory` | `{"model":"google/...","effort":"low|medium|high|xhigh"}` |
| `gemini/governance` | `{"model":"google/gemini-3.1-pro","effort":"high|xhigh"}`; requires `governance=true`, a non-Google artifact snapshot, and broker proof |
| `gemini/long_context` | Gemini advisory fields plus `"documents":[{"label":"...","content":"..."}]` |
| `codex/advisory` | `{"model":"openai/...","effort":"low|medium|high|xhigh","mode":"prompt-only"}` or `mode=repo-review` plus absolute `cwd` |
| `opencode/plan` | Absolute `cwd`; optional explicitly observed `model` and `variant` |
| `opencode/build` | Absolute read-only caller `cwd`; optional explicitly observed `model` and `variant`; private temporary workspace with output-only caller authority |
| `grok/architecture` | `{"mode":"prompt-only"}` or `mode=repo-review` plus absolute `cwd` |
| `grok/governance` | Same exact row as architecture; requires `governance=true` and an artifact snapshot |
| `grok/huge_context` | `{"documents":[{"label":"...","content":"..."}]}` |
| `composer/codegen` | `{"task_class":"simple_codegen|standard_codegen|complex_codegen","effort":"low|medium|high"}` |
| `inbox/async` | `{"target_id":"claude|antigravity","target_family":"anthropic|google","target_session_identifier":"..."}`; readiness-only, non-governance, observed host transport |

The public Grok review rows do not accept caller-selected task or effort
fields. Policy seals `architecture/high`, `governance/high`, and
`huge_context/medium` after validating the public row. The compatibility
codegen route requires an explicit task class: `simple_codegen` has a low
minimum, `standard_codegen` a medium minimum, and `complex_codegen` a high
minimum. A caller may raise effort above a floor, but may not select `xhigh`,
`max`, a retired model name, or any raw model/tool/sandbox/environment field.
Both `grok/*` and `composer/codegen` require runtime provenance identifying the
same author model, `xai/grok-4.5`.

For OpenCode, a `model` field in the row is compatibility input only and never
selects a backend. Selection is recomputed for every request from the strong
live OpenCode or ZCode active-model observation, then explicit central
`primary.opencode_model`, then the fixed `opencode-go/glm-5.2` preset. Row
values are not fallbacks. The selected model must resolve to a known
non-Anthropic family, and its family supplies artifact provenance and
independence exclusion. Set
`AGENT_COLLAB_OPENCODE_PROVIDER=opencode-go` to enforce the OpenCode Go
subscription on a host. With that guard set, malformed policy values and every
model outside the exact `opencode-go/<model>` namespace fail closed both when
the policy envelope is issued and immediately before runtime launch. The guard
therefore rejects the standard metered OpenCode Zen namespace and prefix
lookalikes rather than silently switching providers.

The inbox row is exact: `target_id=claude` requires
`target_family=anthropic`, while `target_id=antigravity` requires
`target_family=google`; the target session identifier must be nonblank and
current. `primary.async_inbox` and `AGENT_COLLAB_ASYNC_INBOX` report transport
availability only and cannot supply target provenance. The coordinator never
sends an inbox message and never invokes Claude headlessly.

Automatic general advisory routing uses `route=auto`, `action=advisory`; its
`row` has exactly `gemini` and `codex` keys. Automatic architecture uses
`action=architecture` and automatic governance uses `action=governance`; those
rows have exact `gemini`, `codex`, and `grok` keys. For architecture the
coordinator maps only Grok to `architecture`; for governance it maps Gemini and
Grok to `governance` while Codex remains advisory. Generic advisory,
brainstorm, debate, QA, and fallback calls cannot select Grok. Explicit targets
never fall back.

There is no image, media-type, or binary-attachment request field. Managed
cross-family visual review and visual structural extraction are temporarily
unavailable. The `visual-review` and `ui-to-code` skills disclose that boundary
and may guide a primary-only host visual pass, but they never encode image bytes
as text documents or reconstruct a provider attachment command.

Two coordinator-only unavailable contracts are also recognized:
`codex/build` with `row={}` and `auto/worker` with `row={}`. Both return the
typed `unavailable` status, never enter the signed native manifest, and never
fall back or promote into an advisory route. Example:

```json
{
  "protocol_version": 2,
  "request_id": "review-1",
  "operation": "execute",
  "route": "codex",
  "action": "advisory",
  "timeout_ms": 30000,
  "governance": false,
  "primary": {},
  "row": {
    "model": "openai/codex",
    "effort": "high",
    "mode": "prompt-only"
  },
  "prompt": "Review this bounded artifact."
}
```

No private repository, downloader, provider CLI recipe, or backend source is
needed on a plugin-only machine. The coordinator accepts closed policy fields;
the native client accepts only its sealed envelope. The first release target is
Darwin arm64 and requires exact integer protocol versions, exact bundle
membership and identity, safe ownership/mode/link state, per-member digests and
Mach-O facts, Developer ID team, the actual numeric hardened-runtime
code-signing flag, and entrypoint notarization. Runtime stdout and stderr are bounded
during execution; an output-limit violation terminates and reaps the runtime
process group before returning typed `output_limit`. Unexpected selector or
pipe-read failures follow the same terminate-and-reap rule before returning a
typed lifecycle error.

This protects distribution integrity and narrows path substitution, but it does
not claim isolation from a malicious process already running as the same UID.
macOS has no descriptor-only Mach-O execution path here; the client rechecks
the complete bundle and entrypoint identity immediately before its fixed-path
spawn, while treating the operator account and selected plugin cache as
trusted.

The manifest cannot choose its own signer. `signing_policy.py` pins the
operator-owned Developer ID Team ID in reviewed policy source, and runtime plus
release verification require the manifest and `codesign` output to match that
anchor. The anchor is intentionally empty in this source revision because no
valid Developer ID identity is installed on the build host; native activation
and release fail closed until the operator-owned Team ID is configured.

The full old namespace mapping and clean-history public-export requirement are
documented in
[`docs/migration-from-legacy-packages.md`](https://github.com/sumitake/agent-collab/blob/main/docs/migration-from-legacy-packages.md).
