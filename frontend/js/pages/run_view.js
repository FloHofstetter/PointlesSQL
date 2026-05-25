// Auto-extracted from frontend/templates/pages/run_view.html.
// Side-effect module: see frontend/js/bootstrap.js import site.
//
// Page-local IIFE — bare side-effect module imported via bootstrap.js.
// Wrapped in DOMContentLoaded so DOM lookups inside resolve.

function _init() {
    // URL-hash to top-tab activation. When the URL
    // carries a sub-pane hash (#tab-lineage, #tab-ops, …) we walk up
    // the DOM to find the parent top-pane and activate the matching
    // top-tab in addition to the sub-tab — Bootstrap's data-bs-toggle
    // handler only activates the leaf, so on its own a deep-link from
    // e.g. an op-row's "column edges" badge would land on a hidden
    // pane. The sub-pane id stays the same as in the pre-17.2 layout
    // so existing badge links keep working.
    (function () {
     function activateForHash() {
     const hash = window.location.hash;
     if (!hash) return;
     const id = hash.slice(1);
     const subPane = document.getElementById(id);
     if (!subPane) return;
     const topPane = subPane.closest('#runDetailTabContent >.tab-pane');
     if (topPane) {
     const topBtn = document.querySelector('[data-bs-target="#' + topPane.id + '"]');
     if (topBtn && window.bootstrap) {
     window.bootstrap.Tab.getOrCreateInstance(topBtn).show();
     }
     }
     const subBtn = document.querySelector('[data-bs-target="' + hash + '"]');
     if (subBtn && window.bootstrap) {
     window.bootstrap.Tab.getOrCreateInstance(subBtn).show();
     }
     }
     if (document.readyState === 'loading') {
     document.addEventListener('DOMContentLoaded', activateForHash);
     } else {
     activateForHash();
     }
     window.addEventListener('hashchange', activateForHash);
    })();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init, { once: true });
} else {
    _init();
}
