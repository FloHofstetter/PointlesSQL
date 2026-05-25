/**
 * HTMX bridge wiring for every page.
 *
 * Side-effect module: registering listeners on document.body and
 * setting htmx.config flags. Imported once from ``bootstrap.js`` so
 * the wiring lives in a single place. None of the listeners need to
 * fire before DOMContentLoaded — they observe ``htmx:configRequest``
 * + ``htmx:afterSwap`` + the ``pqlToast`` custom event, all of which
 * are user-triggered or post-swap signals.
 *
 * Wires:
 *  - htmx ``globalViewTransitions = true`` (smooth cross-fade on
 *    boost-swaps; falls back gracefully in non-supporting browsers)
 *  - CSRF token + X-Workspace header auto-attach on every non-safe
 *    htmx verb
 *  - ``syncActiveSection`` after every htmx-boosted nav so the icon
 *    rail's ``.active`` class follows the new ``<main>``'s
 *    ``data-active-section`` / ``data-active-page``
 *  - Server-side ``HX-Trigger: pqlToast`` bridge — htmx dispatches a
 *    DOM event, this listener forwards it to ``window.pqlToast``
 */

if (typeof htmx !== 'undefined') {
 htmx.config.globalViewTransitions = true;
}

(function () {
 const csrfMeta = document.querySelector('meta[name="csrf-token"]');
 const token = csrfMeta ? csrfMeta.content : '';
 const SAFE = new Set(['GET', 'HEAD', 'OPTIONS']);
 document.body.addEventListener('htmx:configRequest', (e) => {
  const verb = (e.detail.verb || '').toUpperCase();
  if (token && !SAFE.has(verb)) {
   e.detail.headers['X-CSRF-Token'] = token;
  }
  const wsMeta = document.querySelector('meta[name="workspace-slug"]');
  const slug = wsMeta ? wsMeta.content : '';
  if (slug) {
   e.detail.headers['X-Workspace'] = slug;
  }
 });
})();

// Alpine 3 has its own MutationObserver that picks up DOM additions
// and initialises any new ``x-data``/``x-init`` automatically; an
// explicit ``Alpine.initTree`` here was a double-init that crashed
// mid-walk with ``TypeError: can't convert undefined to object`` and
// aborted the entire init for the boosted page — surfacing as e.g. a
// blank Preview tab on table-detail. Trust Alpine's observer; do not
// call ``initTree``.

// Sync the icon-rail's ``.active`` class after every HTMX-boosted
// navigation. ``hx-target="#main-content"`` keeps the rail (which
// lives outside main) frozen at whatever the first page render
// produced; this listener reads ``data-active-section`` from the new
// ``<main>`` and applies the matching ``.active`` class to the rail
// link with the same ``data-section``. Same for the offcanvas
// ``nav_links`` rail on mobile if it ever grows the attribute.
function syncActiveSection() {
 const main = document.getElementById('main-content');
 if (!main) return;
 const section = main.dataset.activeSection || '';
 const page = main.dataset.activePage || '';
 document
  .querySelectorAll('.pql-icon-rail__link[data-section]')
  .forEach((link) => {
   // Page-specific entries (ML Models, Agents) opt out of section
   // matching with ``data-active-page``; they highlight only when
   // the page matches.
   const matchPage = link.dataset.activePage || '';
   let active;
   if (matchPage) {
    active = page === matchPage;
   } else {
    // Section-matching entries (Catalog, People) can ALSO exclude
    // specific pages via ``data-exclude-active-page`` so they do
    // not double-light when a page-specific sibling is the real
    // target.
    const exclude = link.dataset.excludeActivePage || '';
    active = link.dataset.section === section
     && (!exclude || page !== exclude);
   }
   link.classList.toggle('active', active);
  });
}
document.body.addEventListener('htmx:afterSwap', syncActiveSection);

// Server-side HX-Trigger toast bridge. Domain errors from a
// non-boosted HTMX request do not swap the DOM (htmx ignores 4xx/5xx
// by default); the server emits an HX-Trigger header carrying a
// ``pqlToast`` payload and htmx dispatches it as a DOM event here. We
// defer the display until pqlToast is defined (toast.js loads after
// htmx.min.js) so the listener is safe to register at any point in
// the script ordering.
document.body.addEventListener('pqlToast', (e) => {
 if (!window.pqlToast) return;
 const data = (e.detail && typeof e.detail === 'object') ? e.detail : {};
 const level = data.level || 'info';
 const fn = window.pqlToast[level] || window.pqlToast.info;
 let message = data.message || '';
 if (data.request_id) {
  message = message
   ? message + ' [req ' + data.request_id + ']'
   : '[req ' + data.request_id + ']';
 }
 fn(message, { timeout: 6000 });
});
