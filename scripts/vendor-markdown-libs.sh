#!/usr/bin/env bash
# Fetch markdown-it, KaTeX, and markdown-it-texmath into
# frontend/js/vendor/, mirroring the Monaco vendoring pattern locked
# in by ADR 0001.
#
# Phase 12.7 Sprint 69 — replaces the regex markdown renderer in
# frontend/js/notebook/markdown.js with markdown-it, and adds KaTeX
# math rendering via markdown-it-texmath.  The repo carries no JS
# bundler, so each lib is pulled as its pre-built UMD bundle from
# the npm registry tarball and served as a global from
# notebook_editor.html.  Contents are gitignored; run this script
# once after ``git clone`` and any time one of the pinned versions
# below changes.
set -euo pipefail

MARKDOWN_IT_VERSION="${MARKDOWN_IT_VERSION:-14.1.0}"
TEXMATH_VERSION="${TEXMATH_VERSION:-1.0.0}"
KATEX_VERSION="${KATEX_VERSION:-0.16.11}"

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

# markdown-it: dist/markdown-it.min.js exposes window.markdownit (UMD).
fetch_tarball markdown-it "$MARKDOWN_IT_VERSION" "$VENDOR/markdown-it"
cp "$VENDOR/markdown-it/package/dist/markdown-it.min.js" "$VENDOR/markdown-it/markdown-it.min.js"
rm -rf "$VENDOR/markdown-it/package"

# markdown-it-texmath: ships as CommonJS only.  Append a one-line
# global binding so the UMD-style ``window.texmath`` reference in
# notebook_editor.html resolves when the script tag is parsed.  The
# function declaration itself hoists to the global anyway under
# script-mode (strict directive notwithstanding), but the explicit
# ``window.texmath = texmath`` makes the contract obvious to readers
# and survives any future minifier rename.
fetch_tarball markdown-it-texmath "$TEXMATH_VERSION" "$VENDOR/markdown-it-texmath"
cp "$VENDOR/markdown-it-texmath/package/texmath.js" "$VENDOR/markdown-it-texmath/texmath.js"
rm -rf "$VENDOR/markdown-it-texmath/package"
cat >> "$VENDOR/markdown-it-texmath/texmath.js" <<'TEXMATH_GLOBAL'

// PointlesSQL Sprint 69: expose as a browser global for the
// vendored UMD-style script-tag load in notebook_editor.html.
if (typeof window !== 'undefined') { window.texmath = texmath; }
TEXMATH_GLOBAL

# KaTeX: dist/katex.min.{js,css} + dist/fonts/.  The fonts directory
# is referenced by relative URL from katex.min.css — keep the layout
# (fonts/ as a sibling of katex.min.css) so the CSS resolves.
fetch_tarball katex "$KATEX_VERSION" "$VENDOR/katex"
cp "$VENDOR/katex/package/dist/katex.min.js" "$VENDOR/katex/katex.min.js"
cp "$VENDOR/katex/package/dist/katex.min.css" "$VENDOR/katex/katex.min.css"
cp -R "$VENDOR/katex/package/dist/fonts" "$VENDOR/katex/fonts"
rm -rf "$VENDOR/katex/package"

echo "==> Done."
echo "    markdown-it          ${MARKDOWN_IT_VERSION}  → $VENDOR/markdown-it/"
echo "    markdown-it-texmath  ${TEXMATH_VERSION}  → $VENDOR/markdown-it-texmath/"
echo "    katex                ${KATEX_VERSION}  → $VENDOR/katex/"
