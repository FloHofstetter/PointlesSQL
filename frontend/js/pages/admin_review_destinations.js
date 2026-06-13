// Admin review-destination CRUD page (/admin/review-destinations).
// Two Alpine factories: per-row actions + create form.

export function reviewDestRow(destId, name, isActive, minSeverity) {
  return {
    destId,
    name,
    isActive,
    minSeverity,
    busy: false,

    get webhookUrl() {
      return this.$el ? this.$el.querySelector('td.font-monospace')?.textContent.trim() : '';
    },

    async toggleActive(checked) {
      this.busy = true;
      const res = await window.pqlApi.fetch('/api/admin/review-destinations/' + this.destId, {
        method: 'PATCH',
        body: { is_active: checked },
      });
      this.busy = false;
      if (res.ok) {
        this.isActive = checked;
        window.pqlToast.success('Destination ' + (checked ? 'activated' : 'deactivated') + '.');
      } else {
        this.isActive = !checked;
        window.pqlToast.error(res.error || 'Failed to update destination.');
      }
    },

    async updateSeverity(value) {
      this.busy = true;
      const res = await window.pqlApi.fetch('/api/admin/review-destinations/' + this.destId, {
        method: 'PATCH',
        body: { min_severity: value },
      });
      this.busy = false;
      if (res.ok) {
        this.minSeverity = value;
        window.pqlToast.success('Min severity set to ' + value + '.');
      } else {
        window.pqlToast.error(res.error || 'Failed to update destination.');
      }
    },

    async remove() {
      const ok = window.pqlConfirm
        ? await window.pqlConfirm(
            'Delete destination?',
            'Delete "' + this.name + '". Historical fan-out lines survive.'
          )
        : window.confirm(
            'Delete destination "' + this.name + '"? Historical fan-out lines survive.'
          );
      if (!ok) return;
      this.busy = true;
      const res = await window.pqlApi.fetch('/api/admin/review-destinations/' + this.destId, {
        method: 'DELETE',
      });
      this.busy = false;
      if (res.ok) {
        window.pqlApi.reloadWithToast('Destination deleted.');
      } else {
        window.pqlToast.error(res.error || 'Failed to delete destination.');
      }
    },
  };
}

export function reviewDestCreate() {
  return {
    form: {
      name: '',
      webhookUrl: '',
      hmacSecret: '',
      minSeverity: 'warn',
      isActive: true,
      workspaceFilter: [],
    },
    creating: false,
    error: '',
    createdSecret: '',

    canSubmit() {
      return !!(this.form.name.trim() && this.form.webhookUrl.trim());
    },

    copySecret() {
      if (!navigator.clipboard || !navigator.clipboard.writeText) return;
      navigator.clipboard.writeText(this.createdSecret).then(
        () => window.pqlToast && window.pqlToast.success('Secret copied to clipboard.'),
        () =>
          window.pqlToast &&
          window.pqlToast.error('Copy failed — select the field and copy manually.')
      );
    },

    async create() {
      this.error = '';
      this.creating = true;
      const body = {
        name: this.form.name.trim(),
        webhook_url: this.form.webhookUrl.trim(),
        min_severity: this.form.minSeverity,
        is_active: this.form.isActive,
      };
      if (this.form.hmacSecret) body.hmac_secret = this.form.hmacSecret;
      if (this.form.workspaceFilter.length) {
        body.workspace_filter = this.form.workspaceFilter.map((x) => parseInt(x, 10));
      }
      const res = await window.pqlApi.fetch('/api/admin/review-destinations', {
        method: 'POST',
        body,
      });
      this.creating = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to create destination.';
        return;
      }
      // The cleartext HMAC secret is returned exactly once. If one was
      // set, surface it in a copy field and hold the reload until the
      // admin has copied it; otherwise reload straight away.
      const secret = (res.data && res.data.hmac_secret) || body.hmac_secret || '';
      if (secret) {
        this.createdSecret = secret;
        if (window.pqlToast) window.pqlToast.success('Destination created.');
      } else {
        window.pqlApi.reloadWithToast('Destination created.');
      }
    },
  };
}
