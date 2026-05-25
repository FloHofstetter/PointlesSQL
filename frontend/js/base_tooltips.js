/**
 * Auto-initialise Bootstrap tooltips.
 *
 * Any element carrying ``data-bs-toggle="tooltip"`` gets a
 * ``new bootstrap.Tooltip(el)`` on first paint, plus an
 * ``htmx:afterSwap`` re-init so tooltips on swapped HTML
 * (#main-content) still work. The ``data-bs-tooltip-init`` marker
 * prevents double-init when a partial swap re-visits a node that
 * already has a Tooltip instance attached.
 *
 * Side-effect module imported once from ``bootstrap.js``.
 */

(() => {
  function initTooltips(root) {
    (root || document)
      .querySelectorAll('[data-bs-toggle="tooltip"]:not([data-bs-tooltip-init])')
      .forEach((el) => {
        try {
          new bootstrap.Tooltip(el);
          el.setAttribute('data-bs-tooltip-init', '1');
        } catch (_) {
          /* Bootstrap missing on auth pages */
        }
      });
  }
  document.addEventListener('DOMContentLoaded', () => initTooltips());
  document.body.addEventListener('htmx:afterSwap', (e) => {
    initTooltips(e.target);
  });
})();
