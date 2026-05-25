// Auto-extracted from frontend/templates/pages/settings_notifications.html.
// Exports: notificationSettings.
//
export function notificationSettings() {
    return {
        loaded: false,
        events: [],
        prefs: {},
        savedAt: null,
        async init() { await this.load(); },
        async load() {
            try {
                const res = await fetch('/api/settings/notifications');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                this.events = data.known_event_types || [];
                this.prefs = data.prefs || {};
            } catch (e) { console.error('prefs load failed', e); }
            finally { this.loaded = true; }
        },
        async save() {
            try {
                const res = await fetch('/api/settings/notifications', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.prefs),
                });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                this.savedAt = Date.now();
                setTimeout(() => { this.savedAt = null; }, 2500);
            } catch (e) { console.error('prefs save failed', e); }
        },
    };
};
