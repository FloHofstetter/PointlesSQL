// Auto-extracted from frontend/templates/components/notification_bell.html.
// Exports: notificationBell.
//
export function notificationBell() {
    return {
        unread: 0,
        _sse: null,
        async init() {
            await this.refresh();
            setInterval(() => this.refresh(), 60000);
            this._openSse();
        },
        async refresh() {
            try {
                const res = await fetch('/api/notifications/unread-count');
                if (!res.ok) return;
                const data = await res.json();
                this.unread = data.unread || 0;
            } catch (e) { /* swallow */ }
        },
        _openSse() {
            if (this._sse) return;
            try {
                const es = new EventSource('/api/notifications/stream');
                this._sse = es;
                es.addEventListener('notification', (ev) => {
                    this.unread = (this.unread || 0) + 1;
                });
                es.addEventListener('error', () => {
                    es.close();
                    this._sse = null;
                    // Fall back to the 60 s poll already running.
                });
            } catch (e) { /* swallow */ }
        },
    };
}
