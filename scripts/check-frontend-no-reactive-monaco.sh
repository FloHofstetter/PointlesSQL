#!/usr/bin/env bash
# Phase 12.7 Sprint 65 — BUG-64-02 reactivity-boundary gate.
#
# Fails when an Alpine x-data factory module under
# frontend/js/notebook/ stores a Monaco editor / model, a Web Worker,
# a raw WebSocket, or a save-debounce timer as `this._X = …`.
# Background and rationale: Sprint-64 commit 0af7984; helper at
# frontend/js/notebook/closure_state.js.
#
# Why these specific names: `editor` and `model` are the Monaco refs
# that triggered the original hang.  `monaco` and `worker` are
# proxies the same recursion would walk through.  `wsRaw`,
# `lspWsRaw`, and `saveTimer` are reserved for future modules so that
# new closures can't smuggle WS handles or timers back onto `this.X`
# under a different name and reproduce the class of bug.

set -euo pipefail

PATTERN='this\._(editor|model|monaco|worker|wsRaw|lspWsRaw|saveTimer)\s*='
SCAN_ROOT="${1:-frontend/js/notebook/}"

if [ ! -d "$SCAN_ROOT" ]; then
    echo "ERROR: scan root does not exist: $SCAN_ROOT" >&2
    exit 2
fi

if grep -RInE "$PATTERN" "$SCAN_ROOT"; then
    cat >&2 <<EOF

ERROR: BUG-64-02 reactivity-boundary lesson violated.

The lines above assign a high-risk reference (Monaco editor/model,
Web Worker, raw WebSocket, save timer) to a `this._X` field inside
the notebook editor module tree.  These objects MUST live in
closure scope — they break Alpine's deep-reactive Vue Proxy when
passed back to Monaco / Workers / circular-ref libraries.

See:
  - frontend/js/notebook/closure_state.js (createClosureRefs helper)
  - docs/e2e-walkthroughs/notebook-editor.md (BUG-64-02 entry)
  - commit 0af7984 (Sprint 64 fix)

EOF
    exit 1
fi

echo "OK — no Alpine-reactive Monaco/Worker/WS/timer refs in $SCAN_ROOT"
