// Overview-tab panels: lifecycle, bitemporal, consumption-enforcement,
// event-port, infrastructure, use-cases + rating.  Each factory is
// self-contained and fetches its own sub-endpoint, matching the
// existing dataProductPortsPanel / dataProductSemanticPanel style.

function dpBase(catalog, schema) {
  return '/api/data-products/'
    + encodeURIComponent(catalog)
    + '/'
    + encodeURIComponent(schema);
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
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/lifecycle');
        if (!res.ok) {
          this.error = 'Failed to load lifecycle (HTTP ' + res.status + ')';
          return;
        }
        const data = await res.json();
        this.state = data.state || 'active';
        this.changedAt = data.changed_at || '';
        this.replacement = data.replacement_uri || null;
        const reachable = data.reachable_targets || data.allowed_targets || [];
        this.targets = reachable
          .filter((t) => t !== this.state)
          .map((t) => _stateToSlug(this.state, t));
        this.history = data.history || [];
      } catch (e) {
        this.error = 'Lifecycle load failed: ' + e.message;
      }
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
      try {
        const res = await fetch(
          dpBase(this.catalog, this.schema) + '/lifecycle/' + encodeURIComponent(target),
          { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' },
        );
        if (!res.ok) {
          this.error = 'Transition failed (HTTP ' + res.status + ')';
          return;
        }
        await this.reload();
      } catch (e) {
        this.error = 'Transition failed: ' + e.message;
      }
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
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/discovery');
        if (!res.ok) return;
        const env = await res.json();
        const bt = env.bitemporal || {};
        this.enforcement = bt.enforcement || 'off';
        this.requireEventTime = !!bt.require_event_time;
        this.eventCol = bt.event_time_column || '_event_time';
        this.procCol = bt.processing_time_column || '_processing_time';
      } catch (e) {
        this.error = 'Bitemporal load failed: ' + e.message;
      }
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
    draft: { storage_class: '', compute_runtime: '', access_methods_csv: '', region: '', notes: '' },
    error: '',

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/infrastructure');
        if (res.ok) {
          const data = await res.json();
          this.record = data.infrastructure || {};
          this.draft.storage_class = this.record.storage_class || '';
          this.draft.compute_runtime = this.record.compute_runtime || '';
          this.draft.access_methods_csv = (this.record.access_methods || []).join(',');
          this.draft.region = this.record.region || '';
          this.draft.notes = this.record.notes || '';
        }
      } catch (e) {
        this.error = 'Infrastructure load failed: ' + e.message;
      }
    },

    async save() {
      this.error = '';
      const methods = this.draft.access_methods_csv
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/infrastructure', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            storage_class: this.draft.storage_class || null,
            compute_runtime: this.draft.compute_runtime || null,
            access_methods: methods,
            region: this.draft.region || null,
            notes: this.draft.notes || null,
          }),
        });
        if (!res.ok) {
          this.error = 'Save failed (HTTP ' + res.status + ')';
          return;
        }
        this.editing = false;
        await this.reload();
      } catch (e) {
        this.error = 'Save failed: ' + e.message;
      }
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
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/use-cases');
        if (res.ok) this.useCases = (await res.json()).use_cases || [];
      } catch (e) {
        this.error = 'Use cases load failed: ' + e.message;
      }
    },

    async add() {
      this.error = '';
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/use-cases', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: this.draft.title, body: this.draft.body }),
        });
        if (!res.ok) {
          this.error = 'Share failed (HTTP ' + res.status + ')';
          return;
        }
        this.draft.title = '';
        this.draft.body = '';
        await this.reload();
      } catch (e) {
        this.error = 'Share failed: ' + e.message;
      }
    },

    async vote(id) {
      try {
        await fetch(dpBase(this.catalog, this.schema) + '/use-cases/' + id + '/vote', {
          method: 'POST',
        });
        await this.reload();
      } catch (e) {
        this.error = 'Vote failed: ' + e.message;
      }
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
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/rating');
        if (res.ok) {
          const data = await res.json();
          this.summary = { avg: data.avg ?? null, count: data.count || 0 };
          if (data.own) {
            this.myScore = data.own.score || 0;
            this.myComment = data.own.comment || '';
          }
        }
      } catch (e) {
        this.error = 'Rating load failed: ' + e.message;
      }
    },

    async save() {
      this.error = '';
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/rating', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ score: this.myScore, comment: this.myComment }),
        });
        if (!res.ok) {
          this.error = 'Rating save failed (HTTP ' + res.status + ')';
          return;
        }
        await this.reload();
      } catch (e) {
        this.error = 'Rating save failed: ' + e.message;
      }
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
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/discovery');
        if (res.ok) {
          const env = await res.json();
          const policy = (env.policies && env.policies.consumption_enforcement) || {};
          this.mode = policy.value || 'advisory';
          this.modeSource = policy.source || '';
        }
        const audit = await fetch(
          dpBase(this.catalog, this.schema) + '/consumption-acknowledgements?status=open',
        );
        if (audit.ok) this.recent = (await audit.json()).items || [];
      } catch (e) {
        this.error = 'Consumption load failed: ' + e.message;
      }
    },

    async ack(id) {
      this.error = '';
      try {
        await fetch(
          dpBase(this.catalog, this.schema) + '/consumption-acknowledgements/' + id,
          { method: 'POST' },
        );
        await this.reload();
      } catch (e) {
        this.error = 'Ack failed: ' + e.message;
      }
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
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/output-ports');
        if (res.ok) {
          const data = await res.json();
          const event = (data.output_ports || []).find((p) => p.kind === 'event');
          if (event) {
            this.hasPort = true;
            this.port = { name: event.name, format: event.format || 'ndjson' };
          } else {
            this.hasPort = false;
          }
        }
        if (this.hasPort) {
          const subs = await fetch(
            dpBase(this.catalog, this.schema) + '/event-subscriptions',
          );
          if (subs.ok) this.subscriptions = (await subs.json()).items || [];
        }
      } catch (e) {
        this.error = 'Event port load failed: ' + e.message;
      }
    },

    curlSnippet() {
      return (
        'curl -N -H "Accept: application/x-ndjson" \\\n  '
        + window.location.origin
        + dpBase(this.catalog, this.schema)
        + '/events?table=&lt;table&gt;&since=0'
      );
    },

    wsSnippet() {
      const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws';
      return (
        "const ws = new WebSocket('"
        + wsProto
        + '://'
        + window.location.host
        + '/ws/data-products/'
        + this.catalog
        + '/'
        + this.schema
        + "/events?table=<table>');\nws.onmessage = (e) => console.log(JSON.parse(e.data));"
      );
    },

    async subscribe() {
      this.error = '';
      try {
        const res = await fetch(
          dpBase(this.catalog, this.schema) + '/event-subscriptions',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              table: this.draft.table,
              consumer_label: this.draft.consumer_label,
            }),
          },
        );
        if (!res.ok) {
          this.error = 'Subscribe failed (HTTP ' + res.status + ')';
          return;
        }
        this.draft.table = '';
        this.draft.consumer_label = '';
        await this.reload();
      } catch (e) {
        this.error = 'Subscribe failed: ' + e.message;
      }
    },

    async pause(id) {
      await fetch(
        dpBase(this.catalog, this.schema) + '/event-subscriptions/' + id + '/pause',
        { method: 'POST' },
      );
      await this.reload();
    },

    async resume(id) {
      await fetch(
        dpBase(this.catalog, this.schema) + '/event-subscriptions/' + id + '/resume',
        { method: 'POST' },
      );
      await this.reload();
    },
  };
}
