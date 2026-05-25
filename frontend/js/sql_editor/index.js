/**
 * SQL editor Alpine factory — façade.
 *
 * The 608-LOC single-file shape was split into four focused
 * sub-modules under the same namespace:
 *
 * - ``sql_editor_monaco.js`` — CodeMirror lifecycle +
 * autocomplete + Cmd-Enter / Cmd-S keymap.
 * - ``sql_editor_execute.js`` — ``run({explain})`` + ``cancel()``
 * + elapsed-seconds counter.
 * - ``sql_editor_saved.js`` — ``/api/saved-queries`` CRUD +
 * load-into-editor flow.
 * - ``sql_editor_chart.js`` — Chart.js view, axis auto-pick,
 * debounced ``PATCH /api/queries/{id}/chart-config``.
 *
 * This file is now a state-only schema + ``Object.assign`` mixin
 * spread. Closure state from the pre-split shape (``cmView`` +
 * ``catalogCompletions``) lives on ``this._cmView`` +
 * ``this._catalogCompletions`` so all four sub-modules can reach
 * the EditorView through ``this``.
 *
 * ``bootstrap.js`` still re-attaches ``sqlEditor`` to ``window``
 * unchanged — the split is invisible to the template's
 * ``x-data="sqlEditor"`` attribute.
 */

import { builderMethods } from './builder.js';
import { chartMethods } from './chart.js';
import { executeMethods } from './execute.js';
import { monacoMethods } from './monaco.js';
import { savedMethods } from './saved.js';

