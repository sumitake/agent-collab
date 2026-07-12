# Agent Collab Source-Available License Design

**Status:** Approved for implementation on 2026-07-12

**Target release:** `v3.1.0`

**Copyright owner:** John Osumi

**Commercial licensing administrator:** Osumi Consulting LLC

## Objective

Give users an explicit, narrow right to inspect, install, and use the public
plugin for noncommercial purposes while preserving proprietary control over
commercial use, modification, derivative works, and redistribution.

The repository remains publicly readable. Licensing controls permitted use; it
does not make public source confidential or limit statutory fair-use rights.

## License model

The canonical repository license is the unmodified PolyForm Strict License
1.0.0 from:

<https://polyformproject.org/licenses/strict/1.0.0>

PolyForm Strict permits noncommercial use and does not grant permission to
distribute the software or make changes or new works based on it. The official
license text remains unmodified so the repository may accurately identify it as
PolyForm Strict 1.0.0.

Commercial use is not granted by the public license. It requires separate,
explicit written authorization administered by Osumi Consulting LLC. The
authorization must identify the licensee and permitted scope. Repository access,
installation, a GitHub interaction, or acceptance of a pull request does not
constitute commercial approval.

## Copyright and notices

The repository and distributed package identify:

```text
Copyright (c) 2026 John Osumi. All rights reserved except as expressly granted.
Commercial licensing is administered by Osumi Consulting LLC.
```

The root `NOTICE` carries that statement. `COMMERCIAL-LICENSING.md` explains the
approval boundary without attempting to replace or amend the PolyForm terms.

## Public repository and package surfaces

The implementation updates these surfaces together:

- root `LICENSE`, `NOTICE`, and `COMMERCIAL-LICENSING.md`;
- root and plugin READMEs;
- Claude and Codex plugin manifests;
- generated Claude marketplace metadata where its schema permits a license
  field;
- the package archive, which must contain the license, notice, and commercial
  licensing document;
- release-consistency, archive, and public-distribution tests; and
- a `v3.1.0` changelog fragment and version metadata.

The manifest license value is `PolyForm-Strict-1.0.0`. Because that identifier
is not currently on the SPDX License List, SBOM or schema surfaces that require
an SPDX expression use a documented `LicenseRef-PolyForm-Strict-1.0.0` rather
than falsely claiming OSI or SPDX recognition.

Root and packaged legal files have one canonical source and an exact-byte parity
test. Symlinks are not used because public-export and archive safety gates reject
them.

## Agent-neutral repository instructions

The public repository uses root `AGENTS.md` as the sole canonical source for
repository-wide agent instructions. This makes the development, governance,
validation, runtime-boundary, and public-export rules directly discoverable by
Codex and other agents that implement the agent-neutral convention.

Root `CLAUDE.md` remains only as a Claude Code compatibility loader containing
an `@AGENTS.md` import. It carries no independent policy. This preserves native
Claude Code discovery without creating two instruction sources or allowing the
files to drift. A symlink is not used so checkouts, release archives, and
cross-platform clients receive an ordinary portable file.

The implementation updates all active references that currently identify
`CLAUDE.md` as authoritative, including public governance documentation,
scaffolding guidance, compliance-script comments, and public-distribution
contract tests. Tests require `AGENTS.md`, require the Claude compatibility
import, and reject duplicated canonical policy in `CLAUDE.md`.

This public-repository choice is independent of the private source workspace.
Repository-scoped instruction discovery prevents cross-repository conflicts;
the workspace may retain its own `AGENTS.md` and `CLAUDE.md` authority model.
No private workspace document becomes a prerequisite for using or contributing
to the public repository.

## Contribution boundary

The current public history contains only John Osumi-authored commits, so the new
license can be applied without reconciling an existing third-party contribution.

After licensing, an external contribution cannot merge until the contributor
has entered a separate written agreement granting John Osumi sufficient rights
to use, modify, distribute, sublicense, and commercially relicense that
contribution. A Developer Certificate of Origin alone is insufficient for this
commercial relicensing requirement. Public governance and the pull-request
template state the gate; automation checks that the contributor-rights field is
present, while the operator verifies the actual agreement.

## Release behavior

`v3.1.0` is a policy-only release. It does not activate or add a native runtime.
The release archive and public checksum/SBOM evidence include the licensing
files. Release verification fails when:

- a required legal file is missing;
- root and packaged legal files differ;
- a manifest or marketplace reports a conflicting license;
- the package version is not `3.1.0`;
- the release archive omits the legal files; or
- README and changelog licensing statements drift.

The release uses the existing signed-tag workflow. The deleted or absent
`v3.0.0` release is not recreated.

## Validation

The implementation must pass:

```text
python3 scripts/build_marketplace.py --check
python3 -m unittest discover -s tests -t . -v
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/check_release_consistency.py
python3 scripts/check-public-export-safety.py --active-tree --history
python3 scripts/secret_scan.py
git diff --check
```

The release rehearsal must additionally inspect the generated archive and prove
the exact legal-file members and bytes before `v3.1.0` is tagged.

## Limitations

- GitHub may not automatically classify PolyForm Strict because it is not an
  OSI-approved license and is not currently listed by SPDX.
- Public visibility necessarily permits reading the source. The license governs
  granted rights; it is not a confidentiality mechanism.
- This repository records the operator-selected licensing model, not legal
  advice. Bespoke commercial agreements remain separate from the public
  repository.
