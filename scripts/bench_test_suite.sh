#!/usr/bin/env bash
# Bench wrapper for the pytest suite.  Records wall clock + per-test
# durations into ``.bench/<timestamp>-<backend>.txt`` so Phase 31's
# before/after numbers are reproducible.
#
# Usage::
#
#     scripts/bench_test_suite.sh                   # SQLite, single worker
#     BACKEND=postgres scripts/bench_test_suite.sh  # PG via $TEST_DATABASE_URL
#     PYTEST_XDIST=auto scripts/bench_test_suite.sh # parallel
#
# The PG path requires ``TEST_DATABASE_URL`` to already point at a
# running PG (the docker-compose.postgres.yml lane is the canonical
# one).  We do not spin one up here on purpose — keeping the script
# trivial avoids container-lifecycle traps at bench time.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

backend="${BACKEND:-sqlite}"
mkdir -p .bench
ts="$(date -u +%Y%m%dT%H%M%SZ)"
out=".bench/${ts}-${backend}.txt"

xdist_args=()
if [[ -n "${PYTEST_XDIST:-}" ]]; then
    xdist_args=(-n "${PYTEST_XDIST}")
fi

case "${backend}" in
    sqlite)
        unset TEST_DATABASE_URL || true
        ;;
    postgres)
        if [[ -z "${TEST_DATABASE_URL:-}" ]]; then
            echo "BACKEND=postgres requires TEST_DATABASE_URL to be set" >&2
            exit 2
        fi
        ;;
    *)
        echo "Unknown BACKEND='${backend}' — expected 'sqlite' or 'postgres'" >&2
        exit 2
        ;;
esac

{
    echo "# bench run ${ts} backend=${backend} xdist=${PYTEST_XDIST:-off}"
    echo "# repo: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    echo
} >"${out}"

# ``time`` itself writes to stderr; tee both streams into the file.
# The exit code of pytest survives through ``set -o pipefail``.
{ time uv run pytest -q --durations=20 "${xdist_args[@]}" "$@" ; } 2>&1 | tee -a "${out}"

echo "Wrote ${out}"