export function sqlEditor() {
  return {
    // -- base state ---------------------------------------
    running: false,
    result: null,
    error: null,
    errorTitle: 'Query failed',
    referencedTables: [],
    lastRun: null,

    // -- Chat drawer toggle (consumed by the
    // sql_editor/chat_drawer.html partial and chat.js
    // factory; opening the drawer triggers the WS connect
    // inside chatPanel()).
    chatOpen: false,

    // -- Saved queries ----------------------------------
    saved: [],
    savedLoading: false,
    saving: false,
    saveForm: { title: '', description: '', is_shared: false },

    // -- Cancel + elapsed counter -----------------------
    currentQueryId: null,
    elapsedSeconds: 0,
    _tickHandle: null,

    // -- EXPLAIN (; added structured plan) -----
    explainText: null,
    explainPlan: null,
    explainShowJson: false,

    // Walk the parsed JSON plan returned by DuckDB's
    // ``enable_profiling='json'`` pragma into a flat list of
    // operator entries the template iterates over.
    //
    // Skips:
    // * The top-level profiling root (no operator_name; its
    // query-wide totals are surfaced in the header).
    // * The ``EXPLAIN_ANALYZE`` wrapper (instrumentation node,
    // not actual query work).
    //
    // Every other field DuckDB returns per operator surfaces in
    // the rendered tree:
    // - operator_timing → primary "wall time" badge
    // - cpu_time → secondary "CPU" tag (when distinct)
    // - operator_cardinality → "X rows out"
    // - operator_rows_scanned (when > 0) → "Y rows in"
    // - cumulative_cardinality / cumulative_rows_scanned →
    // "subtree" detail entries
    // - result_set_size (bytes) → output buffer size
    // - system_peak_buffer_memory / system_peak_temp_dir_size
    // → only when non-zero
    // - every extra_info entry rendered (no cap), with arrays
    // truncated to the first 8 items so very long
    // Projections lists don't take over the screen.
    flattenPlan(node, depth, path = '') {
      if (!node) return [];
      const out = [];
      const children = Array.isArray(node.children) ? node.children : [];
      const name = node.operator_name || node.operator_type;
      if (depth === 0 && !name) {
        for (let i = 0; i < children.length; i++) {
          out.push(...this.flattenPlan(children[i], 0, `${i}`));
        }
        return out;
      }
      if (name === 'EXPLAIN_ANALYZE') {
        for (let i = 0; i < children.length; i++) {
          out.push(...this.flattenPlan(children[i], depth, `${path}.${i}`));
        }
        return out;
      }
      const timing = typeof node.operator_timing === 'number' ? node.operator_timing : null;
      const cpu = typeof node.cpu_time === 'number' ? node.cpu_time : null;
      const card = typeof node.operator_cardinality === 'number' ? node.operator_cardinality : null;
      const rowsScanned =
        typeof node.operator_rows_scanned === 'number' ? node.operator_rows_scanned : null;
      const cumCard =
        typeof node.cumulative_cardinality === 'number' ? node.cumulative_cardinality : null;
      const cumScan =
        typeof node.cumulative_rows_scanned === 'number' ? node.cumulative_rows_scanned : null;
      const resultSize = typeof node.result_set_size === 'number' ? node.result_set_size : null;
      const peakBuf =
        typeof node.system_peak_buffer_memory === 'number' ? node.system_peak_buffer_memory : null;
      const peakTmp =
        typeof node.system_peak_temp_dir_size === 'number' ? node.system_peak_temp_dir_size : null;

      const extra = node.extra_info && typeof node.extra_info === 'object' ? node.extra_info : {};
      // Render the operator-level metrics that aren't already
      // shown as badges/inline tags as key/value detail rows.
      // We skip values that are zero or absent so the list
      // stays meaningful (every operator carries fifteen
      // fields, most of them zero in trivial plans).
      const details = [];
      if (cpu != null && timing != null && Math.abs(cpu - timing) > 1e-9) {
        details.push(['CPU time', this.formatTiming(cpu)]);
      }
      if (cumCard != null && cumCard > 0 && cumCard !== card) {
        details.push(['Subtree rows produced', cumCard.toLocaleString()]);
      }
      if (cumScan != null && cumScan > 0 && cumScan !== rowsScanned) {
        details.push(['Subtree rows scanned', cumScan.toLocaleString()]);
      }
      if (resultSize != null && resultSize > 0) {
        details.push(['Result set size', this.formatBytes(resultSize)]);
      }
      if (peakBuf != null && peakBuf > 0) {
        details.push(['Peak buffer', this.formatBytes(peakBuf)]);
      }
      if (peakTmp != null && peakTmp > 0) {
        details.push(['Peak temp-dir', this.formatBytes(peakTmp)]);
      }
      // Every ``extra_info`` field, rendered last so the
      // operator-level metrics above stay grouped together.
      for (const [k, v] of Object.entries(extra)) {
        if (k.startsWith('__')) continue;
        if (v == null || v === '') continue;
        let rendered;
        if (Array.isArray(v)) {
          if (v.length === 0) continue;
          rendered = v.slice(0, 8).join(', ');
          if (v.length > 8) {
            rendered += ` (+${v.length - 8} more)`;
          }
        } else {
          rendered = String(v);
        }
        details.push([k, rendered]);
      }
      out.push({
        name,
        kind: this._classifyOperator(name),
        timing,
        cpu,
        cardinality: card,
        rowsScanned,
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

    // Filter the root-level "sub-latency" fields (waiting to
    // attach, WAL replay, checkpoint, …) down to only those
    // that are actually non-zero; rendering nine zero rows in
    // the plan header would just be noise. Returns a list of
    // ``[label, formattedValue]`` ready for the template.
    rootSubLatencies(plan) {
      if (!plan) return [];
      const fields = [
        ['waiting_to_attach_latency', 'Waiting to attach'],
        ['attach_load_storage_latency', 'Attach load storage'],
        ['attach_replay_wal_latency', 'WAL replay'],
        ['blocked_thread_time', 'Blocked thread time'],
        ['checkpoint_latency', 'Checkpoint'],
        ['write_to_wal_latency', 'WAL write'],
        ['commit_local_storage_latency', 'Commit local storage'],
      ];
      const out = [];
      for (const [key, label] of fields) {
        const v = plan[key];
        if (typeof v === 'number' && v > 1e-9) {
          out.push([label, this.formatTiming(v)]);
        }
      }
      return out;
    },

    // Counterpart to ``rootSubLatencies`` — the I/O / memory /
    // result-set metrics that are interesting only when
    // non-zero. Surfaced under the latency line as a second
    // metric strip in the header.
    rootByteMetrics(plan) {
      if (!plan) return [];
      const fields = [
        ['total_bytes_read', 'Bytes read', 'bytes'],
        ['total_bytes_written', 'Bytes written', 'bytes'],
        ['result_set_size', 'Result set', 'bytes'],
        ['total_memory_allocated', 'Memory allocated', 'bytes'],
        ['system_peak_temp_dir_size', 'Peak temp-dir', 'bytes'],
        ['rows_returned', 'Rows returned', 'count'],
        ['cumulative_rows_scanned', 'Cumulative rows scanned', 'count'],
        ['wal_replay_entry_count', 'WAL replay entries', 'count'],
        ['cpu_time', 'CPU time', 'time'],
      ];
      const out = [];
      for (const [key, label, unit] of fields) {
        const v = plan[key];
        if (typeof v !== 'number') continue;
        if (unit === 'time' ? v > 1e-9 : v > 0) {
          const formatted =
            unit === 'bytes'
              ? this.formatBytes(v)
              : unit === 'time'
                ? this.formatTiming(v)
                : v.toLocaleString();
          out.push([label, formatted]);
        }
      }
      return out;
    },

    // Bucket the DuckDB operator name into one of seven kinds the
    // CSS uses to colour the badge. The mapping is approximate
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
    // milliseconds, depending on magnitude. DuckDB returns very
    // small operator timings (sub-millisecond) for cheap
    // operations; rounding to ``0.00 ms`` was unhelpful.
    formatTiming(seconds) {
      if (seconds == null) return '';
      if (seconds < 0.001) return `${(seconds * 1_000_000).toFixed(0)} µs`;
      if (seconds < 1) return `${(seconds * 1000).toFixed(2)} ms`;
      return `${seconds.toFixed(3)} s`;
    },

    // Compact human-readable byte formatting for the plan
    // header line (peak memory, etc.). Mirrors the simple-units
    // pattern used in the catalog tree's volume sidebar.
    formatBytes(n) {
      if (n == null || isNaN(n)) return '';
      if (n < 1024) return `${n} B`;
      if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
      if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MiB`;
      return `${(n / 1024 / 1024 / 1024).toFixed(2)} GiB`;
    },

    // -- Chart view -------------------------------------
    // ``viewMode`` toggles between ``'table'`` (default) and
    // ``'chart'``. ``chartConfig`` carries the user's current
    // selections; the null starts are guarded wherever x-text reads
    // them.
    viewMode: 'table',
    chartConfig: { type: 'bar', x: null, y: null },
    _chartInstance: null,
    // Id of the history row the current ``result`` corresponds to.
    // Set by POST /api/sql/execute response (which carries
    // ``history_id``) and by the deep-link fetch in
    // ``seedFromHistory``. Required so the debounced PATCH knows
    // which row to update.
    currentHistoryId: null,
    _chartSaveTimer: null,

    // -- : closure state promoted to ``this._*`` so the
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
    ...builderMethods,
  };
}
