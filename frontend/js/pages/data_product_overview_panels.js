// Overview-tab panels: lifecycle, bitemporal, consumption-enforcement,
// event-port, infrastructure, use-cases + rating.  Each factory is
// self-contained and fetches its own sub-endpoint, matching the
// existing dataProductPortsPanel / dataProductSemanticPanel style.

function dpBase(catalog, schema) {
  return '/api/data-products/' + encodeURIComponent(catalog) + '/' + encodeURIComponent(schema);
}

const LIFECYCLE_LABELS = {
  'promote-to-active': 'Promote to active',
  deprecate: 'Deprecate',
  retire: 'Retire',
  archive: 'Archive',
  restore: 'Restore',
};

function _stateToSlug(currentState, targetState) {
  if (targetState === 'active') {
    return currentState === 'archived' ? 'restore' : 'promote-to-active';
  }
  if (targetState === 'deprecated') return 'deprecate';
  if (targetState === 'retired') return 'retire';
  if (targetState === 'archived') return 'archive';
  return targetState;
}

export function dataProductLifecyclePanel(catalog, schema, canManage) {
  return {
    catalog,
    schema,
    canManage: !!canManage,
    state: '',
    changedAt: '',
    replacement: null,
    targets: [],
    history: [],
    error: '',

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/lifecycle', {
        silent: true,
      });
      if (res.status === 0) {
        this.error = 'Lifecycle load failed: ' + res.error;
        return;
      }
      if (!res.ok) {
        this.error = 'Failed to load lifecycle (HTTP ' + res.status + ')';
        return;
      }
      const data = res.data || {};
      this.state = data.state || 'active';
      this.changedAt = data.changed_at || '';
      this.replacement = data.replacement_uri || null;
      const reachable = data.reachable_targets || data.allowed_targets || [];
      this.targets = reachable
        .filter((t) => t !== this.state)
        .map((t) => _stateToSlug(this.state, t));
      this.history = data.history || [];
    },

    badgeClass() {
      const map = {
        active: 'bg-success',
        draft: 'bg-info text-dark',
        deprecated: 'bg-warning text-dark',
        retired: 'bg-danger',
        archived: 'bg-secondary',
      };
      return map[this.state] || 'bg-secondary';
    },

    targetLabel(t) {
      return LIFECYCLE_LABELS[t] || t;
    },

    async transition(target) {
      this.error = '';
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/lifecycle/' + encodeURIComponent(target),
        { method: 'POST', body: {}, silent: true }
      );
      if (res.status === 0) {
        this.error = 'Transition failed: ' + res.error;
        return;
      }
      if (!res.ok) {
        this.error = 'Transition failed (HTTP ' + res.status + ')';
        return;
      }
      await this.reload();
    },
  };
}

export function dataProductBitemporalPanel(catalog, schema) {
  return {
    catalog,
    schema,
    enforcement: '',
    requireEventTime: false,
    eventCol: '',
    procCol: '',
    error: '',

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/discovery', {
        silent: true,
      });
      if (res.status === 0) {
        this.error = 'Bitemporal load failed: ' + res.error;
        return;
      }
      if (!res.ok) return;
      const env = res.data || {};
      const bt = env.bitemporal || {};
      this.enforcement = bt.enforcement || 'off';
      this.requireEventTime = !!bt.require_event_time;
      this.eventCol = bt.event_time_column || '_event_time';
      this.procCol = bt.processing_time_column || '_processing_time';
    },
  };
}

export function dataProductInfrastructurePanel(catalog, schema, canManage) {
  return {
    catalog,
    schema,
    canManage: !!canManage,
    editing: false,
    record: {},
    draft: {
      storage_class: '',
      compute_runtime: '',
      access_methods_csv: '',
      region: '',
      notes: '',
    },
    error: '',

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/infrastructure', {
        silent: true,
      });
      if (res.status === 0) {
        this.error = 'Infrastructure load failed: ' + res.error;
        return;
      }
      if (res.ok) {
        const data = res.data || {};
        this.record = data.infrastructure || {};
        this.draft.storage_class = this.record.storage_class || '';
        this.draft.compute_runtime = this.record.compute_runtime || '';
        this.draft.access_methods_csv = (this.record.access_methods || []).join(',');
        this.draft.region = this.record.region || '';
        this.draft.notes = this.record.notes || '';
      }
    },

    async save() {
      this.error = '';
      const methods = this.draft.access_methods_csv
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/infrastructure', {
        method: 'PUT',
        body: {
          storage_class: this.draft.storage_class || null,
          compute_runtime: this.draft.compute_runtime || null,
          access_methods: methods,
          region: this.draft.region || null,
          notes: this.draft.notes || null,
        },
        silent: true,
      });
      if (res.status === 0) {
        this.error = 'Save failed: ' + res.error;
        return;
      }
      if (!res.ok) {
        this.error = 'Save failed (HTTP ' + res.status + ')';
        return;
      }
      this.editing = false;
      await this.reload();
    },
  };
}

