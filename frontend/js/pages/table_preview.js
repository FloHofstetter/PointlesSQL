/**
 * Table-detail Preview-tab Alpine factory.
 *
 * follow-up — lifted the inline ``<script>`` block from
 * ``pages/table.html`` into this ESM module. ``bootstrap.js``
 * re-attaches the factory to ``window.tablePreview`` BEFORE Alpine
 * walks the DOM, fixing the boost-time race where Alpine evaluated
 * ``x-data="tablePreview()"`` before HTMX's async script-injection
 * had assigned the global. Symptom: the Preview tab rendered
 * blank until the user did a full page reload.
 *
 * The factory takes the three-part FQN as an argument so the same
 * function instance serves any table; previously each rendered
 * page baked its own copy of the function with the FQN inlined via
 * Jinja. Now the template only threads the FQN through ``x-data``.
 */

export function tablePreview(fqn) {
 const FQN = fqn || '';
 return {
 loading: true,
 ready: false,
 error: null,
 errorKind: null,
 columns: [],
 rows: [],
 truncated: false,
 versions: [],
 selectedVersion: null,
 async load() {
 this.loading = true;
 this.ready = false;
 this.error = null;
 this.errorKind = null;
 try {
 const url = '/api/catalogs/'
 + encodeURIComponent(FQN.split('.')[0])
 + '/schemas/'
 + encodeURIComponent(FQN.split('.')[1])
 + '/tables/'
 + encodeURIComponent(FQN.split('.')[2])
 + '/preview';
 const resp = await fetch(url, {
 headers: {'Accept': 'application/json'},
 });
 const data = await resp.json();
 if (!resp.ok || data.error) {
 this.error = data.detail || data.error || 'Unable to load preview';
 this.errorKind = data.kind || null;
 } else {
 this.columns = data.columns || [];
 this.rows = data.rows || [];
 this.truncated = !!data.truncated;
 this.ready = true;
 }
 } catch (err) {
 this.error = err.message || 'Network error';
 } finally {
 this.loading = false;
 }
 },
 async loadVersions() {
 try {
 const resp = await fetch(
 `/api/tables/${encodeURIComponent(FQN)}/versions`,
 {headers: {'Accept': 'application/json'}},
 );
 if (!resp.ok) return;
 const data = await resp.json();
 this.versions = data.versions || [];
 } catch (_err) { /* ignore */ }
 },
 async onVersionChange() {
 if (
 this.selectedVersion === null
 || this.selectedVersion === ''
 || this.selectedVersion === undefined
 ) {
 await this.load();
 return;
 }
 this.loading = true;
 this.ready = false;
 this.error = null;
 try {
 const url = `/api/tables/${encodeURIComponent(FQN)}`
 + `/preview-at-version?version=${this.selectedVersion}&limit=50`;
 const resp = await fetch(url, {
 headers: {'Accept': 'application/json'},
 });
 const data = await resp.json();
 if (!resp.ok) {
 this.error = data.detail || 'Unable to load historical version';
 } else {
 this.columns = data.columns || [];
 this.rows = (data.rows || []).map(
 (r) => this.columns.map((c) => r[c]),
 );
 this.truncated = data.total > this.rows.length;
 this.ready = true;
 }
 } catch (err) {
 this.error = err.message || 'Network error';
 } finally {
 this.loading = false;
 }
 },
 };
}
