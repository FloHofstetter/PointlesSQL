// Per-page Alpine entry activation for hx-boost swaps.
//
// Pages opt in via base.html's ``{% block page_entry %}foo.js`` —
// frontend/js/entries/foo.js registers that page's Alpine factories
// on ``window``.
//
// Full loads need no JS here: base.html renders the entry as a
// static module <script> BEFORE the Alpine CDN tag, so document
// order guarantees the factories exist when Alpine's initial walk
// runs.  (x-ignore cannot guard that walk — Alpine defers directive
// handlers during start, so the ignore flag lands only after the
// walk already collected the subtree's x-data handlers.)
//
// hx-boost swaps and history restores arrive while Alpine is
// running.  There the server renders ``x-ignore`` on the swapped
// <main> (honoured immediately on the mutation-observer path), and
// the hooks below import the entry — usually a module-cache hit —
// lift the ignore marks, and initialize the subtree exactly once.

async function activateEntry() {
  const el = document.getElementById('main-content');
  if (!el) return;
  const entry = el.getAttribute('data-pql-entry');
  if (!entry) return;
  try {
    await import(`/static/js/entries/${entry}`);
  } catch (e) {
    // Leave x-ignore in place: the subtree stays inert instead of
    // erroring on every x-data expression.
    console.error(`page entry ${entry} failed to load`, e);
    return;
  }
  if (el.hasAttribute('x-ignore')) {
    el.removeAttribute('x-ignore');
    delete el._x_ignore;
    delete el._x_ignoreSelf;
    if (window.Alpine) {
      window.Alpine.initTree(el);
    }
  }
}

document.addEventListener('htmx:afterSwap', (ev) => {
  if (ev.target && ev.target.id === 'main-content') activateEntry();
});
document.addEventListener('htmx:historyRestore', () => {
  activateEntry();
});
