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
    help: "Read a Unity Catalog table as the canvas's upstream source.",
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
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({
      function: 'row_number',
      target_alias: 'rn',
      partition_by: [],
      order_by: [],
      args: [],
    }),
  },
  Pivot: {
    label: 'Pivot',
    icon: 'bi-arrow-90deg-right',
    help: 'DuckDB PIVOT — turn distinct values of a column into new columns.',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ on_column: '', value_column: '', aggregate: 'sum' }),
  },
  Unpivot: {
    label: 'Unpivot',
    icon: 'bi-arrow-90deg-down',
    help: 'DuckDB UNPIVOT — collapse multiple columns into name/value rows.',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ value_columns: [], name_label: 'name', value_label: 'value' }),
  },
  Union: {
    label: 'Union',
    icon: 'bi-share',
    help: 'Stack two upstream tables row-wise (UNION ALL when `all`).',
    inputs: 2,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ all: true }),
  },
  Distinct: {
    label: 'Distinct',
    icon: 'bi-filter-square',
    help: 'Keep distinct rows (optionally on a subset of columns).',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ columns: [] }),
  },
  Sort: {
    label: 'Sort',
    icon: 'bi-sort-down',
    help: 'ORDER BY multi-key with ASC/DESC per column.',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ order_by: [] }),
  },
  Sample: {
    label: 'Sample',
    icon: 'bi-droplet-half',
    help: 'TABLESAMPLE — pick a percentage or row count at random.',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ kind: 'percent', value: 10 }),
  },
  Cast: {
    label: 'Cast',
    icon: 'bi-arrow-repeat',
    help: 'Per-column DuckDB type cast.',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ casts: [] }),
  },
  Rename: {
    label: 'Rename',
    icon: 'bi-tag',
    help: 'Per-column rename map.',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
    defaultConfig: () => ({ renames: {} }),
  },
  CalcColumn: {
    label: 'Calc column',
    icon: 'bi-calculator',
    help: 'Compute a new column from a DuckDB expression.',
    inputs: 1,
    outputs: 1,
    group: 'transforms',
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
      <div class="pql-node-cols" data-pql-node-cols></div>
      <div class="pql-node-body" data-pql-node-body>
        <span class="text-muted">${def.label}</span>
      </div>
      <div class="pql-node-footer" data-pql-node-footer></div>
    </div>
  `;
}

const TYPE_ICON_MAP = [
  [/^(INT|BIGINT|SMALLINT|TINYINT|INTEGER|HUGEINT|UBIGINT|UINTEGER|USMALLINT|UTINYINT)/i, 'bi-hash'],
  [/^(DOUBLE|FLOAT|REAL|DECIMAL|NUMERIC)/i, 'bi-calculator'],
  [/^(VARCHAR|TEXT|CHAR|STRING|BLOB|BIT)/i, 'bi-text-paragraph'],
  [/^(DATE|TIMESTAMP|TIME|INTERVAL)/i, 'bi-calendar3'],
  [/^(BOOL|BOOLEAN)/i, 'bi-check2-square'],
  [/^(STRUCT|LIST|MAP|UNION|ARRAY|JSON)/i, 'bi-diagram-3'],
];

function typeIcon(typeName) {
  const t = String(typeName || '').toUpperCase();
  for (const [re, icon] of TYPE_ICON_MAP) {
    if (re.test(t)) return icon;
  }
  return 'bi-circle';
}

function renderColsHtml(columns) {
  if (!columns || columns.length === 0) return '';
  const max = 3;
  const shown = columns.slice(0, max);
  const extra = columns.length - shown.length;
  const rows = shown
    .map(
      (c) =>
        `<span><i class="bi ${typeIcon(c.type)}"></i> ${escapeHtml(c.name)} <span class="text-muted">${escapeHtml(c.type || '')}</span></span>`,
    )
    .join('');
  const more = extra > 0 ? `<span class="text-muted">+${extra} more</span>` : '';
  return rows + more;
}

function renderFooterHtml(rowCount, status) {
  const badge =
    rowCount != null
      ? `<span class="badge bg-secondary" title="rows from last preview">${escapeHtml(formatRowCount(rowCount))}</span>`
      : '';
  let statusIcon = '';
  if (status === 'error') {
    statusIcon = '<i class="bi bi-x-circle-fill text-danger" title="validation error"></i>';
  } else if (status === 'ok') {
    statusIcon = '<i class="bi bi-check-circle-fill text-success" title="validated"></i>';
  } else {
    statusIcon = '<i class="bi bi-circle text-muted" title="not yet validated"></i>';
  }
  return `${badge}${statusIcon}`;
}

function formatRowCount(n) {
  if (n == null) return '';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M rows`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k rows`;
  return `${n} rows`;
}

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
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
      return cfg.table_fqn
        ? `<code>${cfg.table_fqn}</code>`
        : '<em class="text-muted">no table</em>';
    case 'Filter':
      return cfg.predicate
        ? `<code>${cfg.predicate.slice(0, 40)}</code>`
        : '<em class="text-muted">no predicate</em>';
    case 'Project':
      return cfg.columns && cfg.columns.length > 0
        ? `${cfg.columns.length} col${cfg.columns.length === 1 ? '' : 's'}`
        : '<em class="text-muted">no columns</em>';
    case 'Join':
      return `${cfg.how || 'inner'} on ${(cfg.keys || []).join(', ') || '—'}`;
    case 'GroupBy':
      return `by ${(cfg.keys || []).join(', ') || '—'}, ${(cfg.aggregations || []).length} agg`;
    case 'Limit':
      return `n = ${cfg.n}`;
    case 'SQL':
      return cfg.query
        ? `<code>${(cfg.query || '').slice(0, 36)}…</code>`
        : '<em class="text-muted">no query</em>';
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

    nodes: {},
    edges: {},
    selectedNodeId: null,

    paletteGroups: {
      sources: ['InputPort', 'DataProduct'],
      transforms: [
        'Filter',
        'Project',
        'Join',
        'GroupBy',
        'Limit',
        'SQL',
        'Window',
        'Pivot',
        'Unpivot',
        'Union',
        'Distinct',
        'Sort',
        'Sample',
        'Cast',
        'Rename',
        'CalcColumn',
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

    versionsOpen: false,
    versionsList: [],
    pinnedVersion: null,

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
      df.on('nodeMoved', (dfId) => this._onNodePositionChanged(dfId));
      df.on('connectionCreated', (info) => {
        this._syncFromDrawflow();
        // After the sync, the edge appears in `this.edges`; walk the
        // target side and fill sensible defaults if its config is empty.
        const tgtDfId = info && info.input_id;
        if (tgtDfId != null) {
          const tgtPqlId = this._pqlIdForDfId(tgtDfId);
          if (tgtPqlId) this._applySensibleDefaultsIfEmpty(tgtPqlId);
        }
      });
      df.on('connectionRemoved', () => this._syncFromDrawflow());
      df.on('nodeRemoved', () => this._syncFromDrawflow());
      df.on('nodeDataChanged', () => this._syncFromDrawflow());

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
        true,
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
        const targetIdx = this._pinIndex(
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
    },

    _pinIndex(blockType, pinName, direction) {
      if (direction === 'in' && (blockType === 'Join' || blockType === 'Union')) {
        return pinName === 'right' ? 1 : 0;
      }
      return 0;
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
            this._statusFor(pqlId),
          );
        }
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
          (n) =>
            n.block_type.toLowerCase().includes(q) ||
            (n.id || '').toLowerCase().includes(q),
        )
        .slice(0, 20);
    },

    searchNavigate(direction) {
      const matches = this.searchMatches();
      if (matches.length === 0) return;
      this.searchCursor =
        (this.searchCursor + direction + matches.length) % matches.length;
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
        const precanvas = df.container.querySelector('.drawflow');
        if (precanvas) {
          precanvas.style.transform = `translate(${df.canvas_x}px, ${df.canvas_y}px) scale(${df.zoom})`;
        }
      }
      this.selectedNodeId = target.id;
      this.closeSearch();
    },

    toggleMinimap() {
      this.minimapVisible = !this.minimapVisible;
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
        host.innerHTML =
          `<svg width="${W}" height="${H}"><rect width="${W}" height="${H}" fill="var(--bs-tertiary-bg)" stroke="var(--bs-border-color)" /></svg>`;
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
      const rects = nodes
        .map((n) => {
          const p = n.position || { x: 100, y: 100 };
          const x = PAD + (p.x - minX) * scale;
          const y = PAD + (p.y - minY) * scale;
          const w = NODE_W * scale;
          const h = NODE_H * scale;
          const fill =
            n.id === this.selectedNodeId
              ? 'var(--bs-primary)'
              : 'var(--bs-secondary)';
          return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" fill="${fill}" />`;
        })
        .join('');
      host.innerHTML =
        `<svg width="${W}" height="${H}">` +
        `<rect width="${W}" height="${H}" fill="var(--bs-tertiary-bg)" stroke="var(--bs-border-color)" />` +
        rects +
        '</svg>';
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
      this._suppressAutosave = true;
      for (const pqlId of ids) {
        const dfId = this._drawflowNodes[pqlId];
        if (dfId != null) df.removeNodeId('node-' + dfId);
      }
      this._suppressAutosave = false;
      this.multiSelectedNodeIds = [];
      this._syncFromDrawflow();
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
        (e) => set.has(e.source_node_id) && set.has(e.target_node_id),
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
          false,
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
        const targetIdx = this._pinIndex(this.nodes[tgtNew].block_type, e.target_pin, 'in');
        try {
          df.addConnection(srcDf, tgtDf, 'output_1', `input_${targetIdx + 1}`);
        } catch (_e) {
          // Skip invalid wire.
        }
      }
      this._suppressAutosave = false;
      this._syncFromDrawflow();
    },

    addStickyNote() {
      if (!this.canWrite) return;
      const note = {
        id: 'note-' + Math.random().toString(36).slice(2, 10),
        x: 60,
        y: 60,
        width: 220,
        height: 120,
        content: '',
      };
      this.annotations = [...this.annotations, note];
      this._scheduleAutosave();
    },

    updateStickyNote(id, patch) {
      const idx = this.annotations.findIndex((a) => a.id === id);
      if (idx < 0) return;
      this.annotations[idx] = { ...this.annotations[idx], ...patch };
      this.annotations = [...this.annotations];
      this._scheduleAutosave();
    },

    removeStickyNote(id) {
      this.annotations = this.annotations.filter((a) => a.id !== id);
      this._scheduleAutosave();
    },

    _stickyNotePointerDown(ev, note) {
      if (ev.target.matches('button, textarea')) return;
      ev.preventDefault();
      const startX = ev.clientX;
      const startY = ev.clientY;
      const baseX = note.x;
      const baseY = note.y;
      const onMove = (e) => {
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        this.updateStickyNote(note.id, { x: baseX + dx, y: baseY + dy });
      };
      const onUp = () => {
        document.removeEventListener('pointermove', onMove);
        document.removeEventListener('pointerup', onUp);
      };
      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
    },

    _pushCommand(cmd) {
      this._undoStack.push(cmd);
      if (this._undoStack.length > this._UNDO_DEPTH) this._undoStack.shift();
      this._redoStack = [];
    },

    undo() {
      const cmd = this._undoStack.pop();
      if (!cmd) return;
      try {
        cmd.undo();
        this._redoStack.push(cmd);
      } catch (_e) {
        // Swallow — best-effort restore.
      }
    },

    redo() {
      const cmd = this._redoStack.pop();
      if (!cmd) return;
      try {
        cmd.do();
        this._undoStack.push(cmd);
      } catch (_e) {
        // Swallow.
      }
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
      df.updateConnectionNodes('node-' + (Object.values(this._drawflowNodes)[0] || ''));
      // updateConnectionNodes touches a single node — easier to just re-render
      // every connection by walking the editor data and calling
      // updateConnectionNodes on each node.
      for (const dfId of Object.values(this._drawflowNodes)) {
        df.updateConnectionNodes('node-' + dfId);
      }
    },

    _refreshEdgeCategoryStyles() {
      const df = this._drawflow;
      if (!df) return;
      const cats = this.edgeCategories || {};
      const knownCats = ['numeric', 'text', 'temporal', 'boolean', 'complex', 'mixed'];
      const connections = df.container.querySelectorAll('.drawflow .connection');
      for (const conn of connections) {
        for (const k of knownCats) conn.classList.remove(`pql-edge-${k}`);
      }
      // Walk the edges dict + look up its drawflow connection by source/target.
      for (const edge of Object.values(this.edges)) {
        const cat = cats[edge.id] || 'mixed';
        const srcDf = this._drawflowNodes[edge.source_node_id];
        const tgtDf = this._drawflowNodes[edge.target_node_id];
        if (!srcDf || !tgtDf) continue;
        const sel =
          `.drawflow .connection.node_in_node-${tgtDf}` +
          `.node_out_node-${srcDf}`;
        const els = df.container.querySelectorAll(sel);
        for (const el of els) el.classList.add(`pql-edge-${cat}`);
      }
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
            false,
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
      const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/materialize`, {
        method: 'POST',
        body: {
          document: this._buildDocument(),
          expected_base_version: this.version,
        },
        silent: true,
      });
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
      const bust = opts.bust ? '?bust=1' : '';
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
    },
  };
}
