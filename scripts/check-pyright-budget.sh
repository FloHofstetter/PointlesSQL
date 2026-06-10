#!/usr/bin/env bash
# Pyright warning-count regression gate.
#
# Errors must always be 0 — Pyright errors block merges.
#
# Warnings are frozen at a budget so future work cannot silently
# regress type-clarity.  The budget is NOT zero because the bulk of
# the warnings are rooted in incomplete third-party stubs that no
# Python-level annotation can fix:
#
#   * PyArrow / pandas / Delta Lake — ``pa.Table`` / ``ChunkedArray`` /
#     DataFrame operations are typed ``Unknown`` in the shipped stubs,
#     so even a fully-annotated ``table: pa.Table`` parameter trips
#     ``reportUnknownParameterType`` / ``reportUnknownMemberType``.
#   * DuckDB result objects — same shape at the query-result seam.
#   * pycrdt (``Doc`` / ``Map``) — co-edit CRDT handles are
#     ``Doc[Unknown]`` in the stubs.
#   * OpenLineage / yaml / JSON payloads — producer-emitted documents
#     decoded with ``json.loads`` / ``yaml.safe_load`` are ``Any``;
#     walking them with ``.get()`` chains cascades partially-unknown
#     warnings.  A full TypedDict model of every facet is upstream
#     work, not a single-pass annotation.
#   * A set of ``reportUnnecessaryIsInstance`` warnings are deliberate
#     defensive checks against generated-client responses (see
#     ``[tool.pyright]`` in pyproject.toml) — kept on purpose.
#
# The only way to drive the count toward zero is custom ``.pyi`` stub
# authoring for the libraries above, which is out of scope for routine
# changes.  When a deliberate change legitimately adds warnings, bump
# BUDGET here with a one-line note; when refactoring removes the
# underlying third-party seam, lower it.
#
# 966 -> 965: extracting the papermill output-frame transform into a
# typed pure helper dropped one partially-unknown nbformat seam.
# 965 -> 962: extracting the replay-worker frame builders into typed
# pure helpers dropped three more untyped-dict seams.
# 962 -> 1029: the backup / data-quality / SLO / tracing / canvas-df
# backbones landed new PyArrow + pandas + subprocess seams (54 of the
# 67 sit in quality/_expectations.py alone); driving them back down
# needs the .pyi stub-authoring pass described above.
BUDGET=1029

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
