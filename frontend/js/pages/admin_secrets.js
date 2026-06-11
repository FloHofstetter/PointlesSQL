// Admin secrets cockpit (/admin/secrets).
//
// adminSecrets: create-scope form + per-scope drill-down into keyed
// secrets (put/delete, values write-only) and the ACL ladder
// (READ < WRITE < MANAGE). All calls go through /api/secrets, the
// same ACL-gated surface non-admin users script against.

export function adminSecrets() {
  return {
    form: { name: '', description: '' },
    creating: false,
    error: '',
    open: {},
    secrets: {},
    acls: {},
    secretDrafts: {},
    aclDrafts: {},

    async create() {
      this.error = '';
      this.creating = true;
      const body = { name: this.form.name.trim() };
      if (this.form.description) body.description = this.form.description.trim();
      const res = await window.pqlApi.fetch('/api/secrets/scopes', { method: 'POST', body: body });
      this.creating = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to create scope';
        return;
      }
      window.pqlApi.reloadWithToast('Secret scope created.');
    },

    async deleteScope(name) {
      if (!window.confirm('Delete secret scope "' + name + '" with all its secrets and grants?'))
        return;
      const res = await window.pqlApi.fetch('/api/secrets/scopes/' + name, { method: 'DELETE' });
      if (!res.ok) return;
      window.pqlApi.reloadWithToast('Secret scope deleted.');
    },

    async toggle(name) {
      this.open[name] = !this.open[name];
      if (this.open[name]) {
        if (!this.secretDrafts[name]) this.secretDrafts[name] = { key: '', value: '' };
        if (!this.aclDrafts[name]) this.aclDrafts[name] = { principal: '', permission: 'READ' };
        await Promise.all([this.loadSecrets(name), this.loadAcls(name)]);
      }
    },

    async loadSecrets(name) {
      const res = await window.pqlApi.fetch('/api/secrets/scopes/' + name + '/secrets');
      if (!res.ok) return;
      this.secrets[name] = (res.data && res.data.secrets) || [];
    },

    async loadAcls(name) {
      const res = await window.pqlApi.fetch('/api/secrets/scopes/' + name + '/acls');
      if (!res.ok) return;
      this.acls[name] = (res.data && res.data.acls) || [];
    },

    async putSecret(name) {
      this.error = '';
      const draft = this.secretDrafts[name];
      const key = (draft.key || '').trim();
      if (!key || !draft.value) return;
      const res = await window.pqlApi.fetch(
        '/api/secrets/scopes/' + name + '/secrets/' + encodeURIComponent(key),
        { method: 'PUT', body: { value: draft.value } }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to store secret';
        return;
      }
      draft.key = '';
      draft.value = '';
      await this.loadSecrets(name);
    },

    async deleteSecret(name, key) {
      if (!window.confirm('Delete secret "' + key + '" from scope "' + name + '"?')) return;
      const res = await window.pqlApi.fetch(
        '/api/secrets/scopes/' + name + '/secrets/' + encodeURIComponent(key),
        { method: 'DELETE' }
      );
      if (!res.ok) return;
      await this.loadSecrets(name);
    },

    async putAcl(name) {
      this.error = '';
      const draft = this.aclDrafts[name];
      const principal = (draft.principal || '').trim();
      if (!principal) return;
      const res = await window.pqlApi.fetch(
        '/api/secrets/scopes/' + name + '/acls/' + encodeURIComponent(principal),
        { method: 'PUT', body: { permission: draft.permission } }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to store grant';
        return;
      }
      draft.principal = '';
      await this.loadAcls(name);
    },

    async deleteAcl(name, principal) {
      const res = await window.pqlApi.fetch(
        '/api/secrets/scopes/' + name + '/acls/' + encodeURIComponent(principal),
        { method: 'DELETE' }
      );
      if (!res.ok) return;
      await this.loadAcls(name);
    },
  };
}
