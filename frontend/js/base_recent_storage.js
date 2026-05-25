/**
 * "Recent catalogs" + "Recent tables" localStorage writers.
 *
 * Side-effect module. Reads ``meta[name="active-catalog"]`` /
 * ``active-schema`` / ``active-table`` set in base.html, and writes
 * the visited catalog (and table FQN if all three are set) into the
 * per-workspace localStorage lists the home dashboard's "Recent
 * catalogs" card and the catalog-tree sidebar's "Recent tables" list
 * consume.
 *
 * Pre-W2 these were two inline ``<script>`` blocks inside ``{% if
 * active_catalog %}`` / ``{% if active_table … %}`` gates. Now the
 * gates live as meta-tag presence checks (empty content == no
 * record), so the JS file stays Jinja-free.
 *
 * Imported once from ``bootstrap.js``.
 */

(function () {
  try {
    const slugMeta = document.querySelector('meta[name="workspace-slug"]');
    const slug = slugMeta && slugMeta.content ? slugMeta.content : 'default';

    const catMeta = document.querySelector('meta[name="active-catalog"]');
    const name = catMeta && catMeta.content ? catMeta.content : '';
    if (!name) return;

    const KEY = 'pql.recentCatalogs.' + slug;
    const MAX = 5;
    let items = [];
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) items = parsed;
    }
    items = items.filter((i) => i && i.name !== name);
    items.unshift({ name: name, ts: Date.now() });
    if (items.length > MAX) items.length = MAX;
    localStorage.setItem(KEY, JSON.stringify(items));
  } catch (e) {
    /* quota / disabled storage — ignore */
  }
})();

(function () {
  try {
    const slugMeta = document.querySelector('meta[name="workspace-slug"]');
    const slug = slugMeta && slugMeta.content ? slugMeta.content : 'default';

    const catMeta = document.querySelector('meta[name="active-catalog"]');
    const schMeta = document.querySelector('meta[name="active-schema"]');
    const tabMeta = document.querySelector('meta[name="active-table"]');
    const catalog = catMeta && catMeta.content ? catMeta.content : '';
    const schema = schMeta && schMeta.content ? schMeta.content : '';
    const table = tabMeta && tabMeta.content ? tabMeta.content : '';
    if (!catalog || !schema || !table) return;

    const KEY = 'pql.recentTables.' + slug;
    const MAX = 5;
    const fqn = catalog + '.' + schema + '.' + table;
    let items = [];
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) items = parsed;
    }
    items = items.filter((i) => i && i.fqn !== fqn);
    items.unshift({
      fqn: fqn,
      catalog: catalog,
      schema: schema,
      table: table,
      ts: Date.now(),
    });
    if (items.length > MAX) items.length = MAX;
    localStorage.setItem(KEY, JSON.stringify(items));
    window.dispatchEvent(new CustomEvent('pql:recent-tables-changed', { detail: { items } }));
  } catch (e) {
    /* quota / disabled storage — ignore */
  }
})();
