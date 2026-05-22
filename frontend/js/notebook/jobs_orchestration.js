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
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const stamp =
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
      `-${pad(d.getHours())}${pad(d.getMinutes())}`;
    return suffix ? `${slug}:${suffix}:${stamp}` : slug;
  };

  // ---- Sprint 113.3: unified Run-notebook modal -----------------------
  // Collapses the former Phase 67.2 Schedule modal + Phase 67.3 Run-Once
  // modal into one tabbed surface.  The Schedule + Run-now flows share
  // their parameter form, their error/submit state, and their close
  // mechanism; only the tab-specific REST call diverges.

  state.openRunModal = function (tab) {
    const nextTab = tab === 'schedule' ? 'schedule' : 'run-now';
    // Per `feedback_alpine_nested_object_replace.md`, mutate the
    // existing object's fields rather than replacing the reference —
    // an Alpine binding on `:disabled` / `x-show` can otherwise drop.
    this.runModal.error = '';
    this.runModal.status = '';
    this.runModal.parameters = {};
    if (!this.runModal.name) {
      this.runModal.name = this._buildDefaultJobName('schedule');
    }
    if (!this.runModal.cronExpr) {
      this.runModal.cronExpr = '0 5 * * *';
    }
    this.loadParameters();
    this.runModal.tab = nextTab;
    this.runModal.open = true;
  };

  state.closeRunModal = function () {
    this.runModal.open = false;
    this.runModal.submitting = false;
    this.runModal.status = '';
  };

  state.submitRunModal = async function () {
    if (this.runModal.submitting) return;
    if (this.runModal.tab === 'schedule') {
      await this._submitRunModalSchedule();
    } else {
      await this._submitRunModalRunNow();
    }
  };

  state._submitRunModalSchedule = async function () {
    this.runModal.error = '';
    const name = (this.runModal.name || '').trim();
    const cronExpr = (this.runModal.cronExpr || '').trim();
    if (!name) {
      this.runModal.error = 'Job name is required.';
      return;
    }
    if (!cronExpr) {
      this.runModal.error = 'Cron expression is required.';
      return;
    }
    if (cronExpr.split(/\s+/).filter(Boolean).length !== 5) {
      this.runModal.error = 'Cron expression must have exactly 5 fields.';
      return;
    }
    const overrides = this._collectRunModalParams();
    const body = {
      name,
      cron_expr: cronExpr,
      kind: 'papermill',
      config: {
        notebook_path: this.path,
        parameters: overrides,
      },
    };
    this.runModal.submitting = true;
    try {
      const res = await window.pqlApi.fetch('/api/jobs', {
        method: 'POST',
        body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json' },
      });
      if (res.ok) {
        this.closeRunModal();
        if (window.pqlToast) {
          window.pqlToast.success(`Scheduled "${name}".`);
        }
        if (this.loadNotebookJobs) this.loadNotebookJobs();
      } else {
        const detail = (res.data && (res.data.detail || res.data.error)) || '';
        this.runModal.error = detail || `Failed (HTTP ${res.status}).`;
      }
    } catch (err) {
      this.runModal.error = (err && err.message) || String(err);
    } finally {
      this.runModal.submitting = false;
    }
  };

  state._submitRunModalRunNow = async function () {
    this.runModal.error = '';
    const overrides = this._collectRunModalParams();
    this.runModal.submitting = true;
    try {
      const res = await window.pqlApi.fetch('/api/notebooks/run-once', {
        method: 'POST',
        body: JSON.stringify({ path: this.path, parameters: overrides }),
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        const detail = (res.data && (res.data.detail || res.data.error)) || '';
        this.runModal.error = detail || `Failed (HTTP ${res.status}).`;
        return;
      }
      const { job_id, job_run_id } = res.data || {};
      this.runModal.status = `Run #${job_run_id} started — polling…`;
      await this._pollJobRun(job_id, job_run_id);
      if (this.loadNotebookJobs) this.loadNotebookJobs();
    } catch (err) {
      this.runModal.error = (err && err.message) || String(err);
    } finally {
      this.runModal.submitting = false;
    }
  };

  state._collectRunModalParams = function () {
    const overrides = {};
    for (const p of this.parameters || []) {
      const raw = this.runModal.parameters[p.name];
      if (raw !== undefined && raw !== '') overrides[p.name] = raw;
    }
    return overrides;
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
      // Sprint 113.3 — short-circuit if the user closed the modal
      // mid-poll.  Without this the in-flight loop would keep
      // re-setting runModal.status after teardown.
      if (!this.runModal || !this.runModal.open) return;
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
            this.runModal.status =
              `Run #${runId} ${run.status}` +
              (run.error ? ` — ${run.error}` : '.');
            return;
          }
        }
      } catch {
        /* swallow + retry */
      }
    }
    this.runModal.status = `Run #${runId} still running after timeout — check /jobs.`;
  };
}
