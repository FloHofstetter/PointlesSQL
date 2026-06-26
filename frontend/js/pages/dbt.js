// dbt cockpit page wiring for /dbt.
//
// Bare side-effect module gated on ``#dbtTabs`` so it is a near-no-op
// on other pages.  Loads summary card + runs tab + failures tab; the
// two tabs lazy-load their tables on the first ``shown.bs.tab`` event.

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  return String(text).replace(
    /[&<>"']/g,
    (c) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[c]
  );
}

function statusBadge(s) {
  const cls =
    s === 'succeeded'
      ? 'bg-success'
      : s === 'failed'
        ? 'bg-danger'
        : s === 'running'
          ? 'bg-info text-dark'
          : 'bg-secondary';
  return `<span class="badge ${cls}">${escapeHtml(s || '—')}</span>`;
}

function severityBadge(sev) {
  if (sev === 'warn') return '<span class="badge bg-warning text-dark">warn</span>';
  return '<span class="badge bg-danger">error</span>';
}

function httpErrorMessage(status, what) {
  if (status === 401) return `Sign in required to view ${what}.`;
  if (status === 403) return `You don't have permission to view ${what}.`;
  if (status === 404) return `${what} not available — no dbt manifest loaded yet.`;
  if (status >= 500) return `Server error (${status}) while loading ${what}. Try refreshing.`;
  return `Couldn't load ${what} (HTTP ${status}).`;
}

async function loadSummary() {
  const elModels = document.getElementById('dbt-summary-models');
  const elModelsHint = document.getElementById('dbt-summary-models-hint');
  const elTests = document.getElementById('dbt-summary-tests');
  const elTestsHint = document.getElementById('dbt-summary-tests-hint');
  const elCov = document.getElementById('dbt-summary-coverage');
  const elCovHint = document.getElementById('dbt-summary-coverage-hint');

  try {
    const r = await fetch('/api/dbt/manifest', { credentials: 'same-origin' });
    if (r.ok) {
      const data = await r.json();
      const manifestModels = (data.models || []).length;
      const totalTests = (data.models || []).reduce((acc, m) => acc + (m.tests || []).length, 0);
      elModels.textContent = String(manifestModels);
      elTests.textContent = String(totalTests);
      if (data.manifest_generated_at) {
        elModelsHint.textContent = 'manifest from ' + data.manifest_generated_at.slice(0, 16);
      }
    } else if (r.status === 404) {
      elModels.textContent = '—';
      elModelsHint.textContent = 'no manifest yet';
      elTests.textContent = '—';
    } else {
      elModelsHint.textContent = 'HTTP ' + r.status;
    }
  } catch (_e) {
    elModelsHint.textContent = 'fetch error';
  }
  // Suppress unused-var lint while keeping the symbol in sight.
  if (elTestsHint && !elTests.textContent) elTestsHint.textContent = '';

  try {
    const r = await fetch('/api/dbt/coverage', { credentials: 'same-origin' });
    if (r.ok) {
      const data = await r.json();
      const ratio = (data.ratio * 100).toFixed(1);
      elCov.textContent = ratio + '%';
      elCovHint.textContent = `${data.models_with_tests}/${data.models_total} tested`;
    } else if (r.status === 404) {
      elCov.textContent = '—';
      elCovHint.textContent = 'no manifest yet';
    } else {
      elCov.textContent = '—';
      elCovHint.textContent = 'HTTP ' + r.status;
    }
  } catch (_e) {
    elCovHint.textContent = 'fetch error';
  }
}

