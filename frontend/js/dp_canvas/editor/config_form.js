/*
 * Right-drawer config-form helpers for the canvas editor.
 *
 * Block label/icon/help lookups (from the shared block catalog), the
 * inline per-node error surface, plus the GroupBy aggregation-row mutators.
 * Generic array-field editing (chips, comma lists) lives in
 * `config_form_structured.js`; this file keeps only the lookups, the error
 * helpers and the one row editor that predates them.  Each mutator routes
 * through `this.onConfigChanged()` (defined on the component) so autosave +
 * revalidate fire uniformly.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

import { BLOCK_DEFS } from '../_block_catalog.js';

export const configFormMethods = {
  blockLabel(kind) {
    return (BLOCK_DEFS[kind] && BLOCK_DEFS[kind].label) || kind;
  },
  blockIcon(kind) {
    return (BLOCK_DEFS[kind] && BLOCK_DEFS[kind].icon) || 'bi-question-square';
  },
  blockHelp(kind) {
    return (BLOCK_DEFS[kind] && BLOCK_DEFS[kind].help) || '';
  },

  // --- Inline per-node error surface -------------------------------------
  // The right drawer lists a block's own validation errors while it is
  // selected, so the user fixes them in place instead of deselecting to
  // read the overview.  The structured CompileError fields (column /
  // expected_type / actual_type / suggestion) drive both a human message
  // and a best-effort highlight of the offending input field.

  nodeErrors() {
    const id = this.selectedNodeId;
    if (!id) return [];
    return this.errors.filter((e) => e.node_id === id);
  },
  formatNodeError(err) {
    if (!err) return '';
    if (err.kind === 'type_mismatch' && err.expected_type && err.actual_type) {
      const col = err.column ? `Column “${err.column}”: ` : '';
      return `${col}expected ${err.expected_type}, got ${err.actual_type}.`;
    }
    if (err.suggestion === 'UNKNOWN_DUCKDB_TYPE' && err.column) {
      const t = err.actual_type ? ` “${err.actual_type}”` : '';
      return `“${err.column}” uses an unknown type${t}.`;
    }
    return err.message || 'Invalid configuration.';
  },
  errorFieldFor(err) {
    if (!err) return null;
    const bt = this.selectedNode && this.selectedNode.block_type;
    // FQN errors carry the exact config key in `column` (table_fqn /
    // materialized_table), so the three-field UC name can be flagged.
    if (err.suggestion === 'INVALID_FQN') {
      return err.column || (bt === 'InputPort' ? 'table_fqn' : 'materialized_table');
    }
    // Schema-flow errors name a *data* column; map it to the config field
    // that lists columns for this block type.
    if (err.kind === 'type_mismatch' || err.column) {
      const byBlock = {
        Project: 'columns',
        Cast: 'casts',
        Join: 'keys',
        GroupBy: 'keys',
        SemiJoin: 'keys',
        AntiJoin: 'keys',
        Unnest: 'column',
      };
      return byBlock[bt] || null;
    }
    return null;
  },
  fieldHasError(field) {
    return this.nodeErrors().some((e) => this.errorFieldFor(e) === field);
  },

  addAggregation() {
    const node = this.selectedNode;
    if (!node) return;
    node.config.aggregations.push({ column: '', fn: 'sum', alias: '' });
    this.onConfigChanged();
  },
  removeAggregation(idx) {
    const node = this.selectedNode;
    if (!node) return;
    node.config.aggregations.splice(idx, 1);
    this.onConfigChanged();
  },
};
