/**
 * Phase 12 SQL editor Alpine factory — Sprint 91 façade.
 *
 * Sprint 75 Phase 4 made this an ES module; Sprint 91 split the
 * 608-LOC single-file shape into four focused sub-modules under
 * the same namespace:
 *
 *   - ``sql_editor_monaco.js``  — CodeMirror lifecycle +
 *     autocomplete + Cmd-Enter / Cmd-S keymap.
 *   - ``sql_editor_execute.js`` — ``run({explain})`` + ``cancel()``
 *     + elapsed-seconds counter.
 *   - ``sql_editor_saved.js``   — ``/api/saved-queries`` CRUD +
 *     load-into-editor flow.
 *   - ``sql_editor_chart.js``   — Chart.js view, axis auto-pick,
 *     debounced ``PATCH /api/queries/{id}/chart-config``.
 *
 * This file is now a state-only schema + ``Object.assign`` mixin
 * spread.  Closure state from the pre-split shape (``cmView`` +
 * ``catalogCompletions``) lives on ``this._cmView`` +
 * ``this._catalogCompletions`` so all four sub-modules can reach
 * the EditorView through ``this``.
 *
 * ``bootstrap.js`` still re-attaches ``sqlEditor`` to ``window``
 * unchanged — the split is invisible to the template's
 * ``x-data="sqlEditor"`` attribute.
 */

import { chartMethods } from './sql_editor_chart.js';
import { executeMethods } from './sql_editor_execute.js';
import { monacoMethods } from './sql_editor_monaco.js';
import { savedMethods } from './sql_editor_saved.js';

export function sqlEditor() {
    return {
        // -- Sprint 49 base state ---------------------------------------
        running: false,
        result: null,
        error: null,
        errorTitle: 'Query failed',
        referencedTables: [],
        lastRun: null,

        // -- Saved queries (Sprint 51) ----------------------------------
        saved: [],
        savedLoading: false,
        saving: false,
        saveForm: { title: '', description: '', is_shared: false },

        // -- Cancel + elapsed counter (Sprint 52) -----------------------
        currentQueryId: null,
        elapsedSeconds: 0,
        _tickHandle: null,

        // -- EXPLAIN (Sprint 53) ----------------------------------------
        explainText: null,

        // -- Chart view (Sprint 54) -------------------------------------
        // ``viewMode`` toggles between ``'table'`` (default) and
        // ``'chart'``.  ``chartConfig`` carries the user's current
        // selections; the null starts are guarded wherever x-text reads
        // them (Phase-12 trap #4).
        viewMode: 'table',
        chartConfig: { type: 'bar', x: null, y: null },
        _chartInstance: null,
        // Id of the history row the current ``result`` corresponds to.
        // Set by POST /api/sql/execute response (Sprint 54 extends that
        // payload with ``history_id``) and by the deep-link fetch in
        // ``seedFromHistory``.  Required so the debounced PATCH knows
        // which row to update.
        currentHistoryId: null,
        _chartSaveTimer: null,

        // -- Sprint 91: closure state promoted to ``this._*`` so the
        // four sub-modules can reach the EditorView + completions list
        // through ``this`` instead of a single-file closure variable.
        _cmView: null,
        _catalogCompletions: [],
        _onKeydown: null,

        // -- Methods (mixed in from the four sub-modules) ---------------
        ...monacoMethods,
        ...executeMethods,
        ...savedMethods,
        ...chartMethods,
    };
}
