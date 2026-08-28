# Status and evidence

< [Architecture handbook index](README.md)

This page prevents five different facts from being collapsed into one word:
repository version, signed tag, GitHub release, installed package, and active
runtime. Each has a different evidence source.

## Evidence planes

| Plane | What it can prove | What it cannot prove |
| --- | --- | --- |
| Repository source | Current files, manifests, generated skills, tests, and repository-only artifacts at a named commit. | That a package was published, installed, selected, or usable on a host. |
| Signed tag | A signed annotated reference and the exact commit it identifies. | That a GitHub release exists, its assets are correct, or a host installed it. |
| GitHub release | Published release metadata and attached evidence for one tag. | That every marketplace or host has updated, or that a route is ready. |
| Package installation | The package/version selected by one host's plugin manager. | That a native route passed readiness or that another host has the same version. |
| Runtime readiness | Provider-free evidence that the selected package and managed boundary are callable for the reported contracts. | A guarantee that provider authentication, quota, or a future request will succeed. |
| Invocation result | The typed outcome of one bounded request. | General availability, permission to retry with wider authority, or merge approval. |

## Current snapshot — v7.0.0

The public [`v7.0.0` release](https://github.com/sumitake/agent-collab/releases/tag/v7.0.0)
is published and its release evidence is verified. This is a dated snapshot:
the release is current, while installation and readiness remain host-specific
evidence planes.

| Observation | Status | Interpretation |
| --- | --- | --- |
| The signed annotated v7.0.0 tag object `e9bdba19191a8b48571d13517faae96a99e4a872` identifies public commit `fb4723c696663efd9c725be8f62c521a720aa15e`; exact-tag workflow run `33152601182` succeeded and GitHub Release `378330262` was published on 2026-08-28 UTC. | published | The immutable release commit contains package 7.0.0 and provider runtime **5.0.0**. |
| The release contains `agent-collab.v7.0.0.plugin`, its checksum, and `agent-collab-v7.0.0.spdx.json`, with GitHub SHA-256 digests `eb1b2aa3eb8fa916bc6ae4e422127c15cc8da81c1a31c202f9bbeffc2c3aa9ac`, `4a82fc421d701d64bb522466cab5b3624d6fe298c410240a8f25f9052ca92381`, and `0401776c60951ee1c508bf94522bf7493c322149e51327b993bc5b00dc3286f1`. | verified release evidence | The published asset set is fixed and independently digest-addressed. |
| The package manifest SHA-256 is `2bf858764510fddfa86f491f677ad1a80d05b854a33d77a9a3230d0cb399fddf`; it binds wire digest `9ec0c1d0c943a9ba9025dbb554847abea45d5c2dcac893a69ac09539d265a85f` and arm64/x86_64 bundle digests `00d6647f161bc66069fd8f2091791585693e9a350c2e678b8ff09634a167d2b3` / `b4bb0ddca2f5cf5ca59ebf2c6d31e9a77de8468e38b06c2b6e2cf66d6b1eeef3`. | verified release evidence | Manifest schema 4, runtime protocol 4, native contract 4, and wire schema 8 bind both supported Darwin architectures to one public contract. |
| The released descriptor and public contract tests agree on 12 logical actions, 15 transport actions, and 19 valid action/source pairs. | verified release evidence | The exact-head repository binding, typed failure/recovery contract, TTY rejection, request-private Grok state, narrow read-only Claude document-intent route, and removal of automatic failure-evidence capture are part of the v7 public contract. |
| One post-restart Codex installation reports the v7.0.0 package, matches all 170 published archive members, and returns provider-free readiness `ok` for all 12 logical actions with zero model calls. | verified host installation | This proves one host's post-restart package bytes and readiness boundary only. It does not establish all-host installation, semantic-canary success, provider authentication, or future provider availability. |

### v7.0.0 closeout determinations

| Surface | Determination | Evidence basis |
| --- | --- | --- |
| Root `README.md` | **updated** | Current-source and publication language now identifies v7.0.0 and bounds installation evidence to the observed Codex installation. |
| `plugins/agent-collab/README.md` | **updated** | The package reference matches runtime 5.0.0, protocol/native contract 4, wire schema 8, and 12/15/19 cardinalities. |
| Public architecture handbook | **updated** | Current-status, lifecycle, authority, project-estimation, and release-closeout pages were reconciled against the immutable tag, manifest, assets, and public contract tests. |
| Generated `CHANGELOG.md` | **verified current** | The immutable v7.0.0 release entry was compiled by the release flow; this post-tag clarification uses a new fragment and does not rewrite generated release history. |

## v6.2.4 release closeout snapshot

The following public and host evidence was reconciled on 2026-08-25. It is a
dated snapshot, not a permanent “latest version” badge.

| Observation | Status | Interpretation |
| --- | --- | --- |
| The locally and GitHub-verified signed annotated [`v6.2.4` tag](https://github.com/sumitake/agent-collab/releases/tag/v6.2.4) identifies public commit `282b1c88abf0cc4613b99d93d69b5def2cee6d8f`. | published | The immutable source contains package 6.2.4 and provider runtime **4.2.1**, built from signed workspace source `6d30aab274f6f977a0e8eed01c734c027743cd93` for macOS arm64 and x86_64. Runtime protocol 4, native contract 4, and wire schema 7 remain unchanged; the wire digest is `774067d0a2a640b2eac27cace99f6cf812649169e03aab2ec8fcf77a2c3fe2a9`. |
| The exact-tag [`Build release archive` run](https://github.com/sumitake/agent-collab/actions/runs/32916415411) completed successfully and the release is published, non-draft, and non-prerelease. | published | The release cutter verified clean freshly fetched `main`, the signed tag target, deterministic archive/evidence, both Developer ID hardened/timestamped/notarized runtime bundles, the exact workflow, and the downloaded public assets before returning success. |
| The release contains exactly `agent-collab.v6.2.4.plugin`, `agent-collab.v6.2.4.plugin.sha256`, and `agent-collab-v6.2.4.spdx.json`. Their SHA-256 values are `4eb2de1726497f4818d311c9c261aaa1bfa7054edc0b2f97bc1ccca759bb5b98`, `29295738c19015c9037e518354c04900aff3a61e21362c32bfb32790f75d8edf`, and `6c49d13d6a39db4f207cea7b0f8c41cb9fe0c102be2eb64c38d2d4a992c7281c`. | verified release evidence | The downloaded archive matched its checksum and GitHub digest; the SBOM matched its GitHub digest. The extracted manifest SHA-256 is `688ae21fa5fd60412def402fd30c1a56a6807435114bd92537f60c89c05138ca`; its arm64 and x86_64 bundle digests are `556f89a5dc77453fa4f7d96b2def716bc6613eb3afa783ed16fb48668a15f155` and `ad6e276846ea8af2fb6de9ea28ab5413768698900ecf4d51847da180585fc991`. |
| Claude, Codex, Antigravity, and Grok each report or resolve package version 6.2.4 through their supported host plugin state. All 170 released members matched every host-resolved package root byte-for-byte; only manager/runtime-generated extra files were outside that comparison. | verified host installation | Claude and Codex report the package enabled; Antigravity's imported manifest reports 6.2.4; Grok's pinned registry binds `v6.2.4` and commit `282b1c88…`. Installation evidence is host-specific and does not by itself prove a future provider call. |
| Provider-free readiness executed from all four host-resolved roots and returned top-level `ok`, 12 logical actions, 62 of 62 candidates ready, manifest `688ae21f…`, wire `774067d0…`, and zero model calls. The same installed coordinator returned `ok` under an explicitly observed x86_64 Rosetta process. | verified loaded runtime bytes | The native arm64 bundle selected and executed independently from every installed tree; the co-packaged x86_64 bundle also loaded and resolved the same signed manifest. The current Codex CLI 0.149.1 executable remained admitted automatically without a governance or functionality downgrade. |
| Pre-publication qualification completed one arm64 Gemini and one arm64 Grok invocation, plus one signed x86_64 Grok Rosetta invocation. | release qualified | The bounded attempts returned content-correct results with one provider process/invocation and cleanup confirmed; the repaired Gemini repository route did not encounter the prior Git-tool denial, and the supervised Grok route did not reproduce the cancellation failure. They were not replayed after installation and do not promise future provider availability. |
| Claude 2.1.246 passed exact-executable, routing, manifest, and loaded-byte qualification for its sole `context.documents.intent` route. Its one inference canary returned typed `provider_error` with no artifact because the CLI is intentionally unauthenticated on this host. | environmental `UNAVAILABLE`; operator-waived | Per the explicit operator waiver, the missing local authentication is non-blocking release-environment evidence, not a runtime regression. The request was not retried, Claude was not re-authenticated, and no coordinator/runtime check was weakened. Provider-free readiness later confirmed the configured native route with zero model calls. |
| Publication closes the PTY canonical-buffer failure tracked in [#148](https://github.com/sumitake/agent-collab/issues/148). | released fix | The shipped coordinator also restores terminal state before default termination signals and preserves typed incomplete-frame results when restoration is impossible. Review-route reliability [#144](https://github.com/sumitake/agent-collab/issues/144), repeatable Intel evidence-extraction documentation [#157](https://github.com/sumitake/agent-collab/issues/157), public-governance protocol wording [#169](https://github.com/sumitake/agent-collab/issues/169), and the separately governed atomic dual-architecture staging runbook clarification remain explicit follow-ups. |
| The generated `CHANGELOG.md` contains the compiled 6.2.4 coordinator/runtime entry and the prior 6.2.3 documentation closeout. | verified current | Generated release history agrees with the signed tag and published assets; this post-release closeout leaves generated history and the immutable tag unchanged. |

### v6.2.4 closeout determinations

| Surface | Determination | Evidence |
| --- | --- | --- |
| `docs/architecture/` | **updated current** | This snapshot records the exact tag, workflow, assets, runtime identities, four-host installation/readiness, dual-architecture execution, bounded provider qualification, the Claude environmental waiver, and explicit residuals. Project-estimation status identifies the refreshed receipt-bound 6.2.4 evidence while retaining v6.2.0 as its historical introduction. |
| Root `README.md` | **updated** | Pre-publication language was replaced with the verified v6.2.4 publication and observed four-host package state. |
| `plugins/agent-collab/README.md` | **updated** | The package reference identifies 6.2.4 as both current source and current published release while keeping installation, readiness, and provider availability separate. |
| Lifecycle/runbook | **verified current** | Host-specific install/update commands, fresh-session guidance, provider-free doctor/readiness checks, build-time CLI qualification, and fail-closed notarization preflight remain executor-neutral and correct for this release. |
| Generated `CHANGELOG.md` | **verified current** | The release flow compiled the 6.2.4 entry; this post-release closeout leaves generated history and signed tags unchanged. |

## Historical v6.2.3 release closeout snapshot

The following public and host evidence was reconciled on 2026-08-25. It is a
dated snapshot, not a permanent “latest version” badge.

| Observation | Status | Interpretation |
| --- | --- | --- |
| The verified signed annotated [`v6.2.3` tag](https://github.com/sumitake/agent-collab/releases/tag/v6.2.3) identifies public commit `bbbfa8c989e9c8b01c33e0f636891c474e9443a1`. | published | The immutable source contains package 6.2.3 and signed/notarized provider runtime **4.2.1** for macOS arm64 and x86_64. Runtime protocol 4, native contract 4, and wire schema 7 remain unchanged; the wire digest is `0c2cba3ab79f0217b1ae4de83ec9723412e46809b98b4f11f8997a8599125a51`. |
| The exact-tag [`release.yml` run](https://github.com/sumitake/agent-collab/actions/runs/32802795398) completed successfully and the release is published, non-draft, and non-prerelease. | published | The release cutter verified clean latest `main`, the signed tag target, deterministic archive/evidence, both Developer ID hardened/timestamped/notarized runtime bundles, the exact workflow, and the downloaded public assets before returning success. |
| The release contains exactly `agent-collab.v6.2.3.plugin`, `agent-collab.v6.2.3.plugin.sha256`, and `agent-collab-v6.2.3.spdx.json`. Their SHA-256 values are `9b8263f9b889f0beedc4ccba62d20a25eded095ec932797c0bdc5928cb4381a8`, `c8b91a17515717fbc825003da97dbb4aafa1a1df28c891b10dbe41af29b42c67`, and `4fb7621d390aaef6501131333551a3ad51d3f966b298232c315763b77f5b9352`. | verified release evidence | The downloaded archive matched its checksum and GitHub digest; the SBOM matched its GitHub digest. The extracted manifest SHA-256 is `a50f9c82aca2af54d764e03a5f00f7c38cd139249146a2edade97d602bf44964`; its arm64 and x86_64 bundle digests are `023679b0a590a88b2e8eb80c6fe180a61793a37ad09ea75ef62b915697d5250c` and `54f1badd1f60466f2039b568e8cd51b293c71fbfdc576d93fb46531917fa8b72`. |
| Claude, Codex, Antigravity, and Grok each report or resolve package version 6.2.3 through their supported host plugin state. All 170 released members matched every host-resolved root byte-for-byte; only host-generated extra files were outside that comparison. | verified host installation | Claude and Codex report the package enabled; Antigravity's imported Claude and Codex manifests report 6.2.3; Grok's pinned registry binds `v6.2.3` and commit `bbbfa8c…`. Installation evidence is host-specific and does not by itself prove a future provider call. |
| Provider-free readiness executed from all four host-resolved roots and returned top-level `ok`, 12 logical actions, 61 of 61 candidates ready, manifest `a50f9c82…`, wire `0c2cba3a…`, cleanup confirmed, and zero model calls. | verified loaded runtime bytes | The native arm64 bundle selected and executed from each installed tree. The active Codex CLI 0.149.1 executable (`f0d8762236594359b60cfbe17f4c7e945a3ce8d1c91e74778838c968d250fb6c`) was admitted automatically under both released compatibility profiles; normal CLI currency imposed no governance or functionality downgrade. |
| Pre-publication qualification completed one Gemini repository read through the permission-capable route and one signed x86_64 Grok Rosetta canary through the supervised ACP route. | release qualified | Both attempts returned grounded artifacts with cleanup confirmed: the Gemini path did not hit the earlier `git rev-parse` denial, and the Grok path did not cancel. These bounded canaries were not replayed after installation and do not promise future provider availability. |
| Release publication closed [#154](https://github.com/sumitake/agent-collab/issues/154), [#155](https://github.com/sumitake/agent-collab/issues/155), [#156](https://github.com/sumitake/agent-collab/issues/156), and [#158](https://github.com/sumitake/agent-collab/issues/158). | released fixes | The broader coordinator-line PTY limit [#148](https://github.com/sumitake/agent-collab/issues/148) and repeatable Intel evidence-extraction documentation [#157](https://github.com/sumitake/agent-collab/issues/157) remain explicit follow-ups; neither was silently folded into this release. |
| The generated `CHANGELOG.md` contains the compiled 6.2.3 coordinator/runtime and maintenance entries. | verified current | Generated release history agrees with the signed tag and published assets; this post-release closeout leaves generated history and the immutable tag unchanged. |

### v6.2.3 closeout determinations

| Surface | Determination | Evidence |
| --- | --- | --- |
| `docs/architecture/` | **updated current** | This snapshot records the exact tag, workflow, assets, runtime identities, four-host installation/readiness, bounded Gemini/Grok qualification, and explicit residuals. Project-estimation status identifies the refreshed receipt-bound 6.2.3 evidence while retaining v6.2.0 as its historical introduction. |
| Root `README.md` | **updated** | Release-candidate and pending-activation language was replaced with the verified v6.2.3 publication and observed four-host readiness state. |
| `plugins/agent-collab/README.md` | **updated** | The package reference identifies 6.2.3 as both current source and current published release without collapsing installation into publication. |
| Lifecycle/runbook | **updated** | Provider CLI refresh is build-time and automatic for the published profile; a normal covered vendor auto-update is not treated as a governance or functionality downgrade. Host-specific update and verification commands remain executor-neutral. |
| Generated `CHANGELOG.md` | **verified current** | The release flow compiled the 6.2.3 entry; this post-release closeout leaves generated history and signed tags unchanged. |

## Historical v6.2.2 release closeout snapshot

The following public and host evidence was reconciled on 2026-08-24. It is a
dated snapshot, not a permanent “latest version” badge.

| Observation | Status | Interpretation |
| --- | --- | --- |
| The verified signed annotated [`v6.2.2` tag](https://github.com/sumitake/agent-collab/releases/tag/v6.2.2) identifies public commit `abe24eefe42734187ae781c5b83b7b36f8f634b8`. | published | The immutable source contains package 6.2.2 and signed/notarized provider runtime **4.2.0** for macOS arm64 and x86_64, imported from runtime source `6e4a9b84`. Runtime protocol 4 remains unchanged; wire schema advances 6 → 7 with digest `0c2cba3a…`. The immutable `v6.2.1` tag remains unchanged and has no GitHub Release. |
| The exact-tag [`release.yml` run](https://github.com/sumitake/agent-collab/actions/runs/32756279670) completed successfully and the release is published, non-draft, and non-prerelease. | published | The clean macOS job verified both Developer ID, hardened, timestamped, notarized bundles. The Ubuntu publication job provisioned pinned `uv`, validated the Draft 2020-12 manifest schema, rebound the commit-specific runtime evidence, and reran the required suites before publication. |
| The release contains exactly `agent-collab.v6.2.2.plugin`, `agent-collab.v6.2.2.plugin.sha256`, and `agent-collab-v6.2.2.spdx.json`. Their SHA-256 values are `d2d69e35ae1641ca04d3d8db2f17c6ef581722de952281496baba54bef11ca7e`, `4652e9daff37e43cbec29eb3bb5e3d75de8c4dffc46ea50d967c62b0f95bf590`, and `44b504cdf9b94c0b47ea2032f5bd0d23c67231e9422f8339cedd93169cb9f396`. | verified release evidence | The downloaded archive matched its checksum and GitHub digest; the SBOM matched its GitHub digest. The extracted manifest SHA-256 is `63f3fc257df1665912ad992d1abe0e470ff06d0013422d25a6d40fb3dc16a8b6`; its arm64 and x86_64 bundle digests are `e4fa16b1…` and `d6fba3e4…`. |
| Claude, Codex, Antigravity, and Grok each report or resolve package version 6.2.2 through their supported host plugin state. Every released archive member matched the corresponding host-resolved root; only host-generated cache/import metadata was excluded. | verified host installation | Claude and Codex report the package enabled; Antigravity's imported manifest reports 6.2.2; Grok's pinned registry binds `v6.2.2` and commit `abe24eef…`. Installation evidence is host-specific and does not by itself prove a future provider call. |
| Provider-free readiness executed from all four host-resolved roots and returned top-level `ok`, 12 logical actions, manifest `63f3fc25…`, wire `0c2cba3a…`, and cleanup confirmed for every candidate. | verified loaded runtime bytes | The native arm64 bundle selected and executed from each installed tree. Locally unqualified Codex candidates remained typed unavailable/temporarily unavailable while the overall snapshot retained valid routes; no model call or false provider-outage claim was introduced. |
| One newline-terminated invocation completed while its PTY remained open. The intentionally underspecified request returned `fix_request`, named only the missing `effort_class`, started no provider, and said not to retry unchanged. | verified invocation recovery | This directly exercises bounded interactive framing and actionable missing-criteria behavior from the installed 6.2.2 coordinator. It is not a governance review or provider-quality canary. |
| The generated `CHANGELOG.md` contains both the unpublished-tag 6.2.1 coordinator/runtime entries and the 6.2.2 clean-runner recovery entry. | verified current | Generated history truthfully preserves the failed immutable 6.2.1 tag while the published 6.2.2 release carries those prepared coordinator/runtime bytes plus the release-runner correction. |

### v6.2.2 closeout determinations

| Surface | Determination | Evidence |
| --- | --- | --- |
| `docs/architecture/` | **updated current** | This snapshot records the exact tag, run, assets, four-host installation/readiness, and invocation-recovery canary. Project-estimation status now identifies the receipt-bound 6.2.2 evidence while retaining v6.2.0 as its historical introduction. |
| Root `README.md` | **updated** | The pre-release/source-only language and v6.2.0 current-release link were replaced with the verified v6.2.2 publication and four-host readiness state. |
| `plugins/agent-collab/README.md` | **updated** | The package reference now identifies 6.2.2 as both current source and current published release without collapsing installation into publication. |
| Lifecycle/runbook | **updated** | The update guide records Antigravity import verification, safe pinned-tag replacement for Grok, and the fail-closed trust-service requirement for local notarization preflight. |
| Generated `CHANGELOG.md` | **verified current** | The release flow compiled the 6.2.1 and 6.2.2 entries; this post-release closeout leaves generated history and signed tags unchanged. |

## Historical v6.2.0 release closeout snapshot

The following public and host evidence was reconciled on 2026-08-22. It is a
dated snapshot, not a permanent “latest version” badge.

| Observation | Status | Interpretation |
| --- | --- | --- |
| The signed annotated [`v6.2.0` tag](https://github.com/sumitake/agent-collab/releases/tag/v6.2.0) identifies public commit `dcb161a08ac50aa4071c28f5ca72d0c13188b85a`. | published | The immutable source contains package version 6.2.0 and the provider runtime **4.1.0** dual-architecture bundle set (macOS arm64 and macOS x86_64), built from workspace source commit `29c41184`. This is a governance-pool-widening generation: the runtime adds `opencode/governance.repository` and lowest-priority governance edges for `zhipu`/`moonshot`/`alibaba`/`deepseek` (read-only; the Phase-1 governance-verdict gate is unchanged), advancing the wire-contract descriptor digest `4de687b8… → e601a455…` as a compatible evolution (protocol 4 unchanged). It also carries the coordinator fault-tolerance client changes and the `project-estimation` skill. |
| The exact-tag [`release.yml` run](https://github.com/sumitake/agent-collab/actions/runs/32602984579) completed successfully and the release is published, non-draft, and non-prerelease. | published | The signed tag and GitHub Release planes agree; neither repository state nor tag existence alone was used as publication proof. |
| The release contains exactly `agent-collab.v6.2.0.plugin`, `agent-collab.v6.2.0.plugin.sha256`, and `agent-collab-v6.2.0.spdx.json`. Their SHA-256 values are `4f0c7687c8f7d1944b1eefbf250575d2868cb62e45c1847bb7e813b52c365f37`, `5469fe9611e4bc1b0552ed4dbdb7fc178f4089ace0ae4ca06581a5097709cb41`, and `211a7f296e177f5cd4315d7276c8a6a35e4653646b2f882d2e85578958e9caf7`. | verified release evidence | The archive, checksum, and SPDX assets were verified against the exact release object by `cut_release.py`. This does not by itself prove installation on a host. |
| All four primary hosts (Claude, Codex, Antigravity, Grok) installed 6.2.0 through their supported plugin CLIs; each installed tree matched the released `agent-collab.v6.2.0.plugin` bytes (0 diffs, excluding host-generated files), and each host returned readiness `ok` (wire `e601a455…`) plus a consumed, content-correct post-install canary. | verified host activation | Byte-exact installation and executed post-install qualification on every primary host. Rollback snapshots of the prior 4.0.6 trees were captured before install; no rollback was needed. |
| The generated `CHANGELOG.md` contains the compiled v6.2.0 entry, including the runtime 4.1.0 wire-contract disclosure (`4de687b8… → e601a455…`, +1 transport / +1 source pair) and the coordinator and project-estimation entries. | verified current | Generated release history agrees with the tag and package bytes; this closeout does not rewrite generated history or a signed release. |
| The Tier-3 distribution PR was merged via the operator-required admin-merge escape for the transition-window receipt-deadlock. | recorded | The routing-policy digest advanced with the runtime, so receipts from the still-installed 4.0.6 runtime could not bind the post-change tree; a grounded distinct-family governance receipt was structurally unobtainable until the new runtime was installed. The escape and the attempted governance leg are recorded in the PR compliance trace. |

### v6.2.0 closeout determinations

| Surface | Determination | Evidence |
| --- | --- | --- |
| `docs/architecture/` | **updated current** | This status snapshot records the v6.2.0 release, the dual-architecture runtime 4.1.0, the governance-pool widening, and four-host activation; the remaining handbook pages describe the direct-runtime lifecycle and boundaries in architecture-neutral terms unchanged by this release. |
| Root `README.md` | **updated** | The current-source paragraph and the project-estimation what's-new note were updated in this closeout to state that v6.2.0 is published and activated on all four hosts (removing the pre-release "not yet tagged/released/installed" language); the runtime 4.1.0 / governance-widening narrative was set in the distribution PR. |
| `plugins/agent-collab/README.md` | **updated** | The `Current:` line and the version-6.2.0 note were updated in this closeout to state the published + activated status and the runtime 4.1.0 advance (removing the "source only; not tagged/released/installed" language); the runtime facts were set in the distribution PR. |
| Generated `CHANGELOG.md` | **verified current** | The release flow compiled the v6.2.0 entry; this post-release closeout leaves generated history unchanged. |

## Historical v6.1.1 release closeout snapshot

The following public and host evidence was reconciled on 2026-08-19. It is a
dated snapshot, not a permanent “latest version” badge.

| Observation | Status | Interpretation |
| --- | --- | --- |
| The signed annotated [`v6.1.1` tag](https://github.com/sumitake/agent-collab/releases/tag/v6.1.1) identifies public commit `816a8b2863ec2475f52014fd0f4d611f2523da39`. | published | The immutable source contains package version 6.1.1 and the provider runtime 4.0.6 bundle set. This is the first release shipping **two per-architecture runtime artifacts** — macOS arm64 and macOS x86_64 — built from the same workspace source commit; the client selects by host at resolution time. It is also the first tagged release carrying the previously merged v6.1.0 skills content (`project-knowledge`, `learning-loop`). |
| The exact-tag [`release.yml` run](https://github.com/sumitake/agent-collab/actions/runs/32306427126) completed successfully and the release is published, non-draft, and non-prerelease. | published | The signed tag and GitHub Release planes agree; neither repository state nor tag existence alone was used as publication proof. |
| The release contains exactly `agent-collab.v6.1.1.plugin`, `agent-collab.v6.1.1.plugin.sha256`, and `agent-collab-v6.1.1.spdx.json`. Their SHA-256 values are `2bec0c7f213e84616517756fa25b6b41442dd8115c6e8294ff0f6ebf3909e822`, `b7f5ea766fcd305d64e0d99a8c9715a9fc6bfb570c2a5265d0eed7165ffdceff`, and `6729f766e8b008384e5466328fc33eee703ce9ce59b8810e1ff95737a88f8579`. | verified release evidence | The archive, checksum, and SPDX assets were verified against the exact release object. This does not by itself prove installation on a host. |
| The generated `CHANGELOG.md` contains the compiled v6.1.1 entry, including the runtime 4.0.6 wire-contract disclosure and the x86_64 second-architecture entry, alongside the co-published v6.1.0 skills entries. | verified current | Generated release history agrees with the tag and package bytes; this closeout does not rewrite generated history or a signed release. |
| Both runtime architectures were qualified before the tag. The arm64 bundle passed staged qualification (zero-inference readiness plus consumed gemini, grok, and OpenCode carrier canaries). The x86_64 bundle, built by the ARM-evidence-gated Intel pipeline from the same source commit, passed a native readiness smoke on an Intel CI runner before signing, and — after local signing and notarization — a Rosetta-executed qualification: direct readiness, a full-stack staged carrier canary through the coordinator, and positive client resolution of the x86_64 artifact whose digest equals the promoted artifact. | release qualified (both architectures) | Each architecture executed end-to-end before publication. Rosetta execution qualifies the signed x86_64 code path on the available hardware; per-host activation on a physical Intel Mac applies only where such a host exists. |
| All four primary hosts — Claude, Codex, Antigravity, and Grok — installed 6.1.1 through their supported plugin CLIs, and every installed tree matched the released archive byte-for-byte (only host-generated cache files excluded). Provider-free readiness from the installed coordinator returned a typed zero-model snapshot with confirmed cleanup (54 candidates ready across 12 actions; only known host-local Codex native-CLI routes degraded, in the same shape as the prior installed release). | installed and provider-free ready on the observed hosts | This proves exact installation and readiness mechanics on those hosts at that time. It does not guarantee future provider authentication, quota, semantic quality, or another host's state. |
| One consumed post-install canary returned a receipted, content-correct result with confirmed cleanup (Grok over `grok_cli`). No carrier moved transport in this release. | activation qualified | The installed release executed one bounded end-to-end request. This does not extend to future requests or unexercised carriers. |

The public repository may advance after this immutable release tag for the
documentation closeout or later work. Re-check the tag, release, assets, host
inventory, and readiness plane before making a new release or activation claim.

### v6.1.1 closeout determinations

| Public surface | Determination | Closeout result |
| --- | --- | --- |
| `docs/architecture/` | **updated current** | This status snapshot records the v6.1.1 release, the dual-architecture runtime, and four-host activation; the remaining handbook pages describe the direct-runtime lifecycle and boundaries in architecture-neutral terms unchanged by this release. |
| Root `README.md` | **verified current** | The version, what's-new narrative (runtime 4.0.6 and the Intel second architecture), and release link were refreshed in the distribution PR and verified by the release-cut consistency gates. |
| `plugins/agent-collab/README.md` | **verified current** | The package reference describes host-keyed artifact selection across the two per-architecture bundles and the unchanged one-process lifecycle shipped in 6.1.1. |
| Generated `CHANGELOG.md` | **verified current** | The release flow compiled the v6.1.1 entry; this post-release closeout leaves generated history unchanged. |

## Historical v6.0.6 release closeout snapshot

The following public and host evidence was reconciled on 2026-08-18. It is a
dated snapshot, not a permanent “latest version” badge.

| Observation | Status | Interpretation |
| --- | --- | --- |
| The signed annotated [`v6.0.6` tag](https://github.com/sumitake/agent-collab/releases/tag/v6.0.6) identifies public commit `1d6ae7a0921e29133eb405e73ffbe820b5c7080c`. | published | The immutable source contains package version 6.0.6 and the provider runtime 4.0.5 bundle (native ACP carriers for Grok and OpenCode with display-drift tolerance, the tagless-catalog fallback ladder, fail-safe failure envelopes, and the repaired zero-inference readiness path that caused the v6.0.5 rollback). |
| The exact-tag [`release.yml` run](https://github.com/sumitake/agent-collab/actions/runs/32143886259) completed successfully and the release is published, non-draft, and non-prerelease. | published | The signed tag and GitHub Release planes agree; neither repository state nor tag existence alone was used as publication proof. |
| The release contains exactly `agent-collab.v6.0.6.plugin`, `agent-collab.v6.0.6.plugin.sha256`, and `agent-collab-v6.0.6.spdx.json`. Their SHA-256 values are `6d74b28b8f659627bf3f2b116183f5407a37feb76b5671f1a51a2e358927f03c`, `a2f6540cbf03cdbea78aa211a1b51c135c2796c29cf72c81be74f2a5a23886a0`, and `23ea532078c1fb3189c4f9ffff0f1a9f5e8c4f4d701f1c5ec210e3c63e9879b3`. The released archive is byte-identical to the locally built commit-bound qualification archive. | verified release evidence | The archive, checksum, and SPDX assets were verified against the exact release object. This does not by itself prove installation on a host. |
| The generated `CHANGELOG.md` contains the compiled v6.0.6 entry (and the intervening v6.0.2–v6.0.5 line, including the v6.0.5 rollback-defect record). | verified current | Generated release history agrees with the tag and package bytes; this closeout does not rewrite generated history or a signed release. |
| All four primary hosts — Claude, Codex, Antigravity, and Grok — installed 6.0.6 through their supported plugin CLIs, and every installed tree matched the released archive byte-for-byte (only host-generated cache files excluded). Provider-free readiness from the installed coordinator returned a typed zero-model snapshot with confirmed cleanup (54 candidates ready across 12 actions; only known host-local Codex native-CLI routes degraded). | installed and provider-free ready on the observed hosts | This proves exact installation and readiness mechanics on those hosts at that time. It does not guarantee future provider authentication, quota, semantic quality, or another host's state. |
| One consumed post-install canary per migrated ACP carrier returned a receipted, content-correct result with repository-read evidence and confirmed cleanup (Grok over `grok_cli`; OpenCode over `opencode_go`). | activation qualified | Both migrated native ACP carriers executed end-to-end on the installed release. This does not extend to unmigrated carriers or future requests. |
| Provider-specific and host-specific predecessor packages | retired | Migration and regression tests block their return as active packages or rollback targets. |

The public repository may advance after this immutable release tag for the
documentation closeout or later work. Re-check the tag, release, assets, host
inventory, and readiness plane before making a new release or activation claim.

### v6.0.6 closeout determinations

| Public surface | Determination | Closeout result |
| --- | --- | --- |
| `docs/architecture/` | **updated current** | This status snapshot records the v6.0.6 release and four-host activation; the remaining handbook pages describe the direct-runtime lifecycle and boundaries unchanged by this release. |
| Root `README.md` | **verified current** | The version, what's-new narrative (runtime 4.0.5 repairs and carrier hardening), and release link were refreshed in the distribution PR and verified by the release-cut consistency gates. |
| `plugins/agent-collab/README.md` | **verified current** | The package reference describes the exact coordinator request, response union, manifest, and one-process lifecycle shipped in 6.0.6. |
| Generated `CHANGELOG.md` | **verified current** | The release flow compiled the v6.0.6 entry; this post-release closeout leaves generated history unchanged. |

## Historical v6.0.1 release closeout snapshot

The following public and host evidence was reconciled on 2026-08-13. It is a
dated snapshot, not a permanent “latest version” badge.

| Observation | Status | Interpretation |
| --- | --- | --- |
| The signed annotated [`v6.0.1` tag](https://github.com/sumitake/agent-collab/releases/tag/v6.0.1) identifies public commit `a49871ac8ea19062f177d8598c9dcc3a751ab306`. | published | The immutable source contains package version 6.0.1 and the exact schema-4, runtime-protocol-4, native-contract-4 activation manifest and Darwin arm64 bundle qualified for v6. |
| The exact-tag [`release.yml` run](https://github.com/sumitake/agent-collab/actions/runs/31712058768) completed successfully and the release is published, non-draft, and non-prerelease. | published | The signed tag and GitHub Release planes agree; neither repository state nor tag existence alone was used as publication proof. |
| The release contains exactly `agent-collab.v6.0.1.plugin`, `agent-collab.v6.0.1.plugin.sha256`, and `agent-collab-v6.0.1.spdx.json`. Their SHA-256 values are `4cd0670e27dc951d060d381621c4116f614ae0f897aa62b9c4408f7e2b0b2960`, `c107624b04186ed8c077aa976957f6b200311e996396c440ceb000f1d8614de9`, and `729c0f3a782a3746043e94abe5bab71624dcef11911f58b186b57d57ac3d92ac`. | verified release evidence | The archive, checksum, and SPDX assets were verified against the exact release object. This does not by itself prove installation on a host. |
| The generated `CHANGELOG.md` contains the compiled v6.0.0 major-contract entry and the v6.0.1 provider-free readiness/release-authority correction. | verified current | Generated release history agrees with the tag and package bytes; this closeout does not rewrite generated history or a signed release. |
| Fresh Codex and Claude host processes reported `agent-collab@agent-collab` 6.0.1 enabled, and Antigravity reported the current shared package import. Across all three package roots, the manifest, runtime bundle, entrypoint, wire, coordinator, and runtime-client bytes matched the public release source. Provider-free readiness returned valid typed snapshots with zero model calls and confirmed cleanup. | installed and provider-free ready on the observed host | This proves exact installation and readiness mechanics on that host at that time. It does not guarantee future provider authentication, quota, semantic quality, or another host's state. |
| The release promotion canary used exactly three one-shot native calls and produced one grounded mechanical success plus two clean ungrounded advisories, with source invariance and cleanup confirmed and no mechanical veto. | mechanically qualified | Model prose, tool choice, and advisory grounding did not become release authority; deterministic fixtures retain exhaustive route coverage. |
| Provider-specific and host-specific predecessor packages | retired | Migration and regression tests block their return as active packages or rollback targets. |

The public repository may advance after this immutable release tag for the
documentation closeout or later work. Re-check the tag, release, assets, host
inventory, and readiness plane before making a new release or activation claim.

### v6.0.1 closeout determinations

| Public surface | Determination | Closeout result |
| --- | --- | --- |
| `docs/architecture/` | **updated current** | The v6 status snapshot, direct-runtime lifecycle, three-call mechanical canary, and schema/protocol-4 activation boundary agree with the published release. |
| Root `README.md` | **updated current** | The overview, current version, release link, capabilities, lifecycle links, and security boundary agree with v6.0.1. |
| `plugins/agent-collab/README.md` | **verified current** | The package reference already describes the exact v6 coordinator request, advisory union, manifest, protocol, and one-process lifecycle. |
| Generated `CHANGELOG.md` | **verified current** | The release flow compiled the v6.0.0 and v6.0.1 entries; this post-release closeout leaves generated history unchanged. |

## Historical v5.0.0 release closeout snapshot

The following public evidence was reconciled on 2026-08-11. It is a dated
snapshot, not a permanent “latest version” badge.

| Observation | Status | Interpretation |
| --- | --- | --- |
| The signed annotated [`v5.0.0` tag](https://github.com/sumitake/agent-collab/releases/tag/v5.0.0) identifies public commit `c85382f11ef68bdca8deedf53c6865838bba1fbf`. | published | The immutable release source contains package version 5.0.0, one unified package, the schema-4 activation manifest, and its manifest-listed Darwin arm64 bundle. |
| The exact-tag [`release.yml` run](https://github.com/sumitake/agent-collab/actions/runs/31479240561) completed successfully and the release is published, non-draft, and non-prerelease. | published | The tag and GitHub Release planes agree; tag existence alone was not used as publication proof. |
| The release contains exactly `agent-collab.v5.0.0.plugin`, `agent-collab.v5.0.0.plugin.sha256`, and `agent-collab-v5.0.0.spdx.json`. The checksum file verifies archive SHA-256 `25b74e4ba72d3dcdd77b476f546bc415627f02c8d3290f7ea0b3e7050d3ec4d4`. | verified release evidence | The archive, checksum, and SPDX planes were downloaded and checked together. This does not by itself prove installation on a host. |
| The generated `CHANGELOG.md` contains the compiled `agent-collab 5.0.0` entry describing the direct-runtime activation and its schema-4/runtime-protocol-3/native-contract-4 boundary. | verified current | Generated release history agrees with the tagged package and release assets; the closeout does not hand-edit it. |
| On one supported macOS arm64 verification host, both Codex and Claude package inventories reported `agent-collab@agent-collab` 5.0.0 enabled. Signed package members matched the release source, and provider-free migration doctor plus zero-inference readiness checks succeeded. | installed and provider-free ready on the observed host | This proves that installation and the direct-runtime readiness boundary worked on that host at that time. It does not guarantee future provider authentication, quota, or semantic outcomes, and a pre-existing UI session still needs a new task/session to load newly installed skills. |
| Provider-specific and host-specific predecessor packages | retired | Migration and regression tests block their return as active packages or rollback targets. |

The public repository may advance after the immutable release tag for this
documentation closeout or later work. Re-check the tag, release, assets, host
inventory, and readiness plane before making a new release or activation
claim.

### v5.0.0 closeout determinations

| Public surface | Determination | Closeout result |
| --- | --- | --- |
| `docs/architecture/` | **updated current** | The status snapshot, v5 direct-runtime lifecycle, and schema-4 activation boundary now agree with the published release. |
| Root `README.md` | **updated current** | The overview, current version, install command, release link, and closeout pointer agree with v5.0.0. |
| Generated `CHANGELOG.md` | **verified current** | The release flow compiled the v5.0.0 activation entry at the tagged commit; this post-release closeout leaves generated history unchanged. |

## Source-priority rule

Use the narrowest evidence that answers the question:

1. For the current public repository contract, inspect merged source,
   manifests, generated outputs, and focused tests.
2. For a published release, inspect the signed tag, release record, assets, and
   release evidence together.
3. For an installed package, inspect that host's plugin inventory after a new
   session starts.
4. For native-route readiness, use the provider-free migration/readiness
   surfaces from the selected package.
5. For a proposal or historical rationale, use its design or review record only
   after labeling it proposed or historical.

## Common category errors

- **“It is in the manifest, so it is active.”** The manifest advertises a
  package contract. Host selection and readiness are additional evidence.
- **“The version is on `main`, so it is released.”** Repository state is not a
  GitHub release or installed-host observation.
- **“The tag exists, so release assets exist.”** Tags and GitHub releases are
  separate objects.
- **“The skill is installed, so its provider is available.”** Skills remain
  discoverable when the corresponding route returns typed unavailable.
- **“Safe mode means the old package is restored.”** Safe mode disables model
  execution; retired packages remain retired.
- **“A green compliance trace proves the quoted review was genuine.”** The
  public gate validates evidence form. Human and independent-agent review still
  establish substance.

## Updating the snapshot

When source, release, or installation state changes:

1. Record the exact evidence plane and date.
2. Update only the row that the new evidence proves.
3. Preserve older facts as historical when they remain useful.
4. Do not promote repository-only behavior to installed/active without a host
   observation.
5. Keep operational detail coarse. Describe readiness and activation at the
   contract level (for example "the supported hosts" and "the advertised
   contracts") without enumerating host fleets, internal route counts, or
   private-runtime mechanism names; existing rows remain as recorded history.
   The fragment-disclosure boundary in
   [`changelog.d/README.md`](../../changelog.d/README.md) applies to snapshot
   prose as well.
6. Re-run the link, generated-source, release-consistency, and sanitization
   checks described in [Repository and release architecture](repository-and-release.md).
