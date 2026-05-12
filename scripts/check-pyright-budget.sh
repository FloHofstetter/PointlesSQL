#!/usr/bin/env bash
# Phase 35 Sprint 35.8 — Pyright warning-count regression gate.
#
# Phase 35's type-hardening work (35.5 / 35.6) brought the project
# from 531 to 522 pyright warnings.  The rest of the warnings are
# rooted in third-party stubs (pyarrow, pandas, deltalake) that
# Python-level annotations can't fix.  This gate freezes the count
# so future work doesn't silently regress: if a touched file adds
# a new ``reportUnknownX`` warning, CI fails with a clear pointer
# to update the BUDGET only after a deliberate decision.
#
# Errors must always be 0 — Pyright errors block merges.

set -euo pipefail

# Phase 36 Sprint 36.2 bumped from 522 → 528: the new
# ``services/dbt_bridge.py`` parses arbitrary JSON manifests and
# run-results, and the ``Any``-typed dict access cascades 6 partially-
# unknown warnings that no Python annotation can fix without a full
# TypedDict schema for dbt's manifest format (a multi-week effort
# upstream of pointlessql, given dbt's 70+ node fields).
#
# Phase 40 Sprint 40.1 bumped from 528 → 559: the new
# ``services/lineage/inbound_parser.py`` walks ``Any``-typed
# OpenLineage facets where every nested ``.get()`` cascades a
# partially-unknown warning.  Same shape as the dbt-bridge:
# producer-emitted JSON, no upstream TypedDict schema, would need
# the full OpenLineage 1.x spec (~50 facets) modelled to silence.
#
# Phase 45 lowered from 559 → 497: cleanup of api/* boundary casts
# (audit_sinks_routes, governance_routes, volumes_routes,
# home_routes) and cost_estimator narrowing, all at JSON / soyuz
# / DuckDB-plan deserialisation seams.  The remaining ~497 are
# rooted in PyArrow / deltalake / OpenLineage stubs that Python
# annotations cannot fix.
#
# Sprint H.2 (2026-05-12) raised from 497 → 585: the drift since
# Phase 45 accumulated in three predictable PyArrow-bottleneck
# files — ``pql/_merge.py`` (+120), ``pql/_autoload.py`` (+46),
# ``api/notebooks_routes.py`` (+34) — plus ``inbound_parser.py``
# (+31) and the ``scheduler/executors.py`` papermill bridge (+24).
# All five are JSON / PyArrow / DuckDB-result deserialisation
# seams whose call sites pyright cannot narrow without custom
# ``.pyi`` stubs (feedback_pyright_thirdparty_stubs.md — real fix
# is multi-week stub authoring, not single-sprint annotation).
# Errors-side, Sprint H.2 also drove ``error count: 28 → 0`` via
# (a) ``__all__`` in ``_bootstrap/_loops.py`` + per-import
# ``reportPrivateUsage`` ignores, (b) datetime/Literal narrowing in
# ``api/lens/sessions.py`` + ``notebook_kernel_ws.py``, (c) inline
# ``# pyright: ignore`` on the 9 OpenAI/Anthropic SDK type-strict
# sites in ``services/lens/llm_provider.py`` (Protocol ↔ Literal
# covariance pyright will not accept).
BUDGET=585

# Run pyright and capture the trailing summary line, e.g.
#   "0 errors, 522 warnings, 0 informations"
summary=$(uv run pyright pointlessql 2>&1 | grep -E '^[0-9]+ errors?,' | tail -1 || true)

if [ -z "$summary" ]; then
    echo "ERROR: could not parse pyright summary line" >&2
    echo "Run \`uv run pyright pointlessql\` manually to investigate." >&2
    exit 1
fi

errors=$(echo "$summary" | grep -oE '^[0-9]+' | head -1)
warnings=$(echo "$summary" | grep -oE '[0-9]+ warnings?' | head -1 | grep -oE '^[0-9]+')

if [ "$errors" -ne 0 ]; then
    echo "ERROR: pyright reports $errors error(s); errors must always be 0." >&2
    echo "Summary: $summary" >&2
    exit 1
fi

if [ "$warnings" -gt "$BUDGET" ]; then
    echo "ERROR: pyright reports $warnings warnings (budget $BUDGET)." >&2
    echo "  Either fix the new warnings or, if the increase is intentional," >&2
    echo "  bump BUDGET in scripts/check-pyright-budget.sh with a short note." >&2
    echo "Summary: $summary" >&2
    exit 1
fi

echo "OK: pyright is at $warnings warnings (budget $BUDGET, errors 0)."
exit 0
