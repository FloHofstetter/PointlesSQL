/**
 * Notebook editor — Job-orchestration mixin.
 *
 * Owns the Schedule modal (cron-based job creation), the Run-Once
 * modal (single-shot papermill execution), and the Notebook-Jobs
 * panel (recent runs + scheduled-jobs listing for the open path).
 * Extracted from ``notebook_editor.js`` in Phase 70.4 — methods are
 * installed onto the shared Alpine state object so ``this`` still
 * resolves to the editor's reactive root.
 */

export function installJobsOrchestration(state) {
  state.describeCron = function (expr) {
    if (!expr) return '';
    if (typeof window.pqlHumanizeCron === 'function') {
      try {
        return window.pqlHumanizeCron(expr);
      } catch {
        /* fall through */
      }
    }
    return '';
  };

  state._buildDefaultJobName = function (suffix) {
    const slug = String(this.path || 'notebook').replace(/[^A-Za-z0-9_-]+/g, '_');
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    return suffix ? `${slug}:${suffix}:${stamp}` : slug;
  };

  // ---- Phase 67.2: Schedule modal --------------------------------------

  state.openScheduleModal = function () {
    this.scheduleError = '';
    this.loadParameters();
    this.scheduleForm = {
      name: this._buildDefaultJobName('schedule'),
      cronExpr: '0 5 * * *',
      parameters: {},
    };
    this.scheduleModalOpen = true;
  };

  state.closeScheduleModal = function () {
    this.scheduleModalOpen = false;
    this.scheduleSubmitting = false;
  };

  state.submitSchedule = async function () {
    if (this.scheduleSubmitting) return;
    this.scheduleError = '';
    const name = (this.scheduleForm.name || '').trim();
    const cronExpr = (this.scheduleForm.cronExpr || '').trim();
    if (!name) {
      this.scheduleError = 'Job name is required.';
      return;
    }
    if (!cronExpr) {
      this.scheduleError = 'Cron expression is required.';
      return;
    }
    if (cronExpr.split(/\s+/).filter(Boolean).length !== 5) {
      this.scheduleError = 'Cron expression must have exactly 5 fields.';
      return;
    }
    const overrides = {};
    for (const p of this.parameters || []) {
      const raw = this.scheduleForm.parameters[p.name];
      if (raw !== undefined && raw !== '') overrides[p.name] = raw;
    }
    const body = {
      name,
      cron_expr: cronExpr,
      kind: 'papermill',
      config: {
        notebook_path: this.path,
        parameters: overrides,
      },
    };
    this.scheduleSubmitting = true;
    try {
      const res = await window.pqlApi.fetch('/api/jobs', {
        method: 'POST',
        body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json' },
      });
      if (res.ok) {
        this.closeScheduleModal();
        if (window.pqlToast) {
          window.pqlToast.success(`Scheduled "${name}".`);
        }
        if (this.loadNotebookJobs) this.loadNotebookJobs();
      } else {
        const detail = (res.data && (res.data.detail || res.data.error)) || '';
        this.scheduleError = detail || `Failed (HTTP ${res.status}).`;
      }
    } catch (err) {
      this.scheduleError = (err && err.message) || String(err);
    } finally {
      this.scheduleSubmitting = false;
    }
  };

  // ---- Phase 67.3: Run-Once modal --------------------------------------

  state.openRunOnceModal = function () {
    this.runOnceError = '';
    this.runOnceStatus = '';
    this.loadParameters();
    this.runOnceForm = { parameters: {} };
    this.runOnceModalOpen = true;
  };

  state.closeRunOnceModal = function () {
    this.runOnceModalOpen = false;
    this.runOnceSubmitting = false;
    this.runOnceStatus = '';
  };

  state.submitRunOnce = async function () {
    if (this.runOnceSubmitting) return;
    this.runOnceError = '';
    const overrides = {};
    for (const p of this.parameters || []) {
      const raw = this.runOnceForm.parameters[p.name];
      if (raw !== undefined && raw !== '') overrides[p.name] = raw;
    }
    this.runOnceSubmitting = true;
    try {
      const res = await window.pqlApi.fetch('/api/notebooks/run-once', {
        method: 'POST',
        body: JSON.stringify({ path: this.path, parameters: overrides }),
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        const detail = (res.data && (res.data.detail || res.data.error)) || '';
        this.runOnceError = detail || `Failed (HTTP ${res.status}).`;
        return;
      }
      const { job_id, job_run_id } = res.data || {};
      this.runOnceStatus = `Run #${job_run_id} started — polling…`;
      await this._pollJobRun(job_id, job_run_id);
      if (this.loadNotebookJobs) this.loadNotebookJobs();
    } catch (err) {
      this.runOnceError = (err && err.message) || String(err);
    } finally {
      this.runOnceSubmitting = false;
    }
  };

  // ---- Phase 67.4: Notebook-Jobs panel ---------------------------------

  state.loadNotebookJobs = async function () {
    if (!this.path) return;
    try {
      const res = await window.pqlApi.fetch(
        `/api/notebooks/jobs?path=${encodeURIComponent(this.path)}`,
        { silent: true },
      );
      if (res.ok && res.data) {
        this.jobsPanel = {
          scheduled_jobs: res.data.scheduled_jobs || [],
          recent_runs: res.data.recent_runs || [],
        };
      }
    } catch {
      /* non-fatal */
    }
  };

  state.toggleJobsPanel = function () {
    this.jobsPanelOpen = !this.jobsPanelOpen;
    if (this.jobsPanelOpen) this.loadNotebookJobs();
  };

  state._pollJobRun = async function (jobId, runId) {
    if (!jobId || !runId) return;
    let delay = 500;
    const cap = 5000;
    for (let i = 0; i < 240; i++) {
      await new Promise((r) => setTimeout(r, delay));
      delay = Math.min(delay * 1.4, cap);
      try {
        const res = await window.pqlApi.fetch(
          `/api/jobs/${jobId}/runs/${runId}/tasks`,
          { silent: true },
        );
        if (!res.ok) continue;
        const listing = await window.pqlApi.fetch(
          `/api/jobs/${jobId}/runs`,
          { silent: true },
        );
        if (listing.ok && Array.isArray(listing.data)) {
          const run = listing.data.find((r) => r.id === runId);
          if (run && run.status !== 'running') {
            this.runOnceStatus =
              `Run #${runId} ${run.status}` +
              (run.error ? ` — ${run.error}` : '.');
            return;
          }
        }
      } catch {
        /* swallow + retry */
      }
    }
    this.runOnceStatus = `Run #${runId} still running after timeout — check /jobs.`;
  };
}
