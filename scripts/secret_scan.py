#!/usr/bin/env python3
"""Dependency-free secret scanner for CI.

Scans tracked and non-ignored untracked text files for high-signal credential patterns. Self-contained
(stdlib only -- no external binary, no network download, no license) by design:
this removes the gitleaks-binary's external-URL / version-pinning fragility that
the Initiative-A cross-check flagged. The pattern set targets this repo's real
exposure surface (a GitHub PAT incident) plus standard high-confidence
credential shapes -- distinctive prefixes only, for a near-zero false-positive
rate.

There is no inline suppression marker. Any future false-positive exception must
be an exact reviewed ``(path, label, line_sha256)`` entry below, so appending a
comment to a real credential can never suppress it.

Run: python scripts/secret_scan.py
Exit: 0 = clean, 1 = a candidate secret found, 2 = could not scan.
"""
from __future__ import annotations

import re
import hashlib
import stat
import subprocess
import sys
from pathlib import Path

# (label, compiled regex) -- distinctive shapes only; near-zero false positives.
PATTERNS = [
    ("GitHub token", re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{36}\b")),
    ("GitHub fine-grained PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("private key block", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
]

# Never scanned: this scanner itself defines the patterns above as literals.
SKIP_PATHS = {"scripts/secret_scan.py"}
ALLOWLISTED_FINDINGS: frozenset[tuple[str, str, str]] = frozenset()


def _source_files(root: Path) -> list[str]:
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"secret-scan: cannot list source files: {e}", file=sys.stderr)
        sys.exit(2)
    if out.returncode != 0:
        print("secret-scan: 'git ls-files' failed -- not a git repo?", file=sys.stderr)
        sys.exit(2)
    return [ln for ln in out.stdout.splitlines() if ln]


def scan_tree(root: Path) -> tuple[list[str], int, list[str]]:
    findings: list[str] = []
    errors: list[str] = []
    scanned = 0
    for rel in _source_files(root):
        if rel in SKIP_PATHS or "/.venv/" in f"/{rel}":
            continue
        path = root / rel
        try:
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                errors.append(f"{rel}: source member is not a regular file")
                continue
            data = path.read_bytes()
        except OSError as exc:
            errors.append(f"{rel}: cannot read source bytes: {type(exc).__name__}")
            continue
        text = data.decode("latin-1")
        scanned += 1
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pat in PATTERNS:
                if pat.search(line):
                    line_digest = hashlib.sha256(
                        line.encode("latin-1")
                    ).hexdigest()
                    if (rel, label, line_digest) in ALLOWLISTED_FINDINGS:
                        continue
                    findings.append(f"{rel}:{lineno}: {label}")
    return findings, scanned, errors


def main(root: Path | None = None) -> int:
    root = root or Path(__file__).resolve().parents[1]
    findings, scanned, errors = scan_tree(root)
    print(f"secret-scan: scanned {scanned} source text files")
    if errors:
        print("\nSECRET SCAN INCOMPLETE:")
        for error in errors:
            print(f"  x {error}")
        return 2
    if findings:
        print("\nPOTENTIAL SECRETS FOUND:")
        for f in findings:
            print(f"  x {f}")
        print("\nFalse-positive exceptions require an exact reviewed path, label, and line digest.")
        return 1
    print("secret-scan: clean -- no credential patterns detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
