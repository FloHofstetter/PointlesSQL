// Per-page Alpine entry loader.
//
// Pages opt in via base.html's ``{% block page_entry %}foo.js`` —
// the server renders ``<main id="main-content" data-pql-entry="…"
// x-ignore>``.  This module (imported once by bootstrap.js, so it
// survives hx-boost swaps) dynamically imports the matching module
// from ``/static/js/entries/`` — which registers that page's Alpine
// factories on ``window`` — then lifts ``x-ignore`` and initializes
// the subtree.
//
// Why x-ignore: Alpine walks the DOM once at start and its
// MutationObserver walks every hx-boost-swapped subtree — both can
// run BEFORE a dynamic import resolves, and an ``x-data`` expression
// whose factory isn't on window yet throws.  The server-rendered
// ``x-ignore`` makes Alpine skip the subtree; the loader activates it
// exactly once, after the factories exist.
//
// Covered arrival paths: full load (either ordering of Alpine start
// vs import resolution), hx-boost swap (htmx:afterSwap), and
// back/forward (htmx:historyRestore — restored snapshots saved before
// activation still carry x-ignore; snapshots saved after don't and
// init directly off the already-registered factories).

let alpineStarted = false;
document.addEventListener('alpine:initialized', () => {
  alpineStarted = true;
});

async function activateEntry() {
  const el = document.getElementById('main-content');
  if (!el) return;
  const entry = el.getAttribute('data-pql-entry');
  if (!entry) return;
  try {
    await import(`/static/js/entries/${entry}`);
  } catch (e) {
    console.error(`page entry ${entry} failed to load`, e);
    return;
  }
  if (el.hasAttribute('x-ignore')) {
    el.removeAttribute('x-ignore');
    if (alpineStarted && window.Alpine) {
      delete el._x_ignore;
      window.Alpine.initTree(el);
    }
  }
}

activateEntry();
document.addEventListener('htmx:afterSwap', (ev) => {
  if (ev.target && ev.target.id === 'main-content') activateEntry();
});
document.addEventListener('htmx:historyRestore', () => {
  activateEntry();
});
