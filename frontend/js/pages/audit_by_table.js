// Auto-extracted from frontend/templates/pages/audit_by_table.html.
// Side-effect module: see frontend/js/bootstrap.js import site.
//
// Two original IIFEs:
//   1) form picker submit handler (#bytable-picker)
//   2) per-kind tab loader  — FQN + KINDS used to be Jinja-injected
//      module consts; now read from a sibling JSON-script-tag
//      ``#bytable-config`` that the template renders unchanged.

function _initPicker() {
    const formEl = document.getElementById('bytable-picker');
    if (!formEl) return;
    const inputEl = document.getElementById('bytable-fqn');
    formEl.addEventListener('submit', (ev) => {
        ev.preventDefault();
        const fqn = inputEl.value.trim();
        if (!fqn) return;
        window.location.assign('/audit/by-table/' + encodeURI(fqn));
    });
}

function _initTabs() {
    const cfgEl = document.getElementById('bytable-config');
    if (!cfgEl) return;
    let cfg;
    try {
        cfg = JSON.parse(cfgEl.textContent || '{}');
    } catch (_e) {
        return;
    }
    const FQN = cfg.fqn;
    const KINDS = cfg.kinds || [];
    if (!FQN || KINDS.length === 0) return;

    const loaded = new Set();

    function escapeHtml(text) {
        if (text === null || text === undefined) return '';
        return String(text).replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[c]);
    }

    function severityBadge(sev) {
        if (!sev) return '<span class="text-muted small">—</span>';
        if (sev === 'critical') return '<span class="badge bg-danger">critical</span>';
        if (sev === 'warn') return '<span class="badge bg-warning text-dark">warn</span>';
        return '<span class="badge bg-secondary-subtle text-secondary-emphasis">ok</span>';
    }

    async function loadKind(kind) {
        const rowsEl = document.getElementById(`bytable-${kind}-rows`);
        const metaEl = document.getElementById(`bytable-${kind}-meta`);
        const params = new URLSearchParams({fqn: FQN, kind: kind, limit: '200'});
        const resp = await fetch('/api/audit/by-table?' + params.toString(), { credentials: 'same-origin' });
        if (!resp.ok) {
            metaEl.textContent = `Error ${resp.status}`;
            rowsEl.innerHTML = `<tr><td colspan="5" class="text-danger py-3">Error ${resp.status}</td></tr>`;
            return;
        }
        const data = await resp.json();
        metaEl.textContent = `${data.row_count} run(s) ${kind} ${escapeHtml(data.fqn)}`;
        if (!data.runs.length) {
            rowsEl.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-4">No runs ${escapeHtml(kind)} this table.</td></tr>`;
            return;
        }
        rowsEl.innerHTML = data.runs.map((run) => {
            return `<tr>
                <td data-label="ID"><a href="/runs/${encodeURIComponent(run.id)}" class="font-monospace small text-decoration-none">${escapeHtml(run.id.slice(0, 8))}</a></td>
                <td data-label="Principal" class="font-monospace small">${escapeHtml(run.principal || '—')}</td>
                <td data-label="Status"><span class="badge bg-secondary">${escapeHtml(run.status)}</span></td>
                <td data-label="Anomaly">${severityBadge(run.anomaly_severity)}</td>
                <td data-label="Started" class="font-monospace small text-muted">${escapeHtml(run.started_at || '—')}</td>
            </tr>`;
        }).join('');
    }

    function activateKind(kind) {
        if (loaded.has(kind)) return;
        loaded.add(kind);
        loadKind(kind);
    }

    document.querySelectorAll('#bytableTabs .nav-link').forEach((btn) => {
        btn.addEventListener('shown.bs.tab', () => activateKind(btn.dataset.kind));
    });
    activateKind(KINDS[0]);
}

function _init() {
    _initPicker();
    _initTabs();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init, { once: true });
} else {
    _init();
}
