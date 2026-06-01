import { installZoomObserver } from '../dp_canvas/_canvas_helpers.js';
import { installSmoothCurvature } from '../dp_canvas/_drawflow_loader.js';

/*
 * Mesh-canvas editor — Alpine factory.
 *
 * Drawflow-based editable surface where each node is a workspace data
 * product and each wire is one ``upstream_product`` input-port row.
 * Save round-trips against ``/api/mesh/canvas`` which diffs the
 * desired edge set against the current DB rows and applies the delta
 * via the standard port-CRUD helpers — no schema mutation, no Delta
 * data motion.
 *
 * Nodes are read-only here (the DP catalog itself is authored on its
 * own surface); only edges can be added/removed.
 */

const NODE_WIDTH = 240;
const NODE_SPACING_X = 320;
const NODE_SPACING_Y = 140;

function meshNodeHtml(node) {
  const isGhost = node.workspace_slug && !node.is_local;
  const wsBadge = isGhost
    ? `<span class="badge bg-warning-subtle text-warning-emphasis ms-2">ws: ${node.workspace_slug}</span>`
    : '';
  return `
    <div class="pql-node-header${isGhost ? ' pql-mesh-ghost-header' : ''}">
      <i class="bi bi-box-seam me-1"></i>
      <span>${node.ref || 'dp ' + node.dp_id}</span>
      ${wsBadge}
    </div>
    <div class="pql-node-body">
      <code class="small">id ${node.dp_id}</code>
    </div>
  `;
}

