/*
 * Output-plus affordance for the canvas editor.
 *
 * The always-on "+" handle on each unwired output pin (mounted in the stage,
 * repositioned on node-move and zoom) and the block picker it opens, which
 * also serves the context-menu "add here" and insert-on-edge flows.  On a
 * pick the chosen block is dropped and auto-wired.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

import { BLOCK_DEFS, pinIndexFor } from '../_block_catalog.js';
import { generateNodeId } from '../_render_helpers.js';

export const outputPlusMethods = {
  _openOutputPlusPicker(sourcePqlId, anchorEl) {
    if (!this.canWrite) return;
    this._insertOnEdgeContext = null;
    const stage = this.$refs.canvas.parentElement;
    const stageRect = stage.getBoundingClientRect();
    const anchorRect = anchorEl.getBoundingClientRect();
    const x = anchorRect.right - stageRect.left + 8;
    const y = anchorRect.top - stageRect.top;
    this.outputPlusPicker = { open: true, x, y, sourcePqlId };
  },
  _closeOutputPlusPicker() {
    this.outputPlusPicker = { open: false, x: 0, y: 0, sourcePqlId: null };
    this._insertOnEdgeContext = null;
  },
  _pickOutputPlusBlock(kind) {
    const def = BLOCK_DEFS[kind];
    if (!def) return;
    const insertCtx = this._insertOnEdgeContext;
    const sourcePqlId = this.outputPlusPicker.sourcePqlId;
    this._closeOutputPlusPicker();

    if (insertCtx) {
      // Insert-on-edge flow: remove original, drop new node at midpoint,
      // wire src→new and new→tgt.  Single undo-command wraps the trio.
      const srcEdge = this.edges[insertCtx.edgeId];
      if (!srcEdge) return;
      const srcDf = this._drawflowNodes[insertCtx.srcPqlId];
      const tgtDf = this._drawflowNodes[insertCtx.tgtPqlId];
      if (srcDf == null || tgtDf == null) return;
      const tgtIdx = pinIndexFor(
        this.nodes[insertCtx.tgtPqlId]?.block_type,
        insertCtx.targetPin,
        'in'
      );
      const origIn = `input_${tgtIdx + 1}`;
      try {
        this._drawflow.removeSingleConnection(srcDf, tgtDf, 'output_1', origIn);
      } catch (_e) {
        return;
      }
      const newPqlId = generateNodeId();
      const pos = insertCtx.dropPos || { x: 200, y: 200 };
      const newDf = this._spawnNode(kind, pos, def.defaultConfig(), newPqlId);
      try {
        this._drawflow.addConnection(srcDf, newDf, 'output_1', 'input_1');
      } catch (_e) {
        // Skip.
      }
      if (
        (def.outputs || 0) > 0 &&
        (BLOCK_DEFS[this.nodes[insertCtx.tgtPqlId]?.block_type]?.inputs || 0) > 0
      ) {
        try {
          this._drawflow.addConnection(newDf, tgtDf, 'output_1', origIn);
        } catch (_e) {
          // Skip.
        }
      }
      this._refreshNodeBody(newPqlId);
      this._renderOutputPlus(newPqlId);
      this._scheduleAutosave();
      this._scheduleValidate();
      return;
    }

    if (!sourcePqlId) {
      // Context-menu "add block here": drop a standalone, unwired node at
      // the stashed canvas-local position.
      const dropPos = this._ctxDropPos;
      this._ctxDropPos = null;
      if (!dropPos) return;
      const newPqlId = generateNodeId();
      this._spawnNode(kind, dropPos, def.defaultConfig(), newPqlId);
      this._refreshNodeBody(newPqlId);
      this._renderOutputPlus(newPqlId);
      this.selectedNodeId = newPqlId;
      this._scheduleAutosave();
      this._scheduleValidate();
      this._scheduleMinimapRender();
      return;
    }
    // Plain output-plus flow: add new block 150 px right of source +
    // auto-wire.
    const src = this.nodes[sourcePqlId];
    if (!src) return;
    const srcDf = this._drawflowNodes[sourcePqlId];
    if (srcDf == null) return;
    const pos = {
      x: (src.position?.x || 100) + 220,
      y: src.position?.y || 100,
    };
    const newPqlId = generateNodeId();
    const newDf = this._spawnNode(kind, pos, def.defaultConfig(), newPqlId);
    if ((def.inputs || 0) > 0) {
      try {
        this._drawflow.addConnection(srcDf, newDf, 'output_1', 'input_1');
      } catch (_e) {
        // Skip.
      }
    }
    this._refreshNodeBody(newPqlId);
    this._renderOutputPlus(newPqlId);
    this._scheduleAutosave();
    this._scheduleValidate();
  },
  // ---------------------------------------------------------------------
  // Always-on output-plus handle — n8n's flagship affordance ported to
  // Drawflow.  One <div> per output pin, mounted absolutely inside the
  // stage (NOT inside the Drawflow precanvas), repositioned on every
  // node-move and zoom event.  Click opens the block-picker; on pick
  // the chosen block lands 220 px to the right of the source and is
  // auto-wired.
  // ---------------------------------------------------------------------

  _renderOutputPlus(pqlId) {
    const df = this._drawflow;
    if (!df) return;
    const dfId = this._drawflowNodes[pqlId];
    if (dfId == null) return;
    const node = this.nodes[pqlId];
    if (!node) return;
    const def = BLOCK_DEFS[node.block_type];
    if (!def || (def.outputs || 0) === 0) return;
    const stage = this.$refs.canvas.parentElement;
    if (!stage) return;
    const dfNodeEl = df.container.querySelector(`#node-${dfId}`);
    if (!dfNodeEl) return;
    // One handle per output pin.
    for (let i = 1; i <= (def.outputs || 0); i++) {
      const pinEl =
        dfNodeEl.querySelector(`.outputs .output_${i}`) ||
        dfNodeEl.querySelector(`.outputs .output:nth-child(${i})`);
      if (!pinEl) continue;
      const key = `${pqlId}:${i}`;
      let handle = this._outputPlusElements.get(key);
      if (!handle) {
        handle = document.createElement('div');
        handle.className = 'pql-output-plus';
        handle.innerHTML = '<i class="bi bi-plus"></i>';
        handle.title = 'Add a block connected to this output';
        handle.addEventListener('click', (ev) => {
          ev.stopPropagation();
          this._openOutputPlusPicker(pqlId, handle);
        });
        stage.appendChild(handle);
        this._outputPlusElements.set(key, handle);
      }
      // Hide the plus when an outgoing edge already occupies this
      // pin — the user has nothing to "add" there; the existing edge
      // visually overlaps the handle and the dual-affordance reads
      // as ambiguous.  Every block in the catalogue exposes a single
      // ``out`` pin per output slot so a same-source check suffices.
      const hasOutgoing = Object.values(this.edges).some((e) => e.source_node_id === pqlId);
      handle.style.display = hasOutgoing ? 'none' : '';
      this._positionOutputPlus(handle, pinEl, stage);
    }
  },
  _positionOutputPlus(handle, pinEl, stage) {
    const pinRect = pinEl.getBoundingClientRect();
    const stageRect = stage.getBoundingClientRect();
    // Anchor the handle 42 px to the right of the pin centre.
    const x = pinRect.right - stageRect.left + 36;
    const y = pinRect.top - stageRect.top + pinRect.height / 2 - 11;
    handle.style.left = `${x}px`;
    handle.style.top = `${y}px`;
  },
  _repositionOutputPlusFor(dfId) {
    const df = this._drawflow;
    if (!df) return;
    let pqlId = null;
    for (const [id, mapped] of Object.entries(this._drawflowNodes)) {
      if (String(mapped) === String(dfId)) {
        pqlId = id;
        break;
      }
    }
    if (!pqlId) return;
    const stage = this.$refs.canvas.parentElement;
    if (!stage) return;
    const dfNodeEl = df.container.querySelector(`#node-${dfId}`);
    if (!dfNodeEl) return;
    const def = BLOCK_DEFS[this.nodes[pqlId]?.block_type];
    if (!def) return;
    for (let i = 1; i <= (def.outputs || 0); i++) {
      const key = `${pqlId}:${i}`;
      const handle = this._outputPlusElements.get(key);
      if (!handle) continue;
      const pinEl =
        dfNodeEl.querySelector(`.outputs .output_${i}`) ||
        dfNodeEl.querySelector(`.outputs .output:nth-child(${i})`);
      if (!pinEl) continue;
      this._positionOutputPlus(handle, pinEl, stage);
    }
  },
  _scheduleAllOutputPlusReposition() {
    if (this._outputPlusRaf) return;
    this._outputPlusRaf = window.setTimeout(() => {
      this._outputPlusRaf = null;
      const df = this._drawflow;
      if (!df) return;
      const stage = this.$refs.canvas.parentElement;
      if (!stage) return;
      for (const [key, handle] of this._outputPlusElements) {
        const [pqlId, idxStr] = key.split(':');
        const dfId = this._drawflowNodes[pqlId];
        if (dfId == null) {
          handle.remove();
          this._outputPlusElements.delete(key);
          continue;
        }
        const dfNodeEl = df.container.querySelector(`#node-${dfId}`);
        if (!dfNodeEl) continue;
        const i = parseInt(idxStr, 10);
        const pinEl =
          dfNodeEl.querySelector(`.outputs .output_${i}`) ||
          dfNodeEl.querySelector(`.outputs .output:nth-child(${i})`);
        if (!pinEl) continue;
        this._positionOutputPlus(handle, pinEl, stage);
      }
    });
  },
};
