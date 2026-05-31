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

const BLOCK_DEFS = {
  InputPort: {
    label: 'Input port',
    icon: 'bi-box-arrow-in-right',
    help: 'Read a Unity Catalog table as the canvas\'s upstream source.',
    inputs: 0,
    outputs: 1,
    group: 'sources',
    defaultConfig: () => ({ table_fqn: '' }),
  },
  DataProduct: {
    label: 'Data product ◫',
    icon: 'bi-box-seam',
    help: 'Read the materialised table of an upstream data product output port (drill in via double-click).',
    inputs: 0,
    outputs: 1,
    group: 'sources',
    defaultConfig: () => ({ dp_id: 0, port_name: '', materialized_table: '' }),
  },
  Filter: {
    label: 'Filter',
    icon: 'bi-funnel',
    help: 'Keep rows matching a SQL boolean predicate.',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ predicate: '' }),
  },
  Project: {
    label: 'Project',
    icon: 'bi-columns-gap',
    help: 'Select a subset of columns to keep.',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ columns: [] }),
  },
  Join: {
    label: 'Join',
    icon: 'bi-link-45deg',
    help: 'Combine two upstream tables on shared keys.',
    inputs: 2,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ how: 'inner', keys: [] }),
  },
  GroupBy: {
    label: 'Group by',
    icon: 'bi-stack',
    help: 'Aggregate rows grouped by one or more keys.',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ keys: [], aggregations: [] }),
  },
  Limit: {
    label: 'Limit',
    icon: 'bi-arrow-down-square',
    help: 'Keep at most N rows.',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ n: 100 }),
  },
  SQL: {
    label: 'Raw SQL',
    icon: 'bi-braces-asterisk',
    help: 'Free-form DuckDB SQL with a {{in}} placeholder for the input.',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ query: 'SELECT * FROM {{in}}' }),
  },
  Window: {
    label: 'Window',
    icon: 'bi-graph-up',
    help: 'Add a windowed aggregation column over a PARTITION/ORDER spec.',
    inputs: 1, outputs: 1, group: 'transforms',
    defaultConfig: () => ({
      function: 'row_number', target_alias: 'rn', partition_by: [], order_by: [], args: [],
    }),
  },
  Pivot: {
    label: 'Pivot',
    icon: 'bi-arrow-90deg-right',
    help: 'DuckDB PIVOT — turn distinct values of a column into new columns.',
    inputs: 1, outputs: 1, group: 'transforms',
    defaultConfig: () => ({ on_column: '', value_column: '', aggregate: 'sum' }),
  },
  Unpivot: {
    label: 'Unpivot',
    icon: 'bi-arrow-90deg-down',
    help: 'DuckDB UNPIVOT — collapse multiple columns into name/value rows.',
    inputs: 1, outputs: 1, group: 'transforms',
    defaultConfig: () => ({ value_columns: [], name_label: 'name', value_label: 'value' }),
  },
  Union: {
    label: 'Union',
    icon: 'bi-share',
    help: 'Stack two upstream tables row-wise (UNION ALL when `all`).',
    inputs: 2, outputs: 1, group: 'transforms',
    defaultConfig: () => ({ all: true }),
  },
  Distinct: {
    label: 'Distinct',
    icon: 'bi-filter-square',
    help: 'Keep distinct rows (optionally on a subset of columns).',
    inputs: 1, outputs: 1, group: 'transforms',
    defaultConfig: () => ({ columns: [] }),
  },
  Sort: {
    label: 'Sort',
    icon: 'bi-sort-down',
    help: 'ORDER BY multi-key with ASC/DESC per column.',
    inputs: 1, outputs: 1, group: 'transforms',
    defaultConfig: () => ({ order_by: [] }),
  },
  Sample: {
    label: 'Sample',
    icon: 'bi-droplet-half',
    help: 'TABLESAMPLE — pick a percentage or row count at random.',
    inputs: 1, outputs: 1, group: 'transforms',
    defaultConfig: () => ({ kind: 'percent', value: 10 }),
  },
  Cast: {
    label: 'Cast',
    icon: 'bi-arrow-repeat',
    help: 'Per-column DuckDB type cast.',
    inputs: 1, outputs: 1, group: 'transforms',
    defaultConfig: () => ({ casts: [] }),
  },
  Rename: {
    label: 'Rename',
    icon: 'bi-tag',
    help: 'Per-column rename map.',
    inputs: 1, outputs: 1, group: 'transforms',
    defaultConfig: () => ({ renames: {} }),
  },
  CalcColumn: {
    label: 'Calc column',
    icon: 'bi-calculator',
    help: 'Compute a new column from a DuckDB expression.',
    inputs: 1, outputs: 1, group: 'transforms',
    defaultConfig: () => ({ expression: '', target_alias: 'calc' }),
  },
  OutputPort: {
    label: 'Output port',
    icon: 'bi-box-arrow-up-right',
    help: 'Materialize the upstream rows to a Delta target table.',
    inputs: 1,
    outputs: 0,
    group: 'sinks',
    defaultConfig: () => ({
      port_name: 'default',
      materialized_table: '',
      mode: 'overwrite',
      merge_on: [],
    }),
  },
};

