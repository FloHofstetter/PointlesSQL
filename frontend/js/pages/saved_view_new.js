// Auto-extracted from frontend/templates/pages/saved_view_new.html.
// Exports: savedViewForm.
//
export function savedViewForm() {
    return {
        saving: false,
        error: null,
        form: {
            title: '',
            description: '',
            sql: '',
            dp_id: null,
            target_fqn: '',
            parameters: []
        },
        addParam() {
            this.form.parameters.push({
                name: '', label: '', type: 'string', default: '', required: false
            });
        },
        async save() {
            this.error = null;
            this.saving = true;
            const body = {
                title: this.form.title,
                description: this.form.description || null,
                sql: this.form.sql,
                dp_id: this.form.dp_id || null,
                target_fqn: this.form.target_fqn || null,
                parameters: this.form.parameters
            };
            const res = await window.pqlApi.fetch('/api/views', { method: 'POST', body });
            this.saving = false;
            if (res.ok && res.data) {
                window.location.href = '/views/' + res.data.slug;
            } else {
                this.error = (res.data && res.data.detail) || res.message || 'Save failed';
            }
        }
    };
}
