/**
 * Alert detail page Alpine factory.
 *
 * lifted the inline ``<script>`` block from
 * ``pages/alert_detail.html`` into this ESM module.
 * ``bootstrap.js`` re-attaches the factory to ``window.alertDetail``.
 *
 * Seed args (``slug`` + ``destinations``) come from the template's
 * ``x-data`` attribute as a Jinja-rendered JSON parameter object.
 */

export function alertDetail({ slug, destinations } = {}) {
 return {
 slug: slug || '',
 destinations: destinations || [],
 destForm: { kind: 'webhook', webhook_url: '', hmac_secret: '' },

 init() { /* seeded server-side */ },

 openAddDest() {
 this.destForm = { kind: 'webhook', webhook_url: '', hmac_secret: '' };
 const el = document.getElementById('pqlAddDestModal');
 if (!el || !window.bootstrap) return;
 window.bootstrap.Modal.getOrCreateInstance(el).show();
 },

 async submitAddDest() {
 const res = await window.pqlApi.fetch(
 '/api/alerts/' + encodeURIComponent(this.slug) + '/destinations',
 { method: 'POST', body: this.destForm, silent: true },
 );
 if (res.ok && res.data) {
 this.destinations = [...this.destinations, res.data];
 const el = document.getElementById('pqlAddDestModal');
 if (el && window.bootstrap) {
 window.bootstrap.Modal.getOrCreateInstance(el).hide();
 }
 } else if (window.pqlToast) {
 window.pqlToast.error(res.error || ('HTTP ' + res.status));
 }
 },

 async removeDest(dest) {
 if (!window.confirm('Remove this destination?')) return;
 const res = await window.pqlApi.fetch(
 '/api/alerts/' + encodeURIComponent(this.slug) +
 '/destinations/' + dest.id,
 { method: 'DELETE', silent: true },
 );
 if (res.ok || res.status === 204) {
 this.destinations = this.destinations.filter(
 (d) => d.id !== dest.id,
 );
 }
 },
 };
}
