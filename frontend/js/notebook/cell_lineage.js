/**
 * Per-cell lineage badges.
 *
 * The backend ships ``GET /api/notebooks/cell/lineage`` (per-cell)
 * and ``/api/notebooks/cell/lineage/bulk`` (whole notebook in one
 * call).  The cell-header chip strip uses the bulk variant so a
 * 50-cell notebook costs one HTTP request instead of 50.
 *
 * Same nested-x-data dodge as :func:`installNotebookTags` and
 * :func:`installCellAuthorship` — methods live on the outer
 * ``notebookEditor`` state so per-cell template code can call
 * ``lineageFor(cell)`` from inside the ``x-for cell in cells``
 * without crossing a child x-data boundary.  ``cellLineageBulk``
 * is keyed by ``cell.content_hash`` because that is the join key
 * the audit trail already records on every ``NotebookCellRun``.
 */

export function installCellLineage(state) {
 state.cellLineageBulk = {};
 state.cellLineageLoaded = false;
 state.cellLineageLoading = false;
 state.cellLineageError = '';

 /**
  * Return the badge list for one cell, or ``[]`` when the cell
  * has no recorded write history.  Reading by ``content_hash``
  * (not cell id) means a re-saved-with-same-content cell still
  * surfaces its prior badges, matching the audit-trail identity.
  */
 state.lineageFor = function (cell) {
  if (!cell || !cell.content_hash) return [];
  return this.cellLineageBulk[cell.content_hash] || [];
 };

 /**
  * Tooltip body for the cell-header ``+N more`` lineage overflow
  * chip.1 caps the visible strip at one badge, so the
  * tail tables move into a hover preview and a read-only section
  * inside the per-cell ⋯ overflow menu.
  */
 state.lineageOverflowTitle = function (cell) {
  const tail = (this.lineageFor(cell) || []).slice(1);
  if (!tail.length) return '';
  return tail
   .map((b) => `${b.op_name} → ${b.target_table || '(none)'}`)
   .join('\n');
 };

/**
  * Notebook-level lineage roll-up.
  *
  * Aggregates the per-cell ``cellLineageBulk`` map into a small
  * summary the meta panel renders (write-target tables + op counts).
  * Pure derived state; no extra fetch — the bulk endpoint already
  * pulls every NotebookCellRun for this notebook.
  */
 state.notebookLineageSummary = function () {
  const writes = new Map();
  for (const lineage of Object.values(this.cellLineageBulk || {})) {
   for (const op of lineage || []) {
    const tbl = op && op.target_table;
    if (!tbl) continue;
    writes.set(tbl, (writes.get(tbl) || 0) + 1);
   }
  }
  let totalOps = 0;
  for (const v of writes.values()) totalOps += v;
  const tables = Array.from(writes.entries())
   .map(([table, count]) => ({ table, count }))
   .sort((a, b) => b.count - a.count);
  return { writeTables: tables, totalOps };
 };

 /**
  * Fetch ``{content_hash: [badge, ...]}`` for the whole notebook.
  * Refreshed implicitly on save (called from ``installPersistence``)
  * + explicitly on first load.
  */
 state.loadCellLineageBulk = async function () {
  if (!this.path) return;
  this.cellLineageLoading = true;
  this.cellLineageError = '';
  try {
   const res = await window.pqlApi.fetch(
    `/api/notebooks/cell/lineage/bulk?path=${encodeURIComponent(this.path)}`,
    { silent: true },
   );
   if (res.ok && res.data) {
    this.cellLineageBulk = res.data.badges || {};
    this.cellLineageLoaded = true;
   } else {
    // Non-fatal: the chip strip just stays empty.
    this.cellLineageError = (res.data && res.data.detail) || `HTTP ${res.status}`;
   }
  } catch (err) {
   this.cellLineageError = (err && err.message) || String(err);
  } finally {
   this.cellLineageLoading = false;
  }
 };
}
