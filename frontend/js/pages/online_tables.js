// Online-tables browser (/online-tables).
//
// onlineTables: synced-table list + create card + per-row "Sync now" /
// "Delete" actions + an expandable lookup tester that point-reads the
// synced target by primary key.

export function onlineTables() {
  return {
    tables: [],
    loading: false,
    error: '',

    creator: null,
    creatorError: '',
    creating: false,

    syncing: '',

    lookupTable: null,
    lookup: { key_column: '', key: '', limit: 10 },
    lookupResult: null,
    lookupError: '',
    lookupRunning: false,

    async init() {
      await this.load();
    },

    async load() {
      this.error = '';
      this.loading = true;
      const res = await window.pqlApi.fetch('/api/online-tables');
      this.loading = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to load online tables';
        return;
      }
      this.tables = res.data?.online_tables || [];
    },

    statusBadge(status) {
      if (status === 'ok') return 'text-bg-success';
      if (status === 'failed') return 'text-bg-danger';
      if (status === 'syncing') return 'text-bg-info';
      return 'text-bg-secondary';
    },

    openCreate() {
      this.creatorError = '';
      this.creator = {
        name: '',
        source_fqn: '',
        target_url: '',
        target_table: '',
        primary_keys: '',
        mode: 'full',
      };
    },

    async create() {
      this.creatorError = '';
      this.creating = true;
      const res = await window.pqlApi.fetch('/api/online-tables', {
        method: 'POST',
        body: {
          name: this.creator.name.trim(),
          source_fqn: this.creator.source_fqn.trim(),
          target_url: this.creator.target_url.trim(),
          target_table: this.creator.target_table.trim(),
          primary_keys: this.creator.primary_keys.trim() || null,
          mode: this.creator.mode,
        },
      });
      this.creating = false;
      if (!res.ok) {
        this.creatorError = res.error || 'Failed to create online table';
        return;
      }
      this.creator = null;
      await this.load();
    },

    async syncNow(table) {
      this.error = '';
      this.syncing = table.name;
      const res = await window.pqlApi.fetch(
        `/api/online-tables/${encodeURIComponent(table.name)}/sync`,
        { method: 'POST' }
      );
      this.syncing = '';
      if (!res.ok) {
        this.error = res.error || 'Sync failed';
      }
      await this.load();
    },

    async remove(table) {
      if (!window.confirm(`Delete online table "${table.name}"?`)) return;
      const res = await window.pqlApi.fetch(
        `/api/online-tables/${encodeURIComponent(table.name)}`,
        { method: 'DELETE' }
      );
      if (!res.ok) {
        this.error = res.error || 'Delete failed';
        return;
      }
      await this.load();
    },

    toggleLookup(table) {
      if (this.lookupTable && this.lookupTable.name === table.name) {
        this.lookupTable = null;
        return;
      }
      this.lookupTable = table;
      this.lookupResult = null;
      this.lookupError = '';
      this.lookup = {
        key_column: table.primary_keys?.[0] || '',
        key: '',
        limit: 10,
      };
    },

    get lookupColumns() {
      if (!this.lookupResult || this.lookupResult.rows.length === 0) return [];
      return Object.keys(this.lookupResult.rows[0]);
    },

    async runLookup() {
      this.lookupError = '';
      this.lookupRunning = true;
      const res = await window.pqlApi.fetch(
        '/api/online-tables/' +
          encodeURIComponent(this.lookupTable.name) +
          '/lookup?key_column=' +
          encodeURIComponent(this.lookup.key_column) +
          '&key=' +
          encodeURIComponent(this.lookup.key) +
          '&limit=' +
          encodeURIComponent(this.lookup.limit || 10)
      );
      this.lookupRunning = false;
      if (!res.ok) {
        this.lookupError = res.error || 'Lookup failed';
        this.lookupResult = null;
        return;
      }
      this.lookupResult = res.data;
    },
  };
}
