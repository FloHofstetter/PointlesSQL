/*
 * Single source of truth for the canvas block taxonomy.
 *
 * Every surface that paints a node — the read-write editor, the
 * read-only diff page, the mesh view — needs the same label, icon, pin
 * shape and node markup per block type.  These used to live as two
 * hand-maintained copies (a rich table in the editor, a leaner one in
 * the Drawflow loader) that drifted apart on every new block.  They are
 * unified here: the editor reads the full records (help text, palette
 * group, default config factory); the loader derives its leaner needs
 * from the same records.
 */

/**
 * @typedef {Object} BlockDef
 * @property {string} type        Block type id (matches backend BLOCK_REGISTRY).
 * @property {string} label       Human label shown in palette + node header.
 * @property {string} icon        Bootstrap-icon class.
 * @property {string} help        One-line palette tooltip.
 * @property {('sources'|'transforms'|'sinks')} group  Palette section.
 * @property {number} inputs      Input pin count (Drawflow `data_node` inputs).
 * @property {number} outputs     Output pin count.
 * @property {string[]} inPins    Named input pins, left→right.
 * @property {string[]} outPins   Named output pins.
 * @property {() => Object} defaultConfig  Fresh default config for a new node.
 */

/** @type {Record<string, BlockDef>} */
export const BLOCK_DEFS = {
  InputPort: {
    type: 'InputPort',
    label: 'Input port',
    icon: 'bi-box-arrow-in-right',
    help: "Read a Unity Catalog table as the canvas's upstream source.",
    inputs: 0,
    outputs: 1,
    inPins: [],
    outPins: ['out'],
    group: 'sources',
    defaultConfig: () => ({ table_fqn: '' }),
  },
  DataProduct: {
    type: 'DataProduct',
    label: 'Data product ◫',
    icon: 'bi-box-seam',
    help: 'Read the materialised table of an upstream data product output port (drill in via double-click).',
    inputs: 0,
    outputs: 1,
    inPins: [],
    outPins: ['out'],
    group: 'sources',
    defaultConfig: () => ({ dp_id: 0, port_name: '', materialized_table: '' }),
  },
  Filter: {
    type: 'Filter',
    label: 'Filter',
    icon: 'bi-funnel',
    help: 'Keep rows matching a SQL boolean predicate.',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ predicate: '' }),
  },
  Project: {
    type: 'Project',
    label: 'Project',
    icon: 'bi-columns-gap',
    help: 'Select a subset of columns to keep.',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ columns: [] }),
  },
  Join: {
    type: 'Join',
    label: 'Join',
    icon: 'bi-link-45deg',
    help: 'Combine two upstream tables on shared keys.',
    inputs: 2,
    outputs: 1,
    inPins: ['left', 'right'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ how: 'inner', keys: [] }),
  },
  GroupBy: {
    type: 'GroupBy',
    label: 'Group by',
    icon: 'bi-stack',
    help: 'Aggregate rows grouped by one or more keys.',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ keys: [], aggregations: [] }),
  },
  Limit: {
    type: 'Limit',
    label: 'Limit',
    icon: 'bi-arrow-down-square',
    help: 'Keep at most N rows.',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ n: 100 }),
  },
  SQL: {
    type: 'SQL',
    label: 'Raw SQL',
    icon: 'bi-braces-asterisk',
    help: 'Free-form DuckDB SQL with a {{in}} placeholder for the input.',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ query: 'SELECT * FROM {{in}}' }),
  },
  Window: {
    type: 'Window',
    label: 'Window',
    icon: 'bi-graph-up',
    help: 'Windowed column over PARTITION BY / ORDER BY. Args depend on the function.',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
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
    type: 'Pivot',
    label: 'Pivot',
    icon: 'bi-arrow-90deg-right',
    help: 'PIVOT: spread distinct values of the ON column into new columns, aggregating VALUE.',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ on_column: '', value_column: '', aggregate: 'sum' }),
  },
  Unpivot: {
    type: 'Unpivot',
    label: 'Unpivot',
    icon: 'bi-arrow-90deg-down',
    help: 'UNPIVOT: fold the chosen columns into two name/value columns.',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ value_columns: [], name_label: 'name', value_label: 'value' }),
  },
  Union: {
    type: 'Union',
    label: 'Union',
    icon: 'bi-share',
    help: 'Stack two upstream tables row-wise (UNION ALL when `all`).',
    inputs: 2,
    outputs: 1,
    inPins: ['left', 'right'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ all: true }),
  },
  Distinct: {
    type: 'Distinct',
    label: 'Distinct',
    icon: 'bi-filter-square',
    help: 'Keep distinct rows (optionally on a subset of columns).',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ columns: [] }),
  },
  Sort: {
    type: 'Sort',
    label: 'Sort',
    icon: 'bi-sort-down',
    help: 'ORDER BY multi-key with ASC/DESC per column.',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ order_by: [] }),
  },
  Sample: {
    type: 'Sample',
    label: 'Sample',
    icon: 'bi-droplet-half',
    help: 'Random sample — a percentage (0–100) or a fixed row count.',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ kind: 'percent', value: 10 }),
  },
  Cast: {
    type: 'Cast',
    label: 'Cast',
    icon: 'bi-arrow-repeat',
    help: 'Per-column type cast (e.g. amount → DECIMAL(10,2)); other columns pass through.',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ casts: [] }),
  },
  Rename: {
    type: 'Rename',
    label: 'Rename',
    icon: 'bi-tag',
    help: 'Rename columns via old→new pairs; unlisted columns keep their names.',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ renames: {} }),
  },
  CalcColumn: {
    type: 'CalcColumn',
    label: 'Calc column',
    icon: 'bi-calculator',
    help: 'Add a computed column from a DuckDB expression (e.g. price * qty).',
    inputs: 1,
    outputs: 1,
    inPins: ['in'],
    outPins: ['out'],
    group: 'transforms',
    defaultConfig: () => ({ expression: '', target_alias: 'calc' }),
  },
  OutputPort: {
    type: 'OutputPort',
    label: 'Output port',
    icon: 'bi-box-arrow-up-right',
    help: 'Materialize the upstream rows to a Delta target table.',
    inputs: 1,
    outputs: 0,
    inPins: ['in'],
    outPins: [],
    group: 'sinks',
    defaultConfig: () => ({
      port_name: 'default',
      materialized_table: '',
      mode: 'overwrite',
      merge_on: [],
    }),
  },
};

