/*
 * Shared canvas helpers — cross-surface utilities for Drawflow.
 *
 * Stateless functions only.  Anything that needs Alpine ``this`` lives
 * on the surface factory (DP editor, mesh editor); helpers here take
 * their inputs as plain arguments so mesh and diff can use them
 * without dragging in DP-editor state shape.
 */

/**
 * Observe a Drawflow root element for live ``transform: ... scale(X)``
 * changes and mirror the current scale into a CSS custom property on
 * ``rootEl`` so zoom-compensated stroke widths track wheel-zoom,
 * programmatic ``df.zoom_in/out/reset``, and any other pathway that
 * mutates the transform.
 *
 * Drawflow 0.0.59 only emits its ``zoom`` event for wheel input, so
 * the legacy ``df.on('zoom', ...)`` hook misses every other entry
 * point.  A style MutationObserver is the only reliable handle on
 * the transform attribute the library actually writes.
 *
 * @param {Element} drawflowEl - the inner ``.drawflow`` element that
 *   carries the live ``style.transform``.
 * @param {Element} rootEl - element to write the ``--pql-zoom``
 *   custom property to (typically the ``.pql-canvas`` host).
 * @param {function} [onChange] - optional callback fired with the new
 *   zoom value after the var is written, useful for repositioning
 *   stage-anchored UI like the mid-edge toolbar or output-plus.
 * @returns {MutationObserver} the observer; caller may ``disconnect()``
 *   it during teardown.
 */
export function installZoomObserver(drawflowEl, rootEl, onChange) {
  if (!drawflowEl || !rootEl || typeof MutationObserver === 'undefined') {
    return null;
  }
  const apply = () => {
    const t = drawflowEl.style.transform || '';
    const m = t.match(/scale\(([\d.]+)\)/);
    const z = m ? parseFloat(m[1]) : 1;
    if (Number.isFinite(z) && z > 0) {
      rootEl.style.setProperty('--pql-zoom', String(z));
      if (typeof onChange === 'function') onChange(z);
    }
  };
  apply();
  const obs = new MutationObserver(apply);
  obs.observe(drawflowEl, { attributes: true, attributeFilter: ['style'] });
  return obs;
}

/**
 * Slide a desired ``(x, y)`` until it no longer overlaps any of the
 * supplied ``others`` rectangles by more than ``maxOverlapRatio``.
 *
 * Used to place sticky-notes and freshly-dropped blocks so they don't
 * land on top of the first node the user already worked on.  Each
 * attempt shifts down+right by ``stepX`` / ``stepY`` until the overlap
 * ratio drops below threshold or ``maxAttempts`` is exhausted, in
 * which case the function returns the original desired position with
 * a ``best-effort`` flag so the caller can decide whether to warn.
 *
 * @param {{x:number, y:number}} desired - starting position.
 * @param {{width:number, height:number}} size - dimensions of the
 *   element we're placing.
 * @param {Array<{x:number, y:number, width:number, height:number}>} others -
 *   bounding rectangles to avoid (in canvas-local coords).
 * @param {object} [opts]
 * @param {number} [opts.stepX=40] - horizontal shift per attempt.
 * @param {number} [opts.stepY=40] - vertical shift per attempt.
 * @param {number} [opts.maxAttempts=8] - cap on attempts.
 * @param {number} [opts.maxOverlapRatio=0.3] - acceptable overlap.
 * @returns {{x:number, y:number, bestEffort:boolean}}
 */
export function findNonOverlappingPosition(desired, size, others, opts = {}) {
  const stepX = opts.stepX ?? 40;
  const stepY = opts.stepY ?? 40;
  const maxAttempts = opts.maxAttempts ?? 8;
  const maxOverlapRatio = opts.maxOverlapRatio ?? 0.3;
  const w = size?.width || 0;
  const h = size?.height || 0;
  const area = w * h || 1;

  const overlapRatio = (px, py) => {
    let worst = 0;
    for (const r of others) {
      if (!r) continue;
      const dx = Math.min(px + w, r.x + r.width) - Math.max(px, r.x);
      const dy = Math.min(py + h, r.y + r.height) - Math.max(py, r.y);
      if (dx > 0 && dy > 0) {
        const ratio = (dx * dy) / area;
        if (ratio > worst) worst = ratio;
      }
    }
    return worst;
  };

  let px = desired.x;
  let py = desired.y;
  for (let i = 0; i < maxAttempts; i++) {
    if (overlapRatio(px, py) <= maxOverlapRatio) {
      return { x: px, y: py, bestEffort: i > 0 };
    }
    px += stepX;
    py += stepY;
  }
  return { x: desired.x, y: desired.y, bestEffort: true };
}

/**
 * Frame a Drawflow graph in its container — fit-to-view zoom plus centring,
 * reading node boxes straight from the rendered DOM so it is agnostic to the
 * surface's model shape.  The zoom is floored (so node bodies stay legible on
 * a wide graph) and a graph too wide to fit at that floor anchors to its
 * top-left rather than centring and clipping both ends — the same behaviour
 * the DP editor's ``fitToView`` applies, so the mesh and editor surfaces frame
 * their graphs consistently.
 *
 * @param {object} df - a started Drawflow instance.
 * @param {object} [opts]
 * @param {number} [opts.pad=60] - viewport padding in px around the graph.
 * @param {number} [opts.minZoom=0.5] - lower bound on the fit zoom.
 */
export function fitDrawflowToView(df, opts = {}) {
  if (!df || !df.container) return;
  const nodeEls = df.container.querySelectorAll('.drawflow-node');
  if (nodeEls.length === 0) return;
  const PAD = opts.pad ?? 60;
  const MIN_ZOOM = opts.minZoom ?? 0.5;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const el of nodeEls) {
    const x0 = el.offsetLeft;
    const y0 = el.offsetTop;
    if (x0 < minX) minX = x0;
    if (y0 < minY) minY = y0;
    if (x0 + el.offsetWidth > maxX) maxX = x0 + el.offsetWidth;
    if (y0 + el.offsetHeight > maxY) maxY = y0 + el.offsetHeight;
  }
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const rect = df.container.getBoundingClientRect();
  const fitW = Math.max(rect.width - PAD * 2, 100);
  const fitH = Math.max(rect.height - PAD * 2, 100);
  const rawZoom = Math.min(fitW / spanX, fitH / spanY, 1);
  const zoom = Math.max(rawZoom, MIN_ZOOM);
  df.zoom = zoom;
  if (zoom > rawZoom + 1e-6) {
    df.canvas_x = PAD - minX * zoom;
    df.canvas_y = PAD - minY * zoom;
  } else {
    df.canvas_x = (rect.width - spanX * zoom) / 2 - minX * zoom;
    df.canvas_y = (rect.height - spanY * zoom) / 2 - minY * zoom;
  }
  if (df.precanvas) {
    df.precanvas.style.transform = `translate(${df.canvas_x}px, ${df.canvas_y}px) scale(${zoom})`;
  }
  // Drawflow computes connection endpoints in a zoom-dependent basis, so a
  // zoom change without a recompute leaves wires pinned to their pre-fit
  // coordinates.  Sweep every node's connections after reframing.
  const home = df.drawflow && df.drawflow.drawflow && df.drawflow.drawflow.Home;
  const data = (home && home.data) || {};
  if (typeof df.updateConnectionNodes === 'function') {
    for (const id of Object.keys(data)) df.updateConnectionNodes(`node-${id}`);
  }
}
