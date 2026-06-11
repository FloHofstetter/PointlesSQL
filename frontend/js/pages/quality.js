// Data-quality cockpit (/quality).
//
// qualityMonitors: monitor table seeded server-side + admin-only
// create form + a per-monitor detail drawer showing the latest
// profile snapshot per table and the anomaly timeline. Admin
// actions: Run now (manual scan through the scheduler), Pause /
// Resume (is_active toggle), Delete.

export function qualityMonitors(initial, isAdmin) {
  return {
    monitors: initial || [],
    isAdmin: !!isAdmin,
    error: '',
    creating: false,
    createError: '',
    form: { target: '', cron_expr: '0 6 * * *', is_active: true },
    busy: {},
    runResults: {},
    detailId: null,
    detail: null,
    detailLoading: false,

    ago(iso) {
      if (!iso) return '—';
      if (typeof window.pqlRelativeTime === 'function') return window.pqlRelativeTime(iso);
      return iso;
    },

    severityBadge(severity) {
      return severity === 'critical' ? 'bg-danger' : 'bg-warning text-dark';
    },

    kindLabel(kind) {
      return String(kind || '').replaceAll('_', ' ');
    },

    columnCount(snapshot) {
      return Object.keys(snapshot.column_metrics || {}).length;
    },

    // Snapshots arrive newest-first; the first row per table is that
    // table's latest profile.
    latestSnapshots() {
      const seen = {};
      const latest = [];
      for (const snapshot of (this.detail && this.detail.snapshots) || []) {
        if (seen[snapshot.table_fqn]) continue;
        seen[snapshot.table_fqn] = true;
        latest.push(snapshot);
      }
      return latest;
    },

    async refresh() {
      const res = await window.pqlApi.fetch('/api/quality/monitors', { silent: true });
      if (res.ok) this.monitors = (res.data && res.data.monitors) || [];
    },

    async create() {
      this.createError = '';
      const target = this.form.target.trim();
      const cron = this.form.cron_expr.trim();
      if (!target || !cron) {
        this.createError = 'Target and cron expression are required.';
        return;
      }
      this.creating = true;
      const res = await window.pqlApi.fetch('/api/quality/monitors', {
        method: 'POST',
        body: { target: target, cron_expr: cron, is_active: this.form.is_active },
      });
      this.creating = false;
      if (!res.ok) {
        this.createError = res.error || 'Failed to create monitor';
        return;
      }
      this.form = { target: '', cron_expr: '0 6 * * *', is_active: true };
      await this.refresh();
    },

    async toggleDetail(monitor) {
      if (this.detailId === monitor.id) {
        this.detailId = null;
        this.detail = null;
        return;
      }
      this.detailId = monitor.id;
      this.detail = null;
      await this.loadDetail(monitor.id);
    },

    async loadDetail(monitorId) {
      this.detailLoading = true;
      const res = await window.pqlApi.fetch('/api/quality/monitors/' + monitorId, {
        silent: true,
      });
      this.detailLoading = false;
      if (this.detailId !== monitorId) return;
      if (!res.ok) {
        this.error = res.error || 'Failed to load monitor detail';
        return;
      }
      this.detail = res.data;
    },

    async runNow(monitor) {
      this.error = '';
      this.busy[monitor.id] = true;
      const res = await window.pqlApi.fetch('/api/quality/monitors/' + monitor.id + '/run', {
        method: 'POST',
      });
      this.busy[monitor.id] = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to run monitor';
        return;
      }
      this.runResults[monitor.id] = res.data.error
        ? res.data.status + ': ' + res.data.error
        : res.data.status;
      await this.refresh();
      if (this.detailId === monitor.id) await this.loadDetail(monitor.id);
    },

    async toggleActive(monitor) {
      this.error = '';
      this.busy[monitor.id] = true;
      const res = await window.pqlApi.fetch('/api/quality/monitors/' + monitor.id, {
        method: 'PATCH',
        body: { is_active: !monitor.is_active },
      });
      this.busy[monitor.id] = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to update monitor';
        return;
      }
      await this.refresh();
    },

    async remove(monitor) {
      if (!window.confirm('Delete quality monitor for "' + monitor.target + '"?')) return;
      const res = await window.pqlApi.fetch('/api/quality/monitors/' + monitor.id, {
        method: 'DELETE',
      });
      if (!res.ok) {
        this.error = res.error || 'Failed to delete monitor';
        return;
      }
      if (this.detailId === monitor.id) {
        this.detailId = null;
        this.detail = null;
      }
      delete this.runResults[monitor.id];
      await this.refresh();
    },
  };
}
