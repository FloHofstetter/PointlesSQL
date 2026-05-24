// ML overlay for the table-detail page.
// Reads /api/ml/table-relations (scoped to the table's catalog +
// schema) and exposes the matching entry's scoring_models list so
// the template can render an "ML model" card analog to the dbt one.

export const mlTableContext = (catalog, schema, table) => ({
    trainedModels: [],
    scoringModels: [],
    loading: true,

    async init() {
        const fqn = `${catalog}.${schema}.${table}`;
        try {
            const url = `/api/ml/table-relations?catalog=${encodeURIComponent(catalog)}`
                + `&schema=${encodeURIComponent(schema)}`;
            const r = await fetch(url, { credentials: 'same-origin' });
            if (r.ok) {
                const data = await r.json();
                const entry = (data.tables || {})[fqn] || {};
                this.trainedModels = entry.trained_models || [];
                this.scoringModels = entry.scoring_models || [];
            }
        } catch (e) { /* silent — no ML lineage yet */ }
        this.loading = false;
    },

    get hasMl() {
        return this.scoringModels.length > 0 || this.trainedModels.length > 0;
    },
});
