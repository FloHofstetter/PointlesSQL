/**
 * Schema-detail dbt + ML overlay factory.
 *
 * Powers four pieces on /catalogs/<c>/schemas/<s>:
 *  - a "dbt" badge inline next to each table-name row when that
 *    table is materialised by a dbt model
 *  - a "Recent dbt runs" mini-card under the Tables card
 *  - a "ml" badge inline next to each table-name row when that
 *    table is a model-prediction destination
 *  - a "Recent ML registrations" mini-card under the Tables card
 *   
 *
 * All four are silently absent when the install has no dbt manifest
 * or no MLflow registry — see the dbt+MLflow hand-off plan for why
 * the joins live client-side rather than on the server.
 */
export function dbtSchemaContext(catalog, schema) {
 return {
 dbtAvailable: false,
 dbtModelByTable: {},
 dbtRuns: [],
 dbtRunsLoading: true,

 mlAvailable: false,
 mlModelByTable: {},
 mlModels: [],
 mlModelsLoading: true,

 async init() {
 try {
 const r = await fetch('/api/dbt/manifest', { credentials: 'same-origin' });
 if (r.ok) {
 const data = await r.json();
 const map = {};
 for (const m of (data.models || [])) {
 if (m.database === catalog && m.schema === schema) {
 map[m.name] = m.unique_id;
 }
 }
 this.dbtModelByTable = map;
 this.dbtAvailable = Object.keys(map).length > 0;
 }
 } catch (e) { /* dbt not configured — silent no-op */ }

 try {
 const r = await fetch('/api/dbt/runs?limit=5', { credentials: 'same-origin' });
 if (r.ok) {
 const data = await r.json();
 this.dbtRuns = Array.isArray(data.runs) ? data.runs : [];
 }
 } catch (e) { /* runs unavailable — silent no-op */ }
 this.dbtRunsLoading = false;

 try {
 const url = `/api/ml/table-relations?catalog=${encodeURIComponent(catalog)}`
 + `&schema=${encodeURIComponent(schema)}`;
 const r = await fetch(url, { credentials: 'same-origin' });
 if (r.ok) {
 const data = await r.json();
 const tables = data.tables || {};
 const map = {};
 const prefix = `${catalog}.${schema}.`;
 for (const fqn of Object.keys(tables)) {
 if (!fqn.startsWith(prefix)) continue;
 const tableName = fqn.slice(prefix.length);
 const scoring = tables[fqn].scoring_models || [];
 if (scoring.length > 0) {
 map[tableName] = scoring[0].full_name;
 }
 }
 this.mlModelByTable = map;
 }
 } catch (e) { /* no ML edges — silent no-op */ }

 try {
 const url = `/api/models?catalog_name=${encodeURIComponent(catalog)}`
 + `&schema_name=${encodeURIComponent(schema)}`;
 const r = await fetch(url, { credentials: 'same-origin' });
 if (r.ok) {
 const data = await r.json();
 this.mlModels = (data.models || []).slice(0, 5);
 }
 } catch (e) { /* MLflow not configured — silent no-op */ }
 this.mlModelsLoading = false;
 this.mlAvailable = this.mlModels.length > 0
 || Object.keys(this.mlModelByTable).length > 0;
 },
 };
}
