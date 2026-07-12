#!/bin/bash
# install-hooks.sh — Configure Git to use custom version-controlled hooks

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Configuring git hooks path in $REPO_ROOT..."
git -C "$REPO_ROOT" config core.hooksPath .githooks

echo "Making hook scripts executable..."
if [ -d "$REPO_ROOT/.githooks" ]; then
    chmod +x "$REPO_ROOT"/.githooks/*
fi

echo "Git hooks successfully installed and activated!"
