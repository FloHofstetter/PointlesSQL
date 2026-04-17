#!/usr/bin/env bash
# Sprint 39: version bump + changelog header flip + annotated tag.
#
# Usage: bash scripts/bump-version.sh <new-version>
#
#   <new-version>   PEP 440 version without leading "v" (e.g. 0.1.0rc1).
#                   The git tag will be "v${new-version}".
#
# Updates the single pyproject.toml version, re-locks uv.lock, renames
# the `## [Unreleased]` heading in CHANGELOG.md to
# `## [${new}] - <today>` and inserts a fresh `## [Unreleased]` block
# above it, commits ("chore(release): v${new}"), and creates an
# annotated tag. Does NOT push — print the push-command at the end so
# the whole action stays reversible up to that point.
#
# Mirrors soyuz-catalog's Sprint 19 script. Difference: PointlesSQL
# is a single-pyproject project (no client sub-package), so only one
# version line is bumped.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ $# -ne 1 ]]; then
    echo "usage: bash scripts/bump-version.sh <new-version>" >&2
    echo "example: bash scripts/bump-version.sh 0.1.0rc1" >&2
    exit 64
fi

NEW="$1"
TAG="v${NEW}"

# PEP 440 sanity-check. Covers the shapes we care about (X.Y.Z,
# X.Y.ZrcN, X.Y.Z.devN, X.Y.ZaN, X.Y.ZbN). Not the full PEP 440 grammar
# — if a user wants something exotic, that is their problem.
if ! [[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+((a|b|rc|\.dev|\.post)[0-9]+)?$ ]]; then
    echo "error: '$NEW' does not look like a PEP 440 version" >&2
    exit 65
fi

# Working tree must be clean of tracked-file changes. Untracked files
# (local SQLite dbs, scratch notebooks, …) are ignored — the user's
# runtime state is not a release concern.
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "error: working tree has uncommitted tracked changes — commit or stash before bumping" >&2
    git status --short --untracked-files=no >&2
    exit 66
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" != "main" ]]; then
    echo "error: must run on branch 'main' (currently on '$BRANCH')" >&2
    exit 67
fi

if git rev-parse --verify --quiet "refs/tags/$TAG" >/dev/null; then
    echo "error: tag '$TAG' already exists" >&2
    exit 68
fi

echo ">>> bumping pyproject.toml version to $NEW"

sed -i -E 's|^(version = )"[^"]+"|\1"'"$NEW"'"|' pyproject.toml

if ! grep -q "^version = \"$NEW\"$" pyproject.toml; then
    echo "error: pyproject.toml version did not update to $NEW" >&2
    exit 69
fi

echo ">>> re-locking uv.lock"
uv lock

echo ">>> flipping CHANGELOG.md [Unreleased] header to [$NEW]"

# Preserve the hand-written per-sprint prose inside `[Unreleased]`.
# Rename the heading to the release version + date, then insert a
# fresh `## [Unreleased]` block above the new release section. Fails
# loudly if the `[Unreleased]` heading is missing.
if ! grep -q '^## \[Unreleased\]$' CHANGELOG.md; then
    echo "error: CHANGELOG.md is missing the '## [Unreleased]' heading" >&2
    exit 70
fi

TODAY="$(date -u +%Y-%m-%d)"
python3 - "$NEW" "$TODAY" <<'PY'
import pathlib
import re
import sys

new_version, today = sys.argv[1], sys.argv[2]
path = pathlib.Path("CHANGELOG.md")
text = path.read_text()

# Anchored match: the heading must occupy a whole line. Prose mentions
# of `## [Unreleased]` elsewhere are not eligible. Exactly one heading
# expected.
heading_re = re.compile(r"^## \[Unreleased\]$", re.MULTILINE)
matches = heading_re.findall(text)
if len(matches) != 1:
    sys.exit(f"error: expected exactly one '## [Unreleased]' heading line, found {len(matches)}")
new_block = f"## [Unreleased]\n\n## [{new_version}] - {today}"
path.write_text(heading_re.sub(new_block, text, count=1))
PY

echo ">>> staging + committing"
git add \
    pyproject.toml \
    uv.lock \
    CHANGELOG.md
git commit -m "chore(release): $TAG"

echo ">>> creating annotated tag $TAG"
git tag -a "$TAG" -m "Release $TAG"

cat <<EOF

==========================================================================
Release commit + tag created locally. Nothing pushed.

To publish, run:

    git push origin main
    git push origin $TAG

The on-tag release.yml workflow will then build the wheel + sdist
and attach them to the GitHub Release.

To abort instead (before pushing):

    git tag -d $TAG
    git reset --hard HEAD~1
    uv lock  # refresh uv.lock back to the pre-bump state
==========================================================================
EOF
