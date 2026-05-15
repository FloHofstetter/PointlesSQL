/**
 * Alerts list page Alpine factory.
 *
 * lifted the inline ``<script>`` block from
 * ``pages/alerts.html`` into this ESM module. ``bootstrap.js``
 * re-attaches the factory to ``window.alertsPage`` so the
 * template's ``x-data="alertsPage({...})"`` resolves unchanged.
 *
 * The factory accepts a seed object so the server-rendered
 * Jinja blob (``{alerts, savedQueries}``) reaches the Alpine
 * scope without needing a second round-trip on first paint.
 */

export function alertsPage({ alerts, savedQueries } = {}) {
 return {
 ...window.bulkSelect(),
 alerts: alerts || [],
 savedQueries: savedQueries || [],
 creating: false,
 showToken: false,
 feedToken: '',
 form: {
 title: '',
 saved_query_id: '',
 cron_expr: '*/15 * * * *',
 condition_op: 'gt',
 threshold: 0,
 },

 init() { /* data seeded server-side via x-data */ },

 atomUrl() {
 return window.location.origin + '/alerts/feed.atom?token=' + this.feedToken;
 },

 jsonUrl() {
 return window.location.origin + '/alerts/feed.json?token=' + this.feedToken;
 },

 async ensureToken() {
 if (this.feedToken) return;
 const res = await window.pqlApi.fetch('/api/me/feed-token', { silent: true });
 if (res.ok && res.data) this.feedToken = res.data.token || '';
 },

 async rotateToken() {
 if (!window.confirm('Rotate the token? Existing subscribers will break.')) return;
 const res = await window.pqlApi.fetch(
 '/api/me/feed-token/rotate', { method: 'POST', silent: true },
 );
 if (res.ok && res.data) {
 this.feedToken = res.data.token || '';
 if (window.pqlToast) window.pqlToast.info('Token rotated.');
 }
 },

 openCreate() {
 this.form = {
 title: '',
 saved_query_id: '',
 cron_expr: '*/15 * * * *',
 condition_op: 'gt',
 threshold: 0,
 };
 const el = document.getElementById('pqlCreateAlertModal');
 if (!el || !window.bootstrap) return;
 window.bootstrap.Modal.getOrCreateInstance(el).show();
 },

 async submitCreate() {
 this.creating = true;
 const res = await window.pqlApi.fetch('/api/alerts', {
 method: 'POST', body: this.form, silent: true,
 });
 this.creating = false;
 if (res.ok && res.data) {
 if (window.pqlToast) window.pqlToast.success('Alert created.');
 const el = document.getElementById('pqlCreateAlertModal');
 if (el && window.bootstrap) {
 window.bootstrap.Modal.getOrCreateInstance(el).hide();
 }
 this.alerts = [res.data,...this.alerts];
 } else if (window.pqlToast) {
 window.pqlToast.error(res.error || ('HTTP ' + res.status));
 }
 },

 async toggleActive(alert) {
 const res = await window.pqlApi.fetch(
 '/api/alerts/' + encodeURIComponent(alert.slug),
 {
 method: 'PATCH',
 body: { is_active: !alert.is_active },
 silent: true,
 },
 );
 if (res.ok && res.data) {
 alert.is_active = res.data.is_active;
 }
 },

 async deleteAlert(alert) {
 const ok = window.pqlConfirm
  ? await window.pqlConfirm(
   'Delete alert?',
   'Permanently delete "' + alert.title + '". This cannot be undone.',
  )
  : window.confirm('Delete alert "' + alert.title + '"?');
 if (!ok) return;
 const res = await window.pqlApi.fetch(
 '/api/alerts/' + encodeURIComponent(alert.slug),
 { method: 'DELETE', silent: true },
 );
 if (res.ok || res.status === 204) {
 this.alerts = this.alerts.filter((a) => a.slug !== alert.slug);
 if (window.pqlToast) window.pqlToast.success('Alert "' + alert.title + '" deleted.');
 } else if (window.pqlToast) {
 window.pqlToast.error(res.error || 'Failed to delete alert.');
 }
 },

 async bulkDelete() {
 const slugs = this.selectedKeys;
 if (!slugs.length) return;
 const ok = window.pqlConfirm
  ? await window.pqlConfirm(
   'Delete ' + slugs.length + ' alert' + (slugs.length === 1 ? '' : 's') + '?',
   'Permanently delete the selected alerts. This cannot be undone.',
  )
  : window.confirm('Delete ' + slugs.length + ' alert(s)?');
 if (!ok) return;
 let failed = 0;
 await Promise.all(slugs.map(async (slug) => {
 const res = await window.pqlApi.fetch(
 '/api/alerts/' + encodeURIComponent(slug),
 { method: 'DELETE', silent: true },
 );
 if (!(res.ok || res.status === 204)) failed++;
 }));
 // Drop every slug we tried to delete from the local list.
 // Failed ones will reappear on next page load; the toast below
 // tells the user how many ops failed.
 const slugSet = new Set(slugs);
 this.alerts = this.alerts.filter((a) => !slugSet.has(a.slug));
 this.clearSelection();
 if (window.pqlToast) {
 if (failed === 0) {
 window.pqlToast.success('Deleted ' + slugs.length + ' alert' + (slugs.length === 1 ? '' : 's') + '.');
 } else {
 window.pqlToast.error(failed + ' of ' + slugs.length + ' deletions failed.');
 }
 }
 },

 async bulkToggleActive() {
 const slugs = this.selectedKeys;
 if (!slugs.length) return;
 const selectedAlerts = this.alerts.filter((a) => slugs.includes(a.slug));
 // Mixed selection: if any are active, pause them all; else resume.
 const anyActive = selectedAlerts.some((a) => a.is_active);
 const targetActive = !anyActive;
 let failed = 0;
 await Promise.all(selectedAlerts.map(async (a) => {
 if (a.is_active === targetActive) return;
 const res = await window.pqlApi.fetch(
 '/api/alerts/' + encodeURIComponent(a.slug),
 { method: 'PATCH', body: { is_active: targetActive }, silent: true },
 );
 if (res.ok && res.data) a.is_active = res.data.is_active;
 else failed++;
 }));
 this.clearSelection();
 if (window.pqlToast) {
 if (failed === 0) {
 window.pqlToast.success((targetActive ? 'Resumed ' : 'Paused ') + selectedAlerts.length + ' alert(s).');
 } else {
 window.pqlToast.error(failed + ' of ' + selectedAlerts.length + ' updates failed.');
 }
 }
 },
 };
}
