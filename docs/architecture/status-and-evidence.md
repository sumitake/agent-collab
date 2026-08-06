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

## Authoring snapshot

This handbook was authored against the following public evidence on
2026-08-05:

| Observation | Status | Interpretation |
| --- | --- | --- |
| `origin/main` began at commit `465c70e` with package version 4.9.0. This documentation change advances the source package to 4.9.1. | current | The handbook describes the public repository contract that will exist when this change merges. |
| The repository contains one unified package, generated host marketplaces, a populated activation manifest, and the manifest-listed Darwin arm64 bundle. | repository-only | The source tree contains activation material; this alone does not prove an installation or active host. |
| The latest GitHub release record observed during authoring was v4.5.1. | historical release observation | It describes the public release list at that point in time, not the newer repository tree. |
| A signed annotated v4.6.0 tag existed without a corresponding GitHub release record. | historical tag observation | Tag existence and release publication are separate lifecycle events. |
| Changelog fragments after the generated `CHANGELOG.md` baseline remain in `changelog.d/`. | staged | Fragments are release inputs. They are not compiled on feature branches. |
| Current host installation and route readiness | unclaimed | This repository documentation intentionally makes no operator-host claim. Inspect the target host. |
| Provider-specific and host-specific predecessor packages | retired | Migration and regression tests block their return as active packages or rollback targets. |

The observed release list is time-sensitive. Re-check it before making a new
release claim. Do not turn this dated row into a permanent “latest version”
badge.

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