export function dataProductUseCasesPanel(catalog, schema, currentUserId) {
  return {
    catalog,
    schema,
    currentUserId: currentUserId || 0,
    useCases: [],
    draft: { title: '', body: '' },
    error: '',

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/use-cases', {
        silent: true,
      });
      if (res.status === 0) {
        this.error = 'Use cases load failed: ' + res.error;
        return;
      }
      if (res.ok) this.useCases = (res.data && res.data.use_cases) || [];
    },

    async add() {
      this.error = '';
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/use-cases', {
        method: 'POST',
        body: { title: this.draft.title, body: this.draft.body },
        silent: true,
      });
      if (res.status === 0) {
        this.error = 'Share failed: ' + res.error;
        return;
      }
      if (!res.ok) {
        this.error = 'Share failed (HTTP ' + res.status + ')';
        return;
      }
      this.draft.title = '';
      this.draft.body = '';
      await this.reload();
    },

    async vote(id) {
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/use-cases/' + id + '/vote',
        { method: 'POST', silent: true }
      );
      if (res.status === 0) {
        this.error = 'Vote failed: ' + res.error;
        return;
      }
      await this.reload();
    },
  };
}

export function dataProductRatingWidget(catalog, schema, currentUserId) {
  return {
    catalog,
    schema,
    currentUserId: currentUserId || 0,
    summary: { avg: null, count: 0 },
    myScore: 0,
    myComment: '',
    error: '',

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/rating', {
        silent: true,
      });
      if (res.status === 0) {
        this.error = 'Rating load failed: ' + res.error;
        return;
      }
      if (res.ok) {
        const data = res.data || {};
        this.summary = { avg: data.avg ?? null, count: data.count || 0 };
        if (data.own) {
          this.myScore = data.own.score || 0;
          this.myComment = data.own.comment || '';
        }
      }
    },

    async save() {
      this.error = '';
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/rating', {
        method: 'PUT',
        body: { score: this.myScore, comment: this.myComment },
        silent: true,
      });
      if (res.status === 0) {
        this.error = 'Rating save failed: ' + res.error;
        return;
      }
      if (!res.ok) {
        this.error = 'Rating save failed (HTTP ' + res.status + ')';
        return;
      }
      await this.reload();
    },
  };
}

export function dataProductConsumptionPanel(catalog, schema, canManage) {
  return {
    catalog,
    schema,
    canManage: !!canManage,
    mode: 'advisory',
    modeSource: '',
    recent: [],
    error: '',

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/discovery', {
        silent: true,
      });
      if (res.status === 0) {
        this.error = 'Consumption load failed: ' + res.error;
        return;
      }
      if (res.ok) {
        const env = res.data || {};
        const policy = (env.policies && env.policies.consumption_enforcement) || {};
        this.mode = policy.value || 'advisory';
        this.modeSource = policy.source || '';
      }
      const audit = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/consumption-acknowledgements?status=open',
        { silent: true }
      );
      if (audit.status === 0) {
        this.error = 'Consumption load failed: ' + audit.error;
        return;
      }
      if (audit.ok) this.recent = (audit.data && audit.data.items) || [];
    },

    async ack(id) {
      this.error = '';
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/consumption-acknowledgements/' + id,
        { method: 'POST', silent: true }
      );
      if (res.status === 0) {
        this.error = 'Ack failed: ' + res.error;
        return;
      }
      await this.reload();
    },
  };
}

export function dataProductEventPortPanel(catalog, schema, canManage) {
  return {
    catalog,
    schema,
    canManage: !!canManage,
    hasPort: false,
    port: { name: '', format: 'ndjson' },
    subscriptions: [],
    draft: { table: '', consumer_label: '' },
    error: '',

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/output-ports', {
        silent: true,
      });
      if (res.status === 0) {
        this.error = 'Event port load failed: ' + res.error;
        return;
      }
      if (res.ok) {
        const data = res.data || {};
        const event = (data.output_ports || []).find((p) => p.kind === 'event');
        if (event) {
          this.hasPort = true;
          this.port = { name: event.name, format: event.format || 'ndjson' };
        } else {
          this.hasPort = false;
        }
      }
      if (this.hasPort) {
        const subs = await window.pqlApi.fetch(
          dpBase(this.catalog, this.schema) + '/event-subscriptions',
          { silent: true }
        );
        if (subs.status === 0) {
          this.error = 'Event port load failed: ' + subs.error;
          return;
        }
        if (subs.ok) this.subscriptions = (subs.data && subs.data.items) || [];
      }
    },

    curlSnippet() {
      return (
        'curl -N -H "Accept: application/x-ndjson" \\\n  ' +
        window.location.origin +
        dpBase(this.catalog, this.schema) +
        '/events?table=&lt;table&gt;&since=0'
      );
    },

    wsSnippet() {
      const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws';
      return (
        "const ws = new WebSocket('" +
        wsProto +
        '://' +
        window.location.host +
        '/ws/data-products/' +
        this.catalog +
        '/' +
        this.schema +
        "/events?table=<table>');\nws.onmessage = (e) => console.log(JSON.parse(e.data));"
      );
    },

    async subscribe() {
      this.error = '';
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/event-subscriptions',
        {
          method: 'POST',
          body: {
            table: this.draft.table,
            consumer_label: this.draft.consumer_label,
          },
          silent: true,
        }
      );
      if (res.status === 0) {
        this.error = 'Subscribe failed: ' + res.error;
        return;
      }
      if (!res.ok) {
        this.error = 'Subscribe failed (HTTP ' + res.status + ')';
        return;
      }
      this.draft.table = '';
      this.draft.consumer_label = '';
      await this.reload();
    },

    async pause(id) {
      await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/event-subscriptions/' + id + '/pause',
        { method: 'POST', silent: true }
      );
      await this.reload();
    },

    async resume(id) {
      await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/event-subscriptions/' + id + '/resume',
        { method: 'POST', silent: true }
      );
      await this.reload();
    },
  };
}
