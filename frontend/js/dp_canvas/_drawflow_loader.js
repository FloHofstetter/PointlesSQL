/*
 * Shared Drawflow loader for the canvas editor + diff page.
 *
 * Both pages mount the same DP canvas DAG into Drawflow but for very
 * different purposes — the editor is read-write, the diff page is two
 * read-only side-by-side surfaces.  Extracted here so the diff page
 * does not need to inline a second copy of the node-add / connect
 * dance the editor already owns.
 */

import { BLOCK_DEFS, nodeHtml, pinIndexFor } from './_block_catalog.js';

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
    const targetIdx = pinIndexFor(targetNode ? targetNode.block_type : '', edge.target_pin, 'in');
    try {
      df.addConnection(sourceDf, targetDf, 'output_1', `input_${targetIdx + 1}`);
    } catch (_e) {
      // Edge target invalid; skip.
    }
  }
  return drawflowIds;
}
