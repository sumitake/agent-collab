# agent-collab

`agent-collab` is the single dynamic-host collaboration package.

Current: **3.0.0**

It resolves `primary_id`, `primary_family`, `active_model`, `host_runtime`, and
`session_identifier` from the current host or explicit configuration. ZCode
model changes are re-observed before routing; OpenCode is a runtime, while the
selected model determines artifact family. The current `opencode/glm-5.2`
preset therefore records **Zhipu** provenance. Exact provider/model segments
produce lineage; conflicting family signals or incidental substrings resolve
to unknown and fail the applicable independence check.

Governance requires a complete trustworthy primary identity: current
`primary_id`, `primary_family`, `active_model`, `host_runtime`, and
`session_identifier` must all be present and mutually consistent. Explicit
configuration may fill signals the host cannot observe, but conflicting
current-session and explicit identity is a configuration error for every
route. Partial or unknown identity is allowed only for non-governance work and
always carries an independence warning.

## Runtime and safe mode

The package may contain a privately built signed native runtime only at the
platform path declared by `runtime-manifest.json`. `runtime_client.py` rejects
overrides, symlinks, parent traversal, wrong platform/architecture, wrong
size/hash, and on macOS the wrong signing team or failed notarization. It
inspects the executable as a thin arm64 Mach-O and requires exactly one macOS
`LC_BUILD_VERSION` with minimum macOS 14.0 instead of trusting those manifest
labels. It uses a fixed JSON protocol and scrubbed environment. The package
carries both `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`; both
identify this same 3.0.0 package.

No signed artifact is present in this source tree yet. Native **Gemini
advisory/long-context**, **Codex advisory**, **OpenCode plan/build**, **Grok 4.5
read-only architecture consultation, governance review, and huge-context
ingestion**, and **Composer output-only code/patch generation**
roles are therefore **temporarily unavailable**. Policy-only safe mode keeps
all native model routes unavailable. A host inbox is eligible only after a
current availability observation, and the public coordinator exposes readiness
only rather than a send primitive.
This package may still be distributed as a policy-only release: its manifest
has no artifact rows, its archive has no runtime executable, and invocation
continues to return typed unavailable until an activation release is verified.
Reinstalling a retired plugin is never a rollback.

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
advisory role as a worker or silently turn output-only Composer generation into
filesystem mutation.

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
Gemini/Codex routes. Automatic architecture and governance actions may also
try the corresponding sealed Grok action, preserving read-only authority and
attempting each target once. Automatic worker routing is temporarily unavailable; worker
requests require an explicit managed target. Read-only, output-only, and
mutation-capable authority never promote or demote into one another.

## Central role mapping

| Request | Authority | Managed route |
|---|---|---|
| `target=gemini` review or advisory | Read-only | Gemini advisory |
| `target=gemini` large-corpus extraction | Read-only | Gemini long-context |
| `target=codex` second opinion, high-stakes advice, or tiebreaker | Read-only | Codex advisory |
| `target=codex` bounded implementation | Mutation-capable worker | Typed unavailable pending hardened mutation backend; no advisory fallback |
| `target=opencode` analysis or implementation plan | Read-only | OpenCode plan |
| `target=opencode` implementation | Mutation-capable worker | OpenCode build with exact workspace-write authority |
| `target=grok` architecture consultation | Read-only | Grok 4.5 `architecture` action |
| `target=grok` governance review | Read-only | Grok 4.5 `governance` action |
| `target=grok` large-corpus extraction | Read-only | Grok 4.5 huge-context ingestion |
| `target=composer` constrained patch/code generation | Output-only | Composer output-only code/patch generation; trusted primary applies and verifies |

## Skills

All skills share the same coordinator, family-exclusion policy, sealed authority
contracts, and managed runtime boundary. Availability is resolved at invocation
time; a listed skill does not imply that its native route is currently active.

| Group | Skills |
|---|---|
| Identity, routing, and readiness | `agent-readiness`, `agent-runtime-status`, `migration-doctor`, `route`, `teamwork` |
| Planning and architecture | `architect`, `brainstorm`, `compose-skills`, `intent-check`, `second-opinion` |
| Governance and assurance | `autonomy-readiness`, `code-review`, `governance-review`, `logic-check`, `qa-verify`, `red-team`, `untrusted-audit` |
| Deliberation and stakeholder lenses | `debate`, `simulate-user` |
| Delegation and implementation | `delegate`, `dev-delegate`, `worker` |
| Large-context and knowledge work | `knowledge-compile`, `long-context` |
| Reproducible workflows | `chain`, `chain-configurator`, `orchestrate` |
| Integration and conflict handling | `ai-merge-resolve` |
| Visual guidance | `ui-to-code`, `visual-review` |

`visual-review` and `ui-to-code` currently provide primary-only guidance because
the managed protocol does not accept image attachments. They never reinterpret
binary images as long-context text. Mutation-capable skills still require an
explicit compatible backend and never borrow advisory authority.

## Migration doctor

