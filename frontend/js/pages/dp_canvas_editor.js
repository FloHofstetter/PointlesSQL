/*
 * Visual Data-Product canvas editor — Alpine factory.
 *
 * Mounts a Drawflow block-and-wire editor inside the right-hand canvas
 * area, syncs the graph against the HTTP routes under ``/api/dp/{id}/canvas``,
 * and renders block-specific config forms in the right drawer.
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

import { installZoomObserver } from '../dp_canvas/_canvas_helpers.js';
import { installSmoothCurvature } from '../dp_canvas/_drawflow_loader.js';
import { installFocusModeShortcut } from '../dp_canvas/_focus_mode.js';
import {
  BLOCK_DEFS,
  nodeHtml,
  paletteGroupsFromCatalog,
  pinIndexFor,
} from '../dp_canvas/_block_catalog.js';
import {
  describeConfig,
  generateNodeId,
  renderColsHtml,
  renderFooterHtml,
} from '../dp_canvas/_render_helpers.js';
import { annotationMethods } from '../dp_canvas/editor/annotations.js';
import { configFormMethods } from '../dp_canvas/editor/config_form.js';
import { historyMethods } from '../dp_canvas/editor/history.js';

export function dpCanvasEditor(product, ctx) {
  const ctxSafe = ctx || {};
  return {
    // Behaviour bundles — plain `this`-based method objects composed onto
    // the component.  State + getters stay inline below (object spread
    // would snapshot a getter's value, breaking reactivity).
    ...historyMethods,
    ...configFormMethods,
    ...annotationMethods,

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

    async init() {
      // Alpine auto-invokes init() on any x-data object that defines it, and
      // the template also carries x-init="init()" — so without this guard the
      // body runs twice, spinning up two Drawflow instances (two .drawflow
      // precanvases in one container).  The second became this._drawflow while
      // the first was left empty but first in the DOM, so every
      // querySelector('.drawflow') and the fit-to-view targeted the wrong,
      // empty canvas.
      if (this._initialized) return;
      this._initialized = true;
      this._focusModeOff = installFocusModeShortcut(this);
      try {
        if (localStorage.getItem('pql.canvas.minimap.collapsed') === '1') {
          this.minimapVisible = false;
        }
      } catch (_e) {
        // localStorage unavailable — keep the minimap visible.
      }
      if (typeof window.Drawflow !== 'function') {
        // Defer one tick — the bundle <script> at the bottom of the
        // template may not have executed yet when Alpine kicks init().
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
      if (typeof window.Drawflow !== 'function') {
        this.loading = false;
        this.saveState = 'error';
        this.saveError = 'Block-editor library failed to load.';
        return;
      }
      const node = this.$refs.canvas;
      const df = new window.Drawflow(node);
      df.reroute = true;
      df.start();
      this._drawflow = df;

      // Swap in the smooth/step connection-path generator (shared with the
      // mesh + diff surfaces).  ``df.curvature`` is 0.5 by Drawflow default,
      // set explicitly so the orthogonal toggle has a known value to flip
      // back to.
      installSmoothCurvature(window.Drawflow);
      df.curvature = 0.5;

      // One shared observer for every node box: when a node grows (async
      // schema columns, row-count / status footer, error badge, compact
      // toggle, late web-font), its pins move, so the connections wired to
      // it must be recomputed or they point at the old pin position.
      this._nodeResizeObserver =
        typeof ResizeObserver === 'function'
          ? new ResizeObserver((entries) => {
              // Only the nodes that actually resized need their wires
              // recomputed — collect their dfIds and do a targeted update
              // instead of sweeping the whole graph on every body growth.
              if (!this._connNodeDirty) this._connNodeDirty = new Set();
              for (const e of entries) {
                const m = e.target.id && e.target.id.match(/^node-(\d+)$/);
                if (m) this._connNodeDirty.add(m[1]);
              }
              this._scheduleResizeConnUpdate();
            })
          : null;

      // Defensive wrap around Drawflow's internal `position()` — it throws
      // a TypeError on `data[id].pos_x` when the mousedown that set
      // ele_selected hit an element whose id-strip yields no data entry
      // (sticky notes, toolbar overlays, etc).  Swallow only that exact
      // shape so a real bug still surfaces.  Drag itself completes fine
      // before the throw; this just silences the console noise.
      const _origPosition = df.position && df.position.bind(df);
      if (_origPosition) {
        df.position = (...args) => {
          try {
            return _origPosition(...args);
          } catch (e) {
            if (e instanceof TypeError && String(e.message || '').includes('pos_x')) {
              return undefined;
            }
            throw e;
          }
        };
      }

      df.on('nodeSelected', (id) => this._onDrawflowNodeSelected(id));
      df.on('nodeUnselected', () => {
        this.selectedNodeId = null;
      });
      df.on('nodeMoved', (dfId) => {
        this._onNodePositionChanged(dfId);
        this._repositionOutputPlusFor(dfId);
        this._scheduleEdgeToolbarReposition();
      });
      df.on('connectionCreated', (info) => {
        this._syncFromDrawflow();
        // After the sync, the edge appears in `this.edges`; walk the
        // target side and fill sensible defaults if its config is empty.
        const tgtDfId = info && info.input_id;
        if (tgtDfId != null) {
          const tgtPqlId = this._pqlIdForDfId(tgtDfId);
          if (tgtPqlId) this._applySensibleDefaultsIfEmpty(tgtPqlId);
        }
        this._scheduleDecorateAllConnections();
      });
      df.on('connectionRemoved', () => {
        this._clearSelectedEdge();
        this._hideEdgeToolbar();
        this._syncFromDrawflow();
      });
      df.on('nodeCreated', (dfId) => this._observeNode(dfId));
      df.on('nodeRemoved', (dfId) => {
        this._unobserveNode(dfId);
        this._syncFromDrawflow();
      });
      df.on('nodeDataChanged', () => this._syncFromDrawflow());

      // Live zoom value as CSS custom property so the edge-stroke math
      // (and hit-area width) stay legible at every zoom level — same
      // technique n8n uses, only stroke-driven via CSS instead of OKLCH.
      //
      // Drawflow 0.0.59 only emits the ``zoom`` event for mousewheel
      // input — programmatic ``df.zoom_in/out/reset`` and any other
      // path that mutates the transform silently bypass the listener.
      // A MutationObserver on the live ``.drawflow`` transform is the
      // only reliable hook, so the helper does both jobs at once:
      // mirror the scale into ``--pql-zoom`` and call the existing
      // ``_updateZoomCssVar`` hook so output-plus + mid-toolbar still
      // reposition on every zoom step.
      const inner = df.precanvas;
      this._zoomObserver = installZoomObserver(inner, node, (z) => {
        this._scheduleAllOutputPlusReposition();
        this._scheduleEdgeToolbarReposition();
        // The observer fires on every transform change (pan + zoom), so it's
        // the right place to keep the zoom-% readout and the minimap viewport
        // rectangle in sync.
        this.zoomPct = Math.round(z * 100);
        this._scheduleMinimapRender();
      });

      // Click on empty canvas clears any selected edge.  Click on an
      // edge SVG is handled inside the per-connection decoration below.
      df.container.addEventListener('click', (ev) => {
        if (ev.target.closest('.connection')) return;
        if (ev.target.closest('.pql-edge-toolbar')) return;
        this._clearSelectedEdge();
      });

      // Right-click context menu — target-aware (node / edge / empty canvas).
      df.container.addEventListener('contextmenu', (ev) => this._onCanvasContextMenu(ev));

      // Live drag-to-connect validation.  Drawflow exposes no drag-start
      // event, so listen for a pointerdown on an output socket in parallel
      // with Drawflow's own drag and highlight which input pins are valid
      // drop targets (free slot + no cycle); clear on pointerup.  Drawflow's
      // connectionCreated stays the source of truth for the actual wire.
      df.container.addEventListener('pointerdown', (ev) => this._onOutputPointerDown(ev));

      // Keyboard accessibility: Enter / Space on a focused node opens its
      // config; arrow keys pan the canvas when focus is on the canvas chrome
      // (not inside a node or a form field).
      df.container.addEventListener('keydown', (ev) => {
        const nodeEl = ev.target.closest && ev.target.closest('.drawflow-node');
        if (nodeEl && (ev.key === 'Enter' || ev.key === ' ')) {
          ev.preventDefault();
          const pqlId = nodeEl.getAttribute('data-pql-pql-id');
          if (pqlId && this.nodes[pqlId]) this.selectedNodeId = pqlId;
          return;
        }
        if (this._isFormFocused(ev.target) || nodeEl) return;
        const STEP = 60;
        const pan = {
          ArrowLeft: [STEP, 0],
          ArrowRight: [-STEP, 0],
          ArrowUp: [0, STEP],
          ArrowDown: [0, -STEP],
        }[ev.key];
        if (!pan) return;
        ev.preventDefault();
        df.canvas_x += pan[0];
        df.canvas_y += pan[1];
        df.precanvas.style.transform = `translate(${df.canvas_x}px, ${df.canvas_y}px) scale(${df.zoom})`;
        this._scheduleMinimapRender();
      });

      // Double-click on a DP◫ node opens that DP's canvas in-place
      // (push the current DP onto the breadcrumb trail in localStorage).
      const canvasEl = this.$refs.canvas;
      canvasEl.addEventListener('dblclick', (ev) => this._onCanvasDoubleClick(ev));

      // Keyboard shortcuts: Ctrl+D dupes the single-selected node;
      // Ctrl+C / Ctrl+V copy / paste honour the multi-select set if any
      // (otherwise fall back to the single selection); Delete / Backspace
      // bulk-removes the multi-selected set with a confirm prompt.
      document.addEventListener('keydown', (ev) => {
        if (this._isFormFocused(ev.target)) return;
        if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'd' || ev.key === 'D')) {
          if (!this.selectedNodeId) return;
          ev.preventDefault();
          this.duplicateSelectedNode();
          return;
        }
        if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'c' || ev.key === 'C')) {
          if (this.multiSelectedNodeIds.length === 0 && !this.selectedNodeId) return;
          ev.preventDefault();
          this.copySelectionToClipboard();
          return;
        }
        if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'v' || ev.key === 'V')) {
          ev.preventDefault();
          this.pasteClipboard();
          return;
        }
        if (ev.key === 'Delete' || ev.key === 'Backspace') {
          if (this._selectedEdgeId) {
            ev.preventDefault();
            this.deleteEdgeById(this._selectedEdgeId);
            return;
          }
          if (this.multiSelectedNodeIds.length > 1) {
            ev.preventDefault();
            this.bulkDeleteSelected();
          }
        }
        if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'f' || ev.key === 'F')) {
          ev.preventDefault();
          this.openSearch();
        }
        if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'l' || ev.key === 'L')) {
          ev.preventDefault();
          this.autoTidy();
        }
        if ((ev.ctrlKey || ev.metaKey) && !ev.shiftKey && (ev.key === 'z' || ev.key === 'Z')) {
          ev.preventDefault();
          this.undo();
        }
        if (
          ((ev.ctrlKey || ev.metaKey) && (ev.key === 'y' || ev.key === 'Y')) ||
          ((ev.ctrlKey || ev.metaKey) && ev.shiftKey && (ev.key === 'z' || ev.key === 'Z'))
        ) {
          ev.preventDefault();
          this.redo();
        }
      });

      // Shift+click on a node toggles it in the multi-selection set;
      // a plain click clears the set so the right-drawer single-edit
      // flow stays unsurprising.
      canvasEl.addEventListener(
        'click',
        (ev) => {
          const nodeEl = ev.target.closest('.drawflow-node');
          if (!nodeEl) {
            this._clearMultiSelection();
            return;
          }
          if (!ev.shiftKey) {
            this._clearMultiSelection();
            return;
          }
          ev.preventDefault();
          ev.stopPropagation();
          const dfId = nodeEl.id.replace('node-', '');
          const pqlId = this._pqlIdForDfId(dfId);
          if (!pqlId) return;
          const idx = this.multiSelectedNodeIds.indexOf(pqlId);
          if (idx >= 0) this.multiSelectedNodeIds.splice(idx, 1);
          else this.multiSelectedNodeIds.push(pqlId);
          this._refreshMultiSelectStyles();
        },
        true
      );

      this._restoreBreadcrumb();

      // Optional-chain via "&&" — Alpine's expression evaluator complains when
      // selectedNode is null, which surfaces as a console error on every
      // empty-canvas load.  The deep watcher still catches every config
      // mutation once a node is selected.
      this.$watch('(selectedNode && selectedNode.config) || null', () => this.onConfigChanged(), {
        deep: true,
      });

      await this.loadLatest();
      await this._refreshVersionsList();

      // Conditional co-edit attach — opt-in via ?coedit=1 so the
      // single-user editor pays no Y.js download cost by default.
      try {
        const { attachCanvasCoedit, isCoeditEnabled } = await import('../dp_canvas/coedit.js');
        if (isCoeditEnabled()) {
          this._coeditController = await attachCanvasCoedit(this, this.product.id);
        }
      } catch (e) {
        // Coedit is best-effort; never block the single-user editor.
      }
    },

    saveStateLabel() {
      if (this.saveState === 'saving') return 'Saving…';
      if (this.saveState === 'error') return 'Save failed';
      if (this.saveState === 'saved' && this.lastSavedAt) return '✓ Saved';
      if (this.version !== null) return 'v' + this.version;
      return '';
    },

    saveStateTooltip() {
      if (this.saveState === 'error') return this.saveError || 'Save failed';
      if (this.saveState === 'saved' && this.lastSavedAt) {
        const date = new Date(this.lastSavedAt);
        return 'Last saved at ' + date.toLocaleString();
      }
      return '';
    },

    saveStateClass() {
      if (this.saveState === 'error') return 'text-danger';
      if (this.saveState === 'saving') return 'text-muted';
      if (this.saveState === 'saved') return 'text-success';
      return 'text-muted';
    },

    async loadLatest() {
      this.loading = true;
      const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas`, {
        silent: true,
      });
      if (!res.ok) {
        this.loading = false;
        this.saveState = 'error';
        this.saveError = res.error || 'Load failed';
        return;
      }
      this.version = res.data.version;
      if (res.data.document) {
        this._suppressAutosave = true;
        this._loadIntoDrawflow(res.data.document);
        this._suppressAutosave = false;
      }
      this.loading = false;
      this.saveState = 'saved';
      this.lastSavedAt = res.data.created_at || new Date().toISOString();
      this._scheduleValidate();
      // Auto-fit the viewport once per load so multi-node DPs don't open
      // showing only the top-left node.
      if (!this._initialFitDone && Object.keys(this.nodes).length > 0) {
        this._initialFitDone = true;
        this.$nextTick(() => this.fitToView());
      }
    },

    fitToView() {
      const df = this._drawflow;
      if (!df) return;
      const nodes = Object.values(this.nodes);
      if (nodes.length === 0) return;
      const NODE_W = 180;
      const NODE_H = 110;
      const PAD = 60;
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      for (const [pqlId, n] of Object.entries(this.nodes)) {
        const p = n.position || { x: 100, y: 100 };
        // Prefer the live DOM box so the fit accounts for nodes that have
        // grown a schema/row-count body; fall back to the saved position
        // plus a nominal size before the node has rendered.
        const dfId = this._drawflowNodes[pqlId];
        const el = dfId && df.container.querySelector(`#node-${dfId}`);
        const x0 = el ? el.offsetLeft : p.x;
        const y0 = el ? el.offsetTop : p.y;
        const w = el ? el.offsetWidth : NODE_W;
        const h = el ? el.offsetHeight : NODE_H;
        if (x0 < minX) minX = x0;
        if (y0 < minY) minY = y0;
        if (x0 + w > maxX) maxX = x0 + w;
        if (y0 + h > maxY) maxY = y0 + h;
      }
      const spanX = Math.max(maxX - minX, 1);
      const spanY = Math.max(maxY - minY, 1);
      const rect = df.container.getBoundingClientRect();
      const fitW = Math.max(rect.width - PAD * 2, 100);
      const fitH = Math.max(rect.height - PAD * 2, 100);
      const zoom = Math.min(fitW / spanX, fitH / spanY, 1);
      df.zoom = zoom;
      // Centre the graph's bounding box in the viewport rather than pinning it
      // to the top-left corner — a small DAG should sit in the middle of the
      // canvas, not hug the palette edge.
      df.canvas_x = (rect.width - spanX * zoom) / 2 - minX * zoom;
      df.canvas_y = (rect.height - spanY * zoom) / 2 - minY * zoom;
      const precanvas = df.precanvas;
      if (precanvas) {
        precanvas.style.transform = `translate(${df.canvas_x}px, ${df.canvas_y}px) scale(${zoom})`;
      }
      // Drawflow computes connection endpoints in a zoom-dependent basis, so
      // changing df.zoom without recomputing leaves every wire pinned to its
      // pre-fit coordinates (the connections float away from their nodes).
      // CSS-transform changes don't trip the node ResizeObserver, so sweep
      // explicitly here.
      this._scheduleConnNodeUpdate();
      this._scheduleMinimapRender();
      this._scheduleRerouteOrthogonal();
    },

    zoomReset100() {
      // Reset to 1:1 zoom, keeping the current viewport centre fixed.
      const df = this._drawflow;
      if (!df || typeof df.canvas_x === 'undefined') return;
      const rect = df.container.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const factor = 1 / (df.zoom || 1);
      df.canvas_x = cx - (cx - df.canvas_x) * factor;
      df.canvas_y = cy - (cy - df.canvas_y) * factor;
      df.zoom = 1;
      df.precanvas.style.transform = `translate(${df.canvas_x}px, ${df.canvas_y}px) scale(1)`;
      this._scheduleConnNodeUpdate();
      this._scheduleMinimapRender();
    },

    _loadIntoDrawflow(doc) {
      const df = this._drawflow;
      df.clear();
      this._drawflowNodes = {};
      this.nodes = {};
      this.edges = {};
      this.annotations = ((doc.metadata || {}).annotations || []).map((a) => ({
        ...a,
      }));
      // First pass: add nodes.
      for (const node of doc.nodes || []) {
        const def = BLOCK_DEFS[node.block_type];
        if (!def) continue;
        const pos = node.position || { x: 100, y: 100 };
        const dfId = df.addNode(
          node.block_type,
          def.inputs,
          def.outputs,
          pos.x || 100,
          pos.y || 100,
          node.block_type,
          { pql_node_id: node.id, block_type: node.block_type },
          nodeHtml(node.block_type, node.id),
          false
        );
        this._drawflowNodes[node.id] = dfId;
        this.nodes[node.id] = {
          id: node.id,
          block_type: node.block_type,
          config: { ...def.defaultConfig(), ...(node.config || {}) },
          position: pos,
        };
        this._refreshNodeBody(node.id);
      }
      // Second pass: add edges.
      for (const edge of doc.edges || []) {
        const sourceDf = this._drawflowNodes[edge.source_node_id];
        const targetDf = this._drawflowNodes[edge.target_node_id];
        if (!sourceDf || !targetDf) continue;
        const targetNode = (doc.nodes || []).find((n) => n.id === edge.target_node_id);
        const sourceIdx = 1; // Single-output blocks only.
        const targetIdx = pinIndexFor(
          targetNode ? targetNode.block_type : '',
          edge.target_pin,
          'in'
        );
        try {
          df.addConnection(sourceDf, targetDf, `output_${sourceIdx}`, `input_${targetIdx + 1}`);
        } catch (e) {
          // Connection target invalid (block schema mismatch with saved doc);
          // skip the edge — the validator will surface it later.
        }
      }
      this._syncFromDrawflow();
      this._scheduleDecorateAllConnections();
      this.$nextTick(() => {
        for (const pqlId of Object.keys(this.nodes)) this._renderOutputPlus(pqlId);
        // Loaded nodes are observed via the nodeCreated event, but run one
        // explicit observe + connection sweep here too: it catches any
        // layout settle (web-font swap, scrollbar) between addNode and the
        // first paint, and re-renders existing edges with the patched path.
        for (const dfId of Object.values(this._drawflowNodes)) this._observeNode(dfId);
        this._scheduleConnNodeUpdate();
      });
    },

    // Position-only handler: coalesced via requestAnimationFrame so a 60Hz
    // mousemove stream never triggers a full graph rebuild mid-drag.  The
    // node stays glued to the cursor; the structural sync (autosave,
    // validate, edge re-derive) stays on the connection / data-change paths.
    _onNodePositionChanged(dfId) {
      if (!this._dragDirtyDfIds) this._dragDirtyDfIds = new Set();
      this._dragDirtyDfIds.add(String(dfId));
      if (this._dragRafHandle != null) return;
      this._dragRafHandle = window.requestAnimationFrame(() => {
        this._dragRafHandle = null;
        this._flushDragPositions();
      });
    },

    _flushDragPositions() {
      const dirty = this._dragDirtyDfIds;
      if (!dirty || dirty.size === 0) return;
      this._dragDirtyDfIds = new Set();
      if (!this._drawflow) return;
      const raw = this._drawflow.export();
      const home = raw && raw.drawflow && raw.drawflow.Home;
      const dfNodes = (home && home.data) || {};
      for (const dfId of dirty) {
        const dfNode = dfNodes[dfId];
        if (!dfNode) continue;
        const pqlId = (dfNode.data || {}).pql_node_id;
        if (!pqlId || !this.nodes[pqlId]) continue;
        this.nodes[pqlId].position = { x: dfNode.pos_x, y: dfNode.pos_y };
      }
      if (!this._suppressAutosave) {
        this._scheduleAutosave();
      }
      this._scheduleMinimapRender();
      this._scheduleRerouteOrthogonal();
    },

    _syncFromDrawflow() {
      if (!this._drawflow) return;
      const raw = this._drawflow.export();
      const home = raw && raw.drawflow && raw.drawflow.Home;
      const dfNodes = (home && home.data) || {};
      const newNodes = {};
      const newEdges = {};
      const reverseId = {};

      for (const [dfId, dfNode] of Object.entries(dfNodes)) {
        const data = dfNode.data || {};
        const pqlId = data.pql_node_id;
        if (!pqlId) continue;
        reverseId[dfId] = pqlId;
        const existing = this.nodes[pqlId];
        newNodes[pqlId] = {
          id: pqlId,
          block_type: data.block_type,
          config: existing
            ? existing.config
            : (BLOCK_DEFS[data.block_type] || { defaultConfig: () => ({}) }).defaultConfig(),
          position: { x: dfNode.pos_x, y: dfNode.pos_y },
        };
      }
      this._drawflowNodes = {};
      for (const [dfId, pqlId] of Object.entries(reverseId)) {
        this._drawflowNodes[pqlId] = parseInt(dfId, 10);
      }

      // Edges.
      for (const [dfId, dfNode] of Object.entries(dfNodes)) {
        const pqlSourceId = reverseId[dfId];
        if (!pqlSourceId) continue;
        const outputs = dfNode.outputs || {};
        for (const [outputName, outputData] of Object.entries(outputs)) {
          const conns = (outputData && outputData.connections) || [];
          for (const conn of conns) {
            const pqlTargetId = reverseId[conn.node];
            if (!pqlTargetId) continue;
            const sourcePin = 'out';
            const targetIdx = parseInt((conn.output || '').replace('input_', ''), 10) - 1;
            const targetBlock = newNodes[pqlTargetId] ? newNodes[pqlTargetId].block_type : '';
            const targetPin =
              targetBlock === 'Join' || targetBlock === 'Union'
                ? targetIdx === 1
                  ? 'right'
                  : 'left'
                : 'in';
            const sourceOutputIdx = parseInt((outputName || '').replace('output_', ''), 10);
            if (!Number.isFinite(sourceOutputIdx)) continue;
            const edgeId = `e-${pqlSourceId}:${sourcePin}->${pqlTargetId}:${targetPin}`;
            newEdges[edgeId] = {
              id: edgeId,
              source_node_id: pqlSourceId,
              source_pin: sourcePin,
              target_node_id: pqlTargetId,
              target_pin: targetPin,
            };
          }
        }
      }

      this.nodes = newNodes;
      this.edges = newEdges;
      // O(1) lookup from a connection SVG's `node_out_node-<src>` /
      // `node_in_node-<tgt>` dfId pair to the canonical edge id.  Rebuilt
      // each sync so hover, click-select and category styling don't each
      // re-scan all nodes × edges per connection.
      this._edgeByDfIds = {};
      for (const edge of Object.values(newEdges)) {
        const srcDf = this._drawflowNodes[edge.source_node_id];
        const tgtDf = this._drawflowNodes[edge.target_node_id];
        if (srcDf != null && tgtDf != null) {
          this._edgeByDfIds[`${srcDf}|${tgtDf}`] = edge.id;
        }
      }
      if (this.selectedNodeId && !newNodes[this.selectedNodeId]) {
        this.selectedNodeId = null;
      }
      // Output-plus visibility tracks outgoing-edge presence; refresh
      // every source node after the edge dict settles so a freshly
      // connected pin hides its plus and a freshly disconnected one
      // un-hides.  Cheap idempotent loop — _renderOutputPlus reuses
      // the existing handle and only updates style.display.
      for (const pqlId of Object.keys(newNodes)) this._renderOutputPlus(pqlId);
      if (!this._suppressAutosave) {
        this._scheduleAutosave();
        this._scheduleValidate();
      }
    },

    _onDrawflowNodeSelected(dfId) {
      for (const [pqlId, mappedDfId] of Object.entries(this._drawflowNodes)) {
        if (String(mappedDfId) === String(dfId)) {
          this.selectedNodeId = pqlId;
          return;
        }
      }
      this.selectedNodeId = null;
    },

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

    toggleCompactBodies() {
      this.compactBodies = !this.compactBodies;
      const wrap = this.$refs.canvas;
      if (wrap) wrap.classList.toggle('pql-canvas-compact', this.compactBodies);
    },

    openSearch() {
      this.searchOpen = true;
      this.searchQuery = '';
      this.searchCursor = 0;
      this.$nextTick(() => {
        const el = this.$refs.searchInput;
        if (el) el.focus();
      });
    },

    closeSearch() {
      this.searchOpen = false;
    },

    searchMatches() {
      const q = (this.searchQuery || '').toLowerCase().trim();
      const all = Object.values(this.nodes);
      if (!q) return all.slice(0, 20);
      return all
        .filter(
          (n) => n.block_type.toLowerCase().includes(q) || (n.id || '').toLowerCase().includes(q)
        )
        .slice(0, 20);
    },

    searchNavigate(direction) {
      const matches = this.searchMatches();
      if (matches.length === 0) return;
      this.searchCursor = (this.searchCursor + direction + matches.length) % matches.length;
    },

    searchSelectMatch() {
      const matches = this.searchMatches();
      const target = matches[this.searchCursor];
      if (!target) return;
      const dfId = this._drawflowNodes[target.id];
      if (dfId == null) return;
      const df = this._drawflow;
      if (df && typeof df.canvas_x !== 'undefined') {
        const pos = target.position || { x: 100, y: 100 };
        const containerRect = df.container.getBoundingClientRect();
        df.canvas_x = -pos.x * df.zoom + containerRect.width / 2;
        df.canvas_y = -pos.y * df.zoom + containerRect.height / 2;
        const precanvas = df.precanvas;
        if (precanvas) {
          precanvas.style.transform = `translate(${df.canvas_x}px, ${df.canvas_y}px) scale(${df.zoom})`;
        }
      }
      this.selectedNodeId = target.id;
      this.closeSearch();
    },

    toggleMinimap() {
      this.minimapVisible = !this.minimapVisible;
      try {
        if (this.minimapVisible) {
          localStorage.removeItem('pql.canvas.minimap.collapsed');
        } else {
          localStorage.setItem('pql.canvas.minimap.collapsed', '1');
        }
      } catch (_e) {
        // localStorage disabled — visibility still toggles per-session.
      }
      if (this.minimapVisible) this._scheduleMinimapRender();
    },

    _scheduleMinimapRender() {
      if (!this.minimapVisible) return;
      if (this._minimapRafHandle != null) return;
      this._minimapRafHandle = window.requestAnimationFrame(() => {
        this._minimapRafHandle = null;
        this._renderMinimap();
      });
    },

    _renderMinimap() {
      const host = this.$refs.minimap;
      if (!host) return;
      const W = 200;
      const H = 130;
      const PAD = 6;
      const nodes = Object.values(this.nodes);
      if (nodes.length === 0) {
        host.innerHTML = `<svg width="${W}" height="${H}"><rect width="${W}" height="${H}" fill="var(--bs-tertiary-bg)" stroke="var(--bs-border-color)" /></svg>`;
        return;
      }
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      for (const n of nodes) {
        const p = n.position || { x: 100, y: 100 };
        if (p.x < minX) minX = p.x;
        if (p.y < minY) minY = p.y;
        if (p.x > maxX) maxX = p.x;
        if (p.y > maxY) maxY = p.y;
      }
      const NODE_W = 160;
      const NODE_H = 80;
      maxX += NODE_W;
      maxY += NODE_H;
      const spanX = Math.max(maxX - minX, 1);
      const spanY = Math.max(maxY - minY, 1);
      const scale = Math.min((W - PAD * 2) / spanX, (H - PAD * 2) / spanY);
      // Remember the canvas-local → minimap mapping so the click/drag-pan
      // handler can invert it.
      this._minimapTransform = { minX, minY, scale, PAD, W, H };
      const rects = nodes
        .map((n) => {
          const p = n.position || { x: 100, y: 100 };
          const x = PAD + (p.x - minX) * scale;
          const y = PAD + (p.y - minY) * scale;
          const w = NODE_W * scale;
          const h = NODE_H * scale;
          const fill = n.id === this.selectedNodeId ? 'var(--bs-primary)' : 'var(--bs-secondary)';
          return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" fill="${fill}" />`;
        })
        .join('');
      // Viewport rectangle — the slice of the canvas currently on screen,
      // derived from the precanvas transform (origin 0 0): screen 0 maps to
      // canvas-local -canvas_x/zoom, and the visible span is container/zoom.
      let viewport = '';
      const df = this._drawflow;
      if (df && typeof df.canvas_x !== 'undefined' && df.zoom) {
        const rect = df.container.getBoundingClientRect();
        const vlX = -df.canvas_x / df.zoom;
        const vlY = -df.canvas_y / df.zoom;
        const vW = rect.width / df.zoom;
        const vH = rect.height / df.zoom;
        const rx = PAD + (vlX - minX) * scale;
        const ry = PAD + (vlY - minY) * scale;
        const rw = vW * scale;
        const rh = vH * scale;
        viewport =
          `<rect x="${rx.toFixed(1)}" y="${ry.toFixed(1)}" width="${rw.toFixed(1)}" height="${rh.toFixed(1)}" ` +
          'fill="var(--bs-primary)" fill-opacity="0.12" stroke="var(--bs-primary)" stroke-width="1.5" pointer-events="none" />';
      }
      host.innerHTML =
        `<svg width="${W}" height="${H}" style="cursor: pointer;">` +
        `<rect width="${W}" height="${H}" fill="var(--bs-tertiary-bg)" stroke="var(--bs-border-color)" />` +
        rects +
        viewport +
        '</svg>';
    },

    _minimapPanTo(offsetX, offsetY) {
      // Centre the viewport on the canvas-local point under the minimap
      // cursor.  Pan is a pure translate (transform-origin 0 0) so no
      // connection recompute is needed — only zoom changes affect local
      // endpoint coords.
      const t = this._minimapTransform;
      const df = this._drawflow;
      if (!t || !df || typeof df.canvas_x === 'undefined') return;
      const localX = t.minX + (offsetX - t.PAD) / t.scale;
      const localY = t.minY + (offsetY - t.PAD) / t.scale;
      const rect = df.container.getBoundingClientRect();
      df.canvas_x = -localX * df.zoom + rect.width / 2;
      df.canvas_y = -localY * df.zoom + rect.height / 2;
      df.precanvas.style.transform = `translate(${df.canvas_x}px, ${df.canvas_y}px) scale(${df.zoom})`;
      this._scheduleMinimapRender();
    },

    minimapPointerDown(ev) {
      ev.preventDefault();
      const host = this.$refs.minimap;
      if (!host) return;
      const rect = host.getBoundingClientRect();
      const toLocal = (e) => this._minimapPanTo(e.clientX - rect.left, e.clientY - rect.top);
      toLocal(ev);
      const move = (e) => toLocal(e);
      const up = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    },

    // ---------------------------------------------------------------------
    // Right-click context menu — target-aware, reuses existing actions.
    // ---------------------------------------------------------------------

    _onCanvasContextMenu(ev) {
      const nodeEl = ev.target.closest('.drawflow-node');
      const connEl = ev.target.closest('.connection');
      ev.preventDefault();
      let kind = 'canvas';
      let nodeId = null;
      let edgeId = null;
      if (nodeEl) {
        kind = 'node';
        const m = nodeEl.id && nodeEl.id.match(/^node-(\d+)$/);
        const dfId = m ? parseInt(m[1], 10) : null;
        for (const [pql, df] of Object.entries(this._drawflowNodes)) {
          if (df === dfId) {
            nodeId = pql;
            break;
          }
        }
        if (nodeId) this.selectedNodeId = nodeId;
      } else if (connEl) {
        kind = 'edge';
        edgeId = this._edgeIdForSvg(connEl);
      }
      // Stash the drop position (canvas-local) for "add block here".
      const df = this._drawflow;
      const rect = df.container.getBoundingClientRect();
      this._ctxDropPos = {
        x: (ev.clientX - rect.left - (df.canvas_x || 0)) / (df.zoom || 1),
        y: (ev.clientY - rect.top - (df.canvas_y || 0)) / (df.zoom || 1),
      };
      this.ctxMenu = { open: true, x: ev.clientX, y: ev.clientY, kind, nodeId, edgeId };
    },

    closeContextMenu() {
      this.ctxMenu = { ...this.ctxMenu, open: false };
    },

    ctxAction(action) {
      const { kind, nodeId, edgeId } = this.ctxMenu;
      this.closeContextMenu();
      if (action === 'add') {
        // Open the existing block picker at the cursor; _pickOutputPlusBlock
        // drops a standalone node at the stashed drop position.
        if (!this.canWrite) return;
        this._insertOnEdgeContext = null;
        this.outputPlusPicker = {
          open: true,
          x: this.ctxMenu.x - (this.$refs.canvas.parentElement.getBoundingClientRect().left || 0),
          y: this.ctxMenu.y - (this.$refs.canvas.parentElement.getBoundingClientRect().top || 0),
          sourcePqlId: null,
        };
        return;
      }
      if (kind === 'node' && nodeId) {
        this.selectedNodeId = nodeId;
        if (action === 'duplicate') this.duplicateSelectedNode();
        else if (action === 'delete') this.deleteSelectedNode();
        else if (action === 'preview') this.openPreviewForSelected();
        else if (action === 'peek') {
          const dfId = this._drawflowNodes[nodeId];
          const el = dfId != null && this._drawflow.container.querySelector(`#node-${dfId}`);
          this.openInlinePeek(nodeId, el || null);
        }
      } else if (kind === 'edge' && edgeId) {
        if (action === 'deleteEdge') this.deleteEdgeById(edgeId);
        else if (action === 'insert') this.insertBlockOnEdge(edgeId);
      }
    },

    // ---------------------------------------------------------------------
    // Inline preview peek — a compact popover at a node showing the first
    // few output rows, reusing the same /canvas/preview endpoint as the
    // full modal but capped tight.
    // ---------------------------------------------------------------------

    async openInlinePeek(nodeId, anchorEl) {
      if (!nodeId) return;
      const stage = this.$refs.canvas.parentElement;
      const sr = stage.getBoundingClientRect();
      const ar = (anchorEl || this.$refs.canvas).getBoundingClientRect();
      this.inlinePeek = {
        open: true,
        x: ar.right - sr.left + 8,
        y: ar.top - sr.top,
        nodeId,
        loading: true,
        columns: [],
        rows: [],
      };
      try {
        const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/preview`, {
          method: 'POST',
          body: { document: this._buildDocument(), upto_node_id: nodeId, limit: 5 },
          silent: true,
        });
        if (!this.inlinePeek.open || this.inlinePeek.nodeId !== nodeId) return;
        if (res.ok && res.data) {
          this.inlinePeek = {
            ...this.inlinePeek,
            loading: false,
            columns: res.data.columns || [],
            rows: (res.data.rows || []).slice(0, 5),
          };
        } else {
          this.inlinePeek = { ...this.inlinePeek, loading: false };
        }
      } catch (_e) {
        this.inlinePeek = { ...this.inlinePeek, loading: false };
      }
    },

    closeInlinePeek() {
      this.inlinePeek = { ...this.inlinePeek, open: false };
    },

    // ---------------------------------------------------------------------
    // Agent ghost-diff review — load a proposed CanvasDoc, diff it against
    // the current canvas via /canvas/ghost-diff (read-only), let the human
    // accept or reject each change, then merge the accepted deltas and save.
    // The proposal source is a pasted doc or ``?propose=<base64-json>`` in
    // the URL (e.g. handed off from an agent run).
    // ---------------------------------------------------------------------

    openGhostReview() {
      this.ghost.open = true;
      // Auto-load a proposal handed off via the URL, if present.
      try {
        const raw = new URL(window.location.href).searchParams.get('propose');
        if (raw && !this.ghost.text) {
          this.ghost.text = decodeURIComponent(escape(window.atob(raw)));
        }
      } catch (_e) {
        // Malformed param — ignore, user can paste manually.
      }
    },

    closeGhostReview() {
      this.ghost.open = false;
    },

    async computeGhostDiff() {
      // Mutate ghost.* fields individually rather than replacing the whole
      // nested object — replacing it detaches some Alpine bindings and races
      // the x-for over ghost.errors.
      let proposed;
      try {
        proposed = JSON.parse(this.ghost.text);
      } catch (_e) {
        this.ghost.errors = [{ message: 'Proposal is not valid JSON.' }];
        return;
      }
      this.ghost.busy = true;
      this.ghost.proposed = proposed;
      this.ghost.diff = null;
      this.ghost.errors = [];
      const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/ghost-diff`, {
        method: 'POST',
        body: { proposed_document: proposed },
        silent: true,
      });
      this.ghost.busy = false;
      if (!res.ok) {
        this.ghost.errors = [{ message: res.error || 'ghost-diff failed' }];
        return;
      }
      // Default every change to accepted so "apply" with no fiddling takes
      // the whole proposal; the human unticks what they want to reject.
      const accept = {};
      const d = res.data.diff;
      for (const n of d.added_nodes) accept[`an:${n.id}`] = true;
      for (const n of d.removed_nodes) accept[`rn:${n.id}`] = true;
      for (const n of d.modified_nodes) accept[`mn:${n.id}`] = true;
      for (const e of d.added_edges) accept[`ae:${this._ghostEdgeKey(e)}`] = true;
      for (const e of d.removed_edges) accept[`re:${this._ghostEdgeKey(e)}`] = true;
      this.ghost.diff = d;
      this.ghost.errors = res.data.errors || [];
      this.ghost.accept = accept;
    },

    _ghostEdgeKey(e) {
      return `${e.source_node_id}:${e.source_pin}->${e.target_node_id}:${e.target_pin}`;
    },

    ghostDiffEmpty() {
      const d = this.ghost.diff;
      if (!d) return true;
      return (
        d.added_nodes.length +
          d.removed_nodes.length +
          d.modified_nodes.length +
          d.added_edges.length +
          d.removed_edges.length ===
        0
      );
    },

    async applyGhostSelection() {
      const d = this.ghost.diff;
      const proposed = this.ghost.proposed;
      if (!d || !proposed || !this.canWrite) return;
      const accept = this.ghost.accept;
      // Start from the live canvas; apply only the ticked deltas, taking
      // full node/edge objects (with positions) from the proposed doc.
      const current = this._buildDocument();
      const nodesById = {};
      for (const n of current.nodes) nodesById[n.id] = n;
      const propNodesById = {};
      for (const n of proposed.nodes) propNodesById[n.id] = n;
      for (const n of d.added_nodes) {
        if (accept[`an:${n.id}`] && propNodesById[n.id]) nodesById[n.id] = propNodesById[n.id];
      }
      for (const n of d.modified_nodes) {
        if (accept[`mn:${n.id}`] && propNodesById[n.id]) nodesById[n.id] = propNodesById[n.id];
      }
      for (const n of d.removed_nodes) {
        if (accept[`rn:${n.id}`]) delete nodesById[n.id];
      }
      const edgesByKey = {};
      for (const e of current.edges) edgesByKey[this._ghostEdgeKey(e)] = e;
      const propEdgesByKey = {};
      for (const e of proposed.edges) propEdgesByKey[this._ghostEdgeKey(e)] = e;
      for (const e of d.added_edges) {
        const k = this._ghostEdgeKey(e);
        if (accept[`ae:${k}`] && propEdgesByKey[k]) edgesByKey[k] = propEdgesByKey[k];
      }
      for (const e of d.removed_edges) {
        if (accept[`re:${this._ghostEdgeKey(e)}`]) delete edgesByKey[this._ghostEdgeKey(e)];
      }
      // Drop edges whose endpoints no longer exist after node removals.
      const merged = {
        schema_version: 1,
        nodes: Object.values(nodesById),
        edges: Object.values(edgesByKey).filter(
          (e) => nodesById[e.source_node_id] && nodesById[e.target_node_id]
        ),
        metadata: current.metadata || {},
      };
      this.ghost.busy = true;
      const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas`, {
        method: 'POST',
        body: { document: merged },
        silent: true,
      });
      this.ghost.busy = false;
      if (!res.ok) {
        this.ghost.errors = [{ message: res.error || 'apply failed' }];
        return;
      }
      this.version = res.data.version;
      this._suppressAutosave = true;
      this._loadIntoDrawflow(merged);
      this._suppressAutosave = false;
      this.saveState = 'saved';
      this.lastSavedAt = res.data.created_at;
      this.closeGhostReview();
      this._scheduleValidate();
      this.$nextTick(() => this.fitToView());
    },

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

    _isFormFocused(target) {
      if (!target || target.matches == null) return false;
      return (
        target.matches('input, textarea, select, [contenteditable], [contenteditable=""]') ||
        target.closest('.cm-editor') != null
      );
    },

    _pqlIdForDfId(dfId) {
      for (const [pqlId, mappedDfId] of Object.entries(this._drawflowNodes)) {
        if (String(mappedDfId) === String(dfId)) return pqlId;
      }
      return null;
    },

    _clearMultiSelection() {
      if (this.multiSelectedNodeIds.length === 0) return;
      this.multiSelectedNodeIds = [];
      this._refreshMultiSelectStyles();
    },

    _refreshMultiSelectStyles() {
      const df = this._drawflow;
      if (!df) return;
      const selected = new Set(this.multiSelectedNodeIds);
      for (const [pqlId, dfId] of Object.entries(this._drawflowNodes)) {
        const el = df.container.querySelector(`#node-${dfId}`);
        if (!el) continue;
        el.classList.toggle('pql-node-selected-multi', selected.has(pqlId));
      }
    },

    async bulkDeleteSelected() {
      const ids = [...this.multiSelectedNodeIds];
      if (ids.length === 0) return;
      const ok = window.confirm(`Delete ${ids.length} blocks?`);
      if (!ok) return;
      const df = this._drawflow;
      if (!df) return;
      const set = new Set(ids);
      const removedNodes = ids
        .map((id) => this.nodes[id])
        .filter(Boolean)
        .map((n) => ({
          id: n.id,
          block_type: n.block_type,
          config: JSON.parse(JSON.stringify(n.config || {})),
          position: { ...(n.position || { x: 100, y: 100 }) },
        }));
      const removedEdges = Object.values(this.edges).filter(
        (e) => set.has(e.source_node_id) || set.has(e.target_node_id)
      );
      this._suppressAutosave = true;
      for (const pqlId of ids) {
        const dfId = this._drawflowNodes[pqlId];
        if (dfId != null) df.removeNodeId('node-' + dfId);
      }
      this._suppressAutosave = false;
      this.multiSelectedNodeIds = [];
      this._syncFromDrawflow();
      this._pushCommand({
        do: () => {
          // Re-apply the delete (re-resolve current drawflow ids by pql_id).
          for (const n of removedNodes) {
            const cur = this._drawflowNodes[n.id];
            if (cur != null) this._drawflow.removeNodeId('node-' + cur);
            delete this._drawflowNodes[n.id];
            delete this.nodes[n.id];
          }
          this._syncFromDrawflow();
        },
        undo: () => {
          // Re-create nodes + re-wire edges that were within the deleted set.
          this._suppressAutosave = true;
          for (const n of removedNodes) {
            const def = BLOCK_DEFS[n.block_type];
            if (!def) continue;
            const dfId = this._drawflow.addNode(
              n.block_type,
              def.inputs || 0,
              def.outputs || 0,
              n.position.x,
              n.position.y,
              n.block_type,
              { pql_node_id: n.id, block_type: n.block_type },
              nodeHtml(n.block_type, n.id),
              false
            );
            this._drawflowNodes[n.id] = dfId;
            this.nodes[n.id] = { ...n };
          }
          for (const e of removedEdges) {
            const sd = this._drawflowNodes[e.source_node_id];
            const td = this._drawflowNodes[e.target_node_id];
            if (sd == null || td == null) continue;
            const targetIdx = pinIndexFor(
              this.nodes[e.target_node_id]?.block_type,
              e.target_pin,
              'in'
            );
            try {
              this._drawflow.addConnection(sd, td, 'output_1', `input_${targetIdx + 1}`);
            } catch (_e) {
              // Skip.
            }
          }
          this._suppressAutosave = false;
          this._syncFromDrawflow();
        },
      });
      this._scheduleMinimapRender();
    },

    copySelectionToClipboard() {
      const ids =
        this.multiSelectedNodeIds.length > 0
          ? [...this.multiSelectedNodeIds]
          : this.selectedNodeId
            ? [this.selectedNodeId]
            : [];
      if (ids.length === 0) return;
      const set = new Set(ids);
      const nodes = ids
        .map((id) => this.nodes[id])
        .filter(Boolean)
        .map((n) => ({
          id: n.id,
          block_type: n.block_type,
          config: JSON.parse(JSON.stringify(n.config || {})),
          position: { ...(n.position || { x: 100, y: 100 }) },
        }));
      const edges = Object.values(this.edges).filter(
        (e) => set.has(e.source_node_id) && set.has(e.target_node_id)
      );
      const payload = { kind: 'pql-canvas-clipboard', version: 1, nodes, edges };
      try {
        window.localStorage.setItem('pql-canvas-clipboard', JSON.stringify(payload));
      } catch (_e) {
        // Quota / disabled — silent.
      }
    },

    pasteClipboard() {
      let payload = null;
      try {
        const raw = window.localStorage.getItem('pql-canvas-clipboard');
        if (raw) payload = JSON.parse(raw);
      } catch (_e) {
        return;
      }
      if (!payload || payload.kind !== 'pql-canvas-clipboard' || !Array.isArray(payload.nodes)) {
        return;
      }
      const df = this._drawflow;
      if (!df) return;
      const idMap = {};
      this._suppressAutosave = true;
      for (const n of payload.nodes) {
        const def = BLOCK_DEFS[n.block_type];
        if (!def) continue;
        const newId = generateNodeId();
        idMap[n.id] = newId;
        const pos = {
          x: (n.position && n.position.x ? n.position.x : 100) + 40,
          y: (n.position && n.position.y ? n.position.y : 100) + 40,
        };
        const dfId = df.addNode(
          n.block_type,
          def.inputs || 0,
          def.outputs || 0,
          pos.x,
          pos.y,
          n.block_type,
          { pql_node_id: newId, block_type: n.block_type },
          nodeHtml(n.block_type, newId),
          false
        );
        this._drawflowNodes[newId] = dfId;
        this.nodes[newId] = {
          id: newId,
          block_type: n.block_type,
          config: JSON.parse(JSON.stringify(n.config || {})),
          position: pos,
        };
      }
      for (const e of payload.edges || []) {
        const srcNew = idMap[e.source_node_id];
        const tgtNew = idMap[e.target_node_id];
        if (!srcNew || !tgtNew) continue;
        const srcDf = this._drawflowNodes[srcNew];
        const tgtDf = this._drawflowNodes[tgtNew];
        if (!srcDf || !tgtDf) continue;
        const targetIdx = pinIndexFor(this.nodes[tgtNew].block_type, e.target_pin, 'in');
        try {
          df.addConnection(srcDf, tgtDf, 'output_1', `input_${targetIdx + 1}`);
        } catch (_e) {
          // Skip invalid wire.
        }
      }
      this._suppressAutosave = false;
      this._syncFromDrawflow();
      const pastedIds = Object.values(idMap);
      if (pastedIds.length > 0) {
        this._pushCommand({
          do: () => {
            // Best-effort re-paste: re-invoke from the clipboard payload.
            this.pasteClipboard();
          },
          undo: () => {
            for (const newId of pastedIds) {
              const dfId = this._drawflowNodes[newId];
              if (dfId != null) this._drawflow.removeNodeId('node-' + dfId);
              delete this._drawflowNodes[newId];
              delete this.nodes[newId];
            }
            this._syncFromDrawflow();
          },
        });
      }
      this._scheduleMinimapRender();
    },

    _applySensibleDefaultsIfEmpty(nodeId) {
      const node = this.nodes[nodeId];
      if (!node) return;
      const upstream = this.upstreamColumns(nodeId, 'in');
      if (upstream.length === 0) return;
      const cfg = node.config || {};
      switch (node.block_type) {
        case 'Sort':
          if (!cfg.order_by || cfg.order_by.length === 0) {
            cfg.order_by = [{ column: upstream[0], direction: 'asc' }];
            node.config = cfg;
          }
          break;
        case 'Project':
          if (!cfg.columns || cfg.columns.length === 0) {
            cfg.columns = upstream.slice(0, 3);
            node.config = cfg;
          }
          break;
        case 'GroupBy':
          if (!cfg.keys || cfg.keys.length === 0) {
            cfg.keys = [upstream[0]];
            node.config = cfg;
          }
          break;
        default:
          return;
      }
      this._refreshNodeBody(nodeId);
    },

    async autoTidy() {
      const df = this._drawflow;
      if (!df) return;
      const { computeLayout, animateTo } = await import('../dp_canvas/_auto_layout.js');
      const nodes = Object.values(this.nodes);
      const edges = Object.values(this.edges);
      if (nodes.length === 0) return;
      const targets = computeLayout(nodes, edges, { rankdir: 'LR' });
      if (!targets || Object.keys(targets).length === 0) return;
      const currentPos = {};
      for (const n of nodes) currentPos[n.id] = n.position || { x: 100, y: 100 };
      this._suppressAutosave = true;
      await animateTo(df, this._drawflowNodes, currentPos, targets, 250);
      // Persist final positions into the editor state.
      for (const [pqlId, pos] of Object.entries(targets)) {
        if (this.nodes[pqlId]) this.nodes[pqlId].position = { x: pos.x, y: pos.y };
      }
      this._suppressAutosave = false;
      this._scheduleAutosave();
      this._scheduleMinimapRender();
    },

    toggleOrthogonalEdges() {
      this.orthogonalEdges = !this.orthogonalEdges;
      const df = this._drawflow;
      if (!df) return;
      df.curvature = this.orthogonalEdges ? 0 : 0.5;
      // Drawflow's updateConnectionNodes() emits nodeMoved internally for
      // every connected node, which would cascade into autosave + minimap
      // re-render.  Suppress autosave around the visual-only rewrite.
      const wasSuppressed = this._suppressAutosave;
      this._suppressAutosave = true;
      try {
        for (const dfId of Object.values(this._drawflowNodes)) {
          df.updateConnectionNodes('node-' + dfId);
        }
      } finally {
        this._suppressAutosave = wasSuppressed;
      }
      this._scheduleRerouteOrthogonal();
    },

    // ---------------------------------------------------------------------
    // Obstacle-aware orthogonal routing.  Drawflow's createCurvature only
    // sees the two endpoints, so the step path it draws can run straight
    // through intervening nodes.  In orthogonal mode only, this post-pass
    // rewrites each connection's `d` to route around the other nodes' boxes:
    // it first looks for a clear vertical corridor between the pins, then
    // falls back to a detour over/under the blocking band.  Smooth (bézier)
    // mode is untouched.
    // ---------------------------------------------------------------------

    _scheduleRerouteOrthogonal() {
      if (!this.orthogonalEdges) return;
      if (this._rerouteRaf) return;
      this._rerouteRaf = window.setTimeout(() => {
        this._rerouteRaf = null;
        this._rerouteOrthogonalEdges();
      }, 0);
    },

    _nodeBoxes(excludeDfIds) {
      const df = this._drawflow;
      const boxes = [];
      for (const dfId of Object.values(this._drawflowNodes)) {
        if (excludeDfIds.has(String(dfId))) continue;
        const el = df.container.querySelector(`#node-${dfId}`);
        if (!el) continue;
        boxes.push({ x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight });
      }
      return boxes;
    },

    _orthogonalPath(sx, sy, ex, ey, boxes, STUB, GAP) {
      // Does an axis-aligned segment (inflated by GAP) intersect any box?
      const hit = (x0, y0, x1, y1) => {
        const xmin = Math.min(x0, x1);
        const xmax = Math.max(x0, x1);
        const ymin = Math.min(y0, y1);
        const ymax = Math.max(y0, y1);
        return boxes.some(
          (b) =>
            xmax > b.x - GAP && xmin < b.x + b.w + GAP && ymax > b.y - GAP && ymin < b.y + b.h + GAP
        );
      };
      // 1) Plain H-V-H midpoint path, if all three segments are clear.
      const midX = sx + (ex - sx) / 2;
      if (!hit(sx, sy, midX, sy) && !hit(midX, sy, midX, ey) && !hit(midX, ey, ex, ey)) {
        return ` M ${sx} ${sy} L ${midX} ${sy} L ${midX} ${ey} L ${ex} ${ey}`;
      }
      // 2) Detour over / under the band of boxes spanning the horizontal gap.
      const band = boxes.filter(
        (b) => b.x + b.w + GAP > Math.min(sx, ex) && b.x - GAP < Math.max(sx, ex)
      );
      if (band.length) {
        const top = Math.min(...band.map((b) => b.y)) - GAP;
        const bot = Math.max(...band.map((b) => b.y + b.h)) + GAP;
        const useTop =
          Math.abs(top - sy) + Math.abs(top - ey) <= Math.abs(bot - sy) + Math.abs(bot - ey);
        const clearY = useTop ? top : bot;
        const so = sx + STUB;
        const eo = ex - STUB;
        return (
          ` M ${sx} ${sy} L ${so} ${sy} L ${so} ${clearY}` +
          ` L ${eo} ${clearY} L ${eo} ${ey} L ${ex} ${ey}`
        );
      }
      // 3) Nothing to avoid — plain midpoint split.
      return ` M ${sx} ${sy} L ${midX} ${sy} L ${midX} ${ey} L ${ex} ${ey}`;
    },

    _rerouteOrthogonalEdges() {
      const df = this._drawflow;
      if (!df || !this.orthogonalEdges) return;
      const STUB = 24;
      const GAP = 18;
      const conns = df.container.querySelectorAll('.drawflow .connection');
      for (const conn of conns) {
        const mp = conn.querySelector('.main-path');
        if (!mp) continue;
        const d = mp.getAttribute('d') || '';
        if (d.indexOf('C') !== -1) continue; // bézier — skip
        const nums = d.match(/-?\d+(?:\.\d+)?/g);
        if (!nums || nums.length < 4) continue;
        const sx = parseFloat(nums[0]);
        const sy = parseFloat(nums[1]);
        const ex = parseFloat(nums[nums.length - 2]);
        const ey = parseFloat(nums[nums.length - 1]);
        let srcDf = null;
        let tgtDf = null;
        for (const cls of conn.classList) {
          const inM = cls.match(/^node_in_node-(\d+)$/);
          const outM = cls.match(/^node_out_node-(\d+)$/);
          if (inM) tgtDf = inM[1];
          if (outM) srcDf = outM[1];
        }
        const exclude = new Set([srcDf, tgtDf].filter(Boolean));
        const newD = this._orthogonalPath(sx, sy, ex, ey, this._nodeBoxes(exclude), STUB, GAP);
        if (newD) mp.setAttribute('d', newD);
      }
    },

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
          `${edge.source_node_id}:${edge.source_pin}->` +
          `${edge.target_node_id}:${edge.target_pin}`;
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

    _selectEdge(edgeId) {
      this._clearSelectedEdge();
      this._selectedEdgeId = edgeId;
      const df = this._drawflow;
      if (!df) return;
      const svgs = df.container.querySelectorAll('.drawflow .connection');
      for (const svg of svgs) {
        if (this._edgeIdForSvg(svg) === edgeId) {
          svg.classList.add('pql-edge-selected');
        }
      }
    },

    _clearSelectedEdge() {
      this._selectedEdgeId = null;
      const df = this._drawflow;
      if (!df) return;
      const svgs = df.container.querySelectorAll('.drawflow .connection.pql-edge-selected');
      for (const svg of svgs) svg.classList.remove('pql-edge-selected');
    },

    _showEdgeToolbar(svgEl, edgeId) {
      this._cancelEdgeToolbarHide();
      this._edgeToolbarTarget = { svgEl, edgeId };
      this.edgeToolbar = { ...this.edgeToolbar, edgeId, visible: true };
      this._updateEdgeToolbarPosition();
    },

    _scheduleEdgeToolbarReposition() {
      if (!this.edgeToolbar.visible) return;
      if (this._edgeToolbarRaf) return;
      this._edgeToolbarRaf = window.setTimeout(() => {
        this._edgeToolbarRaf = null;
        this._updateEdgeToolbarPosition();
      }, 0);
    },

    _updateEdgeToolbarPosition() {
      const target = this._edgeToolbarTarget;
      if (!target || !target.svgEl) return;
      const path = target.svgEl.querySelector('.main-path');
      if (!path) return;
      let mid;
      try {
        const len = path.getTotalLength();
        mid = path.getPointAtLength(len / 2);
      } catch (_e) {
        // Some browsers throw if the path is unrendered (zero-length).
        return;
      }
      // Translate from SVG-local coords to the stage's positioned ancestor.
      const stage = this.$refs.canvas.parentElement;
      const svgRect = target.svgEl.getBoundingClientRect();
      const stageRect = stage.getBoundingClientRect();
      const x = svgRect.left - stageRect.left + mid.x;
      const y = svgRect.top - stageRect.top + mid.y;
      this.edgeToolbar = { ...this.edgeToolbar, x, y };
    },

    _scheduleEdgeToolbarHide() {
      this._cancelEdgeToolbarHide();
      // 600 ms exit-delay — same forgiveness window n8n uses so the user
      // can dart the cursor across the edge into the toolbar without it
      // vanishing mid-flight.
      this._edgeToolbarHideTimer = window.setTimeout(() => this._hideEdgeToolbar(), 600);
    },

    _cancelEdgeToolbarHide() {
      if (this._edgeToolbarHideTimer) {
        window.clearTimeout(this._edgeToolbarHideTimer);
        this._edgeToolbarHideTimer = null;
      }
    },

    _hideEdgeToolbar() {
      this._cancelEdgeToolbarHide();
      this.edgeToolbar = { visible: false, x: 0, y: 0, edgeId: null };
      this._edgeToolbarTarget = null;
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
        const newDf = this._drawflow.addNode(
          kind,
          def.inputs || 0,
          def.outputs || 0,
          pos.x,
          pos.y,
          kind,
          { pql_node_id: newPqlId, block_type: kind },
          nodeHtml(kind, newPqlId),
          false
        );
        this._drawflowNodes[newPqlId] = newDf;
        this.nodes[newPqlId] = {
          id: newPqlId,
          block_type: kind,
          config: def.defaultConfig(),
          position: pos,
        };
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
        const newDf = this._drawflow.addNode(
          kind,
          def.inputs || 0,
          def.outputs || 0,
          dropPos.x,
          dropPos.y,
          kind,
          { pql_node_id: newPqlId, block_type: kind },
          nodeHtml(kind, newPqlId),
          false
        );
        this._drawflowNodes[newPqlId] = newDf;
        this.nodes[newPqlId] = {
          id: newPqlId,
          block_type: kind,
          config: def.defaultConfig(),
          position: dropPos,
        };
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
      const newDf = this._drawflow.addNode(
        kind,
        def.inputs || 0,
        def.outputs || 0,
        pos.x,
        pos.y,
        kind,
        { pql_node_id: newPqlId, block_type: kind },
        nodeHtml(kind, newPqlId),
        false
      );
      this._drawflowNodes[newPqlId] = newDf;
      this.nodes[newPqlId] = {
        id: newPqlId,
        block_type: kind,
        config: def.defaultConfig(),
        position: pos,
      };
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

    onPaletteDragStart(event, kind) {
      if (!this.canWrite) {
        event.preventDefault();
        return;
      }
      event.dataTransfer.setData('text/plain', kind);
      event.dataTransfer.effectAllowed = 'copy';
    },

    onCanvasDrop(event) {
      if (!this.canWrite) return;
      const kind = event.dataTransfer.getData('text/plain');
      if (!kind || !BLOCK_DEFS[kind]) return;
      const def = BLOCK_DEFS[kind];
      const rect = event.currentTarget.getBoundingClientRect();
      const pos = { x: event.clientX - rect.left - 60, y: event.clientY - rect.top - 30 };
      const pqlId = generateNodeId();
      const dfId = this._drawflow.addNode(
        kind,
        def.inputs,
        def.outputs,
        pos.x,
        pos.y,
        kind,
        { pql_node_id: pqlId, block_type: kind },
        nodeHtml(kind, pqlId),
        false
      );
      this._drawflowNodes[pqlId] = dfId;
      this.nodes[pqlId] = {
        id: pqlId,
        block_type: kind,
        config: def.defaultConfig(),
        position: pos,
      };
      this._refreshNodeBody(pqlId);
      this._renderOutputPlus(pqlId);
      this._scheduleAutosave();
      this._scheduleValidate();
      this._pushCommand({
        do: () => {
          // Re-create requires re-mint of df-id; punt and just call drop logic
          // recursively from the snapshot.  For simplicity the redo just no-ops
          // when the node already exists.
          if (this.nodes[pqlId]) return;
          const dfId2 = this._drawflow.addNode(
            kind,
            def.inputs,
            def.outputs,
            pos.x,
            pos.y,
            kind,
            { pql_node_id: pqlId, block_type: kind },
            nodeHtml(kind, pqlId),
            false
          );
          this._drawflowNodes[pqlId] = dfId2;
          this.nodes[pqlId] = {
            id: pqlId,
            block_type: kind,
            config: def.defaultConfig(),
            position: pos,
          };
        },
        undo: () => {
          const cur = this._drawflowNodes[pqlId];
          if (cur != null) this._drawflow.removeNodeId('node-' + cur);
          delete this._drawflowNodes[pqlId];
          delete this.nodes[pqlId];
          if (this.selectedNodeId === pqlId) this.selectedNodeId = null;
        },
      });
      this._scheduleMinimapRender();
    },

    deleteSelectedNode() {
      if (!this.selectedNodeId || !this.canWrite) return;
      const pqlId = this.selectedNodeId;
      const snapshotNode = this.nodes[pqlId]
        ? {
            id: pqlId,
            block_type: this.nodes[pqlId].block_type,
            config: JSON.parse(JSON.stringify(this.nodes[pqlId].config || {})),
            position: { ...(this.nodes[pqlId].position || { x: 100, y: 100 }) },
          }
        : null;
      const snapshotEdges = Object.values(this.edges).filter(
        (e) => e.source_node_id === pqlId || e.target_node_id === pqlId
      );
      const dfId = this._drawflowNodes[pqlId];
      if (dfId) this._drawflow.removeNodeId('node-' + dfId);
      delete this._drawflowNodes[pqlId];
      delete this.nodes[pqlId];
      this.selectedNodeId = null;
      this._syncFromDrawflow();
      if (snapshotNode) {
        this._pushCommand({
          do: () => {
            const cur = this._drawflowNodes[pqlId];
            if (cur != null) this._drawflow.removeNodeId('node-' + cur);
            delete this._drawflowNodes[pqlId];
            delete this.nodes[pqlId];
            this._syncFromDrawflow();
          },
          undo: () => {
            const def = BLOCK_DEFS[snapshotNode.block_type];
            if (!def) return;
            this._suppressAutosave = true;
            const nDf = this._drawflow.addNode(
              snapshotNode.block_type,
              def.inputs || 0,
              def.outputs || 0,
              snapshotNode.position.x,
              snapshotNode.position.y,
              snapshotNode.block_type,
              { pql_node_id: pqlId, block_type: snapshotNode.block_type },
              nodeHtml(snapshotNode.block_type, pqlId),
              false
            );
            this._drawflowNodes[pqlId] = nDf;
            this.nodes[pqlId] = { ...snapshotNode };
            for (const e of snapshotEdges) {
              const sd = this._drawflowNodes[e.source_node_id];
              const td = this._drawflowNodes[e.target_node_id];
              if (sd == null || td == null) continue;
              const targetIdx = pinIndexFor(
                this.nodes[e.target_node_id]?.block_type,
                e.target_pin,
                'in'
              );
              try {
                this._drawflow.addConnection(sd, td, 'output_1', `input_${targetIdx + 1}`);
              } catch (_e) {
                // Skip.
              }
            }
            this._suppressAutosave = false;
            this._syncFromDrawflow();
          },
        });
      }
      this._scheduleMinimapRender();
    },

    duplicateSelectedNode() {
      if (!this.selectedNodeId || !this.canWrite) return;
      const src = this.nodes[this.selectedNodeId];
      if (!src) return;
      const def = BLOCK_DEFS[src.block_type];
      if (!def) return;
      const newPqlId = generateNodeId();
      const pos = {
        x: (src.position?.x || 100) + 40,
        y: (src.position?.y || 100) + 40,
      };
      const dfId = this._drawflow.addNode(
        src.block_type,
        def.inputs,
        def.outputs,
        pos.x,
        pos.y,
        src.block_type,
        { pql_node_id: newPqlId, block_type: src.block_type },
        nodeHtml(src.block_type, newPqlId),
        false
      );
      this._drawflowNodes[newPqlId] = dfId;
      this.nodes[newPqlId] = {
        id: newPqlId,
        block_type: src.block_type,
        config: JSON.parse(JSON.stringify(src.config || {})),
        position: pos,
      };
      this._refreshNodeBody(newPqlId);
      this.selectedNodeId = newPqlId;
      this._scheduleAutosave();
      this._scheduleValidate();
      this._pushCommand({
        do: () => {
          // No-op: redo re-adds the duplicate would need full re-clone path.
          // For simplicity, redo of duplicate is best-effort no-op.
        },
        undo: () => {
          const cur = this._drawflowNodes[newPqlId];
          if (cur != null) this._drawflow.removeNodeId('node-' + cur);
          delete this._drawflowNodes[newPqlId];
          delete this.nodes[newPqlId];
          if (this.selectedNodeId === newPqlId) this.selectedNodeId = null;
          this._syncFromDrawflow();
        },
      });
      this._scheduleMinimapRender();
    },

    focusNode(nodeId) {
      if (!nodeId) return;
      const dfId = this._drawflowNodes[nodeId];
      if (!dfId) return;
      this.selectedNodeId = nodeId;
      // Drawflow exposes no public selectNodeById; centring requires
      // poking into its module-local state. Selecting via the DOM
      // click handler is the least-invasive equivalent.
      const el = this._drawflow.container.querySelector(`#node-${dfId}`);
      if (el && typeof el.click === 'function') el.click();
    },


    onConfigChanged() {
      if (this.selectedNodeId) this._refreshNodeBody(this.selectedNodeId);
      if (this._suppressAutosave) return;
      this._scheduleAutosave();
      this._scheduleValidate();
    },

    _scheduleAutosave() {
      if (!this.canWrite) return;
      if (this._saveTimer) window.clearTimeout(this._saveTimer);
      this._saveTimer = window.setTimeout(() => this.save(), 1500);
    },

    _scheduleValidate() {
      // Any edit invalidates the last run's per-sink marks.
      this._clearSinkRunMarks();
      if (this._validateTimer) window.clearTimeout(this._validateTimer);
      this._validateTimer = window.setTimeout(() => this.validate(), 800);
    },

    _buildDocument() {
      return {
        schema_version: 1,
        nodes: Object.values(this.nodes).map((node) => ({
          id: node.id,
          block_type: node.block_type,
          config: node.config,
          position: node.position,
        })),
        edges: Object.values(this.edges).map((edge) => ({
          id: edge.id,
          source_node_id: edge.source_node_id,
          source_pin: edge.source_pin,
          target_node_id: edge.target_node_id,
          target_pin: edge.target_pin,
        })),
        metadata: { annotations: this.annotations || [] },
      };
    },

    async save() {
      if (!this.canWrite || this.saving) return;
      this.saving = true;
      this.saveState = 'saving';
      this.saveError = null;
      const body = {
        document: this._buildDocument(),
        expected_base_version: this.version,
      };
      const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas`, {
        method: 'POST',
        body,
        silent: true,
      });
      this.saving = false;
      if (!res.ok) {
        this.saveState = 'error';
        this.saveError = res.error || 'Save failed';
        return;
      }
      this.version = res.data.version;
      this.saveState = 'saved';
      this.lastSavedAt = res.data.created_at || new Date().toISOString();
    },

    async validate() {
      if (this.validating) return;
      if (this.nodeCount === 0) {
        this.errors = [];
        this.pinSchemas = {};
        this._refreshAllNodeErrors();
        return;
      }
      this.validating = true;
      const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/validate`, {
        method: 'POST',
        body: { document: this._buildDocument() },
        silent: true,
      });
      this.validating = false;
      if (!res.ok) {
        // Validation network/server errors are non-fatal — surface in topbar only.
        this.saveError = res.error || 'Validate failed';
        return;
      }
      this.errors = res.data.errors || [];
      this.pinSchemas = res.data.pin_schemas || {};
      this.edgeCategories = res.data.edge_categories || {};
      this._refreshAllNodeErrors();
      this._refreshAllNodeBodies();
      this._refreshEdgeCategoryStyles();
      this._scheduleMinimapRender();
    },

    async mountPredicateCm(host, nodeId, field) {
      if (!host) return;
      const { mountPredicateEditor } = await import('../dp_canvas/codemirror_predicate.js');
      const node = this.nodes[nodeId];
      if (!node) return;
      await mountPredicateEditor(host, {
        initialValue: String((node.config && node.config[field]) || ''),
        onChange: (value) => {
          const live = this.nodes[nodeId];
          if (!live) return;
          if ((live.config[field] || '') === value) return;
          live.config[field] = value;
          this.onConfigChanged();
        },
        getColumns: () => this.upstreamColumns(nodeId, 'in'),
      });
    },

    async mountSqlCm(host, nodeId, field) {
      if (!host) return;
      const { mountSqlEditor } = await import('../dp_canvas/codemirror_predicate.js');
      const node = this.nodes[nodeId];
      if (!node) return;
      await mountSqlEditor(host, {
        initialValue: String((node.config && node.config[field]) || ''),
        onChange: (value) => {
          const live = this.nodes[nodeId];
          if (!live) return;
          if ((live.config[field] || '') === value) return;
          live.config[field] = value;
          this.onConfigChanged();
        },
        getColumns: () => this.upstreamColumns(nodeId, 'in'),
      });
    },

    upstreamColumns(nodeId, pinName) {
      // Walk reverse edges to find the upstream node feeding *pinName*,
      // then return its output PinSchema columns (if cached).
      for (const edge of Object.values(this.edges)) {
        if (edge.target_node_id === nodeId && edge.target_pin === pinName) {
          const key = `${edge.source_node_id}:${edge.source_pin}`;
          const schema = this.pinSchemas[key];
          if (schema && Array.isArray(schema.columns)) {
            return schema.columns.map((c) => c.name);
          }
        }
      }
      return [];
    },

    async runCanvas() {
      if (this.running) return;
      this.runDockOpen = true;
      this.runResult = null;
      this.runError = null;
      this._clearSinkRunMarks();

      // Validation errors are already drawn on the canvas (node badges +
      // the Errors list in the drawer); refuse to run and point the user
      // at the first offending block instead of failing server-side.
      if (this.errors.length > 0) {
        const n = this.errors.length;
        this.runError = `Fix ${n} validation ${n === 1 ? 'error' : 'errors'} before running.`;
        const first = this.errors.find((e) => e.node_id);
        if (first) this.focusNode(first.node_id);
        return;
      }

      this.running = true;
      const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/materialize`, {
        method: 'POST',
        body: {
          document: this._buildDocument(),
          expected_base_version: this.version,
        },
        silent: true,
      });
      this.running = false;
      if (!res.ok) {
        this.runError = res.error || 'Run failed';
        return;
      }
      this.runResult = res.data;
      this.version = res.data.graph_version;
      this.saveState = 'saved';
      this.lastSavedAt = new Date().toISOString();
      this._applySinkRunMarks(res.data.sinks);
    },

    closeRunDock() {
      this.runDockOpen = false;
    },

    _outputNodeForSink(sink) {
      return Object.values(this.nodes).find(
        (n) =>
          n.block_type === 'OutputPort' &&
          (n.config.materialized_table === sink.target_fqn || n.config.port_name === sink.port_name)
      );
    },

    focusSinkByTarget(targetFqn) {
      const node = this._outputNodeForSink({ target_fqn: targetFqn, port_name: null });
      if (node) this.focusNode(node.id);
    },

    _clearSinkRunMarks() {
      const df = this._drawflow;
      if (!df) return;
      df.container.querySelectorAll('.pql-node-run-ok, .pql-node-run-failed').forEach((el) => {
        el.classList.remove('pql-node-run-ok', 'pql-node-run-failed');
      });
    },

    _applySinkRunMarks(sinks) {
      const df = this._drawflow;
      if (!df || !Array.isArray(sinks)) return;
      for (const sink of sinks) {
        const node = this._outputNodeForSink(sink);
        if (!node) continue;
        const dfId = this._drawflowNodes[node.id];
        if (!dfId) continue;
        const wrap = df.container.querySelector(`#node-${dfId}`);
        if (!wrap) continue;
        wrap.classList.add(sink.status === 'ok' ? 'pql-node-run-ok' : 'pql-node-run-failed');
      }
    },

    canPreviewSelected() {
      const node = this.selectedNode;
      if (!node) return false;
      if (node.block_type === 'OutputPort') return false;
      return true;
    },

    openPreviewForSelected() {
      if (!this.canPreviewSelected()) return;
      this.previewNodeId = this.selectedNodeId;
      this.previewOpen = true;
      this.previewResult = null;
      this.previewError = null;
      // Auto-fire on open so the user sees rows without an extra click.
      this.runPreview();
    },

    closePreviewModal() {
      this.previewOpen = false;
    },

    async ensureDpPickerLoaded() {
      if (this.dpPicker.loaded) return;
      const res = await window.pqlApi.fetch('/api/dp/_picker', { silent: true });
      if (!res.ok) return;
      this.dpPicker = { loaded: true, products: res.data.data_products || [] };
    },

    dpPortsFor(dpId) {
      const entry = (this.dpPicker.products || []).find((p) => p.dp_id === dpId);
      return entry ? entry.output_ports : [];
    },

    onDataProductPicked(node) {
      // After cfg.dp_id changes, default the port to the first available.
      const ports = this.dpPortsFor(node.config.dp_id);
      if (ports.length > 0 && !ports.some((p) => p.name === node.config.port_name)) {
        node.config.port_name = ports[0].name;
        node.config.materialized_table = ports[0].location || '';
      } else if (node.config.port_name) {
        const port = ports.find((p) => p.name === node.config.port_name);
        node.config.materialized_table = (port && port.location) || '';
      }
      this.onConfigChanged();
    },

    _onCanvasDoubleClick(ev) {
      const nodeEl = ev.target.closest('.drawflow-node');
      if (!nodeEl) return;
      const dfId = (nodeEl.id || '').replace('node-', '');
      const pqlId = Object.keys(this._drawflowNodes).find(
        (k) => String(this._drawflowNodes[k]) === dfId
      );
      const node = pqlId && this.nodes[pqlId];
      if (!node || node.block_type !== 'DataProduct') return;
      const targetDpId = Number(node.config.dp_id || 0);
      if (!targetDpId) return;
      this._pushBreadcrumb();
      window.location.href = `/dp/${targetDpId}/canvas`;
    },

    _restoreBreadcrumb() {
      try {
        const raw = window.localStorage.getItem('pql.dp_canvas.breadcrumb');
        this.breadcrumbTrail = raw ? JSON.parse(raw) : [];
      } catch (e) {
        this.breadcrumbTrail = [];
      }
    },

    _pushBreadcrumb() {
      const entry = {
        dp_id: this.product.id,
        ref: this.product.ref || `${this.product.catalog}.${this.product.schema}`,
      };
      const trail = (this.breadcrumbTrail || []).filter((e) => e.dp_id !== entry.dp_id);
      trail.push(entry);
      window.localStorage.setItem('pql.dp_canvas.breadcrumb', JSON.stringify(trail.slice(-6)));
    },

    popBreadcrumbBack() {
      const trail = this.breadcrumbTrail || [];
      const prev = trail[trail.length - 1];
      if (!prev) return;
      const updated = trail.slice(0, -1);
      window.localStorage.setItem('pql.dp_canvas.breadcrumb', JSON.stringify(updated));
      window.location.href = `/dp/${prev.dp_id}/canvas`;
    },

    async openVersionsDropdown() {
      this.versionsOpen = !this.versionsOpen;
      if (!this.versionsOpen) return;
      await this._refreshVersionsList();
    },

    async _refreshVersionsList() {
      const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/versions`, {
        silent: true,
      });
      if (res.ok) {
        this.versionsList = res.data.versions || [];
        this.pinnedVersion = res.data.pinned_version ?? null;
      }
    },

    async togglePin(v) {
      if (!this.canWrite) return;
      const action = v.is_production ? 'unpin' : 'pin';
      const res = await window.pqlApi.fetch(
        `/api/dp/${this.product.id}/canvas/versions/${v.version}/${action}`,
        { method: 'POST', silent: true }
      );
      if (!res.ok) {
        window.alert(action + ' failed: ' + (res.error || 'rejected'));
        return;
      }
      await this._refreshVersionsList();
    },

    async restoreVersion(version) {
      if (!this.canWrite) return;
      if (!window.confirm('Restore canvas to v' + version + '? This creates a new version.')) {
        return;
      }
      const fetched = await window.pqlApi.fetch(
        `/api/dp/${this.product.id}/canvas/versions/${version}`,
        { silent: true }
      );
      if (!fetched.ok) {
        window.alert('Restore failed: ' + (fetched.error || 'cannot load version'));
        return;
      }
      const doc = fetched.data.document;
      const saved = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas`, {
        method: 'POST',
        body: { document: doc },
        silent: true,
      });
      if (!saved.ok) {
        window.alert('Restore failed: ' + (saved.error || 'save rejected'));
        return;
      }
      this.version = saved.data.version;
      this._suppressAutosave = true;
      this._loadIntoDrawflow(doc);
      this._suppressAutosave = false;
      this.saveState = 'saved';
      this.lastSavedAt = saved.data.created_at;
      this.versionsOpen = false;
      this._scheduleValidate();
    },

    async runPreview(opts = {}) {
      if (this.previewBusy) return;
      if (!this.previewNodeId) return;
      this.previewBusy = true;
      this.previewError = null;
      // Marching-ants on every edge whose target is upstream of the
      // preview-target node — i.e. the path the executor is walking.
      this._setRunningEdges(this._edgesUpstreamOf(this.previewNodeId));
      const bust = opts.bust ? '?bust=1' : '';
      try {
        const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/preview${bust}`, {
          method: 'POST',
          body: {
            document: this._buildDocument(),
            upto_node_id: this.previewNodeId,
            limit: this.previewLimit,
          },
          silent: true,
        });
        this.previewBusy = false;
        if (!res.ok) {
          this.previewError = res.error || 'Preview failed';
          return;
        }
        this.previewResult = res.data;
        if (this.previewNodeId && res.data && typeof res.data.row_count === 'number') {
          this.previewRowCountByNode[this.previewNodeId] = res.data.row_count;
          this._refreshAllNodeBodies();
        }
      } finally {
        this.previewBusy = false;
        this._setRunningEdges(new Set());
      }
    },
  };
}
