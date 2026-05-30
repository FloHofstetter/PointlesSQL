// Admin data-product-as-code surface (/admin/data-product-apply).
//
// Exports: adminDataProductApply — YAML editor + plan/apply buttons.

export function adminDataProductApply() {
  return {
    spec: '',
    plan: null,
    outcome: null,
    error: '',
    busy: false,

    async runPlan() {
      this.busy = true;
      this.error = '';
      this.outcome = null;
      const res = await window.pqlApi.fetch('/api/data-products/plan', {
        method: 'POST',
        body: { spec: this.spec },
      });
      this.busy = false;
      if (!res.ok) {
        this.error = res.error || 'Plan failed';
        this.plan = null;
        return;
      }
      this.plan = res.json?.plan || null;
    },

    async runApply() {
      this.busy = true;
      this.error = '';
      const res = await window.pqlApi.fetch('/api/data-products/apply', {
        method: 'POST',
        body: { spec: this.spec },
      });
      this.busy = false;
      if (!res.ok) {
        this.error = res.error || 'Apply failed';
        return;
      }
      this.plan = res.json?.plan || null;
      this.outcome = res.json?.outcome || null;
    },
  };
}
