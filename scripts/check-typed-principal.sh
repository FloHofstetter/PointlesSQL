#!/usr/bin/env bash
# Typed-principal drift guard.
#
# Routes read the authenticated user through the typed accessors in
# ``pointlessql.api.dependencies`` — ``get_user`` (zero-id placeholder
# for anonymous) or ``get_optional_user`` (``None``-preserving, for
# nullable actor columns).  Raw ``request.state.user`` access lives in
# exactly two owner modules: the auth middleware that produces it and
# the accessor module that wraps it.  This guard keeps new code from
# reverting to untyped dict plumbing.

set -euo pipefail

PATTERN='\.state\.user|state, "user"'

HITS="$(grep -rEn "$PATTERN" pointlessql/ --include='*.py' 2>/dev/null \
    | grep -v "pointlessql/api/middleware.py" \
    | grep -v "pointlessql/api/dependencies/_principal.py" || true)"

if [ -n "$HITS" ]; then
    cat >&2 <<'EOF'
ERROR: raw request.state.user access outside the owner modules.

Use the typed accessors instead:
  from pointlessql.api.dependencies import get_user           # placeholder for anonymous
  from pointlessql.api.dependencies import get_optional_user  # None for anonymous

Only pointlessql/api/middleware.py (producer) and
pointlessql/api/dependencies/_principal.py (accessors) may touch
request.state.user directly.

Offending lines:
EOF
    printf '%s\n' "$HITS" >&2
    exit 1
fi

echo "OK: request.state.user access is confined to the owner modules."
