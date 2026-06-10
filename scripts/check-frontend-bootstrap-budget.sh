#!/usr/bin/env bash
# bootstrap.js window-global budget (ratchet).
#
# The legacy path registers every Alpine factory as a window global in
# frontend/js/bootstrap.js — every page pays for every factory.  The
# replacement is per-page entry modules under frontend/js/entries/
# (loaded by page_entry_loader.js via the data-pql-entry attribute).
# This ratchet freezes the global count so new page factories land as
# entries, and drops as page groups migrate.  Cross-page chrome
# (pqlApi, toast, sidebars, inline editors, time formatters) stays
# global by design — the floor is well above zero.
#
# 154: baseline at ratchet introduction.
# 154 -> 141: admin console factories moved to page entries.
# 141 -> 139: agent profile + hermes pages moved to page entries.
BUDGET=139

count=$(grep -c '^window\.' frontend/js/bootstrap.js)

if [ "$count" -gt "$BUDGET" ]; then
    echo "ERROR: frontend/js/bootstrap.js registers $count window globals (budget $BUDGET)." >&2
    echo "  New page factories belong in frontend/js/entries/<page>.js, loaded" >&2
    echo "  via {% block page_entry %} — not in bootstrap.js.  Only genuinely" >&2
    echo "  cross-page chrome may go global (then bump BUDGET with a note)." >&2
    exit 1
fi

if grep -q "from './entries/" frontend/js/bootstrap.js; then
    echo "ERROR: bootstrap.js must not import from ./entries/ — entries are" >&2
    echo "  page-scoped and loaded on demand by page_entry_loader.js." >&2
    exit 1
fi

echo "OK: bootstrap.js is at $count window globals (budget $BUDGET)."
