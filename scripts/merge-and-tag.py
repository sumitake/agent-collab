#!/usr/bin/env python3
"""Automate pull request merge, release tagging, local worktree/branch cleanup,
and inter-agent notification for agent-collab.

Usage:
  python3 scripts/merge-and-tag.py <pr_number> [--repo OWNER/REPO] [--force] [--no-cleanup] [--no-notify]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run_cmd(args: list[str], cwd: Path | None = None, check: bool = True, input_data: str | None = None) -> subprocess.CompletedProcess:
    # Clear invalid environment token and ensure git operations use keyring
    env = dict(os.environ)
    env["GITHUB_TOKEN"] = ""
    res = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
        input=input_data,
        check=False,
    )
    if check and res.returncode != 0:
        print(f"Command failed: {' '.join(args)}", file=sys.stderr)
        print(f"stdout: {res.stdout}", file=sys.stderr)
        print(f"stderr: {res.stderr}", file=sys.stderr)
        sys.exit(res.returncode)
    return res



def get_git_branch_for_pr(pr_number: str, repo: str, root: Path) -> str:
    res = run_cmd(["gh", "pr", "view", pr_number, "--repo", repo, "--json", "headRefName"], cwd=root)
    try:
        data = json.loads(res.stdout)
        return data["headRefName"]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing PR headRefName: {e}", file=sys.stderr)
        sys.exit(1)


def get_pr_details(pr_number: str, repo: str, root: Path) -> dict:
    res = run_cmd(["gh", "pr", "view", pr_number, "--repo", repo, "--json", "headRefName,title,body"], cwd=root)
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError as e:
        print(f"Error parsing PR details: {e}", file=sys.stderr)
        sys.exit(1)


def extract_version_from_changelog(text: str) -> str | None:
    # Match ## [X.Y.Z]
    m = re.search(r"^##\s+\[(\d+\.\d+\.\d+)\]", text, re.M)
    return m.group(1) if m else None


def extract_version_from_json(text: str, key: str = "version") -> str | None:
    try:
        data = json.loads(text)
        # Handle dotted paths if needed, but simple key lookup is enough for v0.1
        if key == "metadata.version":
            return data.get("metadata", {}).get("version")
        return data.get(key)
    except (json.JSONDecodeError, AttributeError):
        return None


def get_file_content_at_ref(ref: str, path: str, root: Path) -> str | None:
    res = run_cmd(["git", "show", f"{ref}:{path}"], cwd=root, check=False)
    return res.stdout if res.returncode == 0 else None


def detect_version_bumps(head_ref: str, root: Path) -> dict[str, str]:
    """Detects version changes from main to head_ref. Returns a dict of key/tag suffix to version."""
    bumps = {}
    
    # Files to check
    files_to_check = {
        "CHANGELOG.md": ("changelog", extract_version_from_changelog),
        ".claude-plugin/marketplace.json": ("marketplace", lambda t: extract_version_from_json(t, "metadata.version")),
        "plugins/agent-collab/.claude-plugin/plugin.json": ("agent-collab", extract_version_from_json),
    }

    for path, (label, extractor) in files_to_check.items():
        main_content = get_file_content_at_ref("origin/main", path, root)
        head_content = get_file_content_at_ref(f"origin/{head_ref}", path, root)
        if not head_content:
            continue
        
        main_version = extractor(main_content) if main_content else None
        head_version = extractor(head_content)
        
        if head_version and head_version != main_version:
            bumps[label] = head_version

    return bumps


def cleanup_local_branch_and_worktree(branch_name: str, root: Path):
    print(f"Cleaning up local branch and worktree for: {branch_name}")
    
    # 1. Remove worktree if exists
    res = run_cmd(["git", "worktree", "list"], cwd=root, check=False)
    for line in res.stdout.splitlines():
        if f"[{branch_name}]" in line:
            parts = line.split()
            if parts:
                wt_path = parts[0]
                print(f"Removing worktree at: {wt_path}")
                run_cmd(["git", "worktree", "remove", "--force", wt_path], cwd=root, check=False)
                
    # 2. Delete local branch
    run_cmd(["git", "branch", "-D", branch_name], cwd=root, check=False)


def send_notification(repo: str, pr_number: str, title: str, bumps: dict[str, str], root: Path):
    agent_name = os.environ.get("AGENT_NAME", "antigravity").lower()
    other_agent = "claude" if agent_name == "antigravity" else "antigravity"
    
    version_bump_desc = ", ".join(f"{k} to v{v}" for k, v in bumps.items())
    subject_prefix = f"merged PR #{pr_number}"
    if version_bump_desc:
        subject = f"[FYI] {subject_prefix}; signed release pending ({version_bump_desc})"
    else:
        subject = f"[FYI] {subject_prefix} ({title})"
        
    body = f"Merged pull request #{pr_number}: '{title}' in {repo}.\n"
    if bumps:
        body += (
            "Run scripts/cut_release.py from clean main. It will classify and "
            "verify either a policy-only archive or an activation archive; only "
            "activation requires signed/notarized runtime evidence.\n"
        )
        
    # Invoke agent-collab-send.py
    send_script = root / "scripts" / "agent-collab-send.py"
    if send_script.exists():
        run_cmd([
            "python3", str(send_script),
            "--to", other_agent,
            "--type", "fyi",
            "--subject", subject,
            "--topic", "merge-automation",
        ], cwd=root, check=False, input_data=body)
        print("Inter-agent notification sent.")
    else:
        print("Warning: scripts/agent-collab-send.py not found, notification skipped.", file=sys.stderr)



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Automate pull request merge, tagging, and cleanup.")
    ap.add_argument("pr", help="Pull request number")
    ap.add_argument("--repo", help="Target repository (owner/repo), default auto-detected")
    ap.add_argument("--force", action="store_true", help="Bypass compliance-check failure")
    ap.add_argument("--no-cleanup", action="store_true", help="Skip local worktree and branch deletion")
    ap.add_argument("--no-notify", action="store_true", help="Skip inter-agent notification")
    args = ap.parse_args(argv)

    root = repo_root()
    
    # Resolve repository name
    if args.repo:
        repo = args.repo
    else:
        # Detect from git remote
        res = run_cmd(["git", "remote", "get-url", "origin"], cwd=root)
        url = res.stdout.strip()
        # Parse github.com:owner/repo.git or https://github.com/owner/repo.git
        m = re.search(r"github\.com[:/]([^/]+/[^.]+)(?:\.git)?$", url)
        if m:
            repo = m.group(1)
        else:
            print(f"Error: Could not auto-detect repo from remote URL: {url}", file=sys.stderr)
            return 1

    pr_number = str(args.pr)
    print(f"Starting merge automation for {repo} PR #{pr_number}")

    # 1. Run compliance check
    compliance_script = root / "scripts" / "check_pr_compliance.py"
    if compliance_script.exists():
        res = run_cmd(["python3", str(compliance_script), pr_number, "--repo", repo], cwd=root, check=False)
        print(res.stdout)
        if res.returncode != 0:
            if args.force:
                print("Warning: Compliance check failed, but --force was specified. Proceeding.")
            else:
                print("Error: PR compliance check failed. Aborting merge.", file=sys.stderr)
                return res.returncode
    else:
        print("Warning: check_pr_compliance.py not found. Compliance verification skipped.", file=sys.stderr)

    # 2. Get PR details and branch
    pr_details = get_pr_details(pr_number, repo, root)
    head_ref = pr_details["headRefName"]
    title = pr_details["title"]
    
    # Check for self-deletion hazard (running from within the worktree being deleted)
    if not args.no_cleanup:
        res = run_cmd(["git", "worktree", "list"], cwd=root, check=False)
        for line in res.stdout.splitlines():
            if f"[{head_ref}]" in line:
                parts = line.split()
                if parts:
                    wt_path = parts[0]
                    try:
                        wt_realpath = os.path.realpath(wt_path)
                        cwd_realpath = os.path.realpath(os.getcwd())
                        if cwd_realpath == wt_realpath or cwd_realpath.startswith(wt_realpath + os.sep):
                            print(f"Error: Cannot perform merge and cleanup because your current working directory is inside the target worktree path '{wt_path}'.", file=sys.stderr)
                            print("Please change directory (e.g. 'cd' to the main repository checkout) and try again.", file=sys.stderr)
                            return 1
                    except Exception as e:
                        print(f"Warning: Failed to check path safety: {e}", file=sys.stderr)

    # 3. Detect version bumps before merging
    # Run fetch first to make sure origin refs are updated
    run_cmd(["git", "fetch", "origin"], cwd=root)
    bumps = detect_version_bumps(head_ref, root)

    # 4. Perform Squash Merge
    print(f"Merging PR #{pr_number} via gh...")
    run_cmd(["gh", "pr", "merge", pr_number, "--repo", repo, "--squash", "--delete-branch"], cwd=root)
    print("PR successfully squash-merged.")

    # 5. Fetch remote main and get merge commit SHA
    print("Fetching origin main to locate merge commit...")
    run_cmd(["git", "fetch", "origin", "main"], cwd=root)
    res = run_cmd(["git", "rev-parse", "origin/main"], cwd=root)
    merge_sha = res.stdout.strip()
    print(f"Merge commit SHA: {merge_sha}")

    # 6. Deliberately do not tag here. Release mode and archive parity are owned
    # by cut_release.py. It creates the signed annotated tag after classifying
    # policy-only versus activation and applies the macOS evidence gate only to
    # activation.
    if bumps:
        print(
            "Version bump detected; no tag created. Run scripts/cut_release.py "
            "from clean main for the canonical signed release path."
        )
            
    # 7. Local Cleanup
    if not args.no_cleanup:
        cleanup_local_branch_and_worktree(head_ref, root)

    # 8. Inter-agent Notification
    if not args.no_notify:
        send_notification(repo, pr_number, title, bumps, root)

    print("Merge automation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
