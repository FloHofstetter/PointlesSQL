/**
 * Public surface of the lineage-DAG module bundle.
 *
 * ``bootstrap.js`` imports :func:`lineageDag` from here and
 * re-attaches it to ``window`` so the run-detail Graph sub-tab's
 * ``x-data="lineageDag(...)"`` resolves.  The model-detail page
 * (still an inline script, not on the bootstrap import graph) uses
 * the two ``window``-attached helpers below: ``loadCytoscapeOnce``
 * (lazy script loader) and ``renderModelGraph`` (one-shot render).
 */

import { lineageDag } from './factory.js';
import { loadCytoscapeOnce, renderModelGraph } from './cytoscape_init.js';

if (typeof window !== 'undefined') {
    window.loadCytoscapeOnce = loadCytoscapeOnce;
    window.renderModelGraph = renderModelGraph;
}

export { lineageDag, loadCytoscapeOnce, renderModelGraph };
