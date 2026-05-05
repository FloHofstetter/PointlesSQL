/**
 * Catalog-tree sidebar Alpine factory + URL-path helpers.
 *
 * follow-up — lifted the inline ``<script>`` block from
 * ``components/sidebar.html`` into this ESM module. ``bootstrap.js``
 * imports the factory and re-attaches it to ``window.catalogTree``
 * before Alpine's ``x-data`` walk runs, so the sidebar survives the
 * new ``hx-select-oob="#pql-context-panel"`` boost-cycle without
 * relying on inline scripts being re-evaluated mid-swap.
 */

// Sprint 28.4: keys are namespaced by workspace slug so a user that
// switches between workspace-A and workspace-B in the same browser
// tab gets independent tree caches and recent-tables lists.  The slug
// is read fresh on every key access — there is no caching at module
// load — so the meta-tag swap that follows /auth/switch-workspace's
// reload is picked up without a hard module reload.
function workspaceSlug() {
 const meta = document.querySelector('meta[name="workspace-slug"]');
 return meta && meta.content ? meta.content : 'default';
}
const STORAGE_KEY = () => 'pql.tree.' + workspaceSlug();
const OPEN_KEY = () => 'pql.tree.open.' + workspaceSlug();
const RECENTS_KEY = () => 'pql.recentTables.' + workspaceSlug();
function primaryCatalog() {
 const meta = document.querySelector('meta[name="workspace-primary-catalog"]');
 return meta && meta.content ? meta.content : '';
}

export function pathFromUrl() {
 const cat = window.location.pathname.match(
 /^\/catalogs\/([^/]+)(?:\/schemas\/([^/]+)(?:\/tables\/([^/]+))?)?/,
 );
 if (cat) {
 return {
 catalog: cat[1] || '',
 schema: cat[2] || '',
 table: cat[3] || '',
 volume: '',
 model: '',
 };
 }
 const mdl = window.location.pathname.match(
 /^\/models\/([^/.]+)\.([^/.]+)\.([^/.]+)/,
 );
 if (mdl) {
 return {
 catalog: mdl[1] || '',
 schema: mdl[2] || '',
 table: '',
 volume: '',
 model: mdl[3] || '',
 };
 }
 const vol = window.location.pathname.match(
 /^\/volumes\/([^/.]+)\.([^/.]+)\.([^/.]+)/,
 );
 if (vol) {
 return {
 catalog: vol[1] || '',
 schema: vol[2] || '',
 table: '',
 volume: vol[3] || '',
 model: '',
 };
 }
 return { catalog: '', schema: '', table: '', volume: '', model: '' };
}

function loadRecents() {
 try {
 const raw = localStorage.getItem(RECENTS_KEY());
 if (!raw) return [];
 const parsed = JSON.parse(raw);
 return Array.isArray(parsed) ? parsed : [];
 } catch (e) {
 return [];
 }
}

function fqnParts(fqn) {
 const parts = (fqn || '').split('.');
 if (parts.length !== 3) return null;
 return { catalog: parts[0], schema: parts[1], table: parts[2], fqn };
}

