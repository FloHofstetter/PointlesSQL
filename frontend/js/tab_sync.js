// Bootstrap-tab URL-state sync.
//
// On DOMContentLoaded:
//   1. Read ``?tab=<key>`` and ``?subtab=<key>`` from the URL.
//   2. Activate the matching ``[data-bs-toggle="tab"][data-pql-tab-key=...]``
//      via ``bootstrap.Tab.getOrCreateInstance(el).show()``.  Top-tab
//      first (so the parent tab-pane becomes visible), then sub-tab.
//
// On every ``shown.bs.tab`` event:
//   3. Mirror the active tab back to the URL via
//      ``history.replaceState`` — top-tabs write ``?tab=``, sub-tabs
//      write ``?subtab=``.  Other query params are preserved.
//
// A "sub-tab" is any ``[data-bs-toggle="tab"]`` button whose closest
// ancestor ``.tab-pane`` is non-null.  Top-tabs sit above any
// ``.tab-pane`` ancestor.  Nesting deeper than one level is not
// modelled; PointlesSQL only uses one level of nesting (run-detail
// top-tabs → sub-tabs inside each top-pane).
//
// Idempotent: safe to load on pages without tabs (the listener
// early-returns when no ``[data-pql-tab-key]`` elements exist).
//
// Coexists with the legacy ``window.location.hash``-based logic in
// ``pages/run_view.html`` — that script still fires for old
// ``#tab-foo`` bookmarks.  The two write to separate URL slots
// (hash vs query) so they don't fight.

function isSubTab(btn) {
  return btn.closest('.tab-pane') !== null;
}

function pageTypeKey() {
  // ``<main data-active-page="...">`` carries a stable page-type
  // identifier set by base.html (catalog, models, table-detail,
  // run-detail, …).  Without it tab-persistence is a no-op.
  const main = document.getElementById('main-content');
  return main ? main.dataset.activePage || '' : '';
}

function storageKey() {
  const key = pageTypeKey();
  return key ? 'pql:tab:' + key : null;
}

function readStoredTabs() {
  const k = storageKey();
  if (!k) return null;
  try {
    const raw = localStorage.getItem(k);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (e) {
    return null;
  }
}

function writeStoredTabs(patch) {
  const k = storageKey();
  if (!k) return;
  try {
    const current = readStoredTabs() || {};
    const next = { ...current, ...patch };
    localStorage.setItem(k, JSON.stringify(next));
  } catch (e) {}
}

function activateOnLoad() {
  if (!window.bootstrap || !window.bootstrap.Tab) return;
  const params = new URLSearchParams(window.location.search);
  let topKey = params.get('tab');
  let subKey = params.get('subtab');

  // Fallback to localStorage when URL has no tab params — restores
  // the last-active tab for this page-type across cold navigations.
  if (!topKey && !subKey) {
    const stored = readStoredTabs();
    if (stored) {
      topKey = stored.top || null;
      subKey = stored.sub || null;
    }
  }
  if (!topKey && !subKey) return;

  const Tab = window.bootstrap.Tab;
  const all = Array.from(document.querySelectorAll('[data-bs-toggle="tab"][data-pql-tab-key]'));
  if (!all.length) return;

  if (topKey) {
    const top = all.find((el) => el.dataset.pqlTabKey === topKey && !isSubTab(el));
    if (top) Tab.getOrCreateInstance(top).show();
  }
  if (subKey) {
    const sub = all.find((el) => el.dataset.pqlTabKey === subKey && isSubTab(el));
    if (sub) Tab.getOrCreateInstance(sub).show();
  }
}

function mirrorToUrl(event) {
  const btn = event.target;
  if (!btn || !btn.dataset || !btn.dataset.pqlTabKey) return;
  const params = new URLSearchParams(window.location.search);
  if (isSubTab(btn)) {
    params.set('subtab', btn.dataset.pqlTabKey);
    writeStoredTabs({ sub: btn.dataset.pqlTabKey });
  } else {
    params.set('tab', btn.dataset.pqlTabKey);
    writeStoredTabs({ top: btn.dataset.pqlTabKey });
    // Clearing subtab on top-tab change would clobber a fresh
    // ``?tab=X&subtab=Y`` deep-link: Bootstrap fires
    // ``shown.bs.tab`` for the top-tab milliseconds before the
    // sub-tab event during initial activation.  Letting the
    // sub-tab event re-set ``subtab`` immediately after keeps
    // the URL coherent.
  }
  const search = params.toString();
  const newUrl = window.location.pathname + (search ? '?' + search : '') + window.location.hash;
  history.replaceState(history.state, '', newUrl);
}

function init() {
  activateOnLoad();
  document.addEventListener('shown.bs.tab', mirrorToUrl);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init, { once: true });
} else {
  init();
}
