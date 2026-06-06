/*
 * Per-node run-status overlay for the scheduler task-chain editor.
 *
 * Loads a job's recent runs into a picker and, for the selected run, paints
 * each task node with its ``TaskRun`` status (pending / running / succeeded /
 * failed / skipped) via a ``pql-task-status-*`` class on the node box, so the
 * editor doubles as a live run monitor.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

const _STATUS_CLASSES = [
  'pql-task-status-pending',
  'pql-task-status-running',
  'pql-task-status-succeeded',
  'pql-task-status-failed',
  'pql-task-status-skipped',
];

export const schedulerRunStatusMethods = {
  async refreshRunsList() {
    const res = await window.pqlApi.fetch(`/api/jobs/${this.jobId}/runs`, { silent: true });
    if (res.ok) {
      this.runsList = res.data.runs || res.data || [];
    }
  },
  async showRunStatus(runId) {
    this.statusRunId = runId ? Number(runId) : null;
    if (!this.statusRunId) {
      this._clearRunStatus();
      return;
    }
    const res = await window.pqlApi.fetch(
      `/api/jobs/${this.jobId}/canvas/run-status?run_id=${this.statusRunId}`,
      { silent: true }
    );
    if (!res.ok) return;
    this._paintRunStatus(res.data.statuses || {});
  },
  _paintRunStatus(statuses) {
    const df = this._drawflow;
    if (!df) return;
    for (const [pqlId, dfId] of Object.entries(this._drawflowNodes)) {
      const wrap = df.container.querySelector(`#node-${dfId}`);
      if (!wrap) continue;
      wrap.classList.remove(..._STATUS_CLASSES);
      const status = statuses[pqlId];
      if (status) wrap.classList.add(`pql-task-status-${status}`);
    }
  },
  _clearRunStatus() {
    const df = this._drawflow;
    if (!df) return;
    for (const wrap of df.container.querySelectorAll('.drawflow-node')) {
      wrap.classList.remove(..._STATUS_CLASSES);
    }
  },
};
