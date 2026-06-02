/*
 * Connection decoration and lifecycle for the canvas editor.
 *
 * Maps connection SVGs back to model edges, decorates each with a fat
 * hit-area + arrow marker + hover/select wiring, recomputes wire endpoints
 * when a node resizes, colours edges by column-type category, runs the
 * marching-ants upstream highlight, and handles delete / insert-on-edge.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

import { pinIndexFor } from '../_block_catalog.js';

export const edgesMethods = {
  _refreshEdgeCategoryStyles() {
    const df = this._drawflow;
    if (!df) return;
    const cats = this.edgeCategories || {};
    const knownCats = ['numeric', 'text', 'temporal', 'boolean', 'complex', 'mixed'];
    // Pre-resolve edge.id → category once.  Backend categorise key is the
    // canonical pin tuple (no `e-` prefix), so derive it from the edge.
    const catByEdgeId = {};
    for (const edge of Object.values(this.edges)) {
      const catKey =
        `${edge.source_node_id}:${edge.source_pin}->` + `${edge.target_node_id}:${edge.target_pin}`;
      catByEdgeId[edge.id] = cats[catKey] || 'mixed';
    }
    // Single pass over the connection SVGs — each maps to its edge in O(1)
    // via _edgeIdForSvg, so no per-edge DOM query.
    const connections = df.container.querySelectorAll('.drawflow .connection');
    for (const conn of connections) {
      for (const k of knownCats) conn.classList.remove(`pql-edge-${k}`);
      const edgeId = this._edgeIdForSvg(conn);
      conn.classList.add(`pql-edge-${(edgeId && catByEdgeId[edgeId]) || 'mixed'}`);
    }
  },
  _scheduleResizeConnUpdate() {
    if (this._resizeConnRaf) return;
    // setTimeout(0): batch a burst of ResizeObserver entries into one turn
    // (rAF is throttled in background tabs / headless Playwright).
    this._resizeConnRaf = window.setTimeout(() => {
      this._resizeConnRaf = null;
      const df = this._drawflow;
      if (!df) return;
      const ids = this._connNodeDirty ? [...this._connNodeDirty] : [];
      if (this._connNodeDirty) this._connNodeDirty.clear();
      // updateConnectionNodes emits nodeMoved internally → suppress autosave
      // around this visual-only redraw (same guard as the full sweep).
      const wasSuppressed = this._suppressAutosave;
      this._suppressAutosave = true;
      try {
        for (const dfId of ids) df.updateConnectionNodes('node-' + dfId);
      } finally {
        this._suppressAutosave = wasSuppressed;
      }
      this._scheduleRerouteOrthogonal();
    }, 0);
  },
  // ---------------------------------------------------------------------
  // Node-resize → connection-redraw.  Drawflow computes each connection's
  // endpoints from the live pin DOM position, but only recomputes them on
  // nodeMoved.  When a node's height changes (async schema columns, the
  // row-count / status footer, an error badge, the compact toggle) its
  // pins shift and the wires would point at the stale position.  A shared
  // ResizeObserver re-runs updateConnectionNodes for every node that
  // resizes, batched into one event-loop turn.
  // ---------------------------------------------------------------------

  _observeNode(dfId) {
    if (!this._nodeResizeObserver) return;
    const el = this._drawflow?.container.querySelector(`#node-${dfId}`);
    if (el) this._nodeResizeObserver.observe(el);
  },
  _unobserveNode(dfId) {
    if (!this._nodeResizeObserver) return;
    const el = this._drawflow?.container.querySelector(`#node-${dfId}`);
    if (el) this._nodeResizeObserver.unobserve(el);
  },
  _scheduleConnNodeUpdate() {
    if (this._connNodeRaf) return;
    // setTimeout(0), not rAF — same reason as the decoration batch: rAF is
    // throttled in background tabs / headless Playwright and would leave
    // edges pointing at stale pins.
    this._connNodeRaf = window.setTimeout(() => {
      this._connNodeRaf = null;
      this._flushConnNodeUpdate();
    }, 0);
  },
  _flushConnNodeUpdate() {
    const df = this._drawflow;
    if (!df) return;
    // updateConnectionNodes emits nodeMoved internally for every connected
    // node, which would cascade into autosave + minimap; this is a
    // visual-only redraw, so suppress autosave around it.
    const wasSuppressed = this._suppressAutosave;
    this._suppressAutosave = true;
    try {
      for (const dfId of Object.values(this._drawflowNodes)) {
        df.updateConnectionNodes('node-' + dfId);
      }
    } finally {
      this._suppressAutosave = wasSuppressed;
    }
  },
  // ---------------------------------------------------------------------
  // Edge decoration — fat hit-area, hover/select states, directional
  // arrow marker, click-to-select, mid-edge toolbar.  Drawflow renders
  // every connection as a single <svg class="connection"> with a child
  // <path class="main-path">; we decorate that SVG once after each
  // creation (or full reload) without forking the library.
  // ---------------------------------------------------------------------

  _scheduleDecorateAllConnections() {
    if (this._decorateRaf) return;
    // setTimeout instead of rAF: rAF is throttled in non-painting tabs
    // (and in headless Playwright runs), which would leave fresh edges
    // un-decorated.  A 0-tick delay is enough for Drawflow's synchronous
    // addConnection burst to settle and lets us batch repeated calls
    // within the same event-loop turn.
    this._decorateRaf = window.setTimeout(() => {
      this._decorateRaf = null;
      this._decorateAllConnections();
    }, 0);
  },
  _decorateAllConnections() {
    const df = this._drawflow;
    if (!df) return;
    const svgs = df.container.querySelectorAll('.drawflow .connection');
    for (const svg of svgs) this._decorateConnection(svg);
    this._scheduleRerouteOrthogonal();
  },
  _edgeIdForSvg(svgEl) {
    // Drawflow stamps `node_in_node-<tgtDf>` and `node_out_node-<srcDf>`
    // classes on each connection SVG.  Resolve the (srcDf, tgtDf) pair
    // through the `_edgeByDfIds` index (built in _syncFromDrawflow) — O(1)
    // instead of re-scanning every node and edge per call.
    let srcDf = null;
    let tgtDf = null;
    for (const cls of svgEl.classList) {
      const inM = cls.match(/^node_in_node-(\d+)$/);
      const outM = cls.match(/^node_out_node-(\d+)$/);
      if (inM) tgtDf = inM[1];
      if (outM) srcDf = outM[1];
    }
    if (srcDf == null || tgtDf == null) return null;
    return (this._edgeByDfIds && this._edgeByDfIds[`${srcDf}|${tgtDf}`]) || null;
  },
  _decorateConnection(svgEl) {
    if (!svgEl) return;
    const mainPath = svgEl.querySelector('.main-path');
    if (!mainPath) return;
    // Arrow head — set every pass (cheap, idempotent).
    mainPath.setAttribute('marker-end', 'url(#pql-arrow-end)');
    if (this._decoratedSvgs.has(svgEl)) {
      // Refresh hit-area `d` so it tracks moved nodes.
      const hit = svgEl.querySelector('.pql-edge-hit-area');
      if (hit) hit.setAttribute('d', mainPath.getAttribute('d') || '');
      return;
    }
    this._decoratedSvgs.add(svgEl);

    // Inject fat invisible sibling for hit-testing — same `d` as the
    // visible path, transparent stroke 22 px wide.  MUST come AFTER
    // the .main-path because Drawflow's updateConnectionNodes writes
    // the new `d` value into `connection.children[0]`; if the hit-
    // area sat first, every node-drag would update the hit-area and
    // leave the visible edge frozen.  Pointer-events:stroke on the
    // hit-area still captures hover/click while sitting visually on
    // top — transparency makes it invisible regardless of z-order.
    const svgNS = 'http://www.w3.org/2000/svg';
    const hit = document.createElementNS(svgNS, 'path');
    hit.setAttribute('class', 'pql-edge-hit-area');
    hit.setAttribute('d', mainPath.getAttribute('d') || '');
    hit.setAttribute('fill', 'none');
    svgEl.appendChild(hit);

    // Watch the visible path for `d` mutations (Drawflow rewrites it
    // on every nodeMoved) and mirror them into the hit-area.
    try {
      const obs = new MutationObserver(() => {
        hit.setAttribute('d', mainPath.getAttribute('d') || '');
      });
      obs.observe(mainPath, { attributes: true, attributeFilter: ['d'] });
    } catch (_e) {
      // MutationObserver may be unavailable in extreme sandboxes; the
      // _decorateAllConnections rAF pass still refreshes via the
      // _decoratedSvgs early-return branch above.
    }

    // Hover-on with 80 ms debounce so a cursor crossing several
    // edges in succession does not flicker every one through their
    // hover styles (matches n8n's ``delayedHovered`` behaviour).
    // Glow radius scales with the visible path length so short
    // edges between adjacent nodes still get a perceptible halo
    // and long edges don't drown in a bloom — ``--pql-edge-glow``
    // is the CSS custom property the shared stylesheet reads in
    // its ``drop-shadow()`` filter.
    let hoverTimer = null;
    hit.addEventListener('mouseenter', () => {
      if (hoverTimer) window.clearTimeout(hoverTimer);
      hoverTimer = window.setTimeout(() => {
        hoverTimer = null;
        try {
          const len = mainPath.getTotalLength();
          const glow = Math.min(Math.max(len / 30, 2), 8);
          svgEl.style.setProperty('--pql-edge-glow', `${glow}px`);
        } catch (_e) {
          // Path may be zero-length pre-paint; default 4 px is fine.
        }
        svgEl.classList.add('pql-edge-hover');
        const edgeId = this._edgeIdForSvg(svgEl);
        if (edgeId) this._showEdgeToolbar(svgEl, edgeId);
      }, 80);
    });
    hit.addEventListener('mouseleave', () => {
      if (hoverTimer) {
        window.clearTimeout(hoverTimer);
        hoverTimer = null;
      }
      svgEl.classList.remove('pql-edge-hover');
      svgEl.style.removeProperty('--pql-edge-glow');
      this._scheduleEdgeToolbarHide();
    });
    hit.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const edgeId = this._edgeIdForSvg(svgEl);
      if (edgeId) this._selectEdge(edgeId);
    });
  },
  deleteEdgeById(edgeId) {
    if (!this.canWrite || !edgeId) return;
    const edge = this.edges[edgeId];
    if (!edge) return;
    const srcDf = this._drawflowNodes[edge.source_node_id];
    const tgtDf = this._drawflowNodes[edge.target_node_id];
    if (srcDf == null || tgtDf == null) return;
    const targetIdx = pinIndexFor(
      this.nodes[edge.target_node_id]?.block_type,
      edge.target_pin,
      'in'
    );
    const outClass = 'output_1';
    const inClass = `input_${targetIdx + 1}`;
    try {
      this._drawflow.removeSingleConnection(srcDf, tgtDf, outClass, inClass);
    } catch (_e) {
      return;
    }
    this._pushCommand({
      do: () => {
        try {
          this._drawflow.removeSingleConnection(srcDf, tgtDf, outClass, inClass);
        } catch (_e) {
          // Idempotent.
        }
      },
      undo: () => {
        try {
          this._drawflow.addConnection(srcDf, tgtDf, outClass, inClass);
        } catch (_e) {
          // Connection target may have moved away.
        }
      },
    });
    this._hideEdgeToolbar();
    this._clearSelectedEdge();
  },
  async insertBlockOnEdge(edgeId) {
    if (!this.canWrite || !edgeId) return;
    const edge = this.edges[edgeId];
    if (!edge) return;
    const srcPqlId = edge.source_node_id;
    const tgtPqlId = edge.target_node_id;
    const srcNode = this.nodes[srcPqlId];
    const tgtNode = this.nodes[tgtPqlId];
    if (!srcNode || !tgtNode) return;
    // Hide the toolbar before opening the picker so it doesn't linger
    // over the popover.
    this._hideEdgeToolbar();
    // Reuse the output-plus picker as a generic block chooser; remember
    // both endpoints so we can re-wire after the pick.
    const midX = ((srcNode.position?.x || 0) + (tgtNode.position?.x || 0)) / 2;
    const midY = ((srcNode.position?.y || 0) + (tgtNode.position?.y || 0)) / 2;
    this._insertOnEdgeContext = { edgeId, srcPqlId, tgtPqlId, targetPin: edge.target_pin };
    // Position the picker in screen coords near the edge midpoint.
    const stage = this.$refs.canvas.parentElement;
    const stageRect = stage.getBoundingClientRect();
    const df = this._drawflow;
    const zoom = df ? df.zoom || 1 : 1;
    const x = midX * zoom + (df ? df.canvas_x : 0) + 12;
    const y = midY * zoom + (df ? df.canvas_y : 0) + 12;
    this.outputPlusPicker = { open: true, x, y, sourcePqlId: null };
    // Stash the dropped position for the new block.
    this._insertOnEdgeContext.dropPos = { x: midX, y: midY };
  },
  // ---------------------------------------------------------------------
  // Marching-ants helpers — toggle `.pql-edge-running` on the connection
  // SVG for every edge whose source feeds into the preview target node
  // (transitive upstream walk).
  // ---------------------------------------------------------------------

  _edgesUpstreamOf(targetPqlId) {
    const result = new Set();
    if (!targetPqlId) return result;
    const adj = new Map();
    for (const edge of Object.values(this.edges)) {
      if (!adj.has(edge.target_node_id)) adj.set(edge.target_node_id, []);
      adj.get(edge.target_node_id).push(edge);
    }
    const stack = [targetPqlId];
    const seen = new Set();
    while (stack.length) {
      const cur = stack.pop();
      if (seen.has(cur)) continue;
      seen.add(cur);
      const upstream = adj.get(cur) || [];
      for (const edge of upstream) {
        result.add(edge.id);
        stack.push(edge.source_node_id);
      }
    }
    return result;
  },
  _setRunningEdges(edgeIds) {
    const df = this._drawflow;
    if (!df) return;
    this._runningEdgeIds = edgeIds instanceof Set ? edgeIds : new Set(edgeIds);
    const svgs = df.container.querySelectorAll('.drawflow .connection');
    for (const svg of svgs) {
      const id = this._edgeIdForSvg(svg);
      if (this._runningEdgeIds.has(id)) svg.classList.add('pql-edge-running');
      else svg.classList.remove('pql-edge-running');
    }
  },
};
