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
    },

    async save() {
      this.error = '';
      this.saving = true;
      const body = {
        retention_days:
          this.policy.retention_days === '' ? null : Number(this.policy.retention_days),
        encryption_class: this.policy.encryption_class || null,
        residency_region: this.policy.residency_region || null,
        consent_required:
          this.policy.consent_required === '' ? null : this.policy.consent_required === 'true',
        consent_basis: this.policy.consent_basis || null,
      };
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
