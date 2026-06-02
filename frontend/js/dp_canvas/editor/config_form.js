/*
 * Right-drawer config-form helpers for the canvas editor.
 *
 * Block label/icon/help lookups (from the shared block catalog) plus the
 * small add/remove mutators the per-block config forms bind to for their
 * chip-list editors (columns, join/group keys, aggregations, merge keys).
 * Each mutator routes through `this.onConfigChanged()` (defined on the
 * component) so autosave + revalidate fire uniformly.
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
