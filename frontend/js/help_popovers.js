// Phase 23 — initialise Bootstrap Popovers for the contextual
// help-icons rendered by frontend/templates/_macros/help_icon.html.
//
// The macro emits ``<button data-bs-toggle="popover"
// data-bs-trigger="focus" …>``.  Trigger=focus means Bootstrap
// dismisses the popover on outside-click + Escape automatically —
// we only need to construct the Popover instances once on page
// load.
//
// Loaded as a non-module ``<script>`` AFTER the Bootstrap bundle
// in base.html (which exposes ``window.bootstrap``).  HTMX boosts
// swap the entire ``.pql-shell`` (icon-rail + context-panel +
// main) so we also re-init on ``htmx:afterSwap`` to cover icons
// rendered into any of those zones — popover instances bound to
// the previous DOM nodes are GC'd along with their elements.
(function () {
    'use strict';

    function initHelpPopovers(root) {
        if (!window.bootstrap || !window.bootstrap.Popover) return;
        const scope = root || document;
        scope.querySelectorAll('[data-bs-toggle="popover"]').forEach(function (el) {
            // Skip elements already wired by an earlier init call.
            if (window.bootstrap.Popover.getInstance(el)) return;
            new window.bootstrap.Popover(el);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initHelpPopovers(document);
        });
    } else {
        initHelpPopovers(document);
    }

    document.body.addEventListener('htmx:afterSwap', function (evt) {
        initHelpPopovers(evt.target || document);
    });
})();
