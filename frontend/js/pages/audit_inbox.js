// Anomaly-inbox page wiring for /audit/inbox.
//
// Bare side-effect module: imported (and so evaluated) on every page
// via bootstrap.js.  Bails out cheaply on pages without the
// ``#inbox-filter`` form so the cost on unrelated pages is one
// ``getElementById`` lookup.

function _init() {
  const formEl = document.getElementById('inbox-filter');
  if (!formEl) return;

  const sevEl = document.getElementById('inbox-severity');
  const metricEl = document.getElementById('inbox-metric');
  const binEl = document.getElementById('inbox-bin');
  const sinceEl = document.getElementById('inbox-since');
  const tableEl = document.getElementById('inbox-table');
  const includeAckedEl = document.getElementById('inbox-include-acked');
  const rowsEl = document.getElementById('inbox-rows');
  const metaEl = document.getElementById('inbox-meta');
  const selectAllEl = document.getElementById('inbox-select-all');
  const bulkBarEl = document.getElementById('inbox-bulk-bar');
  const bulkCountEl = document.getElementById('inbox-bulk-count');
  const bulkClearBtn = document.getElementById('inbox-bulk-clear');
  const bulkAckBtn = document.getElementById('inbox-bulk-ack');

  const selected = new Map();
  let lastAnomalies = [];

  function rowKey(a) {
    return a.metric + '|' + a.bin_kind + '|' + a.bin_iso;
  }

  function ackableAnomalies() {
    return lastAnomalies.filter((a) => !a.ack);
  }

  function syncBulkBar() {
    const n = selected.size;
    bulkCountEl.textContent = String(n);
    bulkBarEl.classList.toggle('d-none', n === 0);
    bulkBarEl.classList.toggle('d-flex', n > 0);
    const ackable = ackableAnomalies();
    selectAllEl.checked = ackable.length > 0 && ackable.every((a) => selected.has(rowKey(a)));
    selectAllEl.indeterminate = n > 0 && !selectAllEl.checked;
  }

  function clearSelection() {
    selected.clear();
    rowsEl.querySelectorAll('input[data-anomaly-key]').forEach((cb) => {
      cb.checked = false;
    });
    syncBulkBar();
  }

  function severityBadge(sev) {
    const cls =
      sev === 'critical' ? 'bg-danger' : sev === 'warn' ? 'bg-warning text-dark' : 'bg-secondary';
    return `<span class="badge ${cls}">${sev}</span>`;
  }

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

  async function loadInbox() {
    const params = new URLSearchParams();
    params.set('severity', sevEl.value);
    if (metricEl.value) params.set('metric', metricEl.value);
    params.set('bin', binEl.value);
    if (sinceEl.value.trim()) params.set('since', sinceEl.value.trim());
    if (tableEl.value.trim()) params.set('table', tableEl.value.trim());
    if (includeAckedEl.checked) params.set('include_acked', 'true');
    rowsEl.innerHTML =
      '<tr><td colspan="9" class="py-3"><div class="placeholder-glow" aria-hidden="true"><div class="placeholder col-7 mb-2"></div><div class="placeholder col-9 mb-2"></div><div class="placeholder col-5"></div></div></td></tr>';
    const resp = await fetch('/api/audit/inbox?' + params.toString(), {
      credentials: 'same-origin',
    });
    if (!resp.ok) {
      rowsEl.innerHTML = `<tr><td colspan="9" class="text-danger py-3">Error ${resp.status}</td></tr>`;
      metaEl.textContent = '';
      return;
    }
    const data = await resp.json();
    lastAnomalies = data.anomalies || [];
    clearSelection();
    metaEl.textContent = `${data.anomalies.length} of ${data.total_count} breach(es) — metrics ${data.metrics.join(', ')}, ${data.window_days}d baseline at ${data.threshold_sigma}σ`;
    if (!data.anomalies.length) {
      rowsEl.innerHTML =
        '<tr><td colspan="9" class="text-center text-muted py-4">No active anomalies for the chosen filters.</td></tr>';
      return;
    }
    rowsEl.innerHTML = data.anomalies
      .map((a) => {
        const ackCell = a.ack
          ? `<span class="text-muted small">acked by ${escapeHtml(a.ack.acked_by)}${a.ack.dismissed_until ? ' until ' + escapeHtml(a.ack.dismissed_until.slice(0, 16)) : ''}</span>`
          : '<span class="text-muted small">—</span>';
        const actionCell = a.ack
          ? `<button class="btn btn-sm btn-outline-secondary" data-action="unack" data-ack-id="${a.ack.id}"><i class="bi bi-arrow-counterclockwise me-1"></i>Unacknowledge</button>`
          : `<button class="btn btn-sm btn-primary" data-action="ack" data-metric="${escapeHtml(a.metric)}" data-bin-iso="${escapeHtml(a.bin_iso)}" data-bin-kind="${escapeHtml(a.bin_kind)}"><i class="bi bi-check2 me-1"></i>Acknowledge</button>`;
        const checkboxCell = a.ack
          ? '<td></td>'
          : `<td><input type="checkbox" class="form-check-input" data-anomaly-key="${escapeHtml(rowKey(a))}" data-metric="${escapeHtml(a.metric)}" data-bin-iso="${escapeHtml(a.bin_iso)}" data-bin-kind="${escapeHtml(a.bin_kind)}" aria-label="Select anomaly"></td>`;
        return `<tr>
                ${checkboxCell}
                <td>${severityBadge(a.severity)}</td>
                <td class="font-monospace small">${escapeHtml(a.metric)}</td>
                <td class="font-monospace small">${escapeHtml(a.bin_iso)}</td>
                <td class="text-end font-monospace small">${a.observed}</td>
                <td class="text-end font-monospace small text-muted">${a.baseline_mean}</td>
                <td class="text-end font-monospace small text-muted">${a.sigma}</td>
                <td>${ackCell}</td>
                <td>${actionCell}</td>
            </tr>`;
      })
      .join('');
    syncBulkBar();
  }

  rowsEl.addEventListener('change', (ev) => {
    const cb = ev.target.closest('input[data-anomaly-key]');
    if (!cb) return;
    const key = cb.dataset.anomalyKey;
    if (cb.checked) {
      selected.set(key, {
        metric: cb.dataset.metric,
        bin_iso: cb.dataset.binIso,
        bin_kind: cb.dataset.binKind,
      });
    } else {
      selected.delete(key);
    }
    syncBulkBar();
  });

  selectAllEl.addEventListener('change', () => {
    const ackable = ackableAnomalies();
    if (selectAllEl.checked) {
      ackable.forEach((a) => {
        selected.set(rowKey(a), {
          metric: a.metric,
          bin_iso: a.bin_iso,
          bin_kind: a.bin_kind,
        });
      });
    } else {
      selected.clear();
    }
    rowsEl.querySelectorAll('input[data-anomaly-key]').forEach((cb) => {
      cb.checked = selected.has(cb.dataset.anomalyKey);
    });
    syncBulkBar();
  });

  bulkClearBtn.addEventListener('click', () => clearSelection());

  bulkAckBtn.addEventListener('click', async () => {
    if (selected.size === 0) return;
    const comment = prompt(
      'Optional ack comment for all ' + selected.size + ' (leave blank for none)'
    );
    bulkAckBtn.disabled = true;
    let failed = 0;
    const entries = Array.from(selected.values());
    await Promise.all(
      entries.map(async (e) => {
        const body = { metric: e.metric, bin_iso: e.bin_iso, bin_kind: e.bin_kind };
        if (comment) body.comment = comment;
        const r = await fetch('/api/audit/anomaly-acks', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!r.ok) failed++;
      })
    );
    bulkAckBtn.disabled = false;
    if (window.pqlToast) {
      if (failed === 0) {
        window.pqlToast.success('Acknowledged ' + entries.length + ' anomalies.');
      } else {
        window.pqlToast.error(failed + ' of ' + entries.length + ' acks failed.');
      }
    }
    clearSelection();
    await loadInbox();
  });

  rowsEl.addEventListener('click', async (ev) => {
    const btn = ev.target.closest('button[data-action]');
    if (!btn) return;
    ev.preventDefault();
    if (btn.dataset.action === 'ack') {
      const comment = prompt('Optional ack comment (leave blank for none)');
      const snooze = prompt('Snooze until (ISO 8601, leave blank for permanent ack)');
      const body = {
        metric: btn.dataset.metric,
        bin_iso: btn.dataset.binIso,
        bin_kind: btn.dataset.binKind,
      };
      if (comment) body.comment = comment;
      if (snooze) body.dismissed_until = snooze;
      const r = await fetch('/api/audit/anomaly-acks', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        alert('Ack failed: ' + r.status);
        return;
      }
      await loadInbox();
    } else if (btn.dataset.action === 'unack') {
      const id = btn.dataset.ackId;
      if (!confirm(`Un-ack #${id}?  The anomaly will reappear in the inbox.`)) return;
      const r = await fetch(`/api/audit/anomaly-acks/${id}`, {
        method: 'DELETE',
        credentials: 'same-origin',
      });
      if (!r.ok) {
        alert('Un-ack failed: ' + r.status);
        return;
      }
      await loadInbox();
    }
  });

  formEl.addEventListener('submit', (ev) => {
    ev.preventDefault();
    loadInbox();
  });
  loadInbox();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _init, { once: true });
} else {
  _init();
}
