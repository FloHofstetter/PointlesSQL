// Canvas-editor page (/canvas).
//
// ``canvasEditor(supportedKinds)`` takes the supported node-kind list
// as a constructor arg (was Jinja-injected as a module-scope const).
// localStorage carries the node list between visits.

const PQL_CANVAS_STORAGE_KEY = 'pqlCanvasNodes';

export function canvasEditor(supportedKinds) {
  return {
    supportedKinds: supportedKinds || [],
    nodes: [],
    compiled: '',
    errors: [],
    compiling: false,
    nextId: 1,

    init() {
      try {
        const cached = JSON.parse(localStorage.getItem(PQL_CANVAS_STORAGE_KEY) || 'null');
        if (cached && Array.isArray(cached.nodes)) {
          this.nodes = cached.nodes;
          this.nextId = cached.nextId || this.nodes.length + 1;
        }
      } catch (_e) {
        this.nodes = [];
      }
      this.$watch('nodes', () => this.persist(), { deep: true });
    },

    persist() {
      localStorage.setItem(
        PQL_CANVAS_STORAGE_KEY,
        JSON.stringify({
          nodes: this.nodes,
          nextId: this.nextId,
        })
      );
    },

    kindLabel(kind) {
      const labels = {
        read_dp: 'Read DP',
        filter: 'Filter',
        join: 'Join',
        group_by: 'Group + aggregate',
        run_model: 'Run model',
        write_dp: 'Write DP',
      };
      return labels[kind] || kind;
    },

    defaultConfig(kind) {
      switch (kind) {
        case 'read_dp':
          return { table_fqn: '' };
        case 'filter':
          return { predicate: '' };
        case 'join':
          return { right_table_fqn: '', on: '', how: 'inner' };
        case 'group_by':
          return { columns: [], aggregates: {} };
        case 'run_model':
          return { model_uri: '' };
        case 'write_dp':
          return { target_fqn: '', mode: 'overwrite', on: '' };
        default:
          return {};
      }
    },

    addNode(kind) {
      this.nodes.push({
        id: this.nextId++,
        kind,
        config: this.defaultConfig(kind),
      });
    },

    removeNode(idx) {
      this.nodes.splice(idx, 1);
    },

    moveUp(idx) {
      if (idx === 0) return;
      const tmp = this.nodes[idx - 1];
      this.nodes[idx - 1] = this.nodes[idx];
      this.nodes[idx] = tmp;
    },

    moveDown(idx) {
      if (idx === this.nodes.length - 1) return;
      const tmp = this.nodes[idx + 1];
      this.nodes[idx + 1] = this.nodes[idx];
      this.nodes[idx] = tmp;
    },

    updateAggregates(node, raw) {
      const out = {};
      (raw || '').split(',').forEach((pair) => {
        const [col, fn] = pair.split(':').map((s) => (s || '').trim());
        if (col && fn) out[col] = fn;
      });
      node.config.aggregates = out;
    },

    reset() {
      if (!confirm('Reset the canvas?')) return;
      this.nodes = [];
      this.compiled = '';
      this.errors = [];
      this.persist();
    },

    async compile() {
      this.compiling = true;
      this.errors = [];
      this.compiled = '';
      const res = await window.pqlApi.fetch('/api/canvas/compile', {
        method: 'POST',
        body: { nodes: this.nodes },
      });
      this.compiling = false;
      if (res.ok && res.data) {
        this.compiled = res.data.code || '';
        this.errors = res.data.errors || [];
      } else {
        this.errors = ['Compile request failed.'];
      }
    },

    copyCode() {
      if (!this.compiled) return;
      navigator.clipboard.writeText(this.compiled);
    },
  };
}
