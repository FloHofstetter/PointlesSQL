/**
 * Side-panel state helpers consumed by the run-detail Lineage
 * Graph sub-tab template.
 *
 * The Alpine factory in :mod:`./factory.js` calls into these
 * functions whenever the user changes the side-panel selection
 * (clicked an edge, clicked a column inside the edge's column-
 * pair list, or clicked outside to clear).  Each helper returns
 * the next state delta that the factory applies to ``this``.
 */

import { clearHighlight, highlightColumn } from './highlights.js';

/**
 * Look up the edge object backing the currently-selected id.
 *
 * @param {Array<object>} edges - the run's edge payload.
 * @param {string|null} selectedEdgeId
 * @returns {object|null}
 */
export function findSelectedEdge(edges, selectedEdgeId) {
  if (!selectedEdgeId) return null;
  return edges.find((e) => e.id === selectedEdgeId) || null;
}

/**
 * Mark ``column`` as selected and highlight every edge that
 * carries it.
 *
 * @param {object} cy - cytoscape instance.
 * @param {Array<object>} edges
 * @param {string} column
 * @returns {{column: string, direction: 'both'}}
 */
export function selectColumn(cy, edges, column) {
  highlightColumn(cy, edges, column);
  return { column, direction: 'both' };
}

/**
 * Reset the side-panel state and the canvas highlight together.
 *
 * @param {object} cy
 * @returns {{selectedEdgeId: null, selectedColumn: null}}
 */
export function clearSelection(cy) {
  clearHighlight(cy);
  return { selectedEdgeId: null, selectedColumn: null };
}
