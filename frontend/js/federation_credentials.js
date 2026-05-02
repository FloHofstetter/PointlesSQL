/**
 * Federation create-forms — UC credentials + external locations.
 *
 * Split out of ``federation.js``. Bundled together
 * because external locations bind a credential by name (the
 * external-location form's "Credential is required" guard wants
 * the user to create one here first), so admins typically open
 * both pages in the same session.
 *
 * Each factory posts to its respective ``POST /api/credentials``
 * or ``POST /api/external-locations`` endpoint and on success
 * redirects to the per-resource detail page.
 */

import { validateRequired } from './editor_base.js';

export function createCredentialForm() {
 return {
 name: '',
 awsRoleArn: '',
 comment: '',
 saving: false,
 error: null,

 async submit() {
 const n = (this.name || '').trim();
 const validationErr = validateRequired(n, 'Name');
 if (validationErr) { this.error = validationErr; return; }
 this.saving = true;
 this.error = null;
 const body = {
 name: n,
 purpose: 'STORAGE',
 comment: this.comment || undefined,
 };
 if (this.awsRoleArn.trim()) {
 body.aws_iam_role = { role_arn: this.awsRoleArn.trim() };
 }
 const res = await window.pqlApi.fetch('/api/credentials', {
 method: 'POST',
 body,
 });
 if (res.ok) {
 const data = res.data || {};
 window.location.href = '/credentials/' + encodeURIComponent(data.name || n);
 } else {
 this.error = 'Create failed: ' + res.error;
 }
 this.saving = false;
 },
 };
}

export function createExternalLocationForm() {
 return {
 name: '',
 url: '',
 credentialName: '',
 comment: '',
 saving: false,
 error: null,

 async submit() {
 const n = (this.name || '').trim();
 const nameErr = validateRequired(n, 'Name');
 if (nameErr) { this.error = nameErr; return; }
 const urlErr = validateRequired(this.url, 'URL');
 if (urlErr) { this.error = urlErr; return; }
 const credName = (this.credentialName || '').trim();
 if (!credName) {
 this.error = 'Credential is required — create one under Federation ▸ Credentials first.';
 return;
 }
 this.saving = true;
 this.error = null;
 const res = await window.pqlApi.fetch('/api/external-locations', {
 method: 'POST',
 body: {
 name: n,
 url: this.url.trim(),
 credential_name: credName,
 comment: this.comment || undefined,
 },
 });
 if (res.ok) {
 const data = res.data || {};
 window.location.href = '/external-locations/' + encodeURIComponent(data.name || n);
 } else {
 this.error = 'Create failed: ' + res.error;
 }
 this.saving = false;
 },
 };
}
