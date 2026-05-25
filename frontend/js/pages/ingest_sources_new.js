// Ingest-source create wizard (/ingest/sources/new).

export function ingestSourceCreate() {
    return {
        form: {
            name: '',
            kind: '',
            config: {},
            secrets: {}
        },
        probeTable: '',
        probing: false,
        creating: false,
        probeResult: null,
        error: null,
        iconFor(kind) {
            return {
                file_upload: 'bi-file-earmark-arrow-up',
                s3: 'bi-cloud',
                http: 'bi-globe',
                postgres: 'bi-database',
                mysql: 'bi-database',
                sqlite: 'bi-database',
                parquet_glob: 'bi-files'
            }[kind] || 'bi-plug';
        },
        async uploadFile() {
            const input = this.$refs.fileInput;
            const file = input?.files?.[0];
            if (!file) return;
            // Stash locally; the real workspace volume upload is not
            // wired yet, so the file picker doubles as a friendly
            // path resolver for the server-side path field below.
            this.form.config.path = file.name;
            window.pqlToast?.info?.('Path captured; full upload wiring lands later.');
        },
        async probe() {
            this.error = null;
            this.probeResult = null;
            this.probing = true;
            const body = {
                kind: this.form.kind,
                config: this.form.config,
                secrets: this.form.secrets,
            };
            if (this.probeTable) {
                body.source_table = this.probeTable;
            }
            const res = await window.pqlApi.fetch('/api/ingest/probe', {
                method: 'POST',
                body,
            });
            this.probing = false;
            if (!res.ok) {
                this.error = { reason: res.error || 'Probe request failed.', hint: null };
                return;
            }
            if (res.data && res.data.ok === false) {
                this.error = { reason: res.data.reason, hint: res.data.hint };
                return;
            }
            this.probeResult = res.data;
        },
        async create() {
            this.error = null;
            this.creating = true;
            const res = await window.pqlApi.fetch('/api/ingest/sources', {
                method: 'POST',
                body: {
                    name: this.form.name,
                    kind: this.form.kind,
                    config: this.form.config,
                    secrets: this.form.secrets,
                },
            });
            this.creating = false;
            if (!res.ok) {
                this.error = { reason: res.error || 'Save failed.', hint: null };
                return;
            }
            const id = res.data?.source?.id;
            if (id) {
                window.pqlToast?.success?.('Source created.');
                window.location.href = '/ingest/sources/' + id;
            }
        }
    };
}
