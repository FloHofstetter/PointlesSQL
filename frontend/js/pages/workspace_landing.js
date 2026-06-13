// Auto-extracted from frontend/templates/pages/workspace_landing.html.
// Exports: workspaceLanding.
//
// Catalog-browser search hit types that resolve to a pinnable social
// target, mapped to the entity kind the pins API expects. Other hit
// types (jobs, users, topics, …) are pinned from their own pages.
const PIN_HIT_KINDS = {
  catalog: 'catalog',
  schema: 'schema',
  table: 'table',
  data_product: 'dp',
};

export function workspaceLanding(slug) {
  return {
    slug: slug,
    pins: [],
    pinsLoaded: false,
    activity: [],
    activityLoaded: false,
    showAddPin: false,
    pinQuery: '',
    pinResults: [],
    pinSearching: false,
    pinError: '',
    _pinSearchTimer: null,
    _pinSearchSeq: 0,
    async init() {
      await Promise.all([this.refreshPins(), this.refreshActivity()]);
    },
    openAddPin() {
      this.pinQuery = '';
      this.pinResults = [];
      this.pinError = '';
      this.showAddPin = true;
    },
    onPinQueryInput() {
      if (this._pinSearchTimer) clearTimeout(this._pinSearchTimer);
      this.pinError = '';
      const q = this.pinQuery.trim();
      if (!q) {
        this.pinResults = [];
        this.pinSearching = false;
        return;
      }
      this.pinSearching = true;
      this._pinSearchTimer = setTimeout(() => this.searchPinTargets(), 200);
    },
    async searchPinTargets() {
      const q = this.pinQuery.trim();
      if (!q) {
        this.pinResults = [];
        this.pinSearching = false;
        return;
      }
      const seq = ++this._pinSearchSeq;
      const res = await window.pqlApi.fetch('/api/search?q=' + encodeURIComponent(q) + '&limit=50');
      if (seq !== this._pinSearchSeq) return; // a newer keystroke won
      const hits = (res && res.ok && Array.isArray(res.data) ? res.data : []).filter(
        (h) => h.type in PIN_HIT_KINDS
      );
      this.pinResults = hits;
      this.pinSearching = false;
    },
    async pinHit(hit) {
      const kind = PIN_HIT_KINDS[hit.type];
      if (!kind) return;
      this.pinError = '';
      const res = await window.pqlApi.fetch('/api/workspaces/' + slug + '/pins', {
        method: 'POST',
        body: JSON.stringify({ kind: kind, ref: hit.label }),
      });
      if (res && res.ok) {
        this.showAddPin = false;
        this.pinQuery = '';
        this.pinResults = [];
        await this.refreshPins();
      } else {
        this.pinError = (res && res.error) || 'Could not pin that entity.';
      }
    },
    async refreshPins() {
      this.pinsLoaded = false;
      const res = await window.pqlApi.fetch('/api/workspaces/' + slug + '/pins');
      this.pins = (res && res.ok && res.data && res.data.pins) || [];
      this.pinsLoaded = true;
    },
    async refreshActivity() {
      this.activityLoaded = false;
      const res = await window.pqlApi.fetch('/api/workspaces/' + slug + '/activity');
      this.activity = (res && res.ok && res.data && res.data.activity) || [];
      this.activityLoaded = true;
    },
    async removePin(targetId) {
      await window.pqlApi.fetch('/api/workspaces/' + slug + '/pins/' + targetId, {
        method: 'DELETE',
      });
      await this.refreshPins();
    },
  };
}
