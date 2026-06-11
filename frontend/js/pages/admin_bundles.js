// Admin asset-bundle surface (/admin/bundles).
//
// Exports: adminBundles — YAML editor with plan / apply (dry-run
// toggle) plus an export panel that renders bundle YAML for copying.

export function adminBundles() {
  return {
    yamlText: '',
    dryRun: false,
    plan: null,
    outcome: null,
    error: '',
    busy: false,
    exportJobs: '',
    exportPipelines: '',
    exportDashboards: '',
    exportYaml: '',
    exportError: '',
    copied: false,

    async runPlan() {
      this.busy = true;
      this.error = '';
      this.outcome = null;
      const res = await window.pqlApi.fetch('/api/bundles/plan', {
        method: 'POST',
        body: { bundle_yaml: this.yamlText },
      });
      this.busy = false;
      if (!res.ok) {
        this.error = res.error || 'Plan failed';
        this.plan = null;
        return;
      }
      this.plan = res.data?.plan || null;
    },

    async runApply() {
      this.busy = true;
      this.error = '';
      const url = `/api/bundles/apply?dry_run=${this.dryRun ? 'true' : 'false'}`;
      const res = await window.pqlApi.fetch(url, {
        method: 'POST',
        body: { bundle_yaml: this.yamlText },
      });
      this.busy = false;
      if (!res.ok) {
        this.error = res.error || 'Apply failed';
        return;
      }
      this.outcome = res.data?.outcome || null;
    },

    // '' → null (export everything of that type); otherwise the
    // comma-separated names trimmed into a list.
    parseNames(raw) {
      const trimmed = (raw || '').trim();
      if (!trimmed) return null;
      return trimmed
        .split(',')
        .map((entry) => entry.trim())
        .filter((entry) => entry.length > 0);
    },

    async runExport() {
      this.busy = true;
      this.exportError = '';
      const res = await window.pqlApi.fetch('/api/bundles/export', {
        method: 'POST',
        body: {
          jobs: this.parseNames(this.exportJobs),
          pipelines: this.parseNames(this.exportPipelines),
          dashboards: this.parseNames(this.exportDashboards),
        },
      });
      this.busy = false;
      if (!res.ok) {
        this.exportError = res.error || 'Export failed';
        this.exportYaml = '';
        return;
      }
      this.exportYaml = res.data?.yaml || '';
    },

    async copyExport() {
      if (!this.exportYaml) return;
      await navigator.clipboard.writeText(this.exportYaml);
      this.copied = true;
      window.setTimeout(() => {
        this.copied = false;
      }, 1500);
    },

    actionBadge(action) {
      if (action === 'create' || action === 'created') return 'bg-success';
      if (action === 'update' || action === 'updated') return 'bg-warning text-dark';
      if (action === 'error') return 'bg-danger';
      return 'bg-secondary';
    },
  };
}
