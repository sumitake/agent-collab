#!/usr/bin/env python3
"""Extract one version's compiled section from CHANGELOG.md.

Release notes are generated FROM the compiled changelog so the GitHub Release
body always carries the same description as CHANGELOG.md (operator direction
2026-08-19: no more generic boilerplate notes). The extraction FAILS CLOSED:
a missing or empty section exits non-zero so the release step cannot publish
a release whose notes silently dropped the changelog content.

Grammar (produced by build-changelog.py): a version section starts at a line
beginning ``### agent-collab <version>`` (an em-dash suffix with a date or
title may follow) and ends at the next ``### agent-collab `` heading, the
fragments-end marker, or the next ``## `` heading. The FIRST match wins —
historical duplicate version headings exist further down the file.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def extract_section(changelog_text: str, version: str) -> str:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"version {version!r} is not a bare semantic version")
    heading = re.compile(
        r"^### agent-collab " + re.escape(version) + r"(?![\d.])", re.MULTILINE
    )
    match = heading.search(changelog_text)
    if match is None:
        raise ValueError(f"CHANGELOG.md has no section for version {version}")
    tail = changelog_text[match.start():]
    body_start = tail.index("\n") + 1
    end = re.compile(
        r"^(?:### agent-collab |## |<!-- changelog-fragments:end)", re.MULTILINE
    )
    stop = end.search(tail, body_start)
    section = tail[: stop.start()] if stop else tail
    section = section.strip()
    # The heading alone (no body) is as wrong as no section at all.
    if section.splitlines()[1:] == [] or not "".join(section.splitlines()[1:]).strip():
        raise ValueError(f"CHANGELOG.md section for version {version} is empty")
    return section


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="bare semantic version, e.g. 6.1.1")
    parser.add_argument(
        "--changelog",
        default=str(Path(__file__).resolve().parents[1] / "CHANGELOG.md"),
        help="path to CHANGELOG.md (default: repository root)",
    )
    args = parser.parse_args()
    try:
        text = Path(args.changelog).read_text(encoding="utf-8")
        print(extract_section(text, args.version))
    except (OSError, ValueError) as exc:
        print(f"extract-changelog-section: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
