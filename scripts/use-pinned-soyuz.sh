#!/usr/bin/env bash
# Revert pyproject.toml + uv.lock back to the pinned git-tag
# soyuz-catalog-client source from HEAD, then `uv sync`.
#
# Counterpart to use-editable-soyuz.sh. Safe to run at any time: if
# pyproject.toml + uv.lock already match HEAD, the restore is a
# no-op and `uv sync` just re-verifies the environment.
set -euo pipefail

cd "$(dirname "$0")/.."

echo ">>> restoring pyproject.toml + uv.lock from HEAD"
git restore --source=HEAD --staged --worktree pyproject.toml uv.lock

if ! grep -q '^soyuz-catalog-client = { git = ' pyproject.toml; then
    echo "error: HEAD's pyproject.toml does not contain the expected pinned git-tag source" >&2
    echo "       (run this from 'main' or a branch based off it)" >&2
    exit 69
fi

echo ">>> uv sync"
uv sync --all-extras

cat <<EOF

==========================================================================
pyproject.toml is back on the pinned git-tag soyuz-catalog-client
source. uv.lock matches HEAD.
==========================================================================
EOF
