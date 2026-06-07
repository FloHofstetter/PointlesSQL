#!/usr/bin/env bash
# Per-operation latency budget gate.
#
# Compares the measured p95 latency of each named performance scenario
# against a frozen budget, the same floor-ratchet shape as
# check-file-size-budget.sh and check-pyright-budget.sh: a deliberate
# regression must bump the budget (with a reason) on purpose, so it can
# never creep in silently.
#
# Inputs:
#   scripts/perf-budget.json   -- the budgets (committed, audited)
#   .bench/perf-latest.json    -- the latest measured p95s, written by the
#                                 perf harness (tests/perf/, run nightly).
#
# The perf harness is intentionally NOT part of the fast PR gate -- its
# fixtures (1M-row audit corpus, 10k-edge lineage DAG) are too heavy. This
# gate therefore no-ops cleanly when no results file is present yet, so it
# can be wired into CI immediately and start enforcing once the nightly
# run has produced data.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUDGET_FILE="${PERF_BUDGET_FILE:-${REPO_ROOT}/scripts/perf-budget.json}"
RESULTS_FILE="${PERF_RESULTS_FILE:-${REPO_ROOT}/.bench/perf-latest.json}"

if [[ ! -f "${BUDGET_FILE}" ]]; then
  echo "perf-budget: budget file not found at ${BUDGET_FILE}" >&2
  exit 1
fi

if [[ ! -f "${RESULTS_FILE}" ]]; then
  echo "perf-budget: no results at ${RESULTS_FILE} yet -- run the perf harness"
  echo "perf-budget: (tests/perf/, nightly) to populate it. Skipping gate."
  exit 0
fi

python3 - "${BUDGET_FILE}" "${RESULTS_FILE}" <<'PY'
import json
import sys

budget_path, results_path = sys.argv[1], sys.argv[2]

with open(budget_path, encoding="utf-8") as fh:
    budgets = json.load(fh).get("budgets_ms", {})
with open(results_path, encoding="utf-8") as fh:
    results = json.load(fh).get("results_ms", {})

if not budgets:
    print("perf-budget: no budgets defined; nothing to check.")
    sys.exit(0)

violations = []
checked = 0
for name, budget in sorted(budgets.items()):
    measured = results.get(name)
    if not isinstance(measured, dict) or "p95" not in measured:
        # No measurement for this scenario this run -- not a regression.
        continue
    checked += 1
    p95 = float(measured["p95"])
    if p95 > float(budget):
        violations.append((name, p95, float(budget)))

if violations:
    print("perf-budget: FAIL -- measured p95 exceeds budget:")
    for name, p95, budget in violations:
        print(f"  {name}: {p95:.1f} ms > {budget:.1f} ms budget")
    print("Optimize the hot path, or bump scripts/perf-budget.json with a reason.")
    sys.exit(1)

print(f"perf-budget: OK -- {checked} scenario(s) within budget.")
PY
