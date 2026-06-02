/*
 * Visual Data-Product canvas editor — Alpine factory (composition root).
 *
 * Mounts a Drawflow block-and-wire editor inside the right-hand canvas
 * area, syncs the graph against the HTTP routes under ``/api/dp/{id}/canvas``,
 * and renders block-specific config forms in the right drawer.
 *
 * Structure:
 *   This file is intentionally thin — it holds only the reactive state, the
 *   three derived getters, and the composition of the behaviour bundles under
 *   ``dp_canvas/editor/`` (one concern per file: lifecycle, drawflow_sync,
 *   node_render, node_ops, edges, edge_routing, edge_toolbar, connect,
 *   context_menu, output_plus, viewport, clipboard, preview, run, versions,
 *   navigation, annotations, history, config_form, ghost_review).  Each
 *   bundle is a plain object of ``this``-based methods spread into the
 *   returned component; ``this`` resolves to the Alpine proxy at call time, so
 *   methods in different bundles call each other freely through ``this``.
 *   State + getters MUST stay inline here — object spread snapshots a getter's
 *   value, which would break reactivity.
 *
 * Library choice:
 *   Drawflow (single-file UMD, no framework dependency) was picked over
 *   Rete.js v2 because Rete v2 requires a Vue / React / Lit render-
 *   plugin to paint anything, and this codebase carries none of those.
 *   Drawflow ships a vanilla DOM renderer in 50 kB and matches the
 *   ``<script src=>`` lazy-load pattern already used by cytoscape in
 *   ``components/lineage_dag``.  Window globals ``window.Drawflow``
 *   are registered by the CDN bundle loaded from ``dp_canvas_editor.html``.
 */

import { paletteGroupsFromCatalog } from '../dp_canvas/_block_catalog.js';
import { annotationMethods } from '../dp_canvas/editor/annotations.js';
import { clipboardMethods } from '../dp_canvas/editor/clipboard.js';
import { configFormMethods } from '../dp_canvas/editor/config_form.js';
import { connectMethods } from '../dp_canvas/editor/connect.js';
import { contextMenuMethods } from '../dp_canvas/editor/context_menu.js';
import { drawflowSyncMethods } from '../dp_canvas/editor/drawflow_sync.js';
import { edgeRoutingMethods } from '../dp_canvas/editor/edge_routing.js';
import { edgeToolbarMethods } from '../dp_canvas/editor/edge_toolbar.js';
import { edgesMethods } from '../dp_canvas/editor/edges.js';
import { ghostReviewMethods } from '../dp_canvas/editor/ghost_review.js';
import { historyMethods } from '../dp_canvas/editor/history.js';
import { lifecycleMethods } from '../dp_canvas/editor/lifecycle.js';
import { navigationMethods } from '../dp_canvas/editor/navigation.js';
import { nodeOpsMethods } from '../dp_canvas/editor/node_ops.js';
import { nodeRenderMethods } from '../dp_canvas/editor/node_render.js';
import { outputPlusMethods } from '../dp_canvas/editor/output_plus.js';
import { persistenceMethods } from '../dp_canvas/editor/persistence.js';
import { previewMethods } from '../dp_canvas/editor/preview.js';
import { runMethods } from '../dp_canvas/editor/run.js';
import { versionsMethods } from '../dp_canvas/editor/versions.js';
import { viewportMethods } from '../dp_canvas/editor/viewport.js';

export function dpCanvasEditor(product, ctx) {
  const ctxSafe = ctx || {};
  return {
    // Behaviour bundles — plain `this`-based method objects composed onto
    // the component.  State + getters stay inline below (object spread
    // would snapshot a getter's value, breaking reactivity).
    ...historyMethods,
    ...configFormMethods,
    ...annotationMethods,
    ...viewportMethods,
    ...clipboardMethods,
    ...drawflowSyncMethods,
    ...nodeRenderMethods,
    ...nodeOpsMethods,
    ...persistenceMethods,
    ...previewMethods,
    ...runMethods,
    ...versionsMethods,
    ...navigationMethods,
    ...connectMethods,
    ...edgeRoutingMethods,
    ...edgesMethods,
    ...edgeToolbarMethods,
    ...contextMenuMethods,
    ...outputPlusMethods,
    ...ghostReviewMethods,
    ...lifecycleMethods,

    product,
    canWrite: !!(ctxSafe.is_admin || ctxSafe.is_steward),

    loading: true,
    saving: false,
    version: null,
    saveState: 'idle',
    saveError: null,
    lastSavedAt: null,

    errors: [],
    pinSchemas: {},
    validating: false,
    previewRowCountByNode: {},
    compactBodies: false,
    edgeCategories: {},
    orthogonalEdges: false,
    multiSelectedNodeIds: [],
    annotations: [],
    _undoStack: [],
    _redoStack: [],
    _UNDO_DEPTH: 50,
    searchOpen: false,
    searchQuery: '',
    searchCursor: 0,
    minimapVisible: true,
    zoomPct: 100,
    focusMode: false,

    nodes: {},
    edges: {},
    selectedNodeId: null,

    paletteGroups: paletteGroupsFromCatalog(),

    projectInput: '',
    joinKeyInput: '',
    groupKeyInput: '',
    mergeOnInput: '',

    // Run feedback lives in an inline dock anchored to the canvas
    // (not a modal): `running` while the POST is in flight, then either
    // `runResult` (per-sink outcome) or `runError` (a whole-run failure).
    runDockOpen: false,
    runResult: null,
    runError: null,
    running: false,

    previewOpen: false,
    previewBusy: false,
    previewNodeId: null,
    previewLimit: 100,
    previewResult: null,
    previewError: null,

    dpPicker: { loaded: false, products: [] },
    breadcrumbTrail: [],

    versionsOpen: false,
    versionsList: [],
    pinnedVersion: null,

    _drawflow: null,
    _drawflowNodes: {},
    _saveTimer: null,
    _validateTimer: null,
    _suppressAutosave: false,

    edgeToolbar: { visible: false, x: 0, y: 0, edgeId: null },
    outputPlusPicker: { open: false, x: 0, y: 0, sourcePqlId: null },
    ctxMenu: { open: false, x: 0, y: 0, kind: 'canvas', nodeId: null, edgeId: null },
    inlinePeek: { open: false, x: 0, y: 0, nodeId: null, loading: false, columns: [], rows: [] },
    ghost: {
      open: false,
      text: '',
      busy: false,
      diff: null,
      errors: [],
      proposed: null,
      accept: {},
    },
    _selectedEdgeId: null,
    _edgeToolbarHideTimer: null,
    _edgeToolbarRaf: null,
    _runningEdgeIds: new Set(),
    _outputPlusElements: new Map(),
    _decoratedSvgs: new WeakSet(),

    get nodeCount() {
      return Object.keys(this.nodes).length;
    },
    get edgeCount() {
      return Object.keys(this.edges).length;
    },
    get selectedNode() {
      if (!this.selectedNodeId) return null;
      return this.nodes[this.selectedNodeId] || null;
    },
  };
}
