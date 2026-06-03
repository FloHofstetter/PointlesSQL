/*
 * Right-drawer config-form helpers for the canvas editor.
 *
 * Block label/icon/help lookups (from the shared block catalog), the
 * inline per-node error surface, plus the small add/remove mutators the
 * per-block config forms bind to for their chip-list editors (columns,
 * join/group keys, aggregations, merge keys).  Each mutator routes through
 * `this.onConfigChanged()` (defined on the component) so autosave +
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

  addProjectColumn(col) {
    const node = this.selectedNode;
    if (!node || !col) return;
    const trimmed = String(col).trim();
    if (!trimmed) return;
    if (node.config.columns.includes(trimmed)) return;
    node.config.columns.push(trimmed);
    this.onConfigChanged();
  },
  removeProjectColumn(idx) {
    const node = this.selectedNode;
    if (!node) return;
    node.config.columns.splice(idx, 1);
    this.onConfigChanged();
  },
  addJoinKey(col) {
    const node = this.selectedNode;
    if (!node || !col) return;
    const trimmed = String(col).trim();
    if (!trimmed || node.config.keys.includes(trimmed)) return;
    node.config.keys.push(trimmed);
    this.onConfigChanged();
  },
  removeJoinKey(idx) {
    const node = this.selectedNode;
    if (!node) return;
    node.config.keys.splice(idx, 1);
    this.onConfigChanged();
  },
  addGroupKey(col) {
    const node = this.selectedNode;
    if (!node || !col) return;
    const trimmed = String(col).trim();
    if (!trimmed || node.config.keys.includes(trimmed)) return;
    node.config.keys.push(trimmed);
    this.onConfigChanged();
  },
  removeGroupKey(idx) {
    const node = this.selectedNode;
    if (!node) return;
    node.config.keys.splice(idx, 1);
    this.onConfigChanged();
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
  addMergeOn(col) {
    const node = this.selectedNode;
    if (!node || !col) return;
    const trimmed = String(col).trim();
    if (!trimmed) return;
    if (!Array.isArray(node.config.merge_on)) node.config.merge_on = [];
    if (node.config.merge_on.includes(trimmed)) return;
    node.config.merge_on.push(trimmed);
    this.onConfigChanged();
  },
  removeMergeOn(idx) {
    const node = this.selectedNode;
    if (!node) return;
    if (!Array.isArray(node.config.merge_on)) return;
    node.config.merge_on.splice(idx, 1);
    this.onConfigChanged();
  },
};
