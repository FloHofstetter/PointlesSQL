/**
 * Click-driven highlight + dim helpers for the run-detail
 * lineage DAG.
 *
 * Pure functions over a cytoscape instance.  Each one removes the
 * existing ``highlighted`` / ``dimmed`` classes first and then
 * applies the new selection set.  Centralising the toggle logic
 * here keeps the Alpine factory thin and the highlight semantics
 * trivially testable.
 */

/**
 * Highlight one edge plus its endpoints; dim everything else.
 *
 * @param {object} cy - cytoscape instance.
 * @param {string} edgeId
 */
export function highlightEdge(cy, edgeId) {
  if (!cy) return;
  cy.elements().removeClass('highlighted dimmed');
  const edge = cy.getElementById(edgeId);
  edge.addClass('highlighted');
  edge.connectedNodes().addClass('highlighted');
  cy.elements().not(edge).not(edge.connectedNodes()).addClass('dimmed');
}

/**
 * Highlight one node, its incident edges, and the nodes those
 * edges connect to (one-hop neighbourhood); dim everything else.
 *
 * @param {object} cy - cytoscape instance.
 * @param {string} nodeId
 */
export function highlightNode(cy, nodeId) {
  if (!cy) return;
  cy.elements().removeClass('highlighted dimmed');
  const node = cy.getElementById(nodeId);
  node.addClass('highlighted');
  node.connectedEdges().addClass('highlighted');
  node.connectedEdges().connectedNodes().addClass('highlighted');
  cy.elements()
    .not(node)
    .not(node.connectedEdges())
    .not(node.connectedEdges().connectedNodes())
    .addClass('dimmed');
}

/**
 * Highlight every edge whose ``column_pairs`` mention ``column``
 * (as either source_column or target_column) plus the endpoints
 * of those edges; dim the rest.  Used when the user clicks a
 * column name in the side panel.
 *
 * @param {object} cy - cytoscape instance.
 * @param {Array<object>} edges - the run's edge payload, each
 *   carrying optional ``column_pairs``.
 * @param {string} column
 */
export function highlightColumn(cy, edges, column) {
  if (!cy) return;
  cy.elements().removeClass('highlighted dimmed');
  const matching = edges.filter((e) =>
    (e.column_pairs || []).some((p) => p.source_column === column || p.target_column === column)
  );
  const matchingIds = new Set(matching.map((e) => e.id));
  const matchingNodeIds = new Set(matching.flatMap((e) => [e.source, e.target]));
  cy.edges().forEach((e) => {
    if (matchingIds.has(e.data('id'))) e.addClass('highlighted');
    else e.addClass('dimmed');
  });
  cy.nodes().forEach((n) => {
    if (matchingNodeIds.has(n.data('id'))) n.addClass('highlighted');
    else n.addClass('dimmed');
  });
}

/**
 * Drop both ``highlighted`` and ``dimmed`` classes from every
 * element, returning the canvas to its initial neutral state.
 *
 * @param {object} cy
 */
export function clearHighlight(cy) {
  if (!cy) return;
  cy.elements().removeClass('highlighted dimmed');
}
