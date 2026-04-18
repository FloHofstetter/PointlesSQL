#!/usr/bin/env bash
# Fetch the monaco-editor AMD distribution into frontend/js/vendor/monaco/.
#
# Phase 12.6 Sprint 58 — vendoring decision locked in ADR 0001. The
# repo does not carry a JS bundler, so we pull the pre-built ``min/vs``
# tree from the npm registry tarball and drop it under
# frontend/js/vendor/monaco/vs/. Contents are gitignored; run this
# script once after ``git clone`` and any time MONACO_VERSION changes.
set -euo pipefail

MONACO_VERSION="${MONACO_VERSION:-0.52.0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST="$REPO_ROOT/frontend/js/vendor/monaco"
TARBALL_URL="https://registry.npmjs.org/monaco-editor/-/monaco-editor-${MONACO_VERSION}.tgz"

echo "==> Vendoring monaco-editor ${MONACO_VERSION} → ${DEST}"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

curl -fsSL "$TARBALL_URL" -o "$tmp_dir/monaco.tgz"
tar -xzf "$tmp_dir/monaco.tgz" -C "$tmp_dir"

rm -rf "$DEST"
mkdir -p "$DEST"
cp -R "$tmp_dir/package/min/vs" "$DEST/vs"
printf '%s\n' "$MONACO_VERSION" > "$DEST/VERSION"

echo "==> Done. vendored files under ${DEST}/vs"
