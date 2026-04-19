#!/usr/bin/env bash
# Phase 12.7 Sprint 75 — bootstrap-before-alpine ordering gate.
#
# The ESM bridge entrypoint (frontend/js/bootstrap.js, loaded as
# ``<script type="module">``) registers factories on ``window`` before
# Alpine's x-data walk begins.  If Alpine's CDN script ran first, any
# factory consumed by an early x-data attribute would be undefined on
# first render.  This gate asserts base.html keeps the right order.

set -euo pipefail

BASE_HTML="${1:-frontend/templates/base.html}"

if [ ! -f "$BASE_HTML" ]; then
    echo "ERROR: base.html not found at $BASE_HTML" >&2
    exit 2
fi

BOOTSTRAP_LINE="$(grep -n '/static/js/bootstrap\.js' "$BASE_HTML" | head -n1 | cut -d: -f1 || true)"
ALPINE_LINE="$(grep -n 'alpinejs@' "$BASE_HTML" | head -n1 | cut -d: -f1 || true)"

if [ -z "$BOOTSTRAP_LINE" ]; then
    echo "ERROR: frontend/js/bootstrap.js <script> tag missing from $BASE_HTML" >&2
    exit 1
fi

if [ -z "$ALPINE_LINE" ]; then
    echo "ERROR: Alpine CDN <script> tag missing from $BASE_HTML" >&2
    exit 1
fi

if [ "$BOOTSTRAP_LINE" -ge "$ALPINE_LINE" ]; then
    cat >&2 <<EOF
ERROR: bootstrap.js must be loaded BEFORE the Alpine CDN script in $BASE_HTML.

  bootstrap.js line: $BOOTSTRAP_LINE
  alpine CDN line:   $ALPINE_LINE

Alpine walks the DOM and resolves x-data factories the moment its
script runs.  Any factory migrated out of a legacy IIFE file and into
bootstrap.js must have landed on ``window`` before that walk — which
only happens if bootstrap.js is earlier in the document.

See: frontend/js/bootstrap.js (Sprint 75 Phase 2 entrypoint)
EOF
    exit 1
fi

echo "OK — bootstrap.js (line $BOOTSTRAP_LINE) precedes Alpine CDN (line $ALPINE_LINE) in $BASE_HTML"
