/*
 * Drag-to-connect validation for the canvas editor.
 *
 * Drawflow exposes no wire-drag-start event, so a pointerdown on an output
 * socket is tracked in parallel with Drawflow's own drag to highlight which
 * input pins are valid drop targets (free slot, no cycle) and clear them on
 * release.  Drawflow's connectionCreated stays the source of truth for the
 * actual wire.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

import { BLOCK_DEFS } from '../_block_catalog.js';

export const connectMethods = {
  // ---------------------------------------------------------------------
  // Live drag-to-connect validation.  Parallel to Drawflow's own wire
  // drag (which has no public start event), highlight the input pins that
  // are valid drop targets while the user drags from an output.
  // ---------------------------------------------------------------------

  _onOutputPointerDown(ev) {
    const outPin = ev.target.closest && ev.target.closest('.output');
    if (!outPin) return;
    const nodeEl = outPin.closest('.drawflow-node');
    if (!nodeEl) return;
    const dfId = (nodeEl.id || '').replace('node-', '');
    let srcPql = null;
    for (const [pql, mapped] of Object.entries(this._drawflowNodes)) {
      if (String(mapped) === dfId) {
        srcPql = pql;
        break;
      }
    }
    if (!srcPql) return;
    this._highlightDropTargets(srcPql);
    const end = () => {
      this._clearDropTargets();
      window.removeEventListener('pointerup', end);
      window.removeEventListener('pointercancel', end);
    };
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
  },
  _isInputPinFree(pqlId, pinName) {
    return !Object.values(this.edges).some(
      (e) => e.target_node_id === pqlId && e.target_pin === pinName
    );
  },
  _wouldCycle(srcPql, tgtPql) {
    // Connecting src → tgt makes a cycle iff src is already reachable
    // downstream of tgt (tgt → … → src exists).
    if (srcPql === tgtPql) return true;
    const adj = new Map();
    for (const e of Object.values(this.edges)) {
      if (!adj.has(e.source_node_id)) adj.set(e.source_node_id, []);
      adj.get(e.source_node_id).push(e.target_node_id);
    }
    const stack = [tgtPql];
    const seen = new Set();
    while (stack.length) {
      const cur = stack.pop();
      if (cur === srcPql) return true;
      if (seen.has(cur)) continue;
      seen.add(cur);
      for (const nxt of adj.get(cur) || []) stack.push(nxt);
    }
    return false;
  },
  _highlightDropTargets(srcPql) {
    const df = this._drawflow;
    if (!df) return;
    df.container.classList.add('pql-dragging-wire');
    for (const [pql, dfId] of Object.entries(this._drawflowNodes)) {
      const nodeEl = df.container.querySelector(`#node-${dfId}`);
      if (!nodeEl) continue;
      const def = BLOCK_DEFS[this.nodes[pql]?.block_type];
      const inputs = nodeEl.querySelectorAll('.inputs .input');
      inputs.forEach((pin, idx) => {
        const pinName =
          def && (def.block_type === 'Join' || this.nodes[pql]?.block_type === 'Join')
            ? idx === 1
              ? 'right'
              : 'left'
            : this.nodes[pql]?.block_type === 'Union'
              ? idx === 1
                ? 'right'
                : 'left'
              : 'in';
        const ok =
          pql !== srcPql && this._isInputPinFree(pql, pinName) && !this._wouldCycle(srcPql, pql);
        pin.classList.add(ok ? 'pql-pin-ok' : 'pql-pin-no');
      });
    }
  },
  _clearDropTargets() {
    const df = this._drawflow;
    if (!df) return;
    df.container.classList.remove('pql-dragging-wire');
    for (const pin of df.container.querySelectorAll('.input.pql-pin-ok, .input.pql-pin-no')) {
      pin.classList.remove('pql-pin-ok', 'pql-pin-no');
    }
  },
};
