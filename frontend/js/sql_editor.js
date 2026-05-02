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
        // operator entries the template iterates over.
        //
        // Skips:
        //   * The top-level profiling root (no operator_name; just
        //     query-wide totals shown in the header).
        //   * The ``EXPLAIN_ANALYZE`` wrapper (instrumentation node,
        //     not actual query work).
        //
        // Each entry carries name, kind (scan / filter / join / agg /
        // limit / proj / other) for badge colouring, timing, row
        // cardinality, every extra_info field as a list of
        // ``[label, value]`` pairs, depth, and child count.
        flattenPlan(node, depth, path = '') {
            if (!node) return [];
            const out = [];
            const children = Array.isArray(node.children) ? node.children : [];
            const name = node.operator_name || node.operator_type;
            // Top-level profiling root has no operator_name; descend.
            if (depth === 0 && !name) {
                for (let i = 0; i < children.length; i++) {
                    out.push(...this.flattenPlan(children[i], 0, `${i}`));
                }
                return out;
            }
            // EXPLAIN_ANALYZE is the wrapper that adds the profiling
            // hooks — not actual query work.  Skip it but keep
            // walking its children at the same depth.
            if (name === 'EXPLAIN_ANALYZE') {
                for (let i = 0; i < children.length; i++) {
                    out.push(...this.flattenPlan(children[i], depth, `${path}.${i}`));
                }
                return out;
            }
            const timing = (typeof node.operator_timing === 'number')
                ? node.operator_timing : null;
            const card = (typeof node.operator_cardinality === 'number')
                ? node.operator_cardinality : null;
            const extra = node.extra_info && typeof node.extra_info === 'object'
                ? node.extra_info : {};
            // Capture every extra_info entry the template can render
            // as a small key/value table under the node.  Keep the
            // first 4 entries each up to ~3 array items so the row
            // does not turn into a wall of text.
            const details = [];
            for (const [k, v] of Object.entries(extra)) {
                if (k.startsWith('__')) continue;
                if (v == null || v === '') continue;
                let rendered;
                if (Array.isArray(v)) {
                    if (v.length === 0) continue;
                    rendered = v.slice(0, 3).join(', ');
                    if (v.length > 3) {
                        rendered += `  (+${v.length - 3} more)`;
                    }
                } else {
                    rendered = String(v);
                }
                details.push([k, rendered]);
                if (details.length >= 4) break;
            }
            out.push({
                name,
                kind: this._classifyOperator(name),
                timing,
                cardinality: card,
                details,
                depth,
                hasChildren: children.length > 0,
                path,
            });
            for (let i = 0; i < children.length; i++) {
                out.push(...this.flattenPlan(children[i], depth + 1, `${path}.${i}`));
            }
            return out;
        },

        // Bucket the DuckDB operator name into one of seven kinds the
        // CSS uses to colour the badge.  The mapping is approximate
        // and intentionally forgiving — any unrecognised operator
        // gets the neutral ``other`` colour.
        _classifyOperator(name) {
            if (!name) return 'other';
            const u = name.toUpperCase();
            if (u.includes('SCAN')) return 'scan';
            if (u.includes('FILTER')) return 'filter';
            if (u.includes('JOIN')) return 'join';
            if (u.includes('AGG') || u.includes('GROUP')) return 'agg';
            if (u.includes('LIMIT') || u.includes('TOP_N')) return 'limit';
            if (u.includes('PROJECT')) return 'proj';
            if (u.includes('SORT') || u.includes('ORDER')) return 'sort';
            return 'other';
        },

        // Format a duration in seconds as either microseconds or
        // milliseconds, depending on magnitude.  DuckDB returns very
        // small operator timings (sub-millisecond) for cheap
        // operations; rounding to ``0.00 ms`` was unhelpful.
        formatTiming(seconds) {
            if (seconds == null) return '';
            if (seconds < 0.001) return `${(seconds * 1_000_000).toFixed(0)} µs`;
            if (seconds < 1) return `${(seconds * 1000).toFixed(2)} ms`;
            return `${seconds.toFixed(3)} s`;
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
