/*
 * DataFrame Studio block catalog — the data-product catalog minus sinks.
 *
 * The Studio reuses the exact dataframe block taxonomy the data-product
 * editor ships, with the sink (OutputPort / FileOutput) and data-product
 * drill-in (DataProduct) blocks removed: the Studio never materialises and
 * is not data-product-scoped — its terminal is "the node you point at".
 *
 * Reusing ``DP_CATALOG`` keeps every lookup (blockDef / pinIndexFor /
 * nodeHtml / describeConfig) identical to the DP editor; only ``BLOCK_DEFS``
 * and the palette are filtered.
 */

import { DP_CATALOG } from '../dp_canvas/_block_catalog.js';

const DISALLOWED = new Set(['OutputPort', 'FileOutput', 'DataProduct']);

/**
 * Build the Studio catalog: ``DP_CATALOG`` with sink / DP blocks removed
 * from ``BLOCK_DEFS`` and the palette.
 *
 * @returns {Object} A catalog for ``assembleCanvasEditor``.
 */
export function buildStudioCatalog() {
  const BLOCK_DEFS = {};
  for (const [type, def] of Object.entries(DP_CATALOG.BLOCK_DEFS)) {
    if (!DISALLOWED.has(type)) BLOCK_DEFS[type] = def;
  }
  const paletteGroups = {};
  for (const [group, kinds] of Object.entries(DP_CATALOG.paletteGroups)) {
    const filtered = kinds.filter((k) => !DISALLOWED.has(k));
    if (filtered.length) paletteGroups[group] = filtered;
  }
  return { ...DP_CATALOG, BLOCK_DEFS, paletteGroups };
}
