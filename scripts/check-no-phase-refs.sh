#!/usr/bin/env bash
# Frontend phase/sprint/wave/BUG-marker guard.
#
# Asserts the frontend tree stays free of project-management markers
# in source comments + docstrings + user-facing strings.  Backs the
# CLAUDE.md "Source comments + docstrings MUST NOT reference Phase /
# Sprint / Wave numbers or BUG-NN-NN markers" rule with a mechanical
# check so drift can't creep back in via routine edits.
#
# Scope covers frontend/ and pointlessql/.  alembic/versions/
# remains exempt project-wide — the phase tag in a migration
# filename + docstring is the schema-change identity, not project
# noise.

set -euo pipefail

TARGET_DIRS=("frontend" "pointlessql")

# Matches both the space-separated form ("Phase 97", "Sprint 21") AND the
# hyphenated form ("Phase-97", "Sprint-36.D", "Wave-B", "Plan-Agent-Phase-56")
# — the latter used to slip past the old ``\s+``-only pattern.  ``BUG-\w+``
# catches both ``BUG-12-34`` and the ``BUG-grand-08`` word form.
# Regression fixtures (must all be caught): Phase-97, Phase 97, Sprint-36.D,
# Wave-B, Plan-Agent-Phase-56, BUG-grand-08, BUG-12-34.
PATTERN='(Phase|Sprint|Wave)[-[:space:]]+\w+(\.\w+)*|BUG-\w+'

HITS="$(grep -rEn "$PATTERN" "${TARGET_DIRS[@]}" 2>/dev/null \
    | grep -v "pointlessql/alembic/versions/" || true)"

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
