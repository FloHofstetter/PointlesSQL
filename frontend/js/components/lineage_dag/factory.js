/**
 * Lineage-DAG Alpine factory.
 *
 * Mounts on the Graph sub-tab inside the Lineage top-pane of
 * /runs/{id}.  Fetches the JSON payload from
 * ``GET /api/runs/{run_id}/graph?op_id=...`` and feeds it into
 * cytoscape.js with the dagre layout extension for a top-down
 * directed graph (one box per touched table, arrows annotated
 * with transform_kind).
 *
 * The cytoscape stack itself is loaded lazily — see
 * :func:`loadCytoscapeOnce` in :mod:`./cytoscape_init.js`.  Click
 * + dim semantics live in :mod:`./highlights.js`; side-panel
 * helpers live in :mod:`./panel.js`.
 */

import {
  dagLayout,
  ensureDagreRegistered,
  loadCytoscapeOnce,
  RUN_GRAPH_STYLE,
} from './cytoscape_init.js';
import { clearHighlight, highlightEdge, highlightNode } from './highlights.js';
import { clearSelection, findSelectedEdge, selectColumn } from './panel.js';

export function lineageDag(initial) {
  return {
    runId: initial.runId,
    opId: initial.opId || null,
    loading: true,
    error: null,
    nodes: [],
    edges: [],
    cy: null,
    // Side-panel state.
    selectedEdgeId: null,
    selectedColumn: null,

    // The loading flag stays true until the user first
    // activates the Graph sub-tab.  The canvas template's
    // ``x-show="!loading && !error && nodes.length > 0"``
    // keeps showing the spinner until then, which is the
    // correct UX (the user just clicked into the tab; brief
    // load is expected).
    _started: false,

    async init() {
      const tabBtn = document.querySelector('[data-bs-target="#tab-lineage-graph"]');
      if (!tabBtn) {
        // No Bootstrap tab navigation context (e.g. test
        // harness, deeplinked iframe).  Fall through to
        // an immediate load so the component still works.
        return this._loadAndRender();
      }
      if (tabBtn.classList.contains('active')) {
        // Page-load with hash deeplink (#tab-lineage-graph)
        // already activated the tab — load immediately.
        return this._loadAndRender();
      }
      tabBtn.addEventListener('shown.bs.tab', () => this._loadAndRender(), { once: true });
    },

    async _loadAndRender() {
      if (this._started) return;
      this._started = true;
      try {
        await loadCytoscapeOnce();
      } catch (e) {
        this.error = 'cytoscape.js failed to load: ' + String(e);
        this.loading = false;
        return;
      }
      try {
        const res = await fetch(this._url(), {
          headers: { Accept: 'application/json' },
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.nodes = data.nodes || [];
        this.edges = data.edges || [];
      } catch (e) {
        this.error = String(e);
        this.loading = false;
        return;
      }
      this.loading = false;
      // Render after Alpine has flipped the loading flag away
      // (so the canvas div is in the DOM).
      this.$nextTick(() => this._render());
    },

    _url() {
      const params = new URLSearchParams();
      if (this.opId) params.set('op_id', String(this.opId));
      const qs = params.toString();
      return `/api/runs/${encodeURIComponent(this.runId)}/graph${qs ? '?' + qs : ''}`;
    },

    _render() {
      if (this.nodes.length === 0) return;
      if (typeof window.cytoscape !== 'function') {
        this.error =
          'cytoscape.js failed to load — loadCytoscapeOnce() resolved but window.cytoscape is undefined.';
        return;
      }
      ensureDagreRegistered();

      const elements = [
        ...this.nodes.map((n) => ({ data: { id: n.id, table: n.table } })),
        ...this.edges.map((e) => ({
          data: {
            id: e.id,
            source: e.source,
            target: e.target,
            label: this._edgeLabel(e),
          },
        })),
      ];

      const container = this.$refs.canvas;
      this.cy = window.cytoscape({
        container,
        elements,
        style: RUN_GRAPH_STYLE,
        layout: dagLayout(),
        wheelSensitivity: 0.2,
      });

      this.cy.on('tap', 'edge', (evt) => {
        const id = evt.target.data('id');
        this.selectedEdgeId = id;
        this.selectedColumn = null;
        highlightEdge(this.cy, id);
      });
      this.cy.on('tap', 'node', (evt) => {
        const id = evt.target.data('id');
        this.selectedEdgeId = null;
        this.selectedColumn = null;
        highlightNode(this.cy, id);
      });
      this.cy.on('tap', (evt) => {
        if (evt.target === this.cy) {
          clearHighlight(this.cy);
          this.selectedEdgeId = null;
          this.selectedColumn = null;
        }
      });
    },

    _edgeLabel(edge) {
      if (!edge.transform_kinds || edge.transform_kinds.length === 0) {
        return edge.op_name || '';
      }
      return edge.transform_kinds.join(' / ');
    },

    // Side-panel helpers consumed by the template via x-show / x-for.

    currentEdge() {
      return findSelectedEdge(this.edges, this.selectedEdgeId);
    },

    selectColumn(column) {
      this.selectedColumn = selectColumn(this.cy, this.edges, column);
    },

    clearSelection() {
      const next = clearSelection(this.cy);
      this.selectedEdgeId = next.selectedEdgeId;
      this.selectedColumn = next.selectedColumn;
    },
  };
}
