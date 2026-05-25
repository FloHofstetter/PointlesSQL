// Notifications inbox page (/notifications).

export function notificationsInbox() {
    return {
        notifications: [],
        unreadCount: 0,
        unreadOnly: false,
        eventTypeFilter: '',
        loading: false,

        async init() {
            await this.reload();
            await this.refreshUnread();
        },

        shortEventType(et) {
            const tail = (et || '').split('.').pop() || et;
            return tail.replace(/_/g, ' ');
        },

        async reload() {
            this.loading = true;
            try {
                const params = new URLSearchParams();
                if (this.unreadOnly) params.set('unread', 'true');
                if (this.eventTypeFilter) params.set('event_type', this.eventTypeFilter);
                const res = await fetch('/api/notifications?' + params.toString());
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                this.notifications = data.notifications || [];
            } catch (e) {
                console.error('notifications load failed', e);
            } finally {
                this.loading = false;
            }
        },

        async refreshUnread() {
            try {
                const res = await fetch('/api/notifications/unread-count');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                this.unreadCount = data.unread || 0;
            } catch (e) {
                console.error('unread count failed', e);
            }
        },

        async markRead(id) {
            try {
                await fetch('/api/notifications/' + id + '/read', { method: 'POST' });
                await this.refreshUnread();
                const row = this.notifications.find(n => n.id === id);
                if (row && !row.read_at) {
                    row.read_at = new Date().toISOString();
                }
            } catch (e) {
                console.error('mark read failed', e);
            }
        },

        async markAllRead() {
            try {
                await fetch('/api/notifications/read-all', { method: 'POST' });
                await this.reload();
                await this.refreshUnread();
            } catch (e) {
                console.error('mark all read failed', e);
            }
        },
    };
}
