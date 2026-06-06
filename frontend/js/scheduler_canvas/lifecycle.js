/*
 * Mount lifecycle for the scheduler task-chain editor.
 *
 * Instantiates Drawflow, swaps in the shared smooth/step path generator,
 * wires the Drawflow + DOM events the shared graph bundles rely on, fetches
 * the runnable-kind palette (rebuilding the injected catalog from it), then
 * loads the job's task graph.  A trimmed cousin of the data-product
 * lifecycle: no version ledger, no co-edit, no drill-in, no schema preview.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy; the
 * inner event callbacks stay arrows so they capture it.
 */

import { installZoomObserver } from '../canvas/_canvas_helpers.js';
import { installSmoothCurvature } from '../canvas/_drawflow_loader.js';
import { installFocusModeShortcut } from '../canvas/_focus_mode.js';
import { buildSchedulerCatalog } from './catalog.js';

export const schedulerLifecycleMethods = {
  async init() {
    if (this._initialized) return;
    this._initialized = true;
    this._focusModeOff = installFocusModeShortcut(this);

    // Fetch the runnable-kind palette and rebuild the catalog from it so the
    // palette never declares a kind the scheduler cannot execute.
    try {
      const kindsRes = await window.pqlApi.fetch(`/api/jobs/${this.jobId}/_kinds`, {
        silent: true,
      });
      if (kindsRes.ok && Array.isArray(kindsRes.data.kinds)) {
        this.catalog = buildSchedulerCatalog(kindsRes.data.kinds);
        this.paletteGroups = this.catalog.paletteGroups;
      }
    } catch (_e) {
      // Keep the fallback catalog assembleCanvasEditor injected.
    }

    if (typeof window.Drawflow !== 'function') {
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
    installSmoothCurvature(window.Drawflow);
    df.curvature = 0.5;

    this._nodeResizeObserver =
      typeof ResizeObserver === 'function'
        ? new ResizeObserver((entries) => {
            if (!this._connNodeDirty) this._connNodeDirty = new Set();
            for (const e of entries) {
              const m = e.target.id && e.target.id.match(/^node-(\d+)$/);
              if (m) this._connNodeDirty.add(m[1]);
            }
            this._scheduleResizeConnUpdate();
          })
        : null;

    df.on('nodeSelected', (id) => this._onDrawflowNodeSelected(id));
    df.on('nodeUnselected', () => {
      this.selectedNodeId = null;
    });
    df.on('nodeMoved', (dfId) => {
      this._onNodePositionChanged(dfId);
      this._repositionOutputPlusFor(dfId);
      this._scheduleEdgeToolbarReposition();
    });
    df.on('connectionCreated', () => {
      this._syncFromDrawflow();
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

    const inner = df.precanvas;
    this._zoomObserver = installZoomObserver(inner, node, (z) => {
      this._scheduleAllOutputPlusReposition();
      this._scheduleEdgeToolbarReposition();
      this.zoomPct = Math.round(z * 100);
      this._scheduleMinimapRender();
    });

    df.container.addEventListener('click', (ev) => {
      if (ev.target.closest('.connection')) return;
      if (ev.target.closest('.pql-edge-toolbar')) return;
      this._clearSelectedEdge();
    });
    df.container.addEventListener('contextmenu', (ev) => this._onCanvasContextMenu(ev));
    df.container.addEventListener('pointerdown', (ev) => this._onOutputPointerDown(ev));
    df.container.addEventListener('pointermove', () => {
      if (df.drag) this._scheduleAllOutputPlusReposition();
    });

    document.addEventListener('keydown', (ev) => {
      if (this._isFormFocused(ev.target)) return;
      if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'd' || ev.key === 'D')) {
        if (!this.selectedNodeId) return;
        ev.preventDefault();
        this.duplicateSelectedNode();
      } else if (ev.key === 'Delete' || ev.key === 'Backspace') {
        if (this._selectedEdgeId) {
          ev.preventDefault();
          this.deleteEdgeById(this._selectedEdgeId);
        } else if (this.multiSelectedNodeIds.length > 1) {
          ev.preventDefault();
          this.bulkDeleteSelected();
        } else if (this.selectedNodeId) {
          ev.preventDefault();
          this.deleteSelectedNode();
        }
      } else if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'l' || ev.key === 'L')) {
        ev.preventDefault();
        this.autoTidy();
      } else if ((ev.ctrlKey || ev.metaKey) && !ev.shiftKey && (ev.key === 'z' || ev.key === 'Z')) {
        ev.preventDefault();
        this.undo();
      } else if (
        ((ev.ctrlKey || ev.metaKey) && (ev.key === 'y' || ev.key === 'Y')) ||
        ((ev.ctrlKey || ev.metaKey) && ev.shiftKey && (ev.key === 'z' || ev.key === 'Z'))
      ) {
        ev.preventDefault();
        this.redo();
      }
    });

    this.$watch('(selectedNode && selectedNode.config) || null', () => this.onConfigChanged(), {
      deep: true,
    });

    await this.refreshRunsList();
    await this.loadLatest();
  },
  _isFormFocused(target) {
    if (!target || target.matches == null) return false;
    return (
      target.matches('input, textarea, select, [contenteditable], [contenteditable=""]') ||
      target.closest('.cm-editor') != null
    );
  },
  // A task may depend on many upstream tasks, so every input pin accepts
  // more than one wire — override the data-product one-connection-per-pin
  // rule the shared drag-validation assumes.
  _isInputPinFree() {
    return true;
  },
};
