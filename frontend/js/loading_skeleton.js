// PointlesSQL — boost-navigation loading skeleton.
//
// HTMX boost stays on the OLD page until the response arrives, so on
// slow links a click into a heavy page feels like nothing happened.
// This module replaces #main-content with a placeholder-glow skeleton
// if the request hasn't returned within MIN_DELAY_MS; HTMX's
// afterSwap then replaces the skeleton with the real content.
//
// Fast navigations (cached, local, < threshold) skip the skeleton
// entirely so there is no jarring flash on quick page swaps.  The
// reference is the notebooks-workspace tree's resting placeholder —
// users told us they like that pattern; this generalises it to every
// boost-driven page navigation.

const MIN_DELAY_MS = 250;

const SKELETON_HTML = `
<div class="container-fluid pt-3 placeholder-glow" aria-hidden="true" data-pql-skeleton="1">
    <div class="placeholder col-3 mb-3" style="height: 1.6rem; border-radius: 4px;"></div>
    <div class="placeholder col-9 mb-2" style="height: 0.9rem; border-radius: 4px;"></div>
    <div class="placeholder col-7 mb-4" style="height: 0.9rem; border-radius: 4px;"></div>
    <div class="row g-3 mb-3">
        <div class="col-12 col-md-6 col-xl-4">
            <div class="placeholder w-100" style="height: 7rem; border-radius: 0.5rem;"></div>
        </div>
        <div class="col-12 col-md-6 col-xl-4">
            <div class="placeholder w-100" style="height: 7rem; border-radius: 0.5rem;"></div>
        </div>
        <div class="col-12 col-md-6 col-xl-4">
            <div class="placeholder w-100" style="height: 7rem; border-radius: 0.5rem;"></div>
        </div>
    </div>
    <div class="placeholder col-12 mb-2" style="height: 0.8rem; border-radius: 4px;"></div>
    <div class="placeholder col-10 mb-2" style="height: 0.8rem; border-radius: 4px;"></div>
    <div class="placeholder col-11 mb-2" style="height: 0.8rem; border-radius: 4px;"></div>
</div>
`;

let pendingTimer = null;

function clearPending() {
  if (pendingTimer !== null) {
    clearTimeout(pendingTimer);
    pendingTimer = null;
  }
}

function paintSkeleton() {
  pendingTimer = null;
  const main = document.getElementById('main-content');
  if (!main) return;
  main.innerHTML = SKELETON_HTML;
}

document.body.addEventListener('htmx:beforeRequest', (ev) => {
  const detail = ev.detail || {};
  const target = detail.target;
  // Only show skeleton when the request actually targets the main
  // content swap zone — never on inline page-level XHR (e.g. the
  // notebook-tree fetch from notebooks_workspace.js).
  if (!target || target.id !== 'main-content') return;
  clearPending();
  pendingTimer = window.setTimeout(paintSkeleton, MIN_DELAY_MS);
});

// Cancel the pending paint as soon as the response is in flight to
// the swap.  htmx:beforeSwap fires before the DOM is replaced; if
// we cleared on htmx:afterSwap instead we would still flash the
// skeleton just before the real content shows up.
document.body.addEventListener('htmx:beforeSwap', clearPending);
document.body.addEventListener('htmx:responseError', clearPending);
document.body.addEventListener('htmx:sendError', clearPending);
document.body.addEventListener('htmx:timeout', clearPending);
