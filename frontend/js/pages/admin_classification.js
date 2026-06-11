// Data classification console (/admin/classification).
//
// adminClassification: tag-policy rule CRUD (create / toggle active /
// delete) plus the interactive PII scan. All calls go through the
// admin-gated /api/admin/tag-policies and /api/admin/classification
// surfaces.

export function adminClassification(initialRules) {
  return {
    rules: initialRules || [],
    creating: false,
    saving: false,
    error: '',
    form: { tag_key: '', tag_value: '', effect: 'mask', expr: 'redact', priority: 100, description: '' },
    scan: { catalog: '', schema: '', table: '' },
    scanning: false,
    scanError: '',
    findings: null,

    async create() {
      this.error = '';
      this.saving = true;
      const body = {
        tag_key: this.form.tag_key.trim(),
        effect: this.form.effect,
        expr: this.form.expr.trim(),
        priority: Number(this.form.priority) || 100,
      };
      if (this.form.tag_value.trim()) body.tag_value = this.form.tag_value.trim();
      if (this.form.description.trim()) body.description = this.form.description.trim();
      const res = await window.pqlApi.fetch('/api/admin/tag-policies', { method: 'POST', body, silent: true });
      this.saving = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to create rule';
        return;
      }
      this.rules.push(res.data);
      this.creating = false;
      this.form = { tag_key: '', tag_value: '', effect: 'mask', expr: 'redact', priority: 100, description: '' };
    },

    async toggle(rule) {
      const res = await window.pqlApi.fetch(`/api/admin/tag-policies/${rule.id}`, {
        method: 'PATCH',
        body: { is_active: !rule.is_active },
        silent: true,
      });
      if (res.ok) rule.is_active = res.data.is_active;
    },

    async remove(rule) {
      if (!window.confirm(`Delete the ${rule.effect} rule for tag "${rule.tag_key}"?`)) return;
      const res = await window.pqlApi.fetch(`/api/admin/tag-policies/${rule.id}`, {
        method: 'DELETE',
        silent: true,
      });
      if (res.ok) this.rules = this.rules.filter((r) => r.id !== rule.id);
    },

    async runScan() {
      this.scanError = '';
      this.findings = null;
      const body = {};
      if (this.scan.table.trim()) {
        body.table = this.scan.table.trim();
      } else if (this.scan.catalog.trim() && this.scan.schema.trim()) {
        body.catalog = this.scan.catalog.trim();
        body.schema = this.scan.schema.trim();
      } else {
        this.scanError = 'Provide either catalog + schema or a single table.';
        return;
      }
      this.scanning = true;
      const res = await window.pqlApi.fetch('/api/admin/classification/scan', {
        method: 'POST',
        body,
        silent: true,
      });
      this.scanning = false;
      if (!res.ok) {
        this.scanError = res.error || 'Scan failed';
        return;
      }
      this.findings = res.data.findings || [];
    },
  };
}