async function loadRuns() {
  const rowsEl = document.getElementById('dbt-runs-rows');
  const metaEl = document.getElementById('dbt-runs-meta');
  try {
    const r = await fetch('/api/dbt/runs?limit=20', { credentials: 'same-origin' });
    if (!r.ok) {
      const msg = httpErrorMessage(r.status, 'recent dbt runs');
      metaEl.textContent = msg;
      rowsEl.innerHTML = `<tr><td colspan="6" class="text-muted py-3">${escapeHtml(msg)}</td></tr>`;
      return;
    }
    const data = await r.json();
    metaEl.textContent = `${data.row_count} recent dbt run(s) — agent_id="dbt-cli"`;
    if (!data.runs.length) {
      rowsEl.innerHTML =
        '<tr><td colspan="6" class="text-center text-muted py-4">No dbt runs yet.  Trigger one via <code>POST /api/dbt/run</code> or via Hermes.</td></tr>';
      return;
    }
    rowsEl.innerHTML = data.runs
      .map(
        (run) => `<tr>
            <td><a href="/runs/${encodeURIComponent(run.id)}" class="font-monospace small text-decoration-none">${escapeHtml(run.id.slice(0, 8))}</a></td>
            <td class="font-monospace small">${escapeHtml(run.principal || '—')}</td>
            <td class="font-monospace small text-muted">${escapeHtml(run.notebook_path || '—')}</td>
            <td>${statusBadge(run.status)}</td>
            <td class="text-end font-monospace small">${run.exit_code === null || run.exit_code === undefined ? '—' : run.exit_code}</td>
            <td class="font-monospace small text-muted">${escapeHtml(run.started_at || '—')}</td>
        </tr>`
      )
      .join('');
  } catch (e) {
    metaEl.textContent = 'fetch error';
    rowsEl.innerHTML = `<tr><td colspan="6" class="text-danger py-3">Fetch error: ${escapeHtml(e.message)}</td></tr>`;
  }
}

async function loadFailures() {
  const rowsEl = document.getElementById('dbt-failures-rows');
  const metaEl = document.getElementById('dbt-failures-meta');
  try {
    const r = await fetch('/api/dbt/test-failures?limit=50', { credentials: 'same-origin' });
    if (!r.ok) {
      const msg = httpErrorMessage(r.status, 'dbt test failures');
      metaEl.textContent = msg;
      rowsEl.innerHTML = `<tr><td colspan="6" class="text-muted py-3">${escapeHtml(msg)}</td></tr>`;
      return;
    }
    const data = await r.json();
    metaEl.textContent = `${data.row_count} recent test failure(s) across all dbt runs`;
    if (!data.rows.length) {
      rowsEl.innerHTML =
        '<tr><td colspan="6" class="text-center text-muted py-4">No dbt test failures recorded.</td></tr>';
      return;
    }
    rowsEl.innerHTML = data.rows
      .map(
        (row) => `<tr>
            <td class="font-monospace small">${escapeHtml(row.test_unique_id || '—')}</td>
            <td class="font-monospace small">${escapeHtml(row.model_relation || '—')}</td>
            <td>${severityBadge(row.severity)}</td>
            <td class="small">${escapeHtml(row.message || '')}</td>
            <td>${row.agent_run_id ? `<a href="/runs/${encodeURIComponent(row.agent_run_id)}" class="font-monospace small text-decoration-none">${escapeHtml(row.agent_run_id.slice(0, 8))}</a>` : '—'}</td>
            <td class="font-monospace small text-muted">${escapeHtml(row.rejected_at || '—')}</td>
        </tr>`
      )
      .join('');
  } catch (e) {
    metaEl.textContent = 'fetch error';
    rowsEl.innerHTML = `<tr><td colspan="6" class="text-danger py-3">Fetch error: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function _init() {
  const tabsEl = document.getElementById('dbtTabs');
  if (!tabsEl) return;

  const loaded = { runs: false, failures: false };
  tabsEl.querySelectorAll('.nav-link[data-tab]').forEach((btn) => {
    btn.addEventListener('shown.bs.tab', () => {
      const tab = btn.dataset.tab;
      if (tab === 'runs' && !loaded.runs) {
        loaded.runs = true;
        loadRuns();
      }
      if (tab === 'failures' && !loaded.failures) {
        loaded.failures = true;
        loadFailures();
      }
    });
  });

  loadSummary();
  loaded.runs = true;
  loadRuns();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _init, { once: true });
} else {
  _init();
}

// htmx-boosted navigation swaps in a fresh ``#dbtTabs`` without re-running the
// module, so the tables would stay stuck on their "Loading…" seed. Re-run
// ``_init`` after each swap; it no-ops when the dbt tabs are absent.
document.addEventListener('htmx:afterSwap', () => _init());
