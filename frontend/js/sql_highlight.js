/**
 * SQL syntax-highlighting via highlight.js (Sprint 57.3).
 *
 * Loaded only on `/queries` (page-local include in
 * ``queries.html``).  Scans for ``<pre><code class="language-sql">``
 * elements on initial paint and after every HTMX swap so newly
 * appended Load-More rows pick up colors as well.
 *
 * The ``data-hljs="1"`` flag prevents double-highlighting if the
 * same node ends up re-scanned after a partial swap that re-rendered
 * an already-highlighted ancestor.
 */
function highlightAll(root) {
  if (!root || !root.querySelectorAll) return;
  if (typeof window.hljs === "undefined") return;
  root.querySelectorAll("pre code.language-sql").forEach((el) => {
    if (el.dataset.hljs !== "1") {
      window.hljs.highlightElement(el);
      el.dataset.hljs = "1";
    }
  });
}

document.addEventListener("DOMContentLoaded", () => highlightAll(document));
document.addEventListener("htmx:afterSwap", (ev) => highlightAll(ev.target));
