#!/usr/bin/env python3
"""One-command release for the agent-collab plugin.

Replaces the manual 'git tag vX.Y.Z && git push origin vX.Y.Z' step with a
single checked command. It verifies the canonical policy-only or activation
archive and release consistency before a signed tag can be pushed.

  python scripts/cut_release.py                     cut a release for plugin.json's version
  python scripts/cut_release.py --dry-run           print the actions, change nothing
LOCAL OPERATOR TOOL -- run from a clean 'main' checkout with the operator's own
git credentials. It pushes a TAG only (never a branch); the tag push triggers
.github/workflows/release.yml, which builds + publishes the archive and re-runs
the same consistency check as a release gate. Activation additionally requires
live Developer ID/notarization verification; policy-only mode proves that no
runtime is present and does not pretend to satisfy activation evidence. A
pushed version tag is immutable: an existing tag is verified, never moved,
deleted, reused, or assumed to mean that publication succeeded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_release_consistency as crc  # noqa: E402

ROOT = crc.repo_root()
REPOSITORY = "sumitake/agent-collab"
RELEASE_WORKFLOW_PATH = ".github/workflows/release.yml"
PUBLICATION_TIMEOUT_SECONDS = 30 * 60
PUBLICATION_POLL_SECONDS = 10
MAX_RELEASE_ASSET_BYTES = 256 * 1024 * 1024


def _git(*args: str, capture: bool = True, check: bool = True):
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=capture, text=True, check=check)


def _fail(msg: str) -> None:
    print(f"cut-release: {msg}", file=sys.stderr)
    sys.exit(1)


def _tag_exists(tag: str) -> bool:
    local = _git("tag", "-l", tag).stdout.strip()
    remote = _git("ls-remote", "--tags", "origin", f"refs/tags/{tag}").stdout.strip()
    return bool(local or remote)


def _gh_api_json(endpoint: str, *, required: bool) -> object | None:
    try:
        result = subprocess.run(
            ["gh", "api", endpoint],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        if required:
            _fail("GitHub CLI is unavailable")
        return None
    if result.returncode != 0:
        if required:
            _fail(f"GitHub API request failed for {endpoint}")
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        if required:
            _fail(f"GitHub API returned malformed JSON for {endpoint}")
        return None


def _tag_publication_facts(tag: str) -> tuple[str | None, bool, bool]:
    ref = _gh_api_json(
        f"repos/{REPOSITORY}/git/ref/tags/{tag}", required=False
    )
    ref_object = ref.get("object") if type(ref) is dict else None
    if type(ref_object) is not dict:
        return None, False, False
    object_type = ref_object.get("type")
    object_sha = ref_object.get("sha")
    if type(object_sha) is not str:
        return None, False, False
    if object_type == "commit":
        return object_sha, False, False
    if object_type != "tag":
        return None, False, False
    tag_object = _gh_api_json(
        f"repos/{REPOSITORY}/git/tags/{object_sha}", required=False
    )
    target = tag_object.get("object") if type(tag_object) is dict else None
    verification = (
        tag_object.get("verification") if type(tag_object) is dict else None
    )
    commit = target.get("sha") if type(target) is dict else None
    verified = (
        verification.get("verified") if type(verification) is dict else None
    )
    if type(target) is not dict or target.get("type") != "commit":
        commit = None
    return commit if type(commit) is str else None, True, verified is True


def _download_release_assets(
    release: object,
    expected_names: frozenset[str],
) -> dict[str, bytes]:
    assets = release.get("assets") if type(release) is dict else None
    if type(assets) is not list:
        return {}
    by_name: dict[str, Mapping[str, Any]] = {}
    for asset in assets:
        if type(asset) is not dict or type(asset.get("name")) is not str:
            continue
        name = asset["name"]
        if name in by_name:
            return {}
        by_name[name] = asset
    if not expected_names.issubset(by_name):
        return {}
    downloaded: dict[str, bytes] = {}
    for name in sorted(expected_names):
        asset = by_name[name]
        size = asset.get("size")
        url = asset.get("url")
        if (
            type(size) is not int
            or type(size) is bool
            or not 1 <= size <= MAX_RELEASE_ASSET_BYTES
            or type(url) is not str
            or not url.startswith(f"https://api.github.com/repos/{REPOSITORY}/")
        ):
            return {}
        try:
            result = subprocess.run(
                ["gh", "api", url, "-H", "Accept: application/octet-stream"],
                cwd=str(ROOT),
                capture_output=True,
                check=False,
            )
        except OSError:
            return {}
        if result.returncode != 0 or len(result.stdout) != size:
            return {}
        downloaded[name] = result.stdout
    return downloaded


def _publication_state(
    tag: str,
    expected_asset_sha256: Mapping[str, str],
) -> dict[str, object]:
    tag_commit, tag_is_annotated, tag_signature_verified = (
        _tag_publication_facts(tag)
    )
    runs = _gh_api_json(
        f"repos/{REPOSITORY}/actions/workflows/release.yml/runs"
        f"?event=push&branch={tag}&per_page=100",
        required=False,
    )
    workflow_runs = runs.get("workflow_runs") if type(runs) is dict else []
    if type(workflow_runs) is not list:
        workflow_runs = []
    release = _gh_api_json(
        f"repos/{REPOSITORY}/releases/tags/{tag}", required=False
    )
    expected_names = frozenset(expected_asset_sha256)
    return {
        "tag_commit": tag_commit,
        "tag_is_annotated": tag_is_annotated,
        "tag_signature_verified": tag_signature_verified,
        "workflow_runs": workflow_runs,
        "release": release,
        "downloaded_assets": _download_release_assets(
            release, expected_names
        ),
    }


def _validate_publication_state(
    *,
    tag: str,
    commit: str,
    expected_asset_sha256: Mapping[str, str],
    tag_commit: object,
    tag_is_annotated: object,
    tag_signature_verified: object,
    workflow_runs: object,
    release: object,
    downloaded_assets: object,
) -> None:
    version = crc.parse_tag(tag)
    if version is None or len(commit) != 40 or any(
        char not in "0123456789abcdef" for char in commit
    ):
        raise ValueError("invalid expected release identity")
    expected_names = {
        f"agent-collab.v{version}.plugin",
        f"agent-collab.v{version}.plugin.sha256",
        f"agent-collab-v{version}.spdx.json",
    }
    if (
        type(expected_asset_sha256) is not dict
        or set(expected_asset_sha256) != expected_names
        or any(
            type(digest) is not str
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            for digest in expected_asset_sha256.values()
        )
    ):
        raise ValueError("invalid expected release asset identity")
    if (
        tag_commit != commit
        or tag_is_annotated is not True
        or tag_signature_verified is not True
    ):
        raise ValueError("release tag is not a verified immutable exact-commit tag")
    if type(workflow_runs) is not list:
        raise ValueError("release workflow inventory is malformed")
    matching_runs = [
        run for run in workflow_runs
        if type(run) is dict
        and run.get("path") == RELEASE_WORKFLOW_PATH
        and run.get("event") == "push"
        and run.get("head_branch") == tag
        and run.get("head_sha") == commit
    ]
    if len(matching_runs) != 1:
        raise ValueError("exact release workflow run is missing or ambiguous")
    run = matching_runs[0]
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise ValueError("exact release workflow run did not succeed")
    if (
        type(release) is not dict
        or release.get("tag_name") != tag
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise ValueError("exact public release object is missing")
    assets = release.get("assets")
    if type(assets) is not list:
        raise ValueError("public release assets are malformed")
    asset_sizes: dict[str, int] = {}
    for asset in assets:
        if type(asset) is not dict:
            raise ValueError("public release asset is malformed")
        name = asset.get("name")
        size = asset.get("size")
        if (
            type(name) is not str
            or name in asset_sizes
            or type(size) is not int
            or type(size) is bool
            or not 1 <= size <= MAX_RELEASE_ASSET_BYTES
        ):
            raise ValueError("public release asset identity is malformed")
        asset_sizes[name] = size
    if not expected_names.issubset(asset_sizes):
        raise ValueError("public release is missing a required asset")
    if type(downloaded_assets) is not dict or set(downloaded_assets) != expected_names:
        raise ValueError("required release assets were not downloaded exactly")
    for name in sorted(expected_names):
        data = downloaded_assets.get(name)
        if (
            type(data) is not bytes
            or len(data) != asset_sizes[name]
            or hashlib.sha256(data).hexdigest()
            != expected_asset_sha256[name]
        ):
            raise ValueError("published release asset digest differs")
    archive_name = f"agent-collab.v{version}.plugin"
    checksum_name = archive_name + ".sha256"
    archive_digest = hashlib.sha256(downloaded_assets[archive_name]).hexdigest()
    if downloaded_assets[checksum_name] != (
        f"{archive_digest}  {archive_name}\n".encode("ascii")
    ):
        raise ValueError("published checksum does not bind the archive")
    try:
        sbom = json.loads(
            downloaded_assets[f"agent-collab-v{version}.spdx.json"]
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("published SPDX asset is malformed") from None
    if type(sbom) is not dict or sbom.get("spdxVersion") != "SPDX-2.3":
        raise ValueError("published SPDX asset has no current authority")


def _verify_published_release_or_fail(
    tag: str,
    commit: str,
    expected_asset_sha256: Mapping[str, str],
) -> None:
    try:
        _validate_publication_state(
            tag=tag,
            commit=commit,
            expected_asset_sha256=expected_asset_sha256,
            **_publication_state(tag, expected_asset_sha256),
        )
    except ValueError as exc:
        _fail(f"{tag} is not a verified exact publication: {exc}")


def _wait_and_verify_published_release_or_fail(
    tag: str,
    commit: str,
    expected_asset_sha256: Mapping[str, str],
) -> None:
    deadline = time.monotonic() + PUBLICATION_TIMEOUT_SECONDS
    last_error = "publication has not appeared"
    while True:
        state = _publication_state(tag, expected_asset_sha256)
        runs = state.get("workflow_runs")
        if type(runs) is list:
            exact = [
                run for run in runs
                if type(run) is dict
                and run.get("path") == RELEASE_WORKFLOW_PATH
                and run.get("event") == "push"
                and run.get("head_branch") == tag
                and run.get("head_sha") == commit
            ]
            if len(exact) == 1 and exact[0].get("status") == "completed" and (
                exact[0].get("conclusion") != "success"
            ):
                _fail(
                    f"exact release workflow for {tag} completed with "
                    f"{exact[0].get('conclusion')}"
                )
        try:
            _validate_publication_state(
                tag=tag,
                commit=commit,
                expected_asset_sha256=expected_asset_sha256,
                **state,
            )
        except ValueError as exc:
            last_error = str(exc)
        else:
            print(
                f"cut-release: verified {tag} workflow, release, and exact assets"
            )
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _fail(f"timed out verifying {tag}: {last_error}")
        time.sleep(min(PUBLICATION_POLL_SECONDS, remaining))


# The public repository contains the imported runtime bundle, not its private
# build source.  Exact bundle/manifest bytes and their signing/notarization are
# authoritative here; a PR title or commit subject is not.
_RUNTIME_STAGE_PATHS = ("plugins/agent-collab/runtime/",)


def _staged_runtime_present_or_fail() -> None:
    """Require an imported runtime bundle before an activation release.

    Runtime source currency is established by the governed workspace build and
    atomic public import.  This repository then verifies the exact imported
    bundle through the closed manifest, archive, signature, and notarization
    gates.  Commit-subject prefixes are descriptive prose and cannot override
    those byte authorities or force a rebuild of unchanged native bytes.
    """
    staged = _git("log", "-1", "--format=%H", "--", *_RUNTIME_STAGE_PATHS).stdout.strip()
    if not staged:
        _fail(
            "no staged runtime found under plugins/agent-collab/runtime/ -- an "
            "activation release requires the workspace-side full runtime build "
            "and stage first (workspace docs/portable-v2-openssl-toolchain-runbook.md)"
        )


def _head_is_published_main_or_fail() -> None:
    _git(
        "fetch",
        "--force",
        "origin",
        "main:refs/remotes/origin/main",
        capture=False,
    )
    head = _git("rev-parse", "HEAD").stdout.strip()
    origin_main = _git("rev-parse", "refs/remotes/origin/main").stdout.strip()
    ancestry = _git(
        "merge-base",
        "--is-ancestor",
        head,
        "refs/remotes/origin/main",
        check=False,
    )
    if ancestry.returncode != 0 or head != origin_main:
        _fail(
            "release HEAD must equal a commit already reachable from origin/main"
        )


def _changelog_compiled_or_fail() -> None:
    """Release gate: CHANGELOG.md must already be compiled from fragments.

    Under the fragment-only convention (2026-06-14) PRs commit ONLY
    changelog.d/ fragments; the generated CHANGELOG.md is compiled into
    [Unreleased] at release time via a release PR. cut_release.py runs on a
    clean 'main' and cannot push a commit (enforce_admins branch protection),
    so it only VERIFIES sync here -- it never writes -- and tells the operator
    how to fix a stale changelog.
    """
    build = ROOT / "scripts" / "build-changelog.py"
    res = subprocess.run([sys.executable, str(build), "--check"],
                         cwd=str(ROOT), capture_output=True, text=True, check=False)
    if res.returncode != 0:
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)  # surface build-changelog's structural errors (exit 2)
        _fail("CHANGELOG.md is out of sync with changelog.d/ fragments. Merge a "
              "release PR that runs `python3 scripts/build-changelog.py` and "
              "commits the compiled CHANGELOG.md before tagging.")


def _signed_runtime_verified_or_fail() -> None:
    """Activation gate: require the packaged Darwin runtime and live macOS proof."""
    verifier = ROOT / "scripts" / "verify_runtime_release.py"
    head = _git("rev-parse", "HEAD").stdout.strip()
    res = subprocess.run(
        [sys.executable, str(verifier), "--git-sha", head],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    sys.stdout.write(res.stdout)
    sys.stderr.write(res.stderr)
    if res.returncode != 0:
        _fail(
            "activation release requires every co-packaged Darwin runtime "
            "and successful Developer ID, hardened-runtime, and notarization verification"
        )


def _release_mode_or_fail() -> str:
    """Classify the source tree through the canonical archive contract."""
    builder = ROOT / "scripts" / "build_plugin_archive.py"
    res = subprocess.run(
        [sys.executable, str(builder), "--print-mode"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    mode = res.stdout.strip()
    if res.returncode != 0 or mode not in {"policy-only", "activation"}:
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)
        _fail("release package is neither canonical policy-only nor activation mode")
    return mode


def _archive_contract_verified_or_fail(
    mode: str,
    *,
    version: str,
    commit: str,
) -> dict[str, str]:
    """Build exact local release assets and return their immutable digests."""
    if mode not in {"policy-only", "activation"}:
        _fail("release archive mode is invalid")
    builder = ROOT / "scripts" / "build_plugin_archive.py"
    evidence_builder = ROOT / "scripts" / "build_release_evidence.py"
    archive_name = f"agent-collab.v{version}.plugin"
    checksum_name = archive_name + ".sha256"
    sbom_name = f"agent-collab-v{version}.spdx.json"
    created = _git("show", "-s", "--format=%cI", commit).stdout.strip()
    if not created:
        _fail("release commit timestamp is unavailable")
    with tempfile.TemporaryDirectory(prefix="agent-collab-release-check-") as temp:
        archive = Path(temp) / archive_name
        checksum = Path(temp) / checksum_name
        sbom = Path(temp) / sbom_name
        res = subprocess.run(
            [
                sys.executable,
                str(builder),
                "--output",
                str(archive),
                "--expected-commit",
                commit,
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)
        if res.returncode != 0:
            _fail("canonical plugin archive verification failed")
        evidence = subprocess.run(
            [
                sys.executable,
                str(evidence_builder),
                "--archive",
                str(archive),
                "--version",
                version,
                "--created",
                created,
                "--checksum",
                str(checksum),
                "--sbom",
                str(sbom),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        sys.stdout.write(evidence.stdout)
        sys.stderr.write(evidence.stderr)
        if evidence.returncode != 0:
            _fail("deterministic release evidence verification failed")
        try:
            expected = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (archive, checksum, sbom)
            }
        except OSError:
            _fail("verified release assets could not be read back")
    observed = _release_mode_or_fail()
    if observed != mode:
        _fail("release mode changed during archive verification")
    return expected


def cut(dry_run: bool) -> int:
    # Release gate (read-only): run regardless of --dry-run so a dry run gives a
    # true preview and fails fast if the changelog is stale vs the fragments.
    _changelog_compiled_or_fail()
    mode = _release_mode_or_fail()

    ok, lines = crc.run_consistency(ROOT)
    print("\n".join(lines))
    if not ok:
        _fail("release-version drift -- fix the files above before releasing")

    version = crc.current_version(ROOT)
    if not version:
        _fail("could not read plugin.json version")
    tag = f"v{version}"

    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        _fail(f"releases are cut from 'main' (currently on '{branch}')")
    if _git("status", "--porcelain").stdout.strip():
        _fail("working tree is not clean -- commit or stash first")
    _head_is_published_main_or_fail()
    head = _git("rev-parse", "HEAD").stdout.strip()
    expected_asset_sha256 = _archive_contract_verified_or_fail(
        mode, version=version, commit=head
    )
    if mode == "activation":
        _signed_runtime_verified_or_fail()
        _staged_runtime_present_or_fail()
    if dry_run:
        print(
            "cut-release: [dry-run] CHANGELOG.md and canonical "
            f"{mode} archive/evidence are verified."
        )

    if _tag_exists(tag):
        _verify_published_release_or_fail(tag, head, expected_asset_sha256)
        print(f"cut-release: existing immutable tag {tag} is fully published")
        return 0

    if dry_run:
        print(f"cut-release: [dry-run] would run: "
              f"git tag -s {tag} -m 'agent-collab {tag}' && git push origin {tag}")
        return 0
    # Signed, annotated tag with a message. -s (not a bare `git tag`): a bare
    # `git tag <name>` aborts with "fatal: no tag message?" under the operator's
    # tag.gpgSign=true config, which promotes it to a signed tag needing -m.
    # -s (not -a): sign explicitly -- a release tag is a provenance control, so
    # signing must not depend on ambient git config. -s fails loud if no GPG
    # key is available, which is correct: this is a local operator tool and an
    # unsigned release tag should never ship.
    _git("tag", "-s", tag, "-m", f"agent-collab {tag}", capture=False)
    _git("verify-tag", tag, capture=False)
    tagged_commit = _git("rev-parse", f"{tag}^{{commit}}").stdout.strip()
    if tagged_commit != head:
        _fail("new signed release tag does not resolve to the exact release HEAD")
    _git("push", "origin", tag, capture=False)
    print(f"cut-release: pushed immutable {tag}; verifying exact publication")
    _wait_and_verify_published_release_or_fail(
        tag, head, expected_asset_sha256
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="One-command agent-collab release")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the actions, change nothing")
    args = ap.parse_args(argv)
    return cut(args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
