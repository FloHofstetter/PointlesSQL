// Auto-extracted from frontend/templates/pages/agent_run_compare.html.
// Side-effect module: see frontend/js/bootstrap.js import site.
//
// Page-local IIFE — bare side-effect module imported via bootstrap.js.
// Wrapped in DOMContentLoaded so DOM lookups inside resolve.

function _init() {
  (() => {
    const payloadEl = document.getElementById('lineage-diff-payload');
    if (!payloadEl) return;
    const payload = JSON.parse(payloadEl.textContent);

    // Chart.js needs the canvas
    // to have non-zero dimensions at construction time.  Bootstrap
    // tab-panes are display:none until activated, so a render fired
    // on page-load against a hidden canvas produces an empty chart
    // that never recovers.  Render lazily on the first `shown.bs.tab`
    // event for each tab; the active-on-load tab gets rendered
    // once on DOMContentLoaded.
    function renderBars(canvasId, shift, badWhenUp) {
      const canvas = document.getElementById(canvasId);
      if (!canvas || !window.Chart) return;
      if (canvas.dataset.rendered === '1') return;
      const labels = Object.keys(shift.delta);
      if (labels.length === 0) {
        canvas.parentElement.innerHTML =
          '<div class="text-muted small fst-italic">No data on either side.</div>';
        canvas.dataset.rendered = '1';
        return;
      }
      new window.Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'A',
              data: labels.map((k) => shift.a[k] || 0),
              backgroundColor: 'rgba(108,117,125,0.6)',
            },
            {
              label: 'B',
              data: labels.map((k) => shift.b[k] || 0),
              backgroundColor: badWhenUp ? 'rgba(220,53,69,0.6)' : 'rgba(13,110,253,0.6)',
            },
          ],
        },
        options: {
          responsive: true,
          plugins: {
            legend: { position: 'top' },
          },
          scales: { y: { beginAtZero: true } },
        },
      });
      canvas.dataset.rendered = '1';
    }

    function renderForTab(targetSelector) {
      if (targetSelector === '#tab-lineage') {
        renderBars('chart-value-changes', payload.value_change_volume_per_table, false);
        renderBars('chart-rows', payload.row_count_delta_per_table, false);
      } else if (targetSelector === '#tab-rejects') {
        renderBars('chart-rejects', payload.reject_pattern_shift, true);
      }
    }

    // 1. Render whatever tab is active on page load (Operations
    //    by default — no charts there — but operators can deep-link
    //    to the Lineage tab via #tab-lineage in the URL).
    document.querySelectorAll('.tab-pane.active').forEach((pane) => {
      renderForTab('#' + pane.id);
    });

    // 2. Render lazily on first activation of each charted tab.
    document.querySelectorAll('button[data-bs-toggle="tab"]').forEach((btn) => {
      btn.addEventListener('shown.bs.tab', (event) => {
        renderForTab(event.target.getAttribute('data-bs-target'));
      });
    });
  })();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _init, { once: true });
} else {
  _init();
}

// htmx-boosted navigation swaps in fresh DOM without re-running this eager
// module, so the lineage diff would not render after an in-app navigation.
// Re-run on every swap; the init guards on its payload element and no-ops
// when it is absent.
document.addEventListener('htmx:afterSwap', () => _init());
