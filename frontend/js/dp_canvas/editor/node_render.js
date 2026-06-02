/*
 * In-canvas node-body rendering for the canvas editor.
 *
 * Rewrites each mounted Drawflow node's config summary, output-schema
 * column list, row-count / status footer, error badge + tooltip, and
 * accessibility attributes from the reactive state.  The schema / row-count
 * data itself arrives from validate / preview; these methods only paint it
 * onto the node DOM.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

import { BLOCK_DEFS } from '../_block_catalog.js';
import { describeConfig, renderColsHtml, renderFooterHtml } from '../_render_helpers.js';

export const nodeRenderMethods = {
  _refreshNodeBody(nodeId) {
    const df = this._drawflow;
    if (!df) return;
    const dfId = this._drawflowNodes[nodeId];
    if (!dfId) return;
    const el = df.container.querySelector(`#node-${dfId} [data-pql-node-body]`);
    if (el) {
      const node = this.nodes[nodeId];
      if (node) el.innerHTML = describeConfig(node.block_type, node.config);
    }
  },
  _outputSchemaFor(nodeId) {
    const key = `${nodeId}:out`;
    const schema = this.pinSchemas[key];
    if (schema && Array.isArray(schema.columns)) return schema.columns;
    return null;
  },
  _statusFor(nodeId) {
    const hasErr = this.errors.some((e) => e.node_id === nodeId);
    if (hasErr) return 'error';
    if (this._outputSchemaFor(nodeId)) return 'ok';
    return 'pending';
  },
  _refreshAllNodeBodies() {
    const df = this._drawflow;
    if (!df) return;
    for (const [pqlId, dfId] of Object.entries(this._drawflowNodes)) {
      const wrap = df.container.querySelector(`#node-${dfId}`);
      if (!wrap) continue;
      const colsEl = wrap.querySelector('[data-pql-node-cols]');
      const footerEl = wrap.querySelector('[data-pql-node-footer]');
      const cols = this._outputSchemaFor(pqlId);
      if (colsEl) colsEl.innerHTML = renderColsHtml(cols);
      if (footerEl) {
        footerEl.innerHTML = renderFooterHtml(
          this.previewRowCountByNode[pqlId],
          this._statusFor(pqlId)
        );
      }
    }
    // The innerHTML rewrites above change node heights → pins move.  The
    // shared ResizeObserver will catch it, but redraw synchronously too so
    // a programmatic screenshot taken on the next tick already shows the
    // wires landing on the new pin positions.
    this._scheduleConnNodeUpdate();
    // The initial fit ran before the async schema bodies arrived, so the
    // graph's real height was unknown.  Re-fit exactly once now that the
    // bodies have content — then never again, so the view never jumps out
    // from under the user mid-edit.
    if (this._initialFitDone && !this._refitAfterBodies) {
      this._refitAfterBodies = true;
      this.$nextTick(() => this.fitToView());
    }
    this._applyNodeA11y();
  },
  _applyNodeA11y() {
    // Make each node a labelled, keyboard-focusable group so screen
    // readers announce the block and Tab/Enter can drive it.
    const df = this._drawflow;
    if (!df) return;
    for (const [pqlId, dfId] of Object.entries(this._drawflowNodes)) {
      const wrap = df.container.querySelector(`#node-${dfId}`);
      if (!wrap) continue;
      const node = this.nodes[pqlId];
      const def = node && BLOCK_DEFS[node.block_type];
      const label = `${(def && def.label) || (node && node.block_type) || 'Block'} block`;
      wrap.setAttribute('role', 'group');
      wrap.setAttribute('aria-label', label);
      wrap.setAttribute('data-pql-pql-id', pqlId);
      if (!wrap.hasAttribute('tabindex')) wrap.setAttribute('tabindex', '0');
    }
  },
  _refreshAllNodeErrors() {
    const df = this._drawflow;
    if (!df) return;
    const perNode = {};
    const tooltipPerNode = {};
    for (const err of this.errors) {
      if (!err.node_id) continue;
      perNode[err.node_id] = (perNode[err.node_id] || 0) + 1;
      if (!tooltipPerNode[err.node_id]) tooltipPerNode[err.node_id] = [];
      tooltipPerNode[err.node_id].push(this._formatErrorTooltip(err));
    }
    for (const [pqlId, dfId] of Object.entries(this._drawflowNodes)) {
      const wrap = df.container.querySelector(`#node-${dfId}`);
      if (!wrap) continue;
      const badge = wrap.querySelector('[data-pql-node-error-badge]');
      if (perNode[pqlId]) {
        wrap.classList.add('pql-node-error');
        if (badge) {
          badge.style.display = '';
          badge.textContent = perNode[pqlId];
          badge.title = (tooltipPerNode[pqlId] || []).join('\n');
          badge.style.cursor = 'help';
        }
      } else {
        wrap.classList.remove('pql-node-error');
        if (badge) {
          badge.style.display = 'none';
          badge.removeAttribute('title');
        }
      }
    }
  },
  _formatErrorTooltip(err) {
    const parts = [`[${err.kind}]`];
    if (err.pin) parts.push(`pin=${err.pin}`);
    if (err.column) parts.push(`column=${err.column}`);
    if (err.expected_type) parts.push(`expected=${err.expected_type}`);
    if (err.actual_type) parts.push(`actual=${err.actual_type}`);
    parts.push(err.message || '');
    return parts.join(' ');
  },
};