const PIN_NAMES_IN = ['in', 'left', 'right'];
const PIN_NAMES_OUT = ['out'];

function nodeHtml(blockType, nodeId) {
  const def = BLOCK_DEFS[blockType] || { label: blockType, icon: 'bi-question-square' };
  return `
    <div data-pql-node-id="${nodeId}">
      <div class="pql-node-header">
        <i class="bi ${def.icon}"></i>
        <span>${def.label}</span>
        <span class="pql-node-badge badge bg-danger" style="display:none"
              data-pql-node-error-badge></span>
      </div>
      <div class="pql-node-body" data-pql-node-body>
        <span class="text-muted">${def.label}</span>
      </div>
    </div>
  `;
}

function generateNodeId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return 'n-' + crypto.randomUUID().slice(0, 12);
  }
  return 'n-' + Math.random().toString(36).slice(2, 14);
}

function inputPinName(blockType, idx) {
  if (blockType === 'Join' || blockType === 'Union') return ['left', 'right'][idx] || 'in';
  return PIN_NAMES_IN[0];
}

function outputPinName(_blockType, _idx) {
  return PIN_NAMES_OUT[0];
}

function describeConfig(blockType, cfg) {
  if (!cfg) return '';
  switch (blockType) {
    case 'InputPort':
      return cfg.table_fqn ? `<code>${cfg.table_fqn}</code>` : '<em class="text-muted">no table</em>';
    case 'Filter':
      return cfg.predicate ? `<code>${cfg.predicate.slice(0, 40)}</code>` : '<em class="text-muted">no predicate</em>';
    case 'Project':
      return (cfg.columns && cfg.columns.length > 0)
        ? `${cfg.columns.length} col${cfg.columns.length === 1 ? '' : 's'}`
        : '<em class="text-muted">no columns</em>';
    case 'Join':
      return `${cfg.how || 'inner'} on ${(cfg.keys || []).join(', ') || '—'}`;
    case 'GroupBy':
      return `by ${(cfg.keys || []).join(', ') || '—'}, ${(cfg.aggregations || []).length} agg`;
    case 'Limit':
      return `n = ${cfg.n}`;
    case 'SQL':
      return cfg.query ? `<code>${(cfg.query || '').slice(0, 36)}…</code>` : '<em class="text-muted">no query</em>';
    case 'OutputPort':
      return cfg.materialized_table
        ? `→ <code>${cfg.materialized_table}</code> (${cfg.mode || 'overwrite'})`
        : '<em class="text-muted">no target</em>';
    default:
      return '';
  }
}

