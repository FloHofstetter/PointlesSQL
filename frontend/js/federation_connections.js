/**
 * Federation create-form — UC connections.
 *
 * Split out of ``federation.js``. Owns the
 * ``x-data="createConnectionForm()"`` factory used by the
 * "Create connection" page (``GET /connections`` modal trigger).
 * Posts to ``POST /api/connections`` and on success redirects to
 * ``/connections/<name>``.
 */

import { validateRequired } from './editor_base.js';

export function createConnectionForm() {
 return {
 name: '',
 connectionType: 'POSTGRESQL',
 comment: '',
 saving: false,
 error: null,

 async submit() {
 const n = (this.name || '').trim();
 const validationErr = validateRequired(n, 'Name');
 if (validationErr) { this.error = validationErr; return; }
 this.saving = true;
 this.error = null;
 const res = await window.pqlApi.fetch('/api/connections', {
 method: 'POST',
 body: {
 name: n,
 connection_type: this.connectionType,
 comment: this.comment || undefined,
 },
 });
 if (res.ok) {
 const data = res.data || {};
 window.location.href = '/connections/' + encodeURIComponent(data.name || n);
 } else {
 this.error = 'Create failed: ' + res.error;
 }
 this.saving = false;
 },
 };
}
