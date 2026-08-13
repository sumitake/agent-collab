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

## v6.0.1 release closeout snapshot

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
5. Re-run the link, generated-source, release-consistency, and sanitization
   checks described in [Repository and release architecture](repository-and-release.md).
