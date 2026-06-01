/*
 * Shared Drawflow loader for the canvas editor + diff page.
 *
 * Both pages mount the same DP canvas DAG into Drawflow but for very
 * different purposes — the editor is read-write, the diff page is two
 * read-only side-by-side surfaces.  Extracted here so the diff page
 * does not need to inline a second copy of the node-add / connect
 * dance the editor already owns.
 */

const PIN_NAMES_IN = ['in', 'left', 'right'];

const BLOCK_LABELS = {
  InputPort: { label: 'Input port', icon: 'bi-box-arrow-in-right', inputs: 0, outputs: 1 },
  DataProduct: { label: 'Data product ◫', icon: 'bi-box-seam', inputs: 0, outputs: 1 },
  Filter: { label: 'Filter', icon: 'bi-funnel', inputs: 1, outputs: 1 },
  Project: { label: 'Project', icon: 'bi-columns-gap', inputs: 1, outputs: 1 },
  Join: { label: 'Join', icon: 'bi-link-45deg', inputs: 2, outputs: 1 },
  GroupBy: { label: 'Group by', icon: 'bi-stack', inputs: 1, outputs: 1 },
  Limit: { label: 'Limit', icon: 'bi-arrow-down-square', inputs: 1, outputs: 1 },
  SQL: { label: 'Raw SQL', icon: 'bi-braces-asterisk', inputs: 1, outputs: 1 },
  Window: { label: 'Window', icon: 'bi-graph-up', inputs: 1, outputs: 1 },
  Pivot: { label: 'Pivot', icon: 'bi-arrow-90deg-right', inputs: 1, outputs: 1 },
  Unpivot: { label: 'Unpivot', icon: 'bi-arrow-90deg-down', inputs: 1, outputs: 1 },
  Union: { label: 'Union', icon: 'bi-share', inputs: 2, outputs: 1 },
  Distinct: { label: 'Distinct', icon: 'bi-filter-square', inputs: 1, outputs: 1 },
  Sort: { label: 'Sort', icon: 'bi-sort-down', inputs: 1, outputs: 1 },
  Sample: { label: 'Sample', icon: 'bi-droplet-half', inputs: 1, outputs: 1 },
  Cast: { label: 'Cast', icon: 'bi-arrow-repeat', inputs: 1, outputs: 1 },
  Rename: { label: 'Rename', icon: 'bi-tag', inputs: 1, outputs: 1 },
  CalcColumn: { label: 'Calc column', icon: 'bi-calculator', inputs: 1, outputs: 1 },
  OutputPort: { label: 'Output port', icon: 'bi-box-arrow-up-right', inputs: 1, outputs: 0 },
};

