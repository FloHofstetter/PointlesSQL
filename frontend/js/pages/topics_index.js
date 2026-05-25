// Auto-extracted from frontend/templates/pages/topics_index.html.
// Exports: topicsIndex.
//
export function topicsIndex(ctx) {
    ctx = ctx || {};
    return {
        isAdmin: !!ctx.is_admin,
        loaded: false,
        topics: [],
        creating: false,
        submitting: false,
        newName: '',
        newDesc: '',
        async init() {
            // ``/topics?new=1`` deep-links open the
            // inline create form so the quick-create menu + topics
            // sidebar can drop the user straight into authoring.
            try {
                if (new URL(location.href).searchParams.get('new') === '1') {
                    this.creating = true;
                }
            } catch (_) { /* URL parse never throws in practice */ }
            await this.load();
        },
        async load() {
            try {
                const res = await fetch('/api/topics');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                this.topics = data.topics || [];
            } catch (e) { console.error('topics load failed', e); }
            finally { this.loaded = true; }
        },
        async create() {
            this.submitting = true;
            const name = this.newName.trim();
            try {
                const res = await fetch('/api/topics', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        display_name: name,
                        description_md: this.newDesc.trim(),
                    }),
                });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                window.pqlToast?.success(`Topic "${name}" created.`);
                this.newName = '';
                this.newDesc = '';
                this.creating = false;
                await this.load();
            } catch (e) {
                console.error('topic create failed', e);
                window.pqlToast?.error(`Failed to create topic: ${e.message}`);
            } finally {
                this.submitting = false;
            }
        },
    };
};
