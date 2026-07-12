#!/usr/bin/env python3
"""Pre-push hook to validate the compliance trace on an open GitHub pull request.

If there is an open PR for the current branch, it parses the PR body and
verifies the C2 (format) and C3 (cross-check verdict) compliance checks.
If no PR is found, the push is allowed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Add scripts directory to sys.path to import check_pr_compliance
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import check_pr_compliance as cpc
except ImportError:
    cpc = None


def run_cmd(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    # Clear invalid environment token
    env = dict(os.environ)
    env["GITHUB_TOKEN"] = ""
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    
    # 1. Check if check_pr_compliance could be loaded
    if cpc is None:
        print("Warning: check_pr_compliance.py not found. Pre-push check skipped.", file=sys.stderr)
        return 0

    # 2. Get current branch name
    res = run_cmd(["git", "symbolic-ref", "--short", "HEAD"], cwd=root)
    branch = res.stdout.strip()
    if not branch:
        # Detached HEAD -> allow push
        return 0

    # Never block pushes on main or if branch is empty
    if branch == "main":
        return 0

    # 3. Query GitHub for a PR on the current branch
    print(f"Pre-push: Checking compliance trace for branch '{branch}'...")
    res = run_cmd(["gh", "pr", "view", "--json", "body,state,number"], cwd=root)
    if res.returncode != 0:
        # No PR exists yet -> allow push
        print(f"No open pull request found on GitHub for branch '{branch}'. Skipping check.")
        return 0

    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        print("Warning: Failed to parse gh output. Skipping check.", file=sys.stderr)
        return 0

    # Check if PR is open
    if data.get("state") != "OPEN":
        print(f"Pull request #{data.get('number')} is not open ({data.get('state')}). Skipping check.")
        return 0

    body = data.get("body", "")
    pr_number = data.get("number")
    print(f"Found open pull request #{pr_number}. Validating compliance trace...")

    # 4. Parse trace block (C2 check)
    trace, trace_errors = cpc.parse_trace_block(body)
    if trace_errors:
        print("=" * 68, file=sys.stderr)
        print(f"PUSH BLOCKED: Pull request #{pr_number} has an invalid compliance trace:", file=sys.stderr)
        for err in trace_errors:
            print(f"  - {err}", file=sys.stderr)
        print("-" * 68, file=sys.stderr)
        print("To fix, update the PR description to include a valid compliance trace.", file=sys.stderr)
        print("If this is an emergency, push with: git push --no-verify", file=sys.stderr)
        print("=" * 68, file=sys.stderr)
        return 1

    # 5. Check cross-check verdict (C3 check)
    # Thread the declared `tier` into cross_check_ok so the local pre-push hook
    # agrees with the authoritative gates: cross_check_ok gates the 'N/A'
    # exemption on the parsed tier (PASS only at Tier 1). Omitting tier here made
    # every tier read as None -> fail-safe strict, wrongly rejecting a legitimate
    # Tier-1 'N/A' and blocking valid pure-documentation pushes. This mirrors
    # check_pr_compliance.py's own C3 call, cross_check_ok parses the raw value.
    c3_ok, c3_detail = cpc.cross_check_ok(trace.get("cross_check", ""), tier=trace.get("tier"))
    if not c3_ok:
        print("=" * 68, file=sys.stderr)
        print(f"PUSH BLOCKED: Pull request #{pr_number} cross-check verdict check failed:", file=sys.stderr)
        print(f"  - {c3_detail}", file=sys.stderr)
        print("-" * 68, file=sys.stderr)
        print("The cross-check verdict must contain 'PROCEED' or 'N/A' to push changes.", file=sys.stderr)
        print("If this is an emergency, push with: git push --no-verify", file=sys.stderr)
        print("=" * 68, file=sys.stderr)
        return 1

    print("✓ PR compliance trace is valid and cross-check verdict indicates PROCEED/NA.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
