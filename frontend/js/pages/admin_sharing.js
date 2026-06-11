// Provider-side Delta Sharing cockpit (/admin/sharing).
//
// adminSharing: share CRUD with a per-share drawer (objects by
// three-part FQN, grant/revoke by recipient name) + recipient CRUD
// whose create/rotate responses carry a ONE-TIME bearer token that
// surfaces in a copy-once modal (only the hash is stored server-side,
// so the plaintext can never be re-fetched).

export function adminSharing() {
  return {
    shares: [],
    recipients: [],
    error: '',
    shareForm: { name: '', comment: '' },
    creatingShare: false,
    recipForm: { name: '', comment: '' },
    creatingRecipient: false,
    open: {},
    details: {},
    objDrafts: {},
    grantDrafts: {},
    tokenModal: { show: false, name: '', token: '', copyLabel: 'Copy' },

    async init() {
      await Promise.all([this.loadShares(), this.loadRecipients()]);
    },

    async loadShares() {
      const res = await window.pqlApi.fetch('/api/sharing/shares');
      if (res.ok) this.shares = (res.data && res.data.shares) || [];
    },

    async loadRecipients() {
      const res = await window.pqlApi.fetch('/api/sharing/recipients');
      if (res.ok) this.recipients = (res.data && res.data.recipients) || [];
    },

    // -- Shares ----------------------------------------------------

    async createShare() {
      this.error = '';
      const name = this.shareForm.name.trim();
      if (!name) {
        this.error = 'Share name is required.';
        return;
      }
      this.creatingShare = true;
      const body = { name: name };
      if (this.shareForm.comment.trim()) body.comment = this.shareForm.comment.trim();
      const res = await window.pqlApi.fetch('/api/sharing/shares', { method: 'POST', body: body });
      this.creatingShare = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to create share';
        return;
      }
      this.shareForm = { name: '', comment: '' };
      await this.loadShares();
    },

    async removeShare(share) {
      if (
        !window.confirm(
          'Delete share "' + share.name + '"? Its objects and grants are removed with it.'
        )
      )
        return;
      const res = await window.pqlApi.fetch(
        '/api/sharing/shares/' + encodeURIComponent(share.name),
        { method: 'DELETE' }
      );
      if (!res.ok) return;
      delete this.open[share.name];
      await this.loadShares();
    },

    async toggleShare(name) {
      this.open[name] = !this.open[name];
      if (this.open[name]) {
        if (!this.objDrafts[name]) this.objDrafts[name] = { table_full_name: '', shared_as: '' };
        if (!this.grantDrafts[name]) this.grantDrafts[name] = '';
        await this.loadDetail(name);
      }
    },

    async loadDetail(name) {
      const res = await window.pqlApi.fetch('/api/sharing/shares/' + encodeURIComponent(name));
      if (res.ok) this.details[name] = res.data || {};
    },

    async addObject(name) {
      this.error = '';
      const draft = this.objDrafts[name];
      const fqn = (draft.table_full_name || '').trim();
      const sharedAs = (draft.shared_as || '').trim();
      if (fqn.split('.').length !== 3) {
        this.error = 'Table name must be three-part: catalog.schema.table';
        return;
      }
      if (sharedAs && sharedAs.split('.').length !== 2) {
        this.error = 'shared_as must be two-part: schema.table';
        return;
      }
      const body = { table_full_name: fqn };
      if (sharedAs) body.shared_as = sharedAs;
      const res = await window.pqlApi.fetch(
        '/api/sharing/shares/' + encodeURIComponent(name) + '/objects',
        { method: 'POST', body: body }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to add table';
        return;
      }
      draft.table_full_name = '';
      draft.shared_as = '';
      await Promise.all([this.loadDetail(name), this.loadShares()]);
    },

    async removeObject(name, tableFullName) {
      const res = await window.pqlApi.fetch(
        '/api/sharing/shares/' +
          encodeURIComponent(name) +
          '/objects?table_full_name=' +
          encodeURIComponent(tableFullName),
        { method: 'DELETE' }
      );
      if (!res.ok) return;
      await Promise.all([this.loadDetail(name), this.loadShares()]);
    },

    async grant(name) {
      this.error = '';
      const recipient = (this.grantDrafts[name] || '').trim();
      if (!recipient) return;
      const res = await window.pqlApi.fetch(
        '/api/sharing/shares/' +
          encodeURIComponent(name) +
          '/recipients/' +
          encodeURIComponent(recipient),
        { method: 'PUT' }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to grant share';
        return;
      }
      window.pqlToast?.success('Granted "' + name + '" to ' + recipient + '.');
    },

    async revoke(name) {
      this.error = '';
      const recipient = (this.grantDrafts[name] || '').trim();
      if (!recipient) return;
      const res = await window.pqlApi.fetch(
        '/api/sharing/shares/' +
          encodeURIComponent(name) +
          '/recipients/' +
          encodeURIComponent(recipient),
        { method: 'DELETE' }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to revoke share';
        return;
      }
      window.pqlToast?.success('Revoked "' + name + '" from ' + recipient + '.');
    },

    // -- Recipients ------------------------------------------------

    async createRecipient() {
      this.error = '';
      const name = this.recipForm.name.trim();
      if (!name) {
        this.error = 'Recipient name is required.';
        return;
      }
      this.creatingRecipient = true;
      const body = { name: name };
      if (this.recipForm.comment.trim()) body.comment = this.recipForm.comment.trim();
      const res = await window.pqlApi.fetch('/api/sharing/recipients', {
        method: 'POST',
        body: body,
      });
      this.creatingRecipient = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to create recipient';
        return;
      }
      this.recipForm = { name: '', comment: '' };
      this.showToken(res.data.name || name, res.data.token || '');
      await this.loadRecipients();
    },

    async rotateToken(recipient) {
      if (
        !window.confirm(
          'Rotate the token for "' +
            recipient.name +
            '"? The current token stops working immediately.'
        )
      )
        return;
      const res = await window.pqlApi.fetch(
        '/api/sharing/recipients/' + encodeURIComponent(recipient.name) + '/rotate-token',
        { method: 'POST' }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to rotate token';
        return;
      }
      this.showToken(recipient.name, res.data.token || '');
    },

    async removeRecipient(recipient) {
      if (
        !window.confirm(
          'Delete recipient "' + recipient.name + '"? Its grants are removed with it.'
        )
      )
        return;
      const res = await window.pqlApi.fetch(
        '/api/sharing/recipients/' + encodeURIComponent(recipient.name),
        { method: 'DELETE' }
      );
      if (!res.ok) return;
      await this.loadRecipients();
    },

    // -- One-time token modal ---------------------------------------

    showToken(name, token) {
      this.tokenModal = { show: true, name: name, token: token, copyLabel: 'Copy' };
    },

    async copyToken() {
      try {
        await navigator.clipboard.writeText(this.tokenModal.token);
        this.tokenModal.copyLabel = 'Copied';
      } catch (_err) {
        this.$refs.tokenField.select();
        document.execCommand('copy');
        this.tokenModal.copyLabel = 'Copied';
      }
    },

    dismissToken() {
      this.tokenModal = { show: false, name: '', token: '', copyLabel: 'Copy' };
    },
  };
}
