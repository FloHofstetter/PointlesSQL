#!/usr/bin/env bash
# Flip the soyuz-catalog-client source in pyproject.toml from the
# pinned git-tag back to an editable path dep on the sibling
# `../soyuz-catalog/soyuz-catalog-client` checkout, then `uv sync`.
#
# This is the dual-mode escape hatch for contributors iterating on
# soyuz-catalog itself: client-regen changes in the sibling repo
# surface here without a tag bump. Revert with use-pinned-soyuz.sh
# when you are done — the swap leaves pyproject.toml dirty on
# purpose so the state stays visible.
set -euo pipefail

cd "$(dirname "$0")/.."

SIBLING="../soyuz-catalog/soyuz-catalog-client"

if [[ ! -d "$SIBLING" ]]; then
    echo "error: sibling checkout '$SIBLING' is missing" >&2
    echo "hint:  clone https://github.com/FloHofstetter/soyuz-catalog next to PointlesSQL first" >&2
    exit 66
fi

if ! grep -q '^soyuz-catalog-client = { git = ' pyproject.toml; then
    if grep -q '^soyuz-catalog-client = { path = ' pyproject.toml; then
        echo "note: pyproject.toml already points at the editable path dep — nothing to swap" >&2
    else
        echo "error: pyproject.toml has no recognised soyuz-catalog-client source line" >&2
        exit 69
    fi
else
    echo ">>> swapping [tool.uv.sources] soyuz-catalog-client to editable path"
    # Anchored whole-line replace. Single quotes are fine because the
    # target line has none.
    sed -i -E \
        "s|^soyuz-catalog-client = \{ git = .*\}$|soyuz-catalog-client = { path = \"$SIBLING\", editable = true }|" \
        pyproject.toml
    if ! grep -q "^soyuz-catalog-client = { path = \"$SIBLING\", editable = true }$" pyproject.toml; then
        echo "error: swap did not apply cleanly — pyproject.toml was not modified" >&2
        exit 70
    fi
fi

echo ">>> uv sync"
uv sync --all-extras

cat <<EOF

==========================================================================
pyproject.toml now points at the editable sibling checkout. The file
is intentionally dirty — revert before committing anything on main:

    bash scripts/use-pinned-soyuz.sh

Or hand-discard:

    git restore pyproject.toml uv.lock
==========================================================================
EOF
