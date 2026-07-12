#!/usr/bin/env python3
"""One-command release for the agent-collab plugin.

Replaces the manual 'git tag vX.Y.Z && git push origin vX.Y.Z' step with a
single checked command. It verifies the canonical policy-only or activation
archive and release consistency before a signed tag can be pushed.

  python scripts/cut_release.py                     cut a release for plugin.json's version
  python scripts/cut_release.py --dry-run           print the actions, change nothing
  python scripts/cut_release.py --rollback vX.Y.Z   undo a release (delete tag + GH release)

LOCAL OPERATOR TOOL -- run from a clean 'main' checkout with the operator's own
git credentials. It pushes a TAG only (never a branch); the tag push triggers
.github/workflows/release.yml, which builds + publishes the archive and re-runs
the same consistency check as a release gate. Activation additionally requires
live Developer ID/notarization verification; policy-only mode proves that no
runtime is present and does not pretend to satisfy activation evidence.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_release_consistency as crc  # noqa: E402

ROOT = crc.repo_root()


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
            "activation release requires the co-packaged Darwin-arm64 runtime "
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


def _archive_contract_verified_or_fail(mode: str) -> None:
    """Build and reopen one disposable archive before a release tag is cut."""
    if mode not in {"policy-only", "activation"}:
        _fail("release archive mode is invalid")
    builder = ROOT / "scripts" / "build_plugin_archive.py"
    with tempfile.TemporaryDirectory(prefix="agent-collab-release-check-") as temp:
        archive = Path(temp) / "agent-collab.plugin"
        res = subprocess.run(
            [sys.executable, str(builder), "--output", str(archive)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)
        if res.returncode != 0:
            _fail("canonical plugin archive verification failed")
    observed = _release_mode_or_fail()
    if observed != mode:
        _fail("release mode changed during archive verification")


def cut(dry_run: bool) -> int:
    # Release gate (read-only): run regardless of --dry-run so a dry run gives a
    # true preview and fails fast if the changelog is stale vs the fragments.
    _changelog_compiled_or_fail()
    mode = _release_mode_or_fail()
    _archive_contract_verified_or_fail(mode)
    if mode == "activation":
        _signed_runtime_verified_or_fail()
    if dry_run:
        print(
            "cut-release: [dry-run] CHANGELOG.md and canonical "
            f"{mode} archive are verified."
        )

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

    if _tag_exists(tag):
        print(f"cut-release: tag {tag} already exists -- nothing to do (already released)")
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
    _git("push", "origin", tag, capture=False)
    print(f"cut-release: pushed {tag} -- release.yml will build and publish the archive")
    return 0


def rollback(tag: str, dry_run: bool) -> int:
    if crc.parse_tag(tag) is None:
        _fail(f"--rollback expects a release tag (vX.Y.Z), got '{tag}'")
    steps = [
        ("delete the remote tag", ["push", "origin", f":refs/tags/{tag}"]),
        ("delete the local tag", ["tag", "-d", tag]),
    ]
    for label, args in steps:
        if dry_run:
            print(f"cut-release: [dry-run] would {label}: git {' '.join(args)}")
        else:
            _git(*args, capture=False, check=False)
            print(f"cut-release: {label} ({tag})")
    if dry_run:
        print(f"cut-release: [dry-run] would delete the GitHub release: gh release delete {tag}")
        return 0
    try:
        subprocess.run(["gh", "release", "delete", tag, "--yes"],
                       cwd=str(ROOT), check=False)
        print(f"cut-release: requested GitHub release deletion ({tag})")
    except OSError:
        print("cut-release: 'gh' not found -- delete the GitHub release manually",
              file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="One-command agent-collab release")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the actions, change nothing")
    ap.add_argument("--rollback", metavar="TAG",
                    help="undo a release: delete its tag (local + remote) and GH release")
    args = ap.parse_args(argv)
    if args.rollback:
        return rollback(args.rollback, args.dry_run)
    return cut(args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
