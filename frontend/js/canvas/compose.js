/*
 * Composition root for the reusable Drawflow canvas editor.
 *
 * ``assembleCanvasEditor`` is the single seam every consumer (data
 * products, the scheduler task-chain editor, DataFrame Studio) calls to
 * build its Alpine component.  It owns the consumer-agnostic half — the
 * shared method bundles under ``canvas/`` and the three derived graph
 * getters — and merges in whatever the consumer's adapter contributes:
 * its block catalog, its own method bundles, and a fresh state object.
 *
 * Why an adapter instead of one giant factory:
 *   The shared bundles are plain objects of ``this``-based methods, so
 *   they bind to whatever component they are merged onto.  De-globalizing
 *   the block catalog (read off ``this.catalog``) was the last thing
 *   welding them to data products; with that gone, a consumer only has to
 *   describe *what* differs — its catalog, its extra bundles, its state —
 *   and reuse the rest verbatim.
 *
 * Merge mechanics:
 *   ``Object.assign`` of the method bundles is equivalent to the object
 *   spread the consumers used before; the bundles carry no own state and
 *   no name collisions, so merge order does not change behaviour.  The
 *   getters are (re)defined as real accessors here rather than spread,
 *   because spreading a getter snapshots its value and breaks reactivity.
 */

import { annotationMethods } from './annotations.js';
import { clipboardMethods } from './clipboard.js';
import { configFormStructuredMethods } from './config_form_structured.js';
import { connectMethods } from './connect.js';
import { contextMenuMethods } from './context_menu.js';
import { drawflowSyncMethods } from './drawflow_sync.js';
import { edgeRoutingMethods } from './edge_routing.js';
import { edgeToolbarMethods } from './edge_toolbar.js';
import { edgesMethods } from './edges.js';
import { historyMethods } from './history.js';
import { nodeOpsMethods } from './node_ops.js';
import { nodeRenderMethods } from './node_render.js';
import { outputPlusMethods } from './output_plus.js';
import { viewportMethods } from './viewport.js';

// The consumer-agnostic bundles, in their historical spread order.  Order
// is immaterial (no cross-bundle method-name collisions) but kept stable
// for readability and review.
const CORE_BUNDLES = [
  historyMethods,
  configFormStructuredMethods,
  annotationMethods,
  viewportMethods,
  clipboardMethods,
  drawflowSyncMethods,
  nodeRenderMethods,
  nodeOpsMethods,
  connectMethods,
  edgeRoutingMethods,
  edgesMethods,
  edgeToolbarMethods,
  contextMenuMethods,
  outputPlusMethods,
];

/**
 * The graph/editor state every canvas consumer needs.
 *
 * Returns a fresh object on each call (the editor mutates the maps, arrays
 * and Sets), so a consumer's state factory spreads this and layers its own
 * domain fields on top.
 *
 * @returns {Object}
 */
export function genericEditorState() {
  return {
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
    paletteQuery: '',
    minimapVisible: true,
    zoomPct: 100,
    focusMode: false,

    nodes: {},
    edges: {},
    selectedNodeId: null,

    _drawflow: null,
    _drawflowNodes: {},
    _saveTimer: null,
    _validateTimer: null,
    _suppressAutosave: false,

    edgeToolbar: { visible: false, x: 0, y: 0, edgeId: null },
    outputPlusPicker: { open: false, x: 0, y: 0, sourcePqlId: null },
    ctxMenu: { open: false, x: 0, y: 0, kind: 'canvas', nodeId: null, edgeId: null },
    _selectedEdgeId: null,
    _edgeToolbarHideTimer: null,
    _edgeToolbarRaf: null,
    _runningEdgeIds: new Set(),
    _outputPlusElements: new Map(),
    _decoratedSvgs: new WeakSet(),
  };
}

/**
 * Build an Alpine canvas-editor component from a consumer adapter.
 *
 * @param {Object} adapter
 * @param {Object} adapter.catalog          Injected block taxonomy, read off
 *   ``this.catalog`` by the shared bundles.
 * @param {Object[]} [adapter.bundles]       Consumer-specific method bundles
 *   merged after the core bundles.
 * @param {(ctx: Object) => Object} [adapter.state]  Fresh state object for
 *   this component (spreads {@link genericEditorState} plus domain fields).
 * @param {Object} [adapter.caps]            Optional capability flags gating
 *   optional behaviour (preview, versions, run, …).
 * @param {Object} [ctx]                     Page context handed to ``state``.
 * @returns {Object} The Alpine component object.
 */
export function assembleCanvasEditor(adapter, ctx) {
  const comp = {};
  for (const bundle of CORE_BUNDLES) Object.assign(comp, bundle);
  for (const bundle of adapter.bundles || []) Object.assign(comp, bundle);
  Object.assign(comp, adapter.state ? adapter.state(ctx) : {});

  // The single seam binding the shared bundles to this consumer's blocks.
  comp.catalog = adapter.catalog;
  if (adapter.caps) comp.caps = adapter.caps;

  // Derived getters as real accessors (spreading a getter snapshots it).
  Object.defineProperties(comp, {
    nodeCount: {
      get() {
        return Object.keys(this.nodes).length;
      },
      enumerable: true,
      configurable: true,
    },
    edgeCount: {
      get() {
        return Object.keys(this.edges).length;
      },
      enumerable: true,
      configurable: true,
    },
    selectedNode: {
      get() {
        if (!this.selectedNodeId) return null;
        return this.nodes[this.selectedNodeId] || null;
      },
      enumerable: true,
      configurable: true,
    },
  });

  return comp;
}