export function dpCanvasEditor(product, ctx) {
  const ctxSafe = ctx || {};
  return {
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

    nodes: {},
    edges: {},
    selectedNodeId: null,

    paletteGroups: {
      sources: ['InputPort', 'DataProduct'],
      transforms: [
        'Filter', 'Project', 'Join', 'GroupBy', 'Limit', 'SQL',
        'Window', 'Pivot', 'Unpivot', 'Union', 'Distinct', 'Sort', 'Sample',
        'Cast', 'Rename', 'CalcColumn',
      ],
      sinks: ['OutputPort'],
    },

    projectInput: '',
    joinKeyInput: '',
    groupKeyInput: '',
    mergeOnInput: '',

    materializeOpen: false,
    materializeResult: null,
    materializeError: null,
    materializing: false,
    materializePreview: null,

    previewOpen: false,
    previewBusy: false,
    previewNodeId: null,
    previewLimit: 100,
    previewResult: null,
    previewError: null,

    dpPicker: { loaded: false, products: [] },
    breadcrumbTrail: [],

    _drawflow: null,
    _drawflowNodes: {},
    _saveTimer: null,
    _validateTimer: null,
    _suppressAutosave: false,

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

    blockLabel(kind) {
      return (BLOCK_DEFS[kind] && BLOCK_DEFS[kind].label) || kind;
    },
    blockIcon(kind) {
      return (BLOCK_DEFS[kind] && BLOCK_DEFS[kind].icon) || 'bi-question-square';
    },
    blockHelp(kind) {
      return (BLOCK_DEFS[kind] && BLOCK_DEFS[kind].help) || '';
    },

    async init() {
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

      df.on('nodeSelected', (id) => this._onDrawflowNodeSelected(id));
      df.on('nodeUnselected', () => {
        this.selectedNodeId = null;
      });
      df.on('nodeMoved', () => this._syncFromDrawflow());
      df.on('connectionCreated', () => this._syncFromDrawflow());
      df.on('connectionRemoved', () => this._syncFromDrawflow());
      df.on('nodeRemoved', () => this._syncFromDrawflow());
      df.on('nodeDataChanged', () => this._syncFromDrawflow());

      // Double-click on a DP◫ node opens that DP's canvas in-place
      // (push the current DP onto the breadcrumb trail in localStorage).
      const canvasEl = this.$refs.canvas;
      canvasEl.addEventListener('dblclick', (ev) => this._onCanvasDoubleClick(ev));

      this._restoreBreadcrumb();

      // Optional-chain via "&&" — Alpine's expression evaluator complains when
      // selectedNode is null, which surfaces as a console error on every
      // empty-canvas load.  The deep watcher still catches every config
      // mutation once a node is selected.
      this.$watch(
        '(selectedNode && selectedNode.config) || null',
        () => this.onConfigChanged(),
        { deep: true },
      );

      await this.loadLatest();

      // Conditional co-edit attach — opt-in via ?coedit=1 so the
      // single-user editor pays no Y.js download cost by default.
      try {
        const { attachCanvasCoedit, isCoeditEnabled } = await import(
          '../dp_canvas/coedit.js'
        );
        if (isCoeditEnabled()) {
          this._coeditController = await attachCanvasCoedit(this, this.product.id);
        }
      } catch (e) {
        // Coedit is best-effort; never block the single-user editor.
      }
    },

    saveStateLabel() {
      if (this.saveState === 'saving') return 'Saving…';
      if (this.saveState === 'error') return 'Save failed — ' + (this.saveError || '');
      if (this.saveState === 'saved' && this.lastSavedAt) {
        const date = new Date(this.lastSavedAt);
        return 'Saved · ' + date.toLocaleTimeString();
      }
      if (this.version !== null) return 'Loaded v' + this.version;
      return '';
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
    },

    _loadIntoDrawflow(doc) {
      const df = this._drawflow;
      df.clear();
      this._drawflowNodes = {};
      this.nodes = {};
      this.edges = {};
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
          false,
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
        const targetIdx = this._pinIndex(targetNode ? targetNode.block_type : '', edge.target_pin, 'in');
        try {
          df.addConnection(sourceDf, targetDf, `output_${sourceIdx}`, `input_${targetIdx + 1}`);
        } catch (e) {
          // Connection target invalid (block schema mismatch with saved doc);
          // skip the edge — the validator will surface it later.
        }
      }
      this._syncFromDrawflow();
    },

    _pinIndex(blockType, pinName, direction) {
      if (direction === 'in' && (blockType === 'Join' || blockType === 'Union')) {
        return pinName === 'right' ? 1 : 0;
      }
      return 0;
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
          config: existing ? existing.config : (BLOCK_DEFS[data.block_type] || { defaultConfig: () => ({}) }).defaultConfig(),
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
            const targetPin = (targetBlock === 'Join' || targetBlock === 'Union')
              ? (targetIdx === 1 ? 'right' : 'left')
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
      if (this.selectedNodeId && !newNodes[this.selectedNodeId]) {
        this.selectedNodeId = null;
      }
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

    _refreshAllNodeErrors() {
      const df = this._drawflow;
      if (!df) return;
      const perNode = {};
      for (const err of this.errors) {
        if (!err.node_id) continue;
        perNode[err.node_id] = (perNode[err.node_id] || 0) + 1;
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
          }
        } else {
          wrap.classList.remove('pql-node-error');
          if (badge) badge.style.display = 'none';
        }
      }
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
        false,
      );
      this._drawflowNodes[pqlId] = dfId;
      this.nodes[pqlId] = {
        id: pqlId,
        block_type: kind,
        config: def.defaultConfig(),
        position: pos,
      };
      this._refreshNodeBody(pqlId);
      this._scheduleAutosave();
      this._scheduleValidate();
    },

    deleteSelectedNode() {
      if (!this.selectedNodeId || !this.canWrite) return;
      const dfId = this._drawflowNodes[this.selectedNodeId];
      if (dfId) this._drawflow.removeNodeId('node-' + dfId);
      delete this._drawflowNodes[this.selectedNodeId];
      delete this.nodes[this.selectedNodeId];
      this.selectedNodeId = null;
      this._syncFromDrawflow();
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

    addProjectColumn(col) {
      const node = this.selectedNode;
      if (!node || !col) return;
      const trimmed = String(col).trim();
      if (!trimmed) return;
      if (node.config.columns.includes(trimmed)) return;
      node.config.columns.push(trimmed);
      this.onConfigChanged();
    },
    removeProjectColumn(idx) {
      const node = this.selectedNode;
      if (!node) return;
      node.config.columns.splice(idx, 1);
      this.onConfigChanged();
    },
    addJoinKey(col) {
      const node = this.selectedNode;
      if (!node || !col) return;
      const trimmed = String(col).trim();
      if (!trimmed || node.config.keys.includes(trimmed)) return;
      node.config.keys.push(trimmed);
      this.onConfigChanged();
    },
    removeJoinKey(idx) {
      const node = this.selectedNode;
      if (!node) return;
      node.config.keys.splice(idx, 1);
      this.onConfigChanged();
    },
    addGroupKey(col) {
      const node = this.selectedNode;
      if (!node || !col) return;
      const trimmed = String(col).trim();
      if (!trimmed || node.config.keys.includes(trimmed)) return;
      node.config.keys.push(trimmed);
      this.onConfigChanged();
    },
    removeGroupKey(idx) {
      const node = this.selectedNode;
      if (!node) return;
      node.config.keys.splice(idx, 1);
      this.onConfigChanged();
    },
    addAggregation() {
      const node = this.selectedNode;
      if (!node) return;
      node.config.aggregations.push({ column: '', fn: 'sum', alias: '' });
      this.onConfigChanged();
    },
    removeAggregation(idx) {
      const node = this.selectedNode;
      if (!node) return;
      node.config.aggregations.splice(idx, 1);
      this.onConfigChanged();
    },
    addMergeOn(col) {
      const node = this.selectedNode;
      if (!node || !col) return;
      const trimmed = String(col).trim();
      if (!trimmed) return;
      if (!Array.isArray(node.config.merge_on)) node.config.merge_on = [];
      if (node.config.merge_on.includes(trimmed)) return;
      node.config.merge_on.push(trimmed);
      this.onConfigChanged();
    },
    removeMergeOn(idx) {
      const node = this.selectedNode;
      if (!node) return;
      if (!Array.isArray(node.config.merge_on)) return;
      node.config.merge_on.splice(idx, 1);
      this.onConfigChanged();
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
      this._refreshAllNodeErrors();
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

    async openMaterializeModal() {
      this.materializeOpen = true;
      this.materializeResult = null;
      this.materializeError = null;
      this.materializePreview = null;
      const outputNode = Object.values(this.nodes).find((n) => n.block_type === 'OutputPort');
      this.materializePreview = {
        target_fqn: outputNode ? outputNode.config.materialized_table : null,
        mode: outputNode ? outputNode.config.mode : null,
        sql: '— SQL preview is rendered server-side on Run —',
      };
    },

    closeMaterializeModal() {
      this.materializeOpen = false;
    },

    async confirmMaterialize() {
      if (this.materializing) return;
      this.materializing = true;
      this.materializeError = null;
      const res = await window.pqlApi.fetch(
        `/api/dp/${this.product.id}/canvas/materialize`,
        {
          method: 'POST',
          body: {
            document: this._buildDocument(),
            expected_base_version: this.version,
          },
          silent: true,
        },
      );
      this.materializing = false;
      if (!res.ok) {
        this.materializeError = res.error || 'Materialize failed';
        return;
      }
      this.materializeResult = res.data;
      this.version = res.data.graph_version;
      this.saveState = 'saved';
      this.lastSavedAt = new Date().toISOString();
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
        (k) => String(this._drawflowNodes[k]) === dfId,
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

    async runPreview() {
      if (this.previewBusy) return;
      if (!this.previewNodeId) return;
      this.previewBusy = true;
      this.previewError = null;
      const res = await window.pqlApi.fetch(
        `/api/dp/${this.product.id}/canvas/preview`,
        {
          method: 'POST',
          body: {
            document: this._buildDocument(),
            upto_node_id: this.previewNodeId,
            limit: this.previewLimit,
          },
          silent: true,
        },
      );
      this.previewBusy = false;
      if (!res.ok) {
        this.previewError = res.error || 'Preview failed';
        return;
      }
      this.previewResult = res.data;
    },
  };
}
