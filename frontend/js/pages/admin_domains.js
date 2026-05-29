// Admin domains cockpit (/admin/domains).
//
// Exports: adminDomains (create form), domainArchiveButton (soft-archive),
// domainMembers (per-row owner/developer member management).

export function adminDomains() {
  return {
    form: { slug: '', name: '', archetype: 'source-aligned', description: '' },
    creating: false,
    error: '',

    async create() {
      this.error = '';
      this.creating = true;
      const body = {
        slug: this.form.slug.trim(),
        name: this.form.name.trim(),
        archetype: this.form.archetype,
      };
      if (this.form.description) body.description = this.form.description.trim();
      const res = await window.pqlApi.fetch('/api/admin/domains', { method: 'POST', body: body });
      this.creating = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to create domain';
        return;
      }
      window.pqlApi.reloadWithToast('Domain created.');
    },
  };
}

export function domainArchiveButton(domainId, slug) {
  return {
    async archive() {
      if (
        !window.confirm(
          'Archive domain "' + slug + '"? Products keep their assignment but it hides from listings.'
        )
      ) {
        return;
      }
      const res = await window.pqlApi.fetch('/api/admin/domains/' + domainId + '/archive', {
        method: 'POST',
      });
      if (!res.ok) return;
      window.pqlApi.reloadWithToast('Domain archived.');
    },
  };
}

export function domainMembers(domainId) {
  return {
    domainId: domainId,
    members: [],
    open: false,
    loading: false,
    error: '',
    newEmail: '',
    newRole: 'owner',

    async toggle() {
      this.open = !this.open;
      if (this.open && this.members.length === 0) await this.load();
    },

    async load() {
      this.loading = true;
      this.error = '';
      const res = await window.pqlApi.fetch('/api/admin/domains/' + this.domainId + '/members');
      this.loading = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to load members';
        return;
      }
      this.members = (res.data && res.data.members) || [];
    },

    async add() {
      if (!this.newEmail.trim()) return;
      this.error = '';
      const res = await window.pqlApi.fetch('/api/admin/domains/' + this.domainId + '/members', {
        method: 'POST',
        body: { user_email: this.newEmail.trim(), role: this.newRole },
      });
      if (!res.ok) {
        this.error = res.error || 'Failed to add member';
        return;
      }
      this.newEmail = '';
      await this.load();
    },

    async changeRole(userId, role) {
      const res = await window.pqlApi.fetch(
        '/api/admin/domains/' + this.domainId + '/members/' + userId,
        { method: 'PATCH', body: { role: role } }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to change role';
        return;
      }
      await this.load();
    },

    async remove(userId) {
      const res = await window.pqlApi.fetch(
        '/api/admin/domains/' + this.domainId + '/members/' + userId,
        { method: 'DELETE' }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to remove member';
        return;
      }
      await this.load();
    },
  };
}