function nodeHtml(blockType, nodeId, mode = 'full') {
  const def = BLOCK_LABELS[blockType] || { label: blockType, icon: 'bi-question-square' };
  if (mode === 'compact') {
    // Compact reads as a single horizontal strip — header only with the
    // block type as a side-note.  Used by the diff page so a side-by-
    // side comparison fits more blocks per panel without each one
    // pulling its full schema body.
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

function pinIndex(blockType, pinName, direction) {
  if (direction === 'in' && (blockType === 'Join' || blockType === 'Union')) {
    return pinName === 'right' ? 1 : 0;
  }
  return 0;
}

// Minimum horizontal stub a wire keeps before it starts to curve, so a
// connection always leaves the output and enters the input horizontally
// even when the two pins sit close together, stacked vertically, or the
// target is to the left of the source.  ``CURVE_K`` scales the control
// offset with the span so distant nodes still bow gracefully.
const MIN_STUB = 40;
const CURVE_K = 0.5;

/**
 * Replace Drawflow's connection-path generator with a smoother one.
 *
 * Drawflow's native ``createCurvature`` offsets the bezier control points
 * by ``|dx| * curvature`` — that magnitude collapses to nothing when two
 * nodes are close, vertically stacked, or the target sits left of the
 * source, leaving a kinked near-straight line.  This drop-in keeps the
 * same method signature but floors the control offset so the wire is
 * smooth at every geometry, and treats ``curvature === 0`` as a request
 * for true right-angle step routing (the "Orthogonal" toolbar toggle)
 * rather than a degenerate diagonal.
 *
 * Idempotent: guarded on a flag set on the constructor function object so
 * the three surfaces that share one ``window.Drawflow`` only patch once.
 * The patch lives on the prototype and is read live on every
 * ``updateConnection`` / ``updateConnectionNodes`` call, so it applies to
 * already-instantiated editors on their next path recompute.
 *
 * @param {Function} Drawflow - the Drawflow constructor (``window.Drawflow``).
 */
export function installSmoothCurvature(Drawflow) {
  if (!Drawflow || Drawflow.__pqlSmoothCurvature) return;
  Drawflow.__pqlSmoothCurvature = true;

  Drawflow.prototype.createCurvature = function (
    start_pos_x,
    start_pos_y,
    end_pos_x,
    end_pos_y,
    curvature_value,
    type
  ) {
    const sx = start_pos_x;
    const sy = start_pos_y;
    const ex = end_pos_x;
    const ey = end_pos_y;

    // Orthogonal / step routing.  Only the main node-to-node connection is
    // drawn with curvature 0 (via the toolbar toggle); reroute waypoint
    // segments keep their own non-zero curvature and fall through to the
    // smooth branch below.
    const isMain = type === 'openclose' || type === undefined || type === 'default';
    if (curvature_value === 0 && isMain) {
      if (ex >= sx) {
        const midX = sx + (ex - sx) / 2;
        return ` M ${sx} ${sy} L ${midX} ${sy} L ${midX} ${ey} L ${ex} ${ey}`;
      }
      // Target left of source — stub out of both pins and route around via
      // the vertical midpoint so the wire never doubles back into a node.
      const sStub = sx + MIN_STUB;
      const eStub = ex - MIN_STUB;
      const midY = sy + (ey - sy) / 2;
      return (
        ` M ${sx} ${sy} L ${sStub} ${sy} L ${sStub} ${midY}` +
        ` L ${eStub} ${midY} L ${eStub} ${ey} L ${ex} ${ey}`
      );
    }

    // Smooth horizontal cubic bezier with a floored control offset.
    const dx = ex - sx;
    const dy = ey - sy;
    const off = Math.max(Math.abs(dx) * CURVE_K, MIN_STUB, Math.abs(dy) * CURVE_K);

    // Reroute segments preserve Drawflow's per-type control-point sign
    // pattern (open / close / other); only the magnitude is swapped to the
    // floored offset so reroute waypoints don't render with the old
    // collapsing formula.
    let hx1;
    let hx2;
    switch (type) {
      case 'open':
        hx1 = sx + off;
        hx2 = sx >= ex ? ex + off : ex - off;
        break;
      case 'close':
        hx1 = sx >= ex ? sx - off : sx + off;
        hx2 = ex - off;
        break;
      case 'other':
        hx1 = sx >= ex ? sx - off : sx + off;
        hx2 = sx >= ex ? ex + off : ex - off;
        break;
      default:
        hx1 = sx + off;
        hx2 = ex - off;
    }
    return ` M ${sx} ${sy} C ${hx1} ${sy} ${hx2} ${ey} ${ex} ${ey}`;
  };
}

/**
 * Render `doc` into a Drawflow editor instance.  Returns a map of
 * `{pqlNodeId: drawflowId}` so callers can layer per-node CSS overlays
 * after the load completes.
 */
export function loadCanvasIntoDrawflow(df, doc, opts = {}) {
  const mode = opts.mode || 'full';
  df.clear();
  const drawflowIds = {};
  for (const node of doc.nodes || []) {
    const def = BLOCK_LABELS[node.block_type];
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
      nodeHtml(node.block_type, node.id, mode),
      false
    );
    drawflowIds[node.id] = dfId;
  }
  for (const edge of doc.edges || []) {
    const sourceDf = drawflowIds[edge.source_node_id];
    const targetDf = drawflowIds[edge.target_node_id];
    if (!sourceDf || !targetDf) continue;
    const targetNode = (doc.nodes || []).find((n) => n.id === edge.target_node_id);
    const targetIdx = pinIndex(targetNode ? targetNode.block_type : '', edge.target_pin, 'in');
    try {
      df.addConnection(sourceDf, targetDf, 'output_1', `input_${targetIdx + 1}`);
    } catch (_e) {
      // Edge target invalid; skip.
    }
  }
  return drawflowIds;
}

export { BLOCK_LABELS, nodeHtml, PIN_NAMES_IN, pinIndex };
