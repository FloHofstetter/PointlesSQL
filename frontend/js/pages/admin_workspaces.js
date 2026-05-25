// Auto-extracted from frontend/templates/pages/admin_workspaces.html.
// Exports: adminWorkspaces, archiveButton.
//
export function adminWorkspaces() {
    return {
        form: { slug: '', name: '', description: '' },
        creating: false,
        error: '',

        async create() {
            this.error = '';
            this.creating = true;
            const body = {
                slug: this.form.slug.trim(),
                name: this.form.name.trim(),
            };
            if (this.form.description) body.description = this.form.description.trim();
            const res = await window.pqlApi.fetch('/api/admin/workspaces', {
                method: 'POST',
                body: body,
            });
            this.creating = false;
            if (!res.ok) {
                this.error = res.error || 'Failed to create workspace';
                return;
            }
            window.pqlApi.reloadWithToast('Workspace created.');
        },
    };
};

export function archiveButton(workspaceId, slug) {
    return {
        async archive() {
            if (!window.confirm('Archive workspace "' + slug + '"? Data is preserved but the workspace hides from listings.')) {
                return;
            }
            const res = await window.pqlApi.fetch(
                '/api/admin/workspaces/' + workspaceId + '/archive',
                { method: 'POST' },
            );
            if (!res.ok) return;
            window.pqlApi.reloadWithToast('Workspace archived.');
        },
    };
};