export function meshCanvasEditor() {
  return {
    loading: true,
    saving: false,
    saveState: 'idle',
    lastSavedAt: null,
    lastSummary: null,
    focusMode: false,
    bannerDismissed: false,

    document: { nodes: [], edges: [] },
    issues: [],

    // Context menu state.
    ctxMenuOpen: false,
    ctxMenuX: 0,
    ctxMenuY: 0,
    ctxDropX: 0,
    ctxDropY: 0,

    // Workspace picker state.
    pickerOpen: false,
    pickerStage: 'workspace',
    pickerWorkspaces: [],
    pickerWorkspaceSlug: '',
    pickerDps: [],
    pickerLoading: false,
    pickerError: null,

    _drawflow: null,
    _dfIdByDpId: {},
    _validateTimer: null,
    _suppress: false,

    async init() {
      // Alpine auto-invokes init() and the template also carries
      // x-init="init()"; guard against the double-run so we don't spin up two
      // Drawflow instances (two .drawflow precanvases) in one container.
      if (this._initialized) return;
      this._initialized = true;
      try {
        this.focusMode = localStorage.getItem('pql.focus-mode') === '1';
        this.bannerDismissed = localStorage.getItem('pql.mesh.banner.dismissed') === '1';
      } catch (_e) {
        this.focusMode = false;
      }
      window.addEventListener('keydown', (ev) => {
        if (
          ev.shiftKey &&
          (ev.key === 'F' || ev.key === 'f') &&
          !ev.target.closest('input, textarea')
        ) {
          ev.preventDefault();
          if (typeof window.pqlToggleFocusMode === 'function') {
            this.focusMode = window.pqlToggleFocusMode();
          }
        }
      });
      if (typeof window.Drawflow !== 'function') {
        await new Promise((r) => setTimeout(r, 50));
      }
      if (typeof window.Drawflow !== 'function') {
        this.loading = false;
        this.saveState = 'error';
        return;
      }
      const df = new window.Drawflow(this.$refs.canvas);
      df.reroute = true;
      df.editor_mode = 'edit';
      df.start();
      this._drawflow = df;

      // Same smooth/step connection paths as the DP editor (shared, single
      // idempotent prototype patch across all Drawflow surfaces).
      installSmoothCurvature(window.Drawflow);
      df.curvature = 0.5;

      df.on('connectionCreated', () => {
        this._syncEdges();
        this._scheduleDecorate();
      });
      df.on('connectionRemoved', () => this._syncEdges());
      df.on('nodeMoved', () => this._scheduleDecorate());

      // Zoom-compensated stroke math (same hook DP-Canvas uses).
      const inner = df.precanvas;
      this._zoomObserver = installZoomObserver(inner, this.$refs.canvas);

      // Right-click on canvas background opens the context menu.
      const canvasEl = this.$refs.canvas;
      canvasEl.addEventListener('contextmenu', (ev) => {
        const onNode = ev.target.closest('.drawflow-node');
        if (onNode) return; // node-level menu is reserved for future use
        ev.preventDefault();
        const rect = canvasEl.getBoundingClientRect();
        this.ctxDropX = ev.clientX - rect.left;
        this.ctxDropY = ev.clientY - rect.top;
        this.ctxMenuX = ev.clientX;
        this.ctxMenuY = ev.clientY;
        this.ctxMenuOpen = true;
      });
      document.addEventListener('click', () => {
        this.ctxMenuOpen = false;
      });

      await this.load();
    },

    createDpHere() {
      this.ctxMenuOpen = false;
      window.location.assign('/dp/new');
    },

    dismissBanner() {
      this.bannerDismissed = true;
      try {
        localStorage.setItem('pql.mesh.banner.dismissed', '1');
      } catch (_e) {
        // Per-session dismissal still works without storage.
      }
    },

    async openCrossWsPicker() {
      this.ctxMenuOpen = false;
      this.pickerOpen = true;
      this.pickerStage = 'workspace';
      this.pickerError = null;
      this.pickerLoading = true;
      this.pickerWorkspaces = [];
      this.pickerDps = [];
      const res = await window.pqlApi.fetch('/api/admin/workspaces', { silent: true });
      this.pickerLoading = false;
      if (!res.ok) {
        this.pickerError = res.error || 'Failed to load workspaces';
        return;
      }
      this.pickerWorkspaces = (res.data && res.data.workspaces) || [];
    },

    async pickWorkspace(slug) {
      this.pickerWorkspaceSlug = slug;
      this.pickerStage = 'dp';
      this.pickerLoading = true;
      this.pickerError = null;
      const res = await window.pqlApi.fetch(`/api/mesh/canvas/picker/${encodeURIComponent(slug)}`, {
        silent: true,
      });
      this.pickerLoading = false;
      if (!res.ok) {
        this.pickerError = res.error || 'Failed to load DPs';
        return;
      }
      this.pickerDps = (res.data && res.data.data_products) || [];
    },

    pickDp(dp) {
      const ghost = {
        dp_id: dp.id,
        ref: dp.slug || dp.ref || 'dp ' + dp.id,
        workspace_slug: this.pickerWorkspaceSlug,
        is_local: false,
      };
      const nodes = [...(this.document.nodes || [])];
      if (!nodes.find((n) => n.dp_id === ghost.dp_id)) nodes.push(ghost);
      this.document = { ...this.document, nodes };
      this._hydrate();
      this.pickerOpen = false;
    },

    closePicker() {
      this.pickerOpen = false;
    },

    async autoLayout() {
      this.ctxMenuOpen = false;
      if (!this._drawflow) return;
      if (!window.dagre) return;
      const { computeLayout, animateTo } = await import('../dp_canvas/_auto_layout.js');
      const nodes = (this.document.nodes || []).map((n) => ({ id: 'dp_' + n.dp_id }));
      const edges = (this.document.edges || []).map((e) => ({
        source_node_id: 'dp_' + e.source_dp_id,
        target_node_id: 'dp_' + e.target_dp_id,
      }));
      if (nodes.length === 0) return;
      const targets = computeLayout(nodes, edges, { rankdir: 'TB' });
      // Map back to drawflow ids; current positions read from drawflow state.
      const raw = this._drawflow.export();
      const dfData = (raw && raw.drawflow && raw.drawflow.Home && raw.drawflow.Home.data) || {};
      const drawflowIdByPqlId = {};
      const currentPos = {};
      for (const n of this.document.nodes || []) {
        const dfId = this._dfIdByDpId[n.dp_id];
        if (dfId == null) continue;
        const key = 'dp_' + n.dp_id;
        drawflowIdByPqlId[key] = dfId;
        const dfNode = dfData[dfId];
        currentPos[key] = { x: dfNode ? dfNode.pos_x : 0, y: dfNode ? dfNode.pos_y : 0 };
      }
      await animateTo(this._drawflow, drawflowIdByPqlId, currentPos, targets, 250);
    },

    statusLabel() {
      if (this.saving) return 'Saving…';
      if (this.saveState === 'error') return 'Save failed';
      if (this.saveState === 'saved' && this.lastSavedAt) return '✓ Saved';
      return '';
    },

    statusTooltip() {
      if (this.saveState === 'saved' && this.lastSavedAt) {
        return 'Last saved at ' + new Date(this.lastSavedAt).toLocaleString();
      }
      return '';
    },

    statusClass() {
      if (this.saveState === 'error') return 'text-danger';
      if (this.saving) return 'text-muted';
      if (this.saveState === 'saved') return 'text-success';
      return 'text-muted';
    },

    async load() {
      this.loading = true;
      const res = await window.pqlApi.fetch('/api/mesh/canvas', { silent: true });
      if (!res.ok) {
        this.loading = false;
        this.saveState = 'error';
        return;
      }
      this.document = res.data.document || { nodes: [], edges: [] };
      this._hydrate();
      this.loading = false;
      this.saveState = 'saved';
      this.lastSavedAt = new Date().toISOString();
      this._scheduleValidate();
    },

    _scheduleDecorate() {
      if (this._decorateRaf) return;
      this._decorateRaf = window.setTimeout(() => {
        this._decorateRaf = null;
        this._decorateAllConnections();
      }, 0);
    },

    _decorateAllConnections() {
      const df = this._drawflow;
      if (!df) return;
      const svgs = df.container.querySelectorAll('.drawflow .connection');
      const svgNS = 'http://www.w3.org/2000/svg';
      for (const svg of svgs) {
        const main = svg.querySelector('.main-path');
        if (!main) continue;
        main.setAttribute('marker-end', 'url(#pql-arrow-end)');
        if (svg.dataset.pqlDecorated === '1') {
          // Refresh hit-area `d` so it tracks moved nodes — same
          // story as the DP-Canvas decorator: Drawflow rewrites
          // children[0]'s `d` on every move, so the hit-area
          // (children[1]) needs an explicit mirror.
          const hit = svg.querySelector('.pql-edge-hit-area');
          if (hit) hit.setAttribute('d', main.getAttribute('d') || '');
          continue;
        }
        svg.dataset.pqlDecorated = '1';
        const hit = document.createElementNS(svgNS, 'path');
        hit.setAttribute('class', 'pql-edge-hit-area');
        hit.setAttribute('d', main.getAttribute('d') || '');
        hit.setAttribute('fill', 'none');
        svg.appendChild(hit);
        try {
          const obs = new MutationObserver(() => {
            hit.setAttribute('d', main.getAttribute('d') || '');
          });
          obs.observe(main, { attributes: true, attributeFilter: ['d'] });
        } catch (_e) {
          // MutationObserver absent in extreme sandboxes; the
          // scheduled-decorate pass keeps `d` in sync.
        }
        hit.addEventListener('mouseenter', () => svg.classList.add('pql-edge-hover'));
        hit.addEventListener('mouseleave', () => svg.classList.remove('pql-edge-hover'));
      }
    },

    _hydrate() {
      this._suppress = true;
      const df = this._drawflow;
      df.clear();
      this._dfIdByDpId = {};
      const cols = Math.max(1, Math.ceil(Math.sqrt((this.document.nodes || []).length)));
      (this.document.nodes || []).forEach((node, idx) => {
        const x = (idx % cols) * NODE_SPACING_X + 40;
        const y = Math.floor(idx / cols) * NODE_SPACING_Y + 40;
        const dfId = df.addNode(
          'dp_' + node.dp_id,
          1,
          1,
          x,
          y,
          'dp_' + node.dp_id,
          { dp_id: node.dp_id, ref: node.ref },
          meshNodeHtml(node),
          false
        );
        this._dfIdByDpId[node.dp_id] = dfId;
      });
      (this.document.edges || []).forEach((edge) => {
        const srcDf = this._dfIdByDpId[edge.source_dp_id];
        const tgtDf = this._dfIdByDpId[edge.target_dp_id];
        if (!srcDf || !tgtDf) return;
        try {
          df.addConnection(srcDf, tgtDf, 'output_1', 'input_1');
        } catch (e) {
          // ignore — the validator surfaces broken wires below.
        }
      });
      this._suppress = false;
      this._scheduleDecorate();
    },

    _syncEdges() {
      if (!this._drawflow || this._suppress) return;
      const raw = this._drawflow.export();
      const dfNodes = (raw && raw.drawflow && raw.drawflow.Home && raw.drawflow.Home.data) || {};
      const dpIdByDfId = {};
      for (const [dfId, dfNode] of Object.entries(dfNodes)) {
        const data = dfNode.data || {};
        if (data.dp_id) dpIdByDfId[dfId] = data.dp_id;
      }
      const existing = (this.document.edges || []).reduce((acc, e) => {
        acc[`${e.source_dp_id}->${e.target_dp_id}`] = e.id;
        return acc;
      }, {});
      const newEdges = [];
      let synthSeq = 0;
      for (const [dfId, dfNode] of Object.entries(dfNodes)) {
        const srcDpId = dpIdByDfId[dfId];
        if (!srcDpId) continue;
        const outputs = dfNode.outputs || {};
        for (const outData of Object.values(outputs)) {
          const conns = (outData && outData.connections) || [];
          for (const conn of conns) {
            const tgtDpId = dpIdByDfId[conn.node];
            if (!tgtDpId) continue;
            const key = `${srcDpId}->${tgtDpId}`;
            const id = existing[key] || `mesh_new_${++synthSeq}_${srcDpId}_${tgtDpId}`;
            newEdges.push({ id, source_dp_id: Number(srcDpId), target_dp_id: Number(tgtDpId) });
          }
        }
      }
      this.document = { ...this.document, edges: newEdges };
      this._scheduleValidate();
    },

    _scheduleValidate() {
      if (this._validateTimer) window.clearTimeout(this._validateTimer);
      this._validateTimer = window.setTimeout(() => this.validate(), 600);
    },

    async validate() {
      const res = await window.pqlApi.fetch('/api/mesh/canvas/validate', {
        method: 'POST',
        body: { document: this.document },
        silent: true,
      });
      if (!res.ok) return;
      this.issues = res.data.issues || [];
    },

    async save() {
      if (this.saving) return;
      this.saving = true;
      this.saveState = 'saving';
      const res = await window.pqlApi.fetch('/api/mesh/canvas', {
        method: 'POST',
        body: { document: this.document },
        silent: true,
      });
      this.saving = false;
      if (!res.ok) {
        this.saveState = 'error';
        return;
      }
      this.lastSummary = res.data.summary;
      this.document = res.data.document || this.document;
      this._hydrate();
      this.saveState = 'saved';
      this.lastSavedAt = new Date().toISOString();
      this._scheduleValidate();
    },
  };
}
