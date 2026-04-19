/**
 * Volume detail page Alpine factory.
 *
 * Sprint 94 lifted the inline ``<script>`` block from
 * ``pages/volume_detail.html`` into this ESM module.
 * ``bootstrap.js`` re-attaches the factory to ``window.volumeDetail``.
 *
 * Multipart upload still goes through raw ``fetch()`` because the
 * shared ``window.pqlApi.fetch`` wrapper is JSON-only — the CSRF
 * header is read directly from the meta tag.
 */

export function volumeDetail({ fullName, files } = {}) {
    return {
        fullName: fullName || '',
        files: files || [],
        uploadPath: '',
        uploadBlob: null,
        uploadName: '',
        uploading: false,

        init() { /* data seeded server-side */ },

        humanBytes(n) {
            if (!n && n !== 0) return '—';
            if (n < 1024) return n + ' B';
            if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
            return (n / (1024 * 1024)).toFixed(2) + ' MB';
        },

        onFileChange(ev) {
            const file = ev.target.files && ev.target.files[0];
            if (!file) return;
            this.uploadBlob = file;
            this.uploadName = file.name;
            if (!this.uploadPath) this.uploadPath = file.name;
        },

        async refresh() {
            const res = await window.pqlApi.fetch(
                '/api/volumes/' + encodeURIComponent(this.fullName) + '/files',
                { silent: true },
            );
            if (res.ok && res.data) this.files = res.data.files || [];
        },

        async submitUpload() {
            if (!this.uploadBlob) {
                if (window.pqlToast) window.pqlToast.error('Choose a file first.');
                return;
            }
            this.uploading = true;
            const form = new FormData();
            form.append('path', this.uploadPath);
            form.append('upload', this.uploadBlob, this.uploadName);
            const csrfMeta = document.querySelector('meta[name="csrf-token"]');
            const token = csrfMeta ? csrfMeta.content : '';
            try {
                const res = await fetch(
                    '/api/volumes/' + encodeURIComponent(this.fullName) + '/files',
                    {
                        method: 'POST',
                        headers: token ? { 'X-CSRF-Token': token } : {},
                        body: form,
                    },
                );
                if (!res.ok) {
                    const detail = await res.text();
                    throw new Error(detail || ('HTTP ' + res.status));
                }
                if (window.pqlToast) window.pqlToast.success('Uploaded.');
                this.uploadBlob = null;
                this.uploadName = '';
                this.uploadPath = '';
                if (this.$refs.fileInput) this.$refs.fileInput.value = '';
                await this.refresh();
            } catch (err) {
                if (window.pqlToast) window.pqlToast.error(err.message || 'Upload failed.');
            } finally {
                this.uploading = false;
            }
        },

        async removeFile(file) {
            if (!window.confirm('Delete ' + file.path + '?')) return;
            const res = await window.pqlApi.fetch(
                '/api/volumes/' + encodeURIComponent(this.fullName) +
                '/files/' + file.path,
                { method: 'DELETE', silent: true },
            );
            if (res.ok || res.status === 204) await this.refresh();
        },

        isConvertible(file) {
            return /\.(csv|parquet|json)$/i.test(file.path || '');
        },

        async convertToDelta(file) {
            const suggested = file.path.split('/').pop().replace(
                /\.(csv|parquet|json)$/i, '',
            );
            const table = window.prompt(
                'Target table name in ' +
                this.fullName.split('.').slice(0, 2).join('.') + ':',
                suggested,
            );
            if (!table) return;
            const res = await window.pqlApi.fetch(
                '/api/volumes/' + encodeURIComponent(this.fullName) +
                '/convert-to-delta',
                {
                    method: 'POST',
                    body: { path: file.path, table_name: table },
                    silent: true,
                },
            );
            if (res.ok && res.data) {
                if (window.pqlToast) {
                    window.pqlToast.success(
                        'Registered as Delta table: ' + res.data.full_name,
                    );
                }
            } else if (window.pqlToast) {
                window.pqlToast.error(res.error || 'Convert failed');
            }
        },
    };
}
