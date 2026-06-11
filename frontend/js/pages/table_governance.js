// Table-detail governance controls.
//
// tableCertification: the owner/admin "Certification" dropdown in the
// table-page header — sets / clears the certification tags through
// PUT /api/tables/{fqn}/certification and reloads so the badge and
// banner re-render server-side.
//
// requestAccess: the "Request access" modal shown to signed-in users
// who lack SELECT — files a request via POST /api/access-requests;
// the owner decides it on /access-requests.

export function tableCertification(fullName) {
  return {
    busy: false,

    async apply(status, note) {
      this.busy = true;
      const res = await window.pqlApi.fetch(
        `/api/tables/${encodeURIComponent(fullName)}/certification`,
        { method: 'PUT', body: { status: status, note: note } }
      );
      this.busy = false;
      if (res.ok) window.pqlApi.reloadWithToast('Certification updated.');
    },

    async setCertified() {
      await this.apply('certified', null);
    },

    async setDeprecated() {
      const note = window.prompt('Deprecation note (what should consumers migrate to?):', '');
      if (note === null) return; // prompt cancelled — leave the tag untouched
      await this.apply('deprecated', note.trim() || null);
    },

    async clearCertification() {
      await this.apply(null, null);
    },
  };
}

export function requestAccess(fullName) {
  return {
    justification: '',
    busy: false,
    error: '',

    async submit() {
      this.busy = true;
      this.error = '';
      const res = await window.pqlApi.fetch('/api/access-requests', {
        method: 'POST',
        body: {
          securable_type: 'table',
          full_name: fullName,
          privileges: ['SELECT'],
          justification: this.justification.trim() || null,
        },
        silent: true,
      });
      this.busy = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to file the access request.';
        return;
      }
      window.pqlApi.reloadWithToast('Access request filed.');
    },
  };
}
