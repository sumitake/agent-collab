#!/bin/bash
# Executable shell wrapper around merge-and-tag.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/merge-and-tag.py" "$@"
