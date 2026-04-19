#!/usr/bin/env bash
# Fetch the jsdiff (npm "diff") UMD bundle into frontend/js/vendor/.
#
# Phase 12.7 Sprint 73 — backs the per-cell run-history popover's
# source-diff rendering in frontend/js/notebook/run_history.js.
# Mirrors the Monaco / markdown-it vendoring pattern locked in by
# ADR 0001: fetch a pinned version's tarball from the npm registry,
# copy out the pre-built UMD bundle, write a VERSION file.  The
# vendored contents are gitignored; run this script once after
# ``git clone`` and any time DIFF_VERSION below changes.
#
# Library: https://github.com/kpdecker/jsdiff (MIT).  Exposes
# ``window.Diff`` with ``Diff.diffLines`` / ``Diff.createPatch`` /
# etc.  ~10 KB minified, no external deps, maintained.
set -euo pipefail

DIFF_VERSION="${DIFF_VERSION:-5.2.0}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENDOR="$REPO_ROOT/frontend/js/vendor"

fetch_tarball() {
    # $1 = npm package name, $2 = version, $3 = destination dir
    local pkg="$1" ver="$2" dest="$3"
    local url tmp
    url="https://registry.npmjs.org/${pkg}/-/$(basename "$pkg")-${ver}.tgz"
    tmp="$(mktemp -d)"
    trap "rm -rf '$tmp'" RETURN
    echo "==> Fetching ${pkg}@${ver}"
    curl -fsSL "$url" -o "$tmp/pkg.tgz"
    tar -xzf "$tmp/pkg.tgz" -C "$tmp"
    rm -rf "$dest"
    mkdir -p "$dest"
    mv "$tmp/package" "$dest/package"
    printf '%s\n' "$ver" > "$dest/VERSION"
}

# jsdiff: dist/diff.min.js (UMD) exposes window.Diff.
fetch_tarball diff "$DIFF_VERSION" "$VENDOR/jsdiff"
cp "$VENDOR/jsdiff/package/dist/diff.min.js" "$VENDOR/jsdiff/diff.min.js"
rm -rf "$VENDOR/jsdiff/package"

echo "==> Done."
echo "    diff (jsdiff)  ${DIFF_VERSION}  → $VENDOR/jsdiff/"
