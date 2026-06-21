/**
 * Federation create-form — foreign UC catalogs + generic delete-confirm.
 *
 * Split out of ``federation.js``. Owns the
 * ``createForeignCatalogForm({connections})`` factory the
 * Connections page's "Create foreign catalog" modal mounts and
 * the small ``deleteConfirm({deleteUrl, redirectUrl})`` factory
 * the per-resource detail pages mount on their delete buttons.
 *
 * ``deleteConfirm`` lives here rather than in its own file
 * because every federation detail page reaches for it; co-locating
 * the two factories most-frequently bound on federation HTML
 * keeps the import surface tight.
 */

import { validateRequired } from '../../editor_base.js';

export function createForeignCatalogForm({ connections, icebergConnectors }) {
  return {
    connections: connections || [],
    icebergConnectors: icebergConnectors || [],
    name: '',
    connectionName: '',
    comment: '',
    options: [],
    connectorType: '',
    connectorHint: '',
    saving: false,
    error: null,

    addOption() {
      this.options.push({ key: '', value: '' });
    },

    removeOption(index) {
      this.options.splice(index, 1);
    },

    applyConnectorPreset() {
      const preset = this.icebergConnectors.find((ct) => ct.key === this.connectorType);
      if (!preset) {
        this.connectorHint = '';
        return;
      }
      this.connectorHint = preset.hint || '';
      this.options = Object.entries(preset.options || {}).map(([key, value]) => ({
        key,
        value: value ?? '',
      }));
    },

    async submit() {
      const n = (this.name || '').trim();
      const validationErr = validateRequired(n, 'Name');
      if (validationErr) {
        this.error = validationErr;
        return;
      }
      if (!this.connectionName) {
        this.error = 'Pick a connection.';
        return;
      }
      const opts = {};
      for (const { key, value } of this.options) {
        const k = (key || '').trim();
        if (!k) continue;
        opts[k] = value ?? '';
      }
      const body = {
        name: n,
        type: 'FOREIGN',
        connection_name: this.connectionName,
      };
      if (this.comment.trim()) body.comment = this.comment.trim();
      if (Object.keys(opts).length > 0) body.options = opts;

      this.saving = true;
      this.error = null;
      const res = await window.pqlApi.fetch('/api/catalogs', {
        method: 'POST',
        body,
      });
      if (res.ok) {
        const data = res.data || {};
        window.location.href = '/catalogs/' + encodeURIComponent(data.name || n);
      } else {
        this.error = 'Create failed: ' + res.error;
      }
      this.saving = false;
    },
  };
}

export function deleteConfirm({ deleteUrl, redirectUrl }) {
  return {
    confirming: false,
    deleting: false,
    error: null,

    async doDelete() {
      this.deleting = true;
      this.error = null;
      const res = await window.pqlApi.fetch(deleteUrl, { method: 'DELETE' });
      if (res.ok) {
        window.location.href = redirectUrl;
      } else {
        this.error = 'Delete failed: ' + res.error;
        this.confirming = false;
      }
      this.deleting = false;
    },
  };
}
