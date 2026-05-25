// Auto-extracted from frontend/templates/components/footer_bar.html.
// Exports: footerBar.
//
// footer-bar status poller.
export function footerBar() {
    return {
        loading: false,
        backends: [
            { name: 'soyuz', label: 'soyuz', status: 'na', title: '' },
            { name: 'mlflow', label: 'mlflow', status: 'na', title: '' },
            { name: 'dbt', label: 'dbt', status: 'na', title: '' },
            { name: 'hermes', label: 'hermes', status: 'na', title: '' },
        ],
        async load() {
            this.loading = true;
            try {
                if (!window.pqlApi) return;
                const res = await window.pqlApi.fetch(
                    '/api/health/backends',
                    { silent: true }
                );
                if (!res || !res.ok || !res.data) return;
                const data = res.data;
                this.backends = this.backends.map(b => ({
                    ...b,
                    status: data[b.name] || 'na',
                    title: b.name === 'soyuz' && data.soyuz_url
                        ? data.soyuz_url + ' · last checked: ' + new Date().toLocaleTimeString()
                        : 'last checked: ' + new Date().toLocaleTimeString(),
                }));
            } catch (e) {
                // Silent — footer is ambient awareness only.
            } finally {
                this.loading = false;
            }
        },
    };
};
// Poll every 60 s.
document.addEventListener('alpine:initialized', () => {
    setInterval(() => {
        const root = document.querySelector('.pql-footer-bar');
        if (root && root._x_dataStack) {
            const ctx = root._x_dataStack[0];
            if (ctx && typeof ctx.load === 'function') ctx.load();
        }
    }, 60000);
});
