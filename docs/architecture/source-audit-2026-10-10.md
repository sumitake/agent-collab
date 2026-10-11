# Architecture source audit — 2026-10-10

This descriptive audit uses public repository baseline
`86b883aac18346992e3665e136714e05d7b8726c`. It is not a new release,
installation, host readiness check, or provider qualification. The published
7.0.8 tag and archive retain their original identities.

## Findings and corrections

The manifest, current handbook, and dated release evidence agree on package
7.0.8, runtime 5.0.9, manifest schema 4, protocol 5, native contract 4, wire 12,
two macOS architectures, twelve logical actions, and eight logical agents.
The existing capability map covers 53 generated skills. These are package
inventory claims, not proof that every provider is available on a host.

The refresh corrects the root README's description of an explicitly targeted
logical agent and clarifies that the public client's process group owns the
verified native-runtime invocation. Provider-native sessions remain inside the
runtime boundary. It also corrects comments that overstated package-README
version enforcement: the current immutable package reference has no legacy
`Current` marker, so the optional regex check does not validate its narrative.
Exact tag/archive comparison and human review remain separate evidence.

There is still exactly one root README latest-release showcase. Earlier release
history remains in the generated changelog. No generated skills, runtime
artifacts, manifests, package versions, signed tags, or executable logic change
in this audit. The package README is intentionally unchanged: postpublication
clarifications belong in current repository docs, not the release-time snapshot.

## Coverage

All nine pre-existing handbook pages and the root README were inspected.
Read-only Terra research returned distilled findings; the primary retained
edits, sanitization, verification, and merge decisions. Such same-family
research is not independent-family approval.

| Surface | Public source/evidence | Disposition |
| --- | --- | --- |
| Index and system context | Manifest, runtime client, package reference, export policy | One-package and public/private boundaries remain current. |
| Capabilities/workflows | `skill-specs/`, generated skills, skill-runtime contract tests | Capability map and primary-executed versus managed work remain distinct. |
| Project estimation | Receipt-bound data inventory and maintenance validator/tests | Bootstrap evidence is not promoted calibration or unrestricted private history. |
| Governance/authority | Public governance, review skill, independence tests | Candidate selection and response-correlated independent approval remain distinct. |
| Lifecycle/operations | Migration doctor, runtime client, lifecycle tests | Installation, selection, fresh loading, readiness, and live completion remain separate. |
| Repository/release | Generators, importer, release workflow, consistency checker/tests | Latest-only showcase remains enforced; optional package-marker coverage clarified. |
| Status/evidence | Manifest and dated tag, release, and installation records | Existing qualification limits and immutable snapshots retained. |
| Claude participation | Signed action inventory and participation contract | Only managed document intent is admitted; resident and async roles remain separate. |
| Root README | Manifest, distribution-contract tests, release checker | Logical-agent terminology and runtime-process ownership corrected. |

Validation and any review outcomes are recorded in the audit PR. Neither green
source tests nor this audit replace the exact-artifact and host evidence owned
by the [status page](status-and-evidence.md). The final release closeout remains
the last release step; its source/evidence review is broader than a version grep.
