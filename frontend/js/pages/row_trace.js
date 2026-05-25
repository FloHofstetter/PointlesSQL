// Row-trace page (/lineage/row-trace/...).
//
// ``rowAtVersion(table, rowId)`` factory takes table-fqn + row-id as
// constructor args (was Jinja-rendered inside the function body).
// Also exports a side-effect PII-reveal binder that wires the
// "Reveal PII" buttons on the same page.

export function rowAtVersion(table, rowId) {
  return {
    table,
    rowId,
    version: null,
    loading: false,
    error: null,
    result: null,
    async lookup() {
      if (this.version === null || this.version === '') return;
      this.loading = true;
      this.error = null;
      this.result = null;
      try {
        const url = `/api/lineage/row-at-version?table=${encodeURIComponent(this.table)}&row_id=${encodeURIComponent(this.rowId)}&version=${this.version}`;
        const resp = await fetch(url, { headers: { Accept: 'application/json' } });
        const data = await resp.json();
        if (!resp.ok) {
          this.error = data.detail || 'Lookup failed';
        } else {
          this.result = data;
        }
      } catch (err) {
        this.error = err.message || 'Network error';
      } finally {
        this.loading = false;
      }
    },
  };
}

function _csrfToken() {
  const m = document.cookie.match(/(?:^|;\s*)pql_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

function _initPiiReveal() {
  const buttons = document.querySelectorAll('button[data-pii-reveal="1"]');
  if (buttons.length === 0) return;
  buttons.forEach((btn) => {
    btn.addEventListener('click', async () => {
      const cell = btn.closest('li[data-pii-cell="1"]');
      if (!cell) return;
      btn.disabled = true;
      btn.innerHTML = '<i class="bi bi-hourglass-split"></i> revealing…';
      try {
        const resp = await fetch('/api/audit/pii/reveal', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': _csrfToken(),
          },
          body: JSON.stringify({
            run_id: cell.dataset.runId,
            op_id: parseInt(cell.dataset.opId, 10),
            table: cell.dataset.table,
            row_id: cell.dataset.rowId,
            column: cell.dataset.column,
          }),
        });
        if (!resp.ok) {
          btn.innerHTML = '<i class="bi bi-x-circle"></i> ' + resp.status;
          return;
        }
        const body = await resp.json();
        const oldEl = cell.querySelector('.pii-old');
        const newEl = cell.querySelector('.pii-new');
        if (oldEl && body.old_value !== null && body.old_value !== undefined) {
          oldEl.textContent = body.old_value;
          oldEl.classList.add('text-warning-emphasis');
        }
        if (newEl && body.new_value !== null && body.new_value !== undefined) {
          newEl.textContent = body.new_value;
          newEl.classList.add('text-warning-emphasis');
        }
        btn.remove();
      } catch (_err) {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-x-circle"></i> error';
      }
    });
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _initPiiReveal, { once: true });
} else {
  _initPiiReveal();
}
