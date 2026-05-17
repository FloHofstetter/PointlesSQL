#!/usr/bin/env bash
# Phase 34 Sprint 34.1 — Grafana dashboard JSON + structural gate.
#
# The Grafana JSONs live in two places (SQLite + Postgres-dialect)
# and have to stay loadable + structurally consistent.  Grafana
# itself swallows malformed dashboards on provisioning startup
# (logs an error, leaves the panel-grid blank), which means a
# breaking edit can ship un-noticed unless the JSON is parsed at
# CI time.  This gate is the cheap pre-flight: parse both files,
# require a non-empty panels array, and check that every panel
# has the structural fields Grafana needs.

set -euo pipefail

DASHBOARDS=(
    "examples/grafana/dashboards/pointlessql_audit.json"
    "examples/grafana/postgres-dashboards/pointlessql_audit.json"
)

failed=0

for path in "${DASHBOARDS[@]}"; do
    if [ ! -f "$path" ]; then
        echo "ERROR: dashboard $path missing" >&2
        failed=1
        continue
    fi

    if ! python3 - "$path" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    with open(path) as fh:
        data = json.load(fh)
except json.JSONDecodeError as exc:
    print(f"ERROR: {path} is not valid JSON: {exc}", file=sys.stderr)
    sys.exit(1)

panels = data.get("panels")
if not isinstance(panels, list) or not panels:
    print(f"ERROR: {path} has no 'panels' array", file=sys.stderr)
    sys.exit(1)

required = {"id", "type", "title", "gridPos"}
ids = []
for idx, panel in enumerate(panels):
    if not isinstance(panel, dict):
        print(f"ERROR: {path} panel index {idx} is not an object", file=sys.stderr)
        sys.exit(1)
    missing = required - panel.keys()
    if missing:
        print(
            f"ERROR: {path} panel index {idx} (id={panel.get('id')}) "
            f"missing required keys: {sorted(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)
    ids.append(panel["id"])

dupes = [pid for pid in set(ids) if ids.count(pid) > 1]
if dupes:
    print(f"ERROR: {path} has duplicate panel IDs: {dupes}", file=sys.stderr)
    sys.exit(1)

print(f"OK — {path}: {len(panels)} panels, distinct IDs.")
PY
    then
        failed=1
    fi
done

if [ "$failed" -ne 0 ]; then
    exit 1
fi
