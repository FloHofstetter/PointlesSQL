#!/usr/bin/env bash
# Raw-fetch budget (ratchet) for frontend/js.
#
# window.pqlApi.fetch is the house HTTP wrapper (CSRF + X-Workspace
# headers, JSON encode/decode, uniform error envelope, optional
# toasts).  Raw ``fetch(`` call sites predate it and re-implement
# error handling by hand; this ratchet freezes their count so new
# code uses the wrapper and the legacy sites migrate cluster by
# cluster.  Legitimate raw users (the wrapper itself, EventSource-
# adjacent code, the standalone embeds' minimal shims) are part of
# the frozen floor.
#
# Count is measured with a negative look-behind so ``pqlApi.fetch(``
# and other member calls don't match.
# 200: baseline at ratchet introduction.
# 200 -> 156: data-product overview panels + social + content moved
# onto pqlApi.fetch (44 sites).
BUDGET=156

count=$(grep -rPoh '(?<![.\w])fetch\(' frontend/js --include='*.js' | wc -l)

if [ "$count" -gt "$BUDGET" ]; then
    echo "ERROR: frontend/js has $count raw fetch( call sites (budget $BUDGET)." >&2
    echo "  Use window.pqlApi.fetch — it handles CSRF, X-Workspace, JSON and" >&2
    echo "  errors uniformly.  If a site genuinely cannot use the wrapper," >&2
    echo "  bump BUDGET with a one-line note explaining why." >&2
    exit 1
fi

echo "OK: frontend/js is at $count raw fetch( call sites (budget $BUDGET)."