export function catalogTree() {
 return {
 tree: null,
 loading: false,
 error: null,
 open: {},
 activePath: pathFromUrl(),
 query: '',
 recents: loadRecents(),
 searchResults: [],
 searching: false,
 searchTruncated: false,

 isOpen(key) {
 return !!this.open[key];
 },

 toggle(key) {
 this.open[key] = !this.open[key];
 try {
 sessionStorage.setItem(OPEN_KEY(), JSON.stringify(this.open));
 } catch (e) {}
 },

 normalisedQuery() {
 return (this.query || '').trim().toLowerCase();
 },
 tableVisible(t) {
 const q = this.normalisedQuery();
 if (!q) return true;
 return (t.name || '').toLowerCase().includes(q);
 },
 volumeVisible(v) {
 const q = this.normalisedQuery();
 if (!q) return true;
 return (v.name || '').toLowerCase().includes(q);
 },
 modelVisible(m) {
 const q = this.normalisedQuery();
 if (!q) return true;
 return (m.name || '').toLowerCase().includes(q);
 },
 schemaVisible(c, s) {
 const q = this.normalisedQuery();
 if (!q) return true;
 if ((s.name || '').toLowerCase().includes(q)) return true;
 if ((s.tables || []).some((t) => this.tableVisible(t))) return true;
 if ((s.volumes || []).some((v) => this.volumeVisible(v))) return true;
 return (s.models || []).some((m) => this.modelVisible(m));
 },
 catalogVisible(c) {
 const q = this.normalisedQuery();
 if (!q) return true;
 if ((c.name || '').toLowerCase().includes(q)) return true;
 return (c.schemas || []).some((s) => this.schemaVisible(c, s));
 },
 isCatalogExpanded(c) {
 if (this.normalisedQuery()) return this.catalogVisible(c);
 return this.isOpen('c:' + c.name);
 },
 isSchemaExpanded(c, s) {
 if (this.normalisedQuery()) return this.schemaVisible(c, s);
 return this.isOpen('s:' + c.name + '.' + s.name);
 },
 filteredEmpty() {
 if (!this.tree || !this.normalisedQuery()) return false;
 return !this.tree.some((c) => this.catalogVisible(c));
 },
 onQueryChange() {
 const q = this.normalisedQuery();
 if (q.length < 2) {
 this.searchResults = [];
 this.searchTruncated = false;
 return;
 }
 this.fetchServerSearch(q);
 },
 async fetchServerSearch(q) {
 this.searching = true;
 try {
 const res = await fetch(
 '/api/tree/search?q=' + encodeURIComponent(q),
 );
 if (!res.ok) throw new Error('HTTP ' + res.status);
 const data = await res.json();
 this.searchResults = Array.isArray(data.matches)
 ? data.matches
 : [];
 this.searchTruncated = !!data.truncated;
 } catch (e) {
 this.searchResults = [];
 this.searchTruncated = false;
 } finally {
 this.searching = false;
 }
 },
 clearRecents() {
 try {
 localStorage.removeItem(RECENTS_KEY());
 } catch (e) {}
 this.recents = [];
 fetch('/api/recents', { method: 'DELETE' }).catch(() => {});
 },
 async fetchRecents() {
 try {
 const res = await fetch('/api/recents');
 if (!res.ok) return;
 const data = await res.json();
 if (!Array.isArray(data.recents)) return;
 const items = data.recents
.map((r) => fqnParts(r.table_full_name))
.filter((p) => p !== null);
 if (items.length > 0) {
 this.recents = items;
 }
 } catch (e) {}
 },

 async load() {
 let hadOpenState = false;
 try {
 const cached = sessionStorage.getItem(STORAGE_KEY());
 if (cached) this.tree = JSON.parse(cached);
 const openCached = sessionStorage.getItem(OPEN_KEY());
 if (openCached) {
 this.open = JSON.parse(openCached);
 hadOpenState = true;
 }
 } catch (e) {}

 if (!hadOpenState) {
 if (this.activePath.catalog) {
 this.open['c:' + this.activePath.catalog] = true;
 }
 if (this.activePath.catalog && this.activePath.schema) {
 this.open[
 's:' +
 this.activePath.catalog +
 '.' +
 this.activePath.schema
 ] = true;
 }
 // Sprint 28.4: pre-expand the workspace's primary-pinned
 // catalog on first load so the sidebar opens at the most
 // relevant tree node without forcing the user to drill down.
 const primary = primaryCatalog();
 if (primary) {
 this.open['c:' + primary] = true;
 }
 try {
 sessionStorage.setItem(OPEN_KEY(), JSON.stringify(this.open));
 } catch (e) {}
 }

 if (!this.tree) await this.fetchTree();
 else this.fetchTree();
 this.fetchRecents();
 },

 async reload() {
 try {
 sessionStorage.removeItem(STORAGE_KEY());
 } catch (e) {}
 this.tree = null;
 await this.fetchTree();
 },

 async fetchTree() {
 this.loading = true;
 this.error = null;
 try {
 const res = await fetch('/api/tree');
 if (!res.ok) throw new Error('HTTP ' + res.status);
 const data = await res.json();
 this.tree = data;
 try {
 sessionStorage.setItem(STORAGE_KEY(), JSON.stringify(data));
 } catch (e) {}
 } catch (e) {
 if (!this.tree) {
 this.error = 'Failed to load tree: ' + e.message;
 }
 } finally {
 this.loading = false;
 }
 },
 };
}
