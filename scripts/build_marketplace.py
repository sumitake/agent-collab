#!/usr/bin/env python3
"""build_marketplace.py — compile the marketplace.json file from base and plugin fragments.

Usage:
  python3 scripts/build_marketplace.py
      Compile .claude-plugin/marketplace.json from base configuration and plugin fragments.
  python3 scripts/build_marketplace.py --check
      Diff the generated marketplace.json with the existing one. Exit 1 on divergence.
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.base.json"
OUTPUT_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"
CODEX_OUTPUT_PATH = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
PLUGINS_DIR = REPO_ROOT / "plugins"
CANONICAL_PACKAGE = "agent-collab"

def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="diff-only mode; exit 1 if working tree differs from generator output",
    )
    args = parser.parse_args(argv)

    if not BASE_PATH.exists():
        print(f"ERROR: Base file {BASE_PATH} does not exist.", file=sys.stderr)
        return 1

    marketplace = load_json(BASE_PATH)
    plugins = []
    codex_plugins = []

    package_dirs = sorted(item.name for item in PLUGINS_DIR.iterdir() if item.is_dir())
    if package_dirs != [CANONICAL_PACKAGE]:
        print(
            "ERROR: plugins/ must contain exactly one package directory: "
            f"{CANONICAL_PACKAGE}; found {package_dirs}",
            file=sys.stderr,
        )
        return 1

    for item in PLUGINS_DIR.iterdir():
        if not item.is_dir():
            continue
        
        # Look for fragment file in the plugin folder
        fragment_path = item / "marketplace-fragment.json"
        if not fragment_path.exists():
            fragment_path = item / ".claude-plugin" / "marketplace-fragment.json"
            if not fragment_path.exists():
                print(
                    f"ERROR: {item.name} is missing marketplace-fragment.json",
                    file=sys.stderr,
                )
                return 1

        # Look for plugin.json in the plugin .claude-plugin folder
        plugin_json_path = item / ".claude-plugin" / "plugin.json"
        if not plugin_json_path.exists():
            print(
                f"ERROR: {item.name} is missing plugin.json at {plugin_json_path}",
                file=sys.stderr,
            )
            return 1

        codex_plugin_json_path = item / ".codex-plugin" / "plugin.json"
        if not codex_plugin_json_path.exists():
            print(
                f"ERROR: {item.name} is missing Codex plugin.json at "
                f"{codex_plugin_json_path}",
                file=sys.stderr,
            )
            return 1

        fragment = load_json(fragment_path)
        plugin_info = load_json(plugin_json_path)
        codex_plugin_info = load_json(codex_plugin_json_path)
        if plugin_info.get("name") != CANONICAL_PACKAGE or item.name != CANONICAL_PACKAGE:
            print(
                "ERROR: package directory and plugin manifest must both be "
                f"named {CANONICAL_PACKAGE}",
                file=sys.stderr,
            )
            return 1
        if (
            codex_plugin_info.get("name") != plugin_info.get("name")
            or codex_plugin_info.get("version") != plugin_info.get("version")
        ):
            print(
                "ERROR: Claude and Codex plugin manifests must identify the same "
                "package and version",
                file=sys.stderr,
            )
            return 1

        entry = {
            "name": plugin_info.get("name", item.name),
            "description": fragment.get("description", plugin_info.get("description", "")),
            "version": plugin_info.get("version", "1.0.0"),
            "author": plugin_info.get("author", {}),
            "category": fragment.get("category", "ai-collaboration"),
            "tags": fragment.get("tags", []),
            "source": f"./plugins/{item.name}"
        }
        plugins.append(entry)
        codex_plugins.append(
            {
                "name": CANONICAL_PACKAGE,
                "source": {
                    "source": "local",
                    "path": f"./plugins/{CANONICAL_PACKAGE}",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Productivity",
            }
        )

    # Deterministic sorting by plugin name
    plugins.sort(key=lambda x: x["name"])
    marketplace["plugins"] = plugins

    # Dump to indented JSON
    rendered = json.dumps(marketplace, indent=2, ensure_ascii=False) + "\n"
    codex_rendered = json.dumps(
        {
            "name": "agent-collab",
            "interface": {"displayName": "Agent Collab"},
            "plugins": codex_plugins,
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"

    if args.check:
        mismatches = 0
        for output_path, expected in (
            (OUTPUT_PATH, rendered),
            (CODEX_OUTPUT_PATH, codex_rendered),
        ):
            current = (
                output_path.read_text(encoding="utf-8")
                if output_path.exists()
                else ""
            )
            if current == expected:
                continue
            mismatches += 1
            try:
                rel_path = output_path.relative_to(REPO_ROOT)
            except ValueError:
                rel_path = output_path
            print(f"DIFF: {rel_path}")
            for line in difflib.unified_diff(
                current.splitlines(keepends=True),
                expected.splitlines(keepends=True),
                fromfile=str(rel_path) + " (working tree)",
                tofile=str(rel_path) + " (generator output)",
            ):
                sys.stdout.write(line)
        if mismatches:
            print(
                "\nERROR: marketplace metadata diverges from generator output. "
                "Run `python3 scripts/build_marketplace.py` to regenerate.",
                file=sys.stderr
            )
            return 1
        print("OK: Claude and Codex marketplace metadata match generator output.")
        return 0

    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    CODEX_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CODEX_OUTPUT_PATH.write_text(codex_rendered, encoding="utf-8")
    print(
        "OK: wrote Claude and Codex marketplace metadata with "
        f"{len(plugins)} plugin(s)."
    )
    return 0

if __name__ == "__main__":
    sys.exit(main())
