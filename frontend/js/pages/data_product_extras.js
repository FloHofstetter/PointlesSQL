// Auto-extracted from frontend/templates/pages/data_product.html.
// Exports: ingestStatusBand, dpReleasesCard.
//
export function ingestStatusBand(catalog, schema) {
    return {
        sources: [],
        async load() {
            const res = await window.pqlApi.fetch(
                `/api/data-products/${catalog}/${schema}/ingest-status`
            );
            if (res.ok && res.data) {
                this.sources = res.data.sources || [];
            }
        }
    };
}

// releases card factory.  Kept outside the main
// dataProductDetail() data so the card stays self-contained.
export function dpReleasesCard() {
    return {
        releases: [],
        loaded: false,
        async load(catalog, schema) {
            try {
                const res = await fetch('/api/data-products/' + catalog + '/' + schema + '/releases');
                if (res.ok) {
                    const data = await res.json();
                    this.releases = (data.releases || []).slice(0, 5);
                }
            } catch (e) {
                this.releases = [];
            }
            this.loaded = true;
        }
    };
}
