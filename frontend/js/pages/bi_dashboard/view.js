// AI/BI dashboard view page factory (/bi/{slug} + /bi/public/{token}).
//
// One factory serves both modes: ``config.publicToken`` flips the
// widget-data URL onto the anonymous token-credentialed path and the
// publish controls simply aren't rendered by the public template.
// Gridstack loads lazily inside init() so a CDN outage degrades to a
// vertical stack of cards instead of a dead page; the data fetches go
// through pqlApi (its CSRF/workspace headers are meta-tag-optional,
// so the wrapper also works on the chromeless public layout).

import { pqlApi, toast } from '../../api.js';
import { refreshWidgets } from './render.js';

export function biDashboardView(config) {
  return {
    slug: config.slug,
    publicToken: config.publicToken || null,
    widgets: config.widgets || [],
    published: !!config.isPublished,
    shareToken: config.shareToken || null,
    canEdit: !!config.canEdit,
    schedule: {
      open: false,
      loading: false,
      saving: false,
      exists: false,
      form: { cron_expr: '0 8 * * *', is_active: true, deliver_inapp: true, webhook_url: '' },
    },
    snapshots: { open: false, loading: false, capturing: false, items: [] },

    async init() {
      await this._initGrid();
      await this.refreshAll();
    },

    async _initGrid() {
      const el = this.$root.querySelector('[data-bi-grid]');
      if (!el) return;
      try {
        const mod = await import('gridstack');
        const GridStack = mod.GridStack || mod.default;
        GridStack.init({ staticGrid: true, margin: 6, cellHeight: 90, column: 12 }, el);
        el.classList.add('pql-bi-grid--ready');
      } catch (e) {
        // Grid library unavailable: the server-rendered cards stack
        // vertically (fallback CSS) and the data still renders.
      }
    },

    dataUrl(widgetId) {
      if (this.publicToken) {
        return `/api/bi/public/${this.publicToken}/widgets/${widgetId}/data`;
      }
      return `/api/bi/dashboards/${this.slug}/widgets/${widgetId}/data`;
    },

    paramValues() {
      const values = {};
      for (const input of this.$root.querySelectorAll('[data-bi-param]')) {
        if (input.value !== '') values[input.getAttribute('data-bi-param')] = input.value;
      }
      return values;
    },

    async refreshAll() {
      await refreshWidgets(this.$root, this.widgets, (id) => this.dataUrl(id), this.paramValues());
    },

    applyParams() {
      this.refreshAll();
    },

    async setPublish(publish) {
      const res = await pqlApi.fetch(`/api/bi/dashboards/${this.slug}/publish`, {
        method: 'POST',
        body: { publish: publish },
      });
      if (!res.ok) return;
      this.published = !!res.data.is_published;
      this.shareToken = res.data.public_token;
      toast('success', publish ? 'Dashboard published.' : 'Dashboard unpublished.');
    },

    async copyPublicLink() {
      if (!this.shareToken) return;
      const url = `${window.location.origin}/bi/public/${this.shareToken}`;
      try {
        await navigator.clipboard.writeText(url);
        toast('success', 'Public link copied.');
      } catch (e) {
        toast('error', 'Could not copy the link — copy it from the address bar instead.');
      }
    },

    async openSchedule() {
      this.snapshots.open = false;
      this.schedule.open = true;
      this.schedule.loading = true;
      const res = await pqlApi.fetch(`/api/bi/dashboards/${this.slug}/schedule`);
      this.schedule.loading = false;
      if (!res.ok) return;
      const row = res.data.schedule;
      this.schedule.exists = !!row;
      if (row) {
        this.schedule.form = {
          cron_expr: row.cron_expr || '',
          is_active: !!row.is_active,
          deliver_inapp: !!row.deliver_inapp,
          webhook_url: row.webhook_url || '',
        };
      }
    },

    async saveSchedule() {
      const form = this.schedule.form;
      this.schedule.saving = true;
      const res = await pqlApi.fetch(`/api/bi/dashboards/${this.slug}/schedule`, {
        method: 'PUT',
        body: {
          cron_expr: form.cron_expr,
          is_active: !!form.is_active,
          deliver_inapp: !!form.deliver_inapp,
          webhook_url: form.webhook_url || null,
        },
      });
      this.schedule.saving = false;
      if (!res.ok) return;
      this.schedule.exists = true;
      this.schedule.open = false;
      toast('success', 'Refresh schedule saved.');
    },

    async removeSchedule() {
      const res = await pqlApi.fetch(`/api/bi/dashboards/${this.slug}/schedule`, {
        method: 'DELETE',
      });
      if (!res.ok) return;
      this.schedule.exists = false;
      this.schedule.form = {
        cron_expr: '0 8 * * *',
        is_active: true,
        deliver_inapp: true,
        webhook_url: '',
      };
      this.schedule.open = false;
      toast('success', 'Refresh schedule removed.');
    },

    async openSnapshots() {
      this.schedule.open = false;
      this.snapshots.open = true;
      await this.loadSnapshots();
    },

    async loadSnapshots() {
      this.snapshots.loading = true;
      const res = await pqlApi.fetch(`/api/bi/dashboards/${this.slug}/snapshots`);
      this.snapshots.loading = false;
      if (!res.ok) return;
      this.snapshots.items = res.data.snapshots || [];
    },

    async snapshotNow() {
      this.snapshots.capturing = true;
      const res = await pqlApi.fetch(`/api/bi/dashboards/${this.slug}/snapshots`, {
        method: 'POST',
        body: {},
      });
      this.snapshots.capturing = false;
      if (!res.ok) return;
      toast('success', 'Snapshot captured.');
      await this.loadSnapshots();
    },

    snapshotHref(id) {
      return `/bi/${this.slug}/snapshots/${id}`;
    },

    formatTs(ts) {
      if (!ts) return '';
      const d = new Date(ts);
      return Number.isNaN(d.getTime()) ? String(ts) : d.toLocaleString();
    },
  };
}