Run `/agent-collab:migration-doctor` after install/update. It uses no provider:
it inventories installed and cache-selected old packages, including enabled or
installed-disabled Codex entries under `~/.codex/config.toml`; records the
source host for each observation; resolves the current host profile; checks the
runtime manifest; blocks routing while any retired package remains installed or
active; and prints exact manager-specific install, verify, and uninstall
actions.

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
`protocol_version` is integer `1`; `request_id` matches
`[A-Za-z0-9._:-]{1,128}`; `operation` is `readiness` or `execute`; and
`timeout_ms` is an integer from 1 through 600000. An `execute` request also has
`prompt`. A governance request has `prompt` plus `artifact`, exactly
`{"content":"...","author_model":"..."}`; both values must be nonblank. It may
use only a read-only governance-review contract: `gemini/advisory`,
`codex/advisory`, or `grok/governance`.
An execute request for `opencode/build`, `composer/codegen`, `codex/build`,
`auto/worker`, `auto/advisory`, `auto/architecture`, `auto/governance`, or an
applicable explicit Gemini/Codex/Grok review action may
optionally carry that same exact `artifact` snapshot. No other
non-governance request accepts it. The captured artifact-author family is
excluded from every applicable review, fallback, and worker selection.

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
`session_identifier`, `opencode_model`, and `async_inbox`. Use `{}` for host
observation; use explicit fields only when the host cannot expose strong
current-session signals. Strong observed session identity, model, family,
runtime, and session identifier are authoritative. Explicit values may fill
missing signals only; conflicting current-session and explicit identity is a
configuration error rather than an override. Complete explicit configuration
is governance-eligible only when its id, family, active-model lineage, runtime,
and session identifier are mutually consistent.

Exact row contracts are:

| Contract | Exact `row` shape |
|---|---|
| `gemini/advisory` | `{"model":"google/...","effort":"low|medium|high|xhigh"}` |
| `gemini/long_context` | Gemini advisory fields plus `"documents":[{"label":"...","content":"..."}]` |
| `codex/advisory` | `{"model":"openai/...","effort":"low|medium|high|xhigh","mode":"prompt-only"}` or `mode=repo-review` plus absolute `cwd` |
| `opencode/plan` | Absolute `cwd`; optional explicitly observed `model` and `variant` |
| `opencode/build` | Absolute `cwd`; optional explicitly observed `model` and `variant`; mutation-capable workspace authority |
| `grok/architecture` | `{"mode":"prompt-only"}` or `mode=repo-review` plus absolute `cwd` |
| `grok/governance` | Same exact row as architecture; requires `governance=true` and an artifact snapshot |
| `grok/huge_context` | `{"documents":[{"label":"...","content":"..."}]}` |
| `composer/codegen` | `{}` |
| `inbox/async` | `{"target_id":"claude|antigravity","target_family":"anthropic|google","target_session_identifier":"..."}`; readiness-only, non-governance, observed host transport |

The inbox row is exact: `target_id=claude` requires
`target_family=anthropic`, while `target_id=antigravity` requires
`target_family=google`; the target session identifier must be nonblank and
current. `primary.async_inbox` and `AGENT_COLLAB_ASYNC_INBOX` report transport
availability only and cannot supply target provenance. The coordinator never
sends an inbox message and never invokes Claude headlessly.

Automatic general advisory routing uses `route=auto`, `action=advisory`; its
`row` has exactly `gemini` and `codex` keys. Automatic architecture uses
`action=architecture` and automatic governance uses `action=governance`; those
rows have exact `gemini`, `codex`, and `grok` keys. The coordinator maps only
the Grok leg to its sealed architecture/governance action. Generic advisory,
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
  "protocol_version": 1,
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
Darwin arm64 and requires exact integer protocol versions, safe ownership/mode/
link state, digest, Developer ID team, the actual numeric hardened-runtime
code-signing flag, and notarization. Runtime stdout and stderr are bounded
during execution; an output-limit violation terminates and reaps the runtime
process group before returning typed `output_limit`. Unexpected selector or
pipe-read failures follow the same terminate-and-reap rule before returning a
typed lifecycle error.

This protects distribution integrity and narrows path substitution, but it does
not claim isolation from a malicious process already running as the same UID.
macOS has no descriptor-only Mach-O execution path here; the client rechecks
file identity immediately before its fixed-path spawn, while treating the
operator account and selected plugin cache as trusted.

The manifest cannot choose its own signer. `signing_policy.py` pins the
operator-owned Developer ID Team ID in reviewed policy source, and runtime plus
release verification require the manifest and `codesign` output to match that
anchor. The anchor is intentionally empty in this source revision because no
valid Developer ID identity is installed on the build host; native activation
and release fail closed until the operator-owned Team ID is configured.

The full old namespace mapping and clean-history public-export requirement are
documented in
[`docs/migration-from-legacy-packages.md`](https://github.com/sumitake/agent-collab-plugin/blob/main/docs/migration-from-legacy-packages.md).
