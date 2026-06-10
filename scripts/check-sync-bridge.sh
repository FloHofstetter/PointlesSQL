#!/usr/bin/env bash
# Sync-bridge drift guard for the request layer.
#
# The api/ tree dispatches blocking work through the app-owned pool
# via ``pointlessql.services._executor.run_sync`` — NOT through
# ``asyncio.to_thread`` (shared loop default executor) or raw
# ``run_in_executor``.  This guard keeps new request-path code from
# silently reverting to the shared pool.
#
# Allowlisted: ``api/_bootstrap/_loops/`` — the background tick loops
# (retention sweeps, badge/trending refreshes, api-key flushes) stay
# on ``asyncio.to_thread`` on purpose: the bounded request pool exists
# to isolate interactive latency FROM that work, so background jobs
# must not compete for its threads.

set -euo pipefail

PATTERN='asyncio\.to_thread\(|run_in_executor\('

HITS="$(grep -rEn "$PATTERN" pointlessql/api/ 2>/dev/null \
    | grep -v "pointlessql/api/_bootstrap/_loops/" || true)"

if [ -n "$HITS" ]; then
    cat >&2 <<'EOF'
ERROR: request-layer code bypasses the app executor.

Use ``from pointlessql.services._executor import run_sync`` and
``await run_sync(func, *args, **kwargs)`` instead of
``asyncio.to_thread`` / ``run_in_executor`` so blocking work lands on
the app-owned, settings-sized pool (and ContextVar propagation is
preserved).  Background loops belong under api/_bootstrap/_loops/,
which is allowlisted.

Offending lines:
EOF
    printf '%s\n' "$HITS" >&2
    exit 1
fi

echo "OK: api/ request paths route blocking work through run_sync."
