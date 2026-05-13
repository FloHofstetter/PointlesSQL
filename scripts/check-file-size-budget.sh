#!/usr/bin/env bash
# Phase 35 Sprint 35.8 — File-size budget for pointlessql/**.py.
#
# After Sprint 35.1-35.3 (and the eventual 35.4 run_view extraction),
# the project no longer has any single source-of-truth file >800 LOC
# that mixes multiple concerns.  This gate prevents new mixed-concerns
# files from sneaking in: any pointlessql/**.py whose line count
# exceeds 800 fails CI unless it appears in the explicit allow-list
# below.
#
# Files in the allow-list are big-by-design — usually a public API
# surface (pql.py 788), a coherent settings tree (settings.py 721),
# or a frozen alembic migration (initial_schema.py 713).  Splitting
# them would create false seams.  When something legitimately new
# crosses the budget, ADD IT to the allow-list with a short comment
# explaining why — don't bump the budget number.

set -euo pipefail

BUDGET=800

# Files explicitly allowed above the budget, with the reason.
ALLOWLIST=(
    # Public PQL primitives — single coherent API surface.
    "pointlessql/pql/pql.py"
    # FastAPI app boot + middleware wiring; coherent module.
    "pointlessql/api/main.py"
    # Pydantic settings tree; splitting hurts discoverability.
    # Path was ``pointlessql/settings.py``; refactored to a package
    # ``pointlessql/config/_settings.py`` in a later sprint.  The
    # cohesive-tree rationale carries across the rename.
    "pointlessql/config/_settings.py"
    # Frozen alembic squash from Sprint 33-era housekeeping.
    "pointlessql/alembic/versions/b55f1020b8a4_initial_schema.py"
    # Cohesive scheduler core — Phase 21 ML registry adds.
    "pointlessql/services/scheduler/runs.py"
    # Cohesive jobs route surface; refused split in Phase 26 audit.
    "pointlessql/api/jobs_routes.py"
    # SQL editor route layer; cohesive query-handling concerns.
    # Path was ``pointlessql/api/sql_routes.py``; refactored into a
    # ``pointlessql/api/sql/`` package, but the two largest files
    # (``editor.py`` and ``_dispatcher.py``) still share the
    # dispatcher state machine.  Each is big-by-design; splitting
    # them would create cross-handler state-passing seams.
    "pointlessql/api/sql/editor.py"
    "pointlessql/api/sql/_dispatcher.py"
    # PQL merge primitive; cohesive write-path concerns.
    "pointlessql/pql/_merge.py"
    # Audit cockpit metrics + inbox routes; share filter / aggregator
    # service layer.  Sprint 35 audit deemed split a false seam.
    # Path was ``pointlessql/api/audit_routes.py``; refactored into a
    # ``pointlessql/api/audit/`` package; the bulk lives in
    # ``_legacy.py`` (the original module preserved through the
    # package split).
    "pointlessql/api/audit/_legacy.py"
    # Cohesive SQL aggregation layer; one shared filter / bin / metric
    # path used by summary / timeseries / anomalies endpoints.
    "pointlessql/services/audit_aggregator.py"
    # Operation recorder + lineage post-commit hooks tightly coupled
    # via the operation_context contract.
    "pointlessql/services/agent_runs/operations.py"
    # Cohesive dbt orchestration surface — Phase 36 (subprocess CLI
    # invocation + manifest read-only accessors + audit emit +
    # severity enforcement + auto-rollback).  Manifest projection
    # already lives in services/dbt_bridge.py; what remains here is
    # one file's worth of route handlers that share the
    # ``_run_or_test`` pipeline state.
    # Path was ``pointlessql/api/dbt_routes.py``; refactored into a
    # ``pointlessql/api/dbt/`` package later.  Same coherent-surface
    # rationale carries across the rename.
    "pointlessql/api/dbt/routes.py"
    # Admin console — cohesive admin-level dashboard + audit-export
    # + sink + review-destination + api-key + system-info pages.
    # Phase 75.1 added the tamper-evidence ``.tar.gz`` variant which
    # pushed the file past 800 LOC; the surface stays coherent
    # (one router, one auth gate, one filter helper-set).
    "pointlessql/api/admin/console.py"
)

is_allowed() {
    local path="$1"
    for allowed in "${ALLOWLIST[@]}"; do
        if [ "$path" = "$allowed" ]; then
            return 0
        fi
    done
    return 1
}

failed=0

while IFS= read -r path; do
    line_count=$(wc -l < "$path")
    if [ "$line_count" -gt "$BUDGET" ]; then
        if is_allowed "$path"; then
            continue
        fi
        echo "ERROR: $path is $line_count LOC (>${BUDGET})" >&2
        echo "  Either split the file (Phase 35 modularization pattern)" >&2
        echo "  or add it to ALLOWLIST in scripts/check-file-size-budget.sh" >&2
        echo "  with a short comment explaining why it is big-by-design." >&2
        failed=1
    fi
done < <(find pointlessql -name '*.py' -type f)

if [ $failed -eq 0 ]; then
    echo "OK: no pointlessql/**.py exceeds ${BUDGET} LOC outside the allowlist."
fi

exit $failed
