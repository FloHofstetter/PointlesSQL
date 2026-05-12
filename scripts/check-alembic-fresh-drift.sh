#!/usr/bin/env bash
# Sprint H.4 — deeper alembic ORM ↔ deployed-DB drift gate.
#
# ``alembic check`` (run by the CI lint job after ``alembic upgrade
# head``) catches the common case where a model column was added
# without an accompanying migration.  It does NOT catch the inverse
# direction: things that exist in the historical migrations but were
# never propagated back to the ORM models (CHECK constraints, named
# FKs, partial / DESC indexes, server_defaults).  Those accumulate
# silently for years — see ``feedback_alembic_check_blind_spot.md``.
#
# This script performs a deeper drift check by:
#   1. Provisioning a fresh SQLite at ``/tmp/pql_drift_check/db``.
#   2. Running ``alembic upgrade head`` to apply every historical
#      migration.
#   3. Dumping the resulting ``.schema`` via the ``sqlite3`` CLI.
#   4. Running ``alembic check`` against the upgraded DB so the
#      autogen-drift gate ALSO runs (cheap double-check of the
#      direction CI already covers).
#   5. Surfacing the dump as a build artifact for human review.
#
# Intended for periodic manual or scheduled use, not as a per-commit
# pre-commit hook (sqlite3 CLI is not guaranteed on contributor
# machines and the gate is broader than per-commit value warrants).
#
# Usage: ``bash scripts/check-alembic-fresh-drift.sh``
#
# Exit codes:
#   0 — alembic upgrade head + alembic check both succeeded.
#   1 — autogen drift detected OR upgrade failed; review the diff
#       in the script output and patch ``pointlessql/models.py`` (the
#       fix lives in the model, never in a new migration that just
#       re-asserts the constraint).

set -euo pipefail

WORK_DIR="${WORK_DIR:-/tmp/pql_drift_check}"
DB_PATH="${WORK_DIR}/drift.sqlite"
SCHEMA_DUMP="${WORK_DIR}/schema.sql"

mkdir -p "${WORK_DIR}"
rm -f "${DB_PATH}" "${SCHEMA_DUMP}"

export POINTLESSQL_DB_URL="sqlite:///${DB_PATH}"

echo ">>> alembic upgrade head against fresh ${DB_PATH}"
uv run alembic upgrade head

echo ">>> alembic check (ORM ↔ generated migration drift)"
uv run alembic check

if command -v sqlite3 >/dev/null 2>&1; then
    echo ">>> dumping schema to ${SCHEMA_DUMP}"
    sqlite3 "${DB_PATH}" .schema > "${SCHEMA_DUMP}"
    echo ">>> schema dump head:"
    head -20 "${SCHEMA_DUMP}"
    echo "... ($(wc -l < "${SCHEMA_DUMP}") lines total — full dump at ${SCHEMA_DUMP})"
else
    echo ">>> sqlite3 CLI not on PATH — skipping schema dump." >&2
fi

echo ">>> drift check passed"
