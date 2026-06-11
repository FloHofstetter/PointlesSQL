// Ingest source detail Alpine factory for /ingest/sources/{id}.
//
// Single ``ingestSourceDetail(sourceId)`` factory carrying the four
// tabs' state (Mappings / Schedule / Runs / Pull-now) and the
// matching API calls (/api/ingest/sources/{id}/{tables,mappings,
// schedule,runs,pulls}).

export function ingestSourceDetail(sourceId) {
  return {
    sourceId,
    source: null,
    pulling: false,
    // Mappings tab state
    availableTables: [],
    mappingsLoading: false,
    mappingsError: null,
    tableFilter: '',
    savingMappings: false,
    async load() {
      const res = await window.pqlApi.fetch('/api/ingest/sources/' + this.sourceId);
      if (res.ok && res.data) {
        this.source = res.data.source;
        this.seedAvailableFromStored();
      }
    },
    // Local-file kinds support the auto-loader pull mode (incremental
    // file discovery); other kinds never render the selector.
    isFileKind() {
      return ['file_upload', 'parquet_glob'].includes(this.source?.kind);
    },
    seedAvailableFromStored() {
      // If the source already has saved mappings, seed the
      // editor with them so the user sees current state when
      // the tab loads (before they hit "Refresh source").
      const stored = this.source?.table_mappings || [];
      if (stored.length === 0) return;
      this.availableTables = stored.map((m) => ({
        name: m.source_table,
        checked: true,
        target_fqn: m.target_fqn,
        mode: m.mode || 'full',
        high_water_col: m.high_water_col || '',
        pull_mode: m.pull_mode || 'full_reload',
      }));
    },
    async loadAvailableTables() {
      this.mappingsError = null;
      this.mappingsLoading = true;
      const res = await window.pqlApi.fetch('/api/ingest/sources/' + this.sourceId + '/tables');
      this.mappingsLoading = false;
      if (!res.ok) {
        this.mappingsError = { reason: res.error || 'List failed.' };
        return;
      }
      if (res.data && res.data.ok === false) {
        this.mappingsError = {
          reason: res.data.reason,
          hint: res.data.hint,
        };
        return;
      }
      const stored = new Map((this.source?.table_mappings || []).map((m) => [m.source_table, m]));
      const targetCatalog = 'main';
      const targetSchema = 'ingest';
      this.availableTables = (res.data.tables || []).map((name) => {
        const prev = stored.get(name);
        const basename = String(name).split('.').pop() || name;
        return {
          name,
          checked: !!prev,
          target_fqn: prev?.target_fqn || `${targetCatalog}.${targetSchema}.${basename}`,
          mode: prev?.mode || 'full',
          high_water_col: prev?.high_water_col || '',
          pull_mode: prev?.pull_mode || 'full_reload',
        };
      });
    },
    filteredTables() {
      const q = (this.tableFilter || '').toLowerCase().trim();
      if (!q) return this.availableTables;
      return this.availableTables.filter((t) => String(t.name).toLowerCase().includes(q));
    },
    toggleAll(checked) {
      for (const t of this.availableTables) {
        t.checked = !!checked;
      }
    },
    selectedCount() {
      return this.availableTables.filter((t) => t.checked).length;
    },
    async saveMappings() {
      this.savingMappings = true;
      const mappings = this.availableTables
        .filter((t) => t.checked)
        .map((t) => {
          const m = {
            source_table: t.name,
            target_fqn: t.target_fqn,
            mode: t.mode,
          };
          if (t.mode === 'incremental' && t.high_water_col) {
            m.high_water_col = t.high_water_col;
          }
          // Only the non-default value travels — absence of the key
          // is the "full reload" default on the server side.
          if (this.isFileKind() && t.pull_mode === 'auto_loader') {
            m.pull_mode = 'auto_loader';
          }
          return m;
        });
      const res = await window.pqlApi.fetch('/api/ingest/sources/' + this.sourceId + '/mappings', {
        method: 'POST',
        body: { mappings },
      });
      this.savingMappings = false;
      if (!res.ok) {
        window.pqlToast?.error?.(res.error || 'Save failed.');
        return;
      }
      window.pqlToast?.success?.(`${(res.data?.mappings || []).length} mapping(s) saved.`);
      await this.load();
    },
    // Schedule + runs state
    cronExpr: '',
    savingSchedule: false,
    runs: { latest_per_mapping: [], scheduled_history: [] },
    runsLoading: false,
    async loadRuns() {
      this.runsLoading = true;
      const res = await window.pqlApi.fetch('/api/ingest/sources/' + this.sourceId + '/runs');
      this.runsLoading = false;
      if (res.ok && res.data) {
        this.runs = res.data;
      }
    },
    async saveSchedule() {
      this.savingSchedule = true;
      const res = await window.pqlApi.fetch('/api/ingest/sources/' + this.sourceId + '/schedule', {
        method: 'PUT',
        body: { cron_expr: this.cronExpr || null },
      });
      this.savingSchedule = false;
      if (!res.ok) {
        window.pqlToast?.error?.(res.error || 'Save failed.');
        return;
      }
      window.pqlToast?.success?.('Schedule saved.');
      await this.load();
    },
    async clearSchedule() {
      this.cronExpr = '';
      this.savingSchedule = true;
      const res = await window.pqlApi.fetch('/api/ingest/sources/' + this.sourceId + '/schedule', {
        method: 'PUT',
        body: { cron_expr: null },
      });
      this.savingSchedule = false;
      if (!res.ok) {
        window.pqlToast?.error?.(res.error || 'Clear failed.');
        return;
      }
      window.pqlToast?.success?.('Schedule cleared.');
      await this.load();
    },
    async pullNow() {
      this.pulling = true;
      const res = await window.pqlApi.fetch('/api/ingest/sources/' + this.sourceId + '/pulls', {
        method: 'POST',
        body: {},
      });
      this.pulling = false;
      if (!res.ok) {
        window.pqlToast?.error?.(res.error || 'Pull failed.');
        return;
      }
      const ok = (res.data?.results || []).length;
      const fail = (res.data?.failures || []).length;
      window.pqlToast?.success?.(`Pulled ${ok} mapping(s)` + (fail ? `, ${fail} failed.` : '.'));
      await this.load();
      await this.loadRuns();
    },
  };
}
