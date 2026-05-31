// Admin Cedar policy-modules cockpit (/admin/policy-modules).
//
// Exports: adminPolicyModules — list + CRUD + dry-run + decision log.

export function adminPolicyModules() {
  return {
    modules: [],
    loading: false,
    error: '',
    editorOpen: false,
    editing: { id: null, name: '', cedar_source: '', enabled: true },
    editorError: '',
    saving: false,
    testOpen: false,
    testTarget: null,
    testForm: {
      principal: 'User::"test"',
      action: 'Action::"read"',
      resource: 'DataProduct::"main.silver"',
    },
    testResult: null,
    decisionsOpen: false,
    decisions: [],

    async load() {
      this.loading = true;
      this.error = '';
      const res = await window.pqlApi.fetch('/api/admin/policy-modules');
      this.loading = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to load modules';
        return;
      }
      this.modules = res.data?.modules || [];
    },

    openCreate() {
      this.editing = { id: null, name: '', cedar_source: '', enabled: true };
      this.editorError = '';
      this.editorOpen = true;
    },

    openEdit(module) {
      this.editing = {
        id: module.id,
        name: module.name,
        cedar_source: module.cedar_source || '',
        enabled: !!module.enabled,
      };
      this.editorError = '';
      this.editorOpen = true;
    },

    closeEditor() {
      this.editorOpen = false;
    },

    async save() {
      this.saving = true;
      this.editorError = '';
      const body = {
        name: this.editing.name.trim(),
        cedar_source: this.editing.cedar_source,
        enabled: this.editing.enabled,
      };
      const url = this.editing.id
        ? '/api/admin/policy-modules/' + this.editing.id
        : '/api/admin/policy-modules';
      const method = this.editing.id ? 'PUT' : 'POST';
      const res = await window.pqlApi.fetch(url, { method: method, body: body });
      this.saving = false;
      if (!res.ok) {
        this.editorError = res.error || 'Failed to save';
        return;
      }
      this.editorOpen = false;
      await this.load();
    },

    async remove(module) {
      if (!window.confirm('Delete policy module "' + module.name + '"?')) return;
      const res = await window.pqlApi.fetch(
        '/api/admin/policy-modules/' + module.id,
        { method: 'DELETE' }
      );
      if (!res.ok) return;
      await this.load();
    },

    openTest(module) {
      this.testTarget = module;
      this.testResult = null;
      this.testOpen = true;
    },

    async runTest() {
      this.testResult = null;
      const res = await window.pqlApi.fetch(
        '/api/admin/policy-modules/' + this.testTarget.id + '/test',
        { method: 'POST', body: this.testForm }
      );
      if (!res.ok) {
        this.testResult = { effect: 'error', error_class: res.error || 'failed' };
        return;
      }
      this.testResult = res.data?.decision || null;
    },

    async openDecisions(module) {
      this.decisionsOpen = true;
      const res = await window.pqlApi.fetch(
        '/api/admin/policy-modules/' + module.id + '/decisions'
      );
      this.decisions = res.ok ? (res.data?.decisions || []) : [];
    },
  };
}
