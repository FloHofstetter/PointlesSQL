// Personal webhook-subscription CRUD page (/me/subscriptions).
// Single ``meSubscriptions`` factory.

export function meSubscriptions() {
    return {
        subs: [],
        loading: false,
        showCreate: false,
        lastSecret: '',
        form: {
            webhook_url: '',
            event_type_filter: '*',
            dp_ref_filter: '',
        },

        async init() {
            await this.reload();
        },

        async reload() {
            this.loading = true;
            try {
                const res = await fetch('/api/me/subscriptions');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                this.subs = data.subscriptions || [];
            } catch (e) {
                console.error('me-subs reload failed', e);
            } finally {
                this.loading = false;
            }
        },

        cancelCreate() {
            this.showCreate = false;
            this.form = { webhook_url: '', event_type_filter: '*', dp_ref_filter: '' };
        },

        async create() {
            const body = {
                webhook_url: this.form.webhook_url,
                event_type_filter: this.form.event_type_filter,
                dp_ref_filter: this.form.dp_ref_filter || null,
            };
            try {
                const res = await fetch('/api/me/subscriptions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                this.lastSecret = data.hmac_secret || '';
                window.pqlToast?.success('Subscription created.');
                this.cancelCreate();
                await this.reload();
            } catch (e) {
                console.error('subscription create failed', e);
                window.pqlToast?.error(`Failed to create subscription: ${e.message}`);
            }
        },

        async toggle(id, isActive) {
            try {
                const res = await fetch('/api/me/subscriptions/' + id, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: !!isActive }),
                });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                window.pqlToast?.success(`Subscription ${isActive ? 'enabled' : 'paused'}.`);
            } catch (e) {
                console.error('subscription toggle failed', e);
                window.pqlToast?.error(`Failed to update subscription: ${e.message}`);
            }
        },

        async remove(id) {
            try {
                const res = await fetch('/api/me/subscriptions/' + id, { method: 'DELETE' });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                window.pqlToast?.success('Subscription removed.');
                await this.reload();
            } catch (e) {
                console.error('subscription delete failed', e);
                window.pqlToast?.error(`Failed to remove subscription: ${e.message}`);
            }
        },
    };
}
