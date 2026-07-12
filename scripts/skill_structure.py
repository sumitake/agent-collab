#!/usr/bin/env python3
"""Single-source the exact generated skill-tree contract."""

from __future__ import annotations

import stat
from pathlib import Path


def spec_names(specs_dir: Path) -> tuple[str, ...]:
    """Return every publishable spec name in deterministic order."""
    if not specs_dir.is_dir():
        return ()
    return tuple(
        sorted(
            path.stem
            for path in specs_dir.glob("*.md")
            if not path.name.startswith("_") and path.name != "README.md"
        )
    )


def expected_skill_relpaths(specs_dir: Path) -> tuple[Path, ...]:
    """Return the exact children permitted below a generated skills root."""
    result: list[Path] = []
    for name in spec_names(specs_dir):
        result.extend((Path(name), Path(name) / "SKILL.md"))
    return tuple(result)


def skill_tree_differences(skills_root: Path, specs_dir: Path) -> tuple[str, ...]:
    """Describe missing, unexpected, symlinked, or mistyped skill members."""
    expected = set(expected_skill_relpaths(specs_dir))
    if not skills_root.exists() or skills_root.is_symlink() or not skills_root.is_dir():
        return ("skills root is missing, symlinked, or not a directory",)
    observed = {path.relative_to(skills_root) for path in skills_root.rglob("*")}
    differences = [
        *(f"missing:{path.as_posix()}" for path in sorted(expected - observed)),
        *(f"unexpected:{path.as_posix()}" for path in sorted(observed - expected)),
    ]
    for relative in sorted(expected & observed):
        path = skills_root / relative
        try:
            info = path.lstat()
        except OSError:
            differences.append(f"unreadable:{relative.as_posix()}")
            continue
        expected_directory = relative.name != "SKILL.md"
        valid_type = (
            stat.S_ISDIR(info.st_mode)
            if expected_directory
            else stat.S_ISREG(info.st_mode)
        )
        if stat.S_ISLNK(info.st_mode) or not valid_type:
            differences.append(f"unsafe_type:{relative.as_posix()}")
    return tuple(sorted(differences))
