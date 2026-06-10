// Admin governance cockpit (/admin/governance): edit the workspace-
// default policy every product inherits, and run the policy-compliance
// scan on demand.

export function adminGovernance() {
  return {
    error: '',
    saving: false,
    scanning: false,
    scanSummary: null,
    policy: {
      retention_days: '',
      encryption_class: '',
      residency_region: '',
      consent_required: '',
      consent_basis: '',
      quota_enforcement: '',
      max_cost_per_day: '',
      max_queries_per_hour: '',
    },

    async init() {
      await this.load();
    },

    async load() {
      const res = await window.pqlApi.fetch('/api/admin/governance/policy');
      if (!res.ok) {
        this.error = res.error || 'Failed to load policy';
        return;
      }
      const wd = (res.data && res.data.workspace_default) || {};
      this.policy.retention_days = wd.retention_days == null ? '' : String(wd.retention_days);
      this.policy.encryption_class = wd.encryption_class || '';
      this.policy.residency_region = wd.residency_region || '';
      this.policy.consent_required =
        wd.consent_required == null ? '' : String(wd.consent_required === true);
      this.policy.consent_basis = wd.consent_basis || '';
      this.policy.quota_enforcement = wd.quota_enforcement || '';
      this.policy.max_cost_per_day = wd.max_cost_per_day == null ? '' : String(wd.max_cost_per_day);
      this.policy.max_queries_per_hour =
        wd.max_queries_per_hour == null ? '' : String(wd.max_queries_per_hour);
    },

    async save() {
      this.error = '';
      this.saving = true;
      // Only emit fields the user touched: workspace policy is the
      // inheritance base, so an undeclared form row means "no change",
      // not "clear back to null" — and the NOT NULL columns
      // (consent_required / consumption_enforcement / quota_enforcement
      // / etc.) reject a null UPDATE outright.
      const body = {};
      if (this.policy.retention_days !== '')
        body.retention_days = Number(this.policy.retention_days);
      if (this.policy.encryption_class !== '') body.encryption_class = this.policy.encryption_class;
      if (this.policy.residency_region !== '') body.residency_region = this.policy.residency_region;
      if (this.policy.consent_required !== '')
        body.consent_required = this.policy.consent_required === 'true';
      if (this.policy.consent_basis !== '') body.consent_basis = this.policy.consent_basis;
      if (this.policy.quota_enforcement !== '')
        body.quota_enforcement = this.policy.quota_enforcement;
      if (this.policy.max_cost_per_day !== '')
        body.max_cost_per_day = Number(this.policy.max_cost_per_day);
      if (this.policy.max_queries_per_hour !== '')
        body.max_queries_per_hour = Number(this.policy.max_queries_per_hour);
      const res = await window.pqlApi.fetch('/api/admin/governance/policy', {
        method: 'PUT',
        body: body,
      });
      this.saving = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to save policy';
        return;
      }
      window.pqlToast.success('Workspace default policy saved.');
    },

    async runScan() {
      this.error = '';
      this.scanning = true;
      this.scanSummary = null;
      const res = await window.pqlApi.fetch('/api/admin/governance/scan', { method: 'POST' });
      this.scanning = false;
      if (!res.ok) {
        this.error = res.error || 'Scan failed';
        return;
      }
      this.scanSummary = res.data;
      window.pqlToast.success(
        'Scanned ' +
          res.data.products_scanned +
          ' product(s), ' +
          res.data.violations.length +
          ' violation(s).'
      );
    },
  };
}
