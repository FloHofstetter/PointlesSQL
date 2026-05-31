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
