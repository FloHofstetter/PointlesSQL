/*
 * Mount lifecycle for the canvas editor.
 *
 * The init() entry point Alpine invokes on mount: instantiate Drawflow, swap
 * in the shared smooth / step path generator, wire every Drawflow event and
 * DOM listener (selection, drag, connect, context menu, drag-to-connect,
 * keyboard shortcuts, multi-select, the zoom observer), then load the latest
 * document.  Plus the _isFormFocused guard those keyboard handlers use to
 * stay out of the way while a field or CodeMirror editor has focus.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy; the
 * inner event callbacks stay arrows so they capture it.
 */

import { installZoomObserver } from '../../canvas/_canvas_helpers.js';
import { installSmoothCurvature } from '../../canvas/_drawflow_loader.js';
import { installFocusModeShortcut } from '../../canvas/_focus_mode.js';

export const lifecycleMethods = {
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

    // Drawflow emits `nodeMoved` only once, on drop — never during the drag.
    // The "+" handles live in stage screen-coords (outside the node's
    // transform), so without a live update they sit still through the whole
    // drag and only snap to the node on release.  Canvas pan already tracks
    // via the precanvas transform observer; node drag is the gap, so
    // reposition every pointermove while a node drag is in flight.
    df.container.addEventListener('pointermove', () => {
      if (df.drag) this._scheduleAllOutputPlusReposition();
    });

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

    // Keyboard shortcuts: Ctrl+S saves; Ctrl+D dupes the single-selected
    // node; Ctrl+C / Ctrl+V copy / paste honour the multi-select set if any
    // (otherwise fall back to the single selection); Delete / Backspace
    // bulk-removes the multi-selected set with a confirm prompt.
    document.addEventListener('keydown', (ev) => {
      // Ctrl+S must win even while a form field or CodeMirror editor has
      // focus — otherwise the browser's save-page dialog hijacks the most
      // natural moment to save (right after typing a config value).
      if ((ev.ctrlKey || ev.metaKey) && (ev.key === 's' || ev.key === 'S')) {
        ev.preventDefault();
        this.save();
        return;
      }
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

    // The app shell leaves the stage quite narrow on common viewports and
    // focus mode (Shift+F) nearly doubles it, but nothing pointed users at
    // it.  Offer it once when the stage is tight; "dismiss" persists.
    try {
      const dismissed = localStorage.getItem('pql.canvas.focus-hint-dismissed') === '1';
      if (!dismissed && !this.focusMode && node.getBoundingClientRect().width < 700) {
        this.focusHintVisible = true;
      }
    } catch (_e) {
      // localStorage unavailable — skip the hint rather than nag every load.
    }

    // Conditional co-edit attach — opt-in via ?coedit=1 so the
    // single-user editor pays no Y.js download cost by default.
    try {
      const { attachCanvasCoedit, isCoeditEnabled } = await import('../coedit.js');
      if (isCoeditEnabled()) {
        this._coeditController = await attachCanvasCoedit(this, this.product.id);
      }
    } catch (_e) {
      // Coedit is best-effort; never block the single-user editor.
    }
  },
  _isFormFocused(target) {
    if (!target || target.matches == null) return false;
    return (
      target.matches('input, textarea, select, [contenteditable], [contenteditable=""]') ||
      target.closest('.cm-editor') != null
    );
  },
  enableFocusFromHint() {
    if (!this.focusMode) this.toggleFocusMode();
    this.dismissFocusHint();
  },
  dismissFocusHint() {
    this.focusHintVisible = false;
    try {
      localStorage.setItem('pql.canvas.focus-hint-dismissed', '1');
    } catch (_e) {
      // localStorage unavailable — the hint stays per-session only.
    }
  },
};
