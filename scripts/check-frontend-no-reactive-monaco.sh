#!/usr/bin/env bash
# Phase 12.7 Sprint 65 — BUG-64-02 reactivity-boundary gate.
#
# Fails when an Alpine x-data factory module under
# frontend/js/notebook/ stores a Monaco editor / model, a Web Worker,
# a raw WebSocket, a save-debounce timer, or a Sprint-66 per-cell
# affordance DOM ref as `this._X = …`.
# Background and rationale: Sprint-64 commit 0af7984; helper at
# frontend/js/notebook/closure_state.js.
#
# Why these specific names: `editor` and `model` are the Monaco refs
# that triggered the original hang.  `monaco` and `worker` are
# proxies the same recursion would walk through.  `wsRaw`,
# `lspWsRaw`, and `saveTimer` are reserved for future modules so that
# new closures can't smuggle WS handles or timers back onto `this.X`
# under a different name and reproduce the class of bug.  Sprint 66
# adds `cellAffordances`, `statusWidgets`, `cellWidgets`, and
# `reactiveRoot` so the toolbar content widget + inserter view zone
# + captured Alpine root stay in closure scope only.  Sprint 67 adds
# `treeFetchCtrl` / `treeAbort` so the sidebar's AbortController for
# inflight `/api/notebooks/tree` fetches stays closure-scoped — an
# AbortController wired into Alpine's proxy would trigger the same
# deep-reactivity walk the Monaco refs did.  Sprint 68 adds
# `tabRefs` and `tabFactories` so the multi-tab editor shell's
# per-tab closure-ref bags and tab-editor factory handles cannot be
# aggregated onto the shell's Alpine proxy — N tabs would otherwise
# reproduce BUG-64-02 at N× scale the moment the shell's reactive
# deep-walk reached into any tab's Monaco state.  Sprint 69 adds
# `mdSingleton`, `mdPinState`, and `pinHandlers` so the cached
# markdown-it instance, per-cell pin flags, and pin-toggle handler
# closures stay closure-scoped — markdown-it instances carry deep
# rule registries that Alpine's reactive walk would otherwise wrap.
# Sprint 70 adds `outlineEntries`, `outlineTimer`, and
# `outlineDebounce` so the right-side Outline panel's cached entry
# list and 150ms recompute-debounce timer stay closure-scoped — a
# `setTimeout` handle parked on Alpine's proxy would let the
# reactive deep-walk reach into the timer's captured closure
# (which holds the live `cells` array) on every re-render,
# reproducing the BUG-64-02 class the next time Monaco state grew
# a cycle.  Sprint 71 adds `resultVarTimers` and `sqlBootstrap` as
# belt-and-suspenders against future submodules — the SQL cell's
# 300ms result_var write-back debounce stays inside the toolbar's
# closure record (cleared on cell teardown via clearResultVarDebounce),
# but a future subsystem must not aggregate per-cell timer handles
# onto Alpine's proxy and rebuild the BUG-64-02 footgun.

set -euo pipefail

# Sprint 73 adds `historyCache`, `historyPopover`, and `historyAbort`
# so the per-cell run-history popover's module-scoped state — the
# `Map<cellId, runs>` cache, the singleton popover DOM node, and the
# in-flight AbortController for the `/api/notebook/cell-runs` fetch —
# never leak onto Alpine's proxy.  An AbortController on the proxy
# would let the reactive deep-walk reach into the WHATWG fetch
# stream's deep registry state, the same class as markdown-it's
# rule registries (BUG-69-01) and the BUG-64-02 footgun.
PATTERN='this\._(editor|model|monaco|worker|wsRaw|lspWsRaw|saveTimer|cellAffordances|statusWidgets|cellWidgets|reactiveRoot|treeFetchCtrl|treeAbort|tabRefs|tabFactories|mdSingleton|mdPinState|pinHandlers|outlineEntries|outlineTimer|outlineDebounce|resultVarTimers|sqlBootstrap|historyCache|historyPopover|historyAbort)\s*='
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
