// Governance tab for the data-product detail page: effective policy
// (inherited vs. overridden), column classifications driving read-time
// masking, the control-port (right-to-be-forgotten), the compliance
// panel (open violations + trust chip), and the A4 ownership hint.
//
// One factory fetches the aggregate /governance endpoint; mutations go
// through window.pqlApi (steward/admin-gated server-side). canManage
// comes back in the aggregate so the template never needs is_steward.

function dpBase(catalog, schema) {
  return '/api/data-products/' + encodeURIComponent(catalog) + '/' + encodeURIComponent(schema);
}

const POLICY_FIELDS = [
  'retention_days',
  'encryption_class',
  'residency_region',
  'consent_required',
  'consent_basis',
];

export function dataProductGovernance(catalog, schema) {
  return {
    catalog: catalog,
    schema: schema,
    canManage: false,
    loaded: false,
    error: '',
    effectivePolicy: {},
    classifications: [],
    violations: [],
    trustDowngraded: false,
    forgetRequests: [],
    ownershipSuggestion: null,
    editPolicy: {
      retention_days: '',
      encryption_class: '',
      residency_region: '',
      consent_required: '',
      consent_basis: '',
    },
    newClass: { table: '', column: '', classification: 'pii', masking_strategy: '' },
    forget: { subject_column: '', subject_value: '' },
    showForgetConfirm: false,

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/governance');
        if (!res.ok) {
          this.error = 'Failed to load governance';
          return;
        }
        const data = await res.json();
        this.canManage = !!data.can_manage;
        this.effectivePolicy = data.effective_policy || {};
        this.classifications = data.classifications || [];
        this.violations = data.violations || [];
        this.trustDowngraded = !!data.trust_downgraded;
        this.forgetRequests = data.forget_requests || [];
        this.ownershipSuggestion = data.ownership_suggestion || null;
        this.seedEdit();
        this.loaded = true;
      } catch (e) {
        this.error = 'Failed to load governance: ' + e.message;
      }
    },

    seedEdit() {
      for (const field of POLICY_FIELDS) {
        const cell = this.effectivePolicy[field];
        const value = cell && cell.value != null ? cell.value : '';
        this.editPolicy[field] =
          field === 'consent_required' ? String(value === true) : String(value);
      }
      // a never-set consent reads as "inherit" rather than "false".
      const consent = this.effectivePolicy.consent_required;
      if (!consent || consent.source === 'unset') this.editPolicy.consent_required = '';
    },

    source(field) {
      const cell = this.effectivePolicy[field];
      return cell ? cell.source : 'unset';
    },

    value(field) {
      const cell = this.effectivePolicy[field];
      return cell && cell.value != null ? cell.value : '—';
    },

    async savePolicy() {
      this.error = '';
      const body = {
        retention_days:
          this.editPolicy.retention_days === '' ? null : Number(this.editPolicy.retention_days),
        encryption_class: this.editPolicy.encryption_class || null,
        residency_region: this.editPolicy.residency_region || null,
        consent_required:
          this.editPolicy.consent_required === ''
            ? null
            : this.editPolicy.consent_required === 'true',
        consent_basis: this.editPolicy.consent_basis || null,
      };
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/policy', {
        method: 'PUT',
        body: body,
      });
      if (!res.ok) {
        this.error = res.error || 'Failed to save policy';
        return;
      }
      window.pqlToast.success('Policy saved.');
      await this.reload();
    },

    async addClassification() {
      this.error = '';
      if (!this.newClass.table.trim() || !this.newClass.column.trim()) {
        this.error = 'Table and column are required';
        return;
      }
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/classifications',
        { method: 'POST', body: { ...this.newClass } }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to classify column';
        return;
      }
      this.newClass = { table: '', column: '', classification: 'pii', masking_strategy: '' };
      await this.reload();
    },

    async removeClassification(id) {
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/classifications/' + id,
        { method: 'DELETE' }
      );
      if (res.ok) await this.reload();
    },

    async runForget() {
      this.error = '';
      this.showForgetConfirm = false;
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/control/forget', {
        method: 'POST',
        body: { ...this.forget },
      });
      if (!res.ok) {
        this.error = res.error || 'Right-to-be-forgotten failed';
        return;
      }
      window.pqlToast.success('Erased ' + res.data.rows_deleted + ' row(s).');
      this.forget = { subject_column: '', subject_value: '' };
      await this.reload();
    },
  };
}
