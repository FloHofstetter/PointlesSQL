// Auto-extracted from frontend/templates/pages/data_products_followed.html.
// Exports: dataProductsFollowed.
//
export function dataProductsFollowed() {
    return {
        recommendations: [],
        recommendationsLoaded: false,

        init() {
            this.loadRecommendations();
        },

        async loadRecommendations() {
            this.recommendationsLoaded = false;
            try {
                const res = await fetch('/api/data-products/recommendations?limit=5');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                this.recommendations = data.recommendations || [];
            } catch (e) {
                console.error('recommendations load failed', e);
                this.recommendations = [];
            } finally {
                this.recommendationsLoaded = true;
            }
        },
    };
};