/** Palette section order (independent of `BLOCK_DEFS` insertion order). */
export const PALETTE_ORDER = ['sources', 'transforms', 'sinks'];

/**
 * Look up a block definition, returning a safe fallback for unknown types
 * so an out-of-date document still renders something rather than throwing.
 *
 * @param {string} type
 * @returns {BlockDef}
 */
export function blockDef(type) {
  return (
    BLOCK_DEFS[type] || {
      type,
      label: type,
      icon: 'bi-question-square',
      help: '',
      inputs: 1,
      outputs: 1,
      inPins: ['in'],
      outPins: ['out'],
      group: 'transforms',
      defaultConfig: () => ({}),
    }
  );
}

/**
 * Drawflow input-pin index for a named pin.
 *
 * Drawflow addresses pins positionally (`input_1`, `input_2`); only the
 * two-input blocks (Join, Union) need a non-zero index, where `right`
 * maps to the second pin.
 *
 * @param {string} type
 * @param {string} pinName
 * @param {('in'|'out')} direction
 * @returns {number}
 */
export function pinIndexFor(type, pinName, direction) {
  const def = BLOCK_DEFS[type];
  if (direction === 'in' && def && def.inPins.length > 1) {
    const i = def.inPins.indexOf(pinName);
    return i >= 0 ? i : 0;
  }
  return 0;
}

/**
 * Group block types into palette sections, derived from each block's
 * `group` field so there is no second hand-maintained list to drift.
 *
 * @returns {Record<string, string[]>}
 */
export function paletteGroupsFromCatalog() {
  /** @type {Record<string, string[]>} */
  const groups = {};
  for (const section of PALETTE_ORDER) groups[section] = [];
  for (const def of Object.values(BLOCK_DEFS)) {
    if (!groups[def.group]) groups[def.group] = [];
    groups[def.group].push(def.type);
  }
  return groups;
}

/**
 * Build the inner DOM for a Drawflow node.
 *
 * Three shapes share one keyed template:
 *   - `editor`  — the read-write authoring node, with the error badge,
 *     schema-column strip and footer the editor mutates live.
 *   - `full`    — a static read-only node with a body (diff / mesh).
 *   - `compact` — a header-only strip for dense side-by-side panels.
 *
 * Labels and icons come from the trusted catalog (no user input), so the
 * markup is built without escaping; any user-controlled schema/config is
 * injected later by the editor through escaped render helpers.
 *
 * @param {string} blockType
 * @param {string} nodeId
 * @param {('editor'|'full'|'compact')} [mode]
 * @returns {string}
 */
export function nodeHtml(blockType, nodeId, mode = 'editor') {
  const def = blockDef(blockType);
  if (mode === 'compact') {
    return `
      <div data-pql-node-id="${nodeId}">
        <div class="pql-node-header">
          <i class="bi ${def.icon}"></i>
          <span>${def.label}</span>
          <span class="text-muted small ms-auto">${blockType}</span>
        </div>
      </div>
    `;
  }
  if (mode === 'full') {
    return `
    <div data-pql-node-id="${nodeId}">
      <div class="pql-node-header">
        <i class="bi ${def.icon}"></i>
        <span>${def.label}</span>
      </div>
      <div class="pql-node-body">
        <span class="text-muted small">${blockType}</span>
      </div>
    </div>
  `;
  }
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
