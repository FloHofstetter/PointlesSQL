/**
 * Table-detail dbt overlay factory.
 *
 * Powers the optional "dbt model" card on /catalogs/<c>/schemas/<s>/
 * tables/<t>. Fetches /api/dbt/manifest and resolves whether *this*
 * UC table is materialised by a dbt model. Resolution accepts either
 * the manifest's ``relation_name`` (dbt 1.7+) or the database/schema/
 * name triple, mirroring :func:`_node_relation_name` server-side.
 */
export function dbtTableContext(catalog, schema, table) {
  return {
    dbtModel: null,
    loading: true,

    async init() {
      try {
        const r = await fetch('/api/dbt/manifest', { credentials: 'same-origin' });
        if (r.ok) {
          const data = await r.json();
          const fqn = catalog + '.' + schema + '.' + table;
          const found = (data.models || []).find(
            (m) =>
              m.relation_name === fqn ||
              (m.database === catalog && m.schema === schema && m.name === table)
          );
          this.dbtModel = found || null;
        }
      } catch (e) {
        /* dbt not configured — silent no-op */
      }
      this.loading = false;
    },
  };
}
