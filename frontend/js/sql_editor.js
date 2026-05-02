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

        // -- EXPLAIN (Sprint 53; Sprint 23 added structured plan) -----
        explainText: null,
        explainPlan: null,
        explainShowJson: false,

        // Walk the parsed JSON plan returned by DuckDB's
        // ``enable_profiling='json'`` pragma into a flat list of
        // ``{ name, timing, cardinality, detail, depth, children, path }``
        // entries the template iterates over.  Skips the top-level
        // root (its operator info is empty) and starts at its
        // children — typically an ``EXPLAIN_ANALYZE`` wrapper, then
        // the actual plan.
        flattenPlan(node, depth, path = '') {
            if (!node) return [];
            const out = [];
            const children = Array.isArray(node.children) ? node.children : [];
            // Top-level root (depth 0) has no operator_name; descend
            // straight into its children at depth 0.
            if (depth === 0 && !node.operator_name) {
                for (let i = 0; i < children.length; i++) {
                    out.push(...this.flattenPlan(children[i], 0, `${i}`));
                }
                return out;
            }
            const name = node.operator_name || node.operator_type || 'UNKNOWN';
            const timing = (typeof node.operator_timing === 'number')
                ? node.operator_timing : null;
            const card = (typeof node.operator_cardinality === 'number')
                ? node.operator_cardinality : null;
            const extra = node.extra_info && typeof node.extra_info === 'object'
                ? node.extra_info : {};
            // Pick the most informative single line of extra_info to
            // render inline under the node.  Estimated Cardinality
            // and Projections are the most-asked-for, so prefer those.
            let detail = null;
            if (Array.isArray(extra.Projections) && extra.Projections.length > 0) {
                detail = 'Projections: ' + extra.Projections.slice(0, 3).join(', ')
                    + (extra.Projections.length > 3 ? ' …' : '');
            } else if (typeof extra.__text__ === 'string' && extra.__text__) {
                detail = extra.__text__;
            } else {
                const interesting = ['Filters', 'Conditions', 'Estimated Cardinality', 'Function'];
                for (const k of interesting) {
                    if (extra[k] != null) {
                        const v = Array.isArray(extra[k]) ? extra[k].join(', ') : String(extra[k]);
                        detail = `${k}: ${v}`;
                        break;
                    }
                }
            }
            out.push({
                name,
                timing,
                cardinality: card,
                detail,
                depth,
                children: children.length,
                path,
            });
            for (let i = 0; i < children.length; i++) {
                out.push(...this.flattenPlan(children[i], depth + 1, `${path}.${i}`));
            }
            return out;
        },

        // Compact human-readable byte formatting for the plan
        // header line (peak memory, etc.).  Mirrors the simple-units
        // pattern used in the catalog tree's volume sidebar.
        formatBytes(n) {
            if (n == null || isNaN(n)) return '';
            if (n < 1024) return `${n} B`;
            if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
            if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MiB`;
            return `${(n / 1024 / 1024 / 1024).toFixed(2)} GiB`;
        },

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
