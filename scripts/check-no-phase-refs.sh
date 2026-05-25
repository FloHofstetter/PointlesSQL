#!/usr/bin/env bash
# Frontend phase/sprint/wave/BUG-marker guard.
#
# Asserts the frontend tree stays free of project-management markers
# in source comments + docstrings + user-facing strings.  Backs the
# CLAUDE.md "Source comments + docstrings MUST NOT reference Phase /
# Sprint / Wave numbers or BUG-NN-NN markers" rule with a mechanical
# check so drift can't creep back in via routine edits.
#
# Scope is intentionally limited to frontend/ today: pointlessql/
# still carries ~107 historical refs in module docstrings that
# pre-date the rule, and tightening the gate broader without first
# scrubbing them would block every commit.  A follow-up wave can
# clean pointlessql/ and then widen this script's scope.
#
# alembic/versions/ stays exempt project-wide — the phase tag in a
# migration is the schema-change identity, not project noise.

set -euo pipefail

TARGET_DIRS=("frontend")

PATTERN='(Phase|Sprint|Wave)\s+\w+(\.\w+)*|BUG-\d+'

HITS="$(grep -rEn "$PATTERN" "${TARGET_DIRS[@]}" 2>/dev/null || true)"

if [ -n "$HITS" ]; then
    cat >&2 <<'EOF'
ERROR: frontend source contains project-management markers
(Phase / Sprint / Wave / BUG-NN-NN).  These belong in
ROADMAP.md + CHANGELOG.md + git history, not in source comments
or user-facing strings.

See CLAUDE.md "Conventions" section for the full rule.

Offending lines:
EOF
    printf '%s\n' "$HITS" >&2
    exit 1
fi
