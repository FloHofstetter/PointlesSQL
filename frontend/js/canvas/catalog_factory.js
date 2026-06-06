/*
 * Generic block-catalog factory for the reusable canvas editor.
 *
 * The data-product editor ships a hand-written catalog
 * (``dp_canvas/_block_catalog.js``); consumers whose block set is small or
 * server-driven (the scheduler's task kinds, the DataFrame Studio block
 * list) build theirs from a list of block definitions with this factory.
 * It produces the same catalog shape the shared editor bundles read off
 * ``this.catalog`` — ``BLOCK_DEFS`` plus the ``blockDef`` / ``pinIndexFor``
 * / ``inputPinName`` / ``nodeHtml`` / ``describeConfig`` / ``paletteGroups``
 * / ``paletteOrder`` lookups — so the same Drawflow shell drives it
 * unchanged.
 *
 * A block definition is the same record the DP catalog uses
 * (``type`` / ``label`` / ``icon`` / ``help`` / ``inputs`` / ``outputs`` /
 * ``inPins`` / ``outPins`` / ``group`` / ``defaultConfig``) plus an optional
 * ``describe(cfg) -> string`` for the per-node body summary.
 */

/**
 * Build the per-node DOM string in the catalog's editor / full / compact
 * mode.  Mirrors the DP catalog's ``nodeHtml`` so the shared node-render
 * bundle finds the ``[data-pql-node-*]`` hooks it rewrites live.
 *
 * @param {Object} def
 * @param {string} nodeId
 * @param {('editor'|'full'|'compact')} mode
 * @returns {string}
 */
function renderNode(def, nodeId, mode) {
  if (mode === 'compact') {
    return `
      <div data-pql-node-id="${nodeId}">
        <div class="pql-node-header">
          <i class="bi ${def.icon}"></i>
          <span>${def.label}</span>
          <span class="text-muted small ms-auto">${def.type}</span>
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
        <span class="text-muted small">${def.type}</span>
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

/**
 * Assemble a catalog object from a list of block definitions.
 *
 * @param {Array<Object>} blockDefs  Block records (see module docstring).
 * @param {Object} [opts]
 * @param {string[]} [opts.paletteOrder]  Palette section order; defaults to
 *   the distinct ``group`` values in first-seen order.
 * @returns {Object} A catalog matching the shape the editor bundles expect.
 */
export function makeCatalog(blockDefs, opts = {}) {
  const BLOCK_DEFS = {};
  for (const def of blockDefs) BLOCK_DEFS[def.type] = def;

  const paletteOrder =
    opts.paletteOrder ||
    blockDefs.reduce((acc, d) => (acc.includes(d.group) ? acc : [...acc, d.group]), []);

  function blockDef(type) {
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
        group: paletteOrder[0] || 'blocks',
        defaultConfig: () => ({}),
      }
    );
  }

  function pinIndexFor(type, pinName, direction) {
    const def = BLOCK_DEFS[type];
    if (direction === 'in' && def && def.inPins.length > 1) {
      const i = def.inPins.indexOf(pinName);
      return i >= 0 ? i : 0;
    }
    return 0;
  }

  function inputPinName(type, index) {
    const def = BLOCK_DEFS[type];
    const pins = (def && def.inPins) || [];
    return pins[index] || (pins.length ? pins[0] : 'in');
  }

  function paletteGroups() {
    const groups = {};
    for (const section of paletteOrder) groups[section] = [];
    for (const def of Object.values(BLOCK_DEFS)) {
      if (!groups[def.group]) groups[def.group] = [];
      groups[def.group].push(def.type);
    }
    return groups;
  }

  function describeConfig(type, cfg) {
    const def = BLOCK_DEFS[type];
    if (def && typeof def.describe === 'function') return def.describe(cfg || {});
    return '';
  }

  function nodeHtml(type, nodeId, mode = 'editor') {
    return renderNode(blockDef(type), nodeId, mode);
  }

  return {
    BLOCK_DEFS,
    blockDef,
    pinIndexFor,
    inputPinName,
    nodeHtml,
    describeConfig,
    paletteGroups: paletteGroups(),
    paletteOrder,
  };
}
