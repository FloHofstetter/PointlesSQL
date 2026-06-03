/**
 * Feed page Alpine factory.
 *
 * The home activity stream. Owns the SSE
 * connection lifecycle, the day-binning getter that groups rows into
 * Today / Yesterday / dated headers, keyboard navigation (j/k/o/e/m/r/?),
 * saved-search bookmarks, and the first-run welcome card.
 *
 * Lifted from the inline ``<script>`` block in
 * ``pages/_partials/feed/scripts.html`` into this ESM module.
 * ``bootstrap.js`` re-attaches the factory to ``window.feedPage`` so
 * the template's ``x-data="feedPage()"`` keeps resolving.
 */

import { avatarFor } from '../avatars.js';
import { installFeedSocial } from '../feed_social.js';
import { renderInlineMd } from '../inline_md.js';

const DAY_MS = 24 * 60 * 60 * 1000;

function _todayStart() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function _dayLabel(rowDate, todayStart) {
  const dayStart = new Date(rowDate);
  dayStart.setHours(0, 0, 0, 0);
  const diffDays = Math.round((todayStart.getTime() - dayStart.getTime()) / DAY_MS);
  if (diffDays <= 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays > 14) return 'Earlier';
  return dayStart.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

function _dayIso(rowDate, todayStart) {
  const dayStart = new Date(rowDate);
  dayStart.setHours(0, 0, 0, 0);
  const diffDays = Math.round((todayStart.getTime() - dayStart.getTime()) / DAY_MS);
  if (diffDays > 14) return 'earlier';
  return dayStart.toISOString().slice(0, 10);
}

// Icon + label maps share the entity-kind keys with the server-side
// registry. Kept inline because the registry's Python config doesn't
// yet emit a JSON consumable.
const KIND_ICONS = {
  dp: 'bi-collection',
  table: 'bi-table',
  model: 'bi-cpu',
  branch: 'bi-bezier2',
  run: 'bi-robot',
  schema: 'bi-diagram-3',
  catalog: 'bi-archive',
  notebook: 'bi-journal-code',
  saved_query: 'bi-code-square',
  issue: 'bi-bug',
  workspace: 'bi-building',
  notification: 'bi-bell',
  comment: 'bi-chat-left-text',
  review: 'bi-star',
  notebook_revision: 'bi-pin-angle-fill',
  notebook_cell_output: 'bi-pin-angle-fill',
};
const KIND_LABELS = {
  dp: 'Data Product',
  table: 'Table',
  model: 'Model',
  branch: 'Branch',
  run: 'Run',
  schema: 'Schema',
  catalog: 'Catalog',
  notebook: 'Notebook',
  saved_query: 'Saved query',
  issue: 'Issue',
  workspace: 'Workspace',
  notification: 'Update',
  comment: 'Comment',
  review: 'Review',
  notebook_revision: 'Pinned revision',
  notebook_cell_output: 'Pinned cell',
};
// Entity kinds whose ``entity_ref`` is an opaque UUID with no
// standalone display value — the summary already names the parent
// surface, so the header line skips the link label and lets the
// kind badge carry the affordance.
const HIDE_ENTITY_REF_KINDS = new Set(['notebook_revision', 'notebook_cell_output']);
// Entity kinds whose ``entity_ref`` is an internal id (a user PK, an
// agent-review id, …) that means nothing on its own — the summary line
// already names the thing, so the object link is suppressed.
const OPAQUE_REF_KINDS = new Set(['user', 'review']);
// Short uppercase lane labels for system-led rows (rows with no human
// actor). Reads as "DATA HEALTH · demo.hr" instead of a fake bold name.
const LANE_EYEBROWS = {
  data_health: 'Data health',
  pipeline: 'Pipeline',
  approval: 'Approval',
  agent_run: 'Agent run',
  badge_award: 'Achievement',
  issue: 'Issue',
  branch: 'Governance',
  fact: 'Pinned',
};

export function feedPage(isAdmin = false) {
  const obj = {
    isAdmin: !!isAdmin,
    loaded: false,
    filter: 'all',
    kindFilter: [],
    searchDraft: '',
    rows: [],
    bufferedRows: [],
    newCount: 0,
    density: 'comfortable',
    connState: 'disconnected',
    trending: [],
    people: [],
    savedSearches: [],

    // Triage state — the "needs you" inbox + the ambient seen-cursor.
    // ``focusMode`` collapses the stream so the inbox can be drained to
    // zero; the counts + ``caughtUp`` come from the /api/feed response
    // and drive the zone header, the caught-up divider, and the badge.
    focusMode: false,
    needsActionCount: 0,
    unreadForYouCount: 0,
    unseenCount: 0,
    caughtUp: false,
    seenAt: null,

    // Coarse lane slice over the unified stream. Sits above the
    // social ``filters`` axis below; the two compose (category narrows
    // by event lane, filter narrows by audience).
    category: 'all',
    categoryCounts: {},
    categories: [
      { key: 'all', label: 'All', icon: 'bi-grid' },
      { key: 'approval', label: 'Approvals', icon: 'bi-shield-check' },
      { key: 'health', label: 'Data health', icon: 'bi-heart-pulse' },
      { key: 'social', label: 'Social', icon: 'bi-chat-dots' },
      { key: 'pipeline', label: 'Pipeline', icon: 'bi-diagram-2' },
      { key: 'governance', label: 'Governance', icon: 'bi-bank' },
    ],

    filters: [
      { key: 'all', label: 'For you', icon: 'bi-stars' },
      { key: 'mentions', label: 'Mentions', icon: 'bi-at' },
      { key: 'my', label: 'My activity', icon: 'bi-person' },
      { key: 'followed_users', label: 'Following', icon: 'bi-people' },
    ],
    kindOptions: [
      { key: 'dp', label: 'Data Products', icon: 'bi-collection' },
      { key: 'table', label: 'Tables', icon: 'bi-table' },
      { key: 'model', label: 'Models', icon: 'bi-cpu' },
      { key: 'branch', label: 'Branches', icon: 'bi-bezier2' },
      { key: 'run', label: 'Runs', icon: 'bi-robot' },
      { key: 'schema', label: 'Schemas', icon: 'bi-diagram-3' },
      { key: 'catalog', label: 'Catalogs', icon: 'bi-archive' },
      { key: 'notebook', label: 'Notebooks', icon: 'bi-journal-code' },
      { key: 'saved_query', label: 'Queries', icon: 'bi-code-square' },
      { key: 'issue', label: 'Issues', icon: 'bi-bug' },
    ],
    densityOptions: [
      { key: 'comfortable', label: 'Comfortable', icon: 'bi-list-ul' },
      { key: 'compact', label: 'Compact', icon: 'bi-list' },
      { key: 'headlines', label: 'Headlines', icon: 'bi-text-left' },
    ],

    // Internal SSE state (not reactive — Alpine doesn't need to
    // observe these).
    _sse: null,
    _sseBackoffMs: 1000,
    _sseReconnectTimer: null,
    _sseFirstFailedAt: 0,

    async init() {
      // Restore density from localStorage so the user lands on
      // whichever stream density they last used.
      try {
        const v = window.localStorage?.getItem('pql.feed.density');
        if (v && ['comfortable', 'compact', 'headlines'].includes(v)) {
          this.density = v;
        }
        const c = window.localStorage?.getItem('pql.feed.category');
        if (c && this.categories.some((cat) => cat.key === c)) {
          this.category = c;
        }
        this.focusMode = window.localStorage?.getItem('pql.feed.focus') === '1';
      } catch (e) {
        /* ignore storage errors */
      }
      this._restoreSavedSearches();
      await this.reload();
      this.loadTrending();
      this.loadPeople();
      this.connectSse();
      this._installHotkeys();
      this._installSeenAutoAdvance();
      // Tear down on page leave so the server-side queue gets released
      // promptly (htmx:beforeRequest fires on boost navs even though the
      // feed root unmounts).
      document.body.addEventListener('htmx:beforeRequest', () => this.disconnectSse(), {
        once: true,
      });
    },

    connectSse() {
      if (this._sse) return;
      try {
        const es = new EventSource('/api/notifications/stream');
        this._sse = es;
        es.addEventListener('open', () => {
          this.connState = 'connected';
          this._sseBackoffMs = 1000;
          this._sseFirstFailedAt = 0;
        });
        es.addEventListener('notification', (ev) => this._onSseMessage(ev));
        es.addEventListener('error', () => {
          if (this._sseFirstFailedAt === 0) {
            this._sseFirstFailedAt = Date.now();
          }
          this.connState =
            Date.now() - this._sseFirstFailedAt > 60_000 ? 'disconnected' : 'reconnecting';
          this.disconnectSse();
          this._scheduleReconnect();
        });
      } catch (e) {
        // EventSource unsupported — leave connState as 'disconnected'.
        console.warn('SSE unsupported:', e);
      }
    },

    disconnectSse() {
      if (this._sse) {
        try {
          this._sse.close();
        } catch (e) {
          /* ignore */
        }
        this._sse = null;
      }
    },

    _scheduleReconnect() {
      if (this._sseReconnectTimer) return;
      const wait = Math.min(this._sseBackoffMs, 30_000);
      this._sseBackoffMs = Math.min(this._sseBackoffMs * 2, 30_000);
      this._sseReconnectTimer = window.setTimeout(() => {
        this._sseReconnectTimer = null;
        this.connectSse();
      }, wait);
    },

    _onSseMessage(ev) {
      let payload;
      try {
        payload = JSON.parse(ev.data);
      } catch (e) {
        console.warn('SSE payload parse failed', e);
        return;
      }
      // A resolved-signal nudge: drop any matching open data-health /
      // pipeline cards in place so the feed self-heals without a
      // reload. No buffered row is added.
      if (payload.signal_resolved) {
        this.rows = this.rows.filter(
          (x) =>
            !(
              x.kind === 'signal' &&
              x.entity_kind === payload.source_entity_kind &&
              x.entity_ref === payload.source_entity_ref
            )
        );
        return;
      }
      // Build a feed-row-shaped object so the renderer treats the new
      // arrival like any /api/feed row. Signal pings carry an explicit
      // ``render_kind`` / ``category`` / ``severity``; social fan-out
      // pings derive them from the event type.
      const derived = this._classifyCategory(payload.event_type || '');
      const isSignal = !!payload.signal_kind;
      const row = {
        kind: isSignal ? 'signal' : 'notification',
        render_kind: payload.render_kind || this._classifyEvent(payload.event_type || ''),
        category: payload.category || derived[0],
        severity: payload.severity || derived[1],
        attention: isSignal
          ? 'act'
          : payload.attention || this._classifyAttention(payload.event_type || ''),
        event_type: payload.event_type,
        signal_kind: payload.signal_kind,
        summary_md: payload.summary_md,
        body_md: payload.summary_md,
        source_url: payload.source_url,
        data_product_id: payload.source_data_product_id,
        entity_kind: payload.source_entity_kind,
        entity_ref: payload.source_entity_ref,
        actor_user_id: payload.actor_user_id,
        actor_display_name: payload.actor_display_name || null,
        created_at: payload.created_at || new Date().toISOString(),
        read_at: null,
        is_new: true,
        _fresh: true,
      };
      this.bufferedRows.unshift(row);
      this.newCount += 1;
    },

    _classifyEvent(eventType) {
      if (!eventType) return 'notification';
      if (eventType.indexOf('mentioned') !== -1 || eventType.indexOf('.mention') !== -1) {
        return 'mention';
      }
      if (eventType === 'pointlessql.agent_run.needs_approval') return 'approval';
      if (eventType.startsWith('pointlessql.agent_run.')) return 'agent_run';
      if (eventType.startsWith('pointlessql.user.badge_')) return 'badge_award';
      if (eventType.startsWith('pointlessql.issue.')) return 'issue';
      if (eventType.startsWith('pointlessql.branch.')) return 'branch';
      if (eventType === 'notebook_revision_pinned') return 'fact';
      return 'notification';
    },

    // Mirror of services/notifications/categories.py:attention_for_event
    // — the legacy fallback for an SSE row that didn't carry a stamped
    // ``attention``. A mention is always addressed to you; anything else
    // arriving through the fan-out is ambient awareness.
    _classifyAttention(eventType) {
      return eventType && eventType.indexOf('mention') !== -1 ? 'for_you' : 'ambient';
    },

    // Mirror of services/notifications/categories.py:classify_category
    // so SSE-built rows bucket into the same lane + severity as
    // server-rendered rows without a round-trip.
    _classifyCategory(eventType) {
      if (!eventType) return ['social', 'info'];
      if (eventType.indexOf('mention') !== -1) return ['social', 'info'];
      const rules = [
        ['pointlessql.agent_run.needs_approval', 'approval', 'warn'],
        ['pointlessql.agent_run.approved', 'approval', 'info'],
        ['pointlessql.agent_run.denied', 'approval', 'warn'],
        ['pointlessql.agent_run.failed', 'pipeline', 'error'],
        ['pointlessql.agent_run.', 'pipeline', 'info'],
        ['pointlessql.alert.', 'health', 'error'],
        ['pointlessql.slo.', 'health', 'warn'],
        ['pointlessql.contract.', 'health', 'error'],
        ['pointlessql.freshness.', 'health', 'warn'],
        ['pointlessql.job_run.failed', 'pipeline', 'error'],
        ['pointlessql.ingest.failed', 'pipeline', 'error'],
        ['pointlessql.ingest.', 'pipeline', 'info'],
        ['pointlessql.branch.', 'governance', 'info'],
        ['pointlessql.agent_review.', 'governance', 'info'],
        ['pointlessql.issue.', 'social', 'info'],
        ['pointlessql.user.badge_', 'social', 'info'],
        ['pointlessql.data_product.', 'social', 'info'],
      ];
      for (const [prefix, category, severity] of rules) {
        if (eventType === prefix || eventType.startsWith(prefix)) return [category, severity];
      }
      return ['social', 'info'];
    },

    setDensity(key) {
      this.density = key;
      try {
        window.localStorage?.setItem('pql.feed.density', key);
      } catch (e) {
        /* ignore */
      }
    },

    async setFilter(key) {
      this.filter = key;
      await this.reload();
    },

    async setCategory(key) {
      this.category = key;
      try {
        window.localStorage?.setItem('pql.feed.category', key);
      } catch (e) {
        /* ignore */
      }
      await this.reload();
    },

    categoryCount(key) {
      if (key === 'all') {
        return Object.values(this.categoryCounts).reduce((sum, n) => sum + n, 0);
      }
      return this.categoryCounts[key] || 0;
    },

    // Inline approval actions. Optimistic: the card collapses in
    // place to a muted "Approved/Denied by you" line (it isn't yanked
    // mid-scroll), then drops on the next reload. The server enforces
    // require_admin regardless of the client-side gate.
    async approveRun(r) {
      if (r._busy) return;
      r._busy = true;
      const res = await window.pqlApi.fetch('/api/agent-runs/' + r.run_id + '/approve', {
        method: 'POST',
      });
      r._busy = false;
      if (!res.ok) return; // pqlApi already toasted the error
      r._resolved = 'approved';
      window.pqlToast?.success?.('Run approved.');
    },

    toggleDenyForm(r) {
      r._showDeny = !r._showDeny;
    },

    async denyRun(r) {
      if (r._busy) return;
      r._busy = true;
      const res = await window.pqlApi.fetch('/api/agent-runs/' + r.run_id + '/deny', {
        method: 'POST',
        body: { reason: (r._denyReason || '').trim() },
      });
      r._busy = false;
      if (!res.ok) return;
      r._resolved = 'denied';
      r._showDeny = false;
      window.pqlToast?.success?.('Run denied.');
    },

    // Acknowledge a data-health card — resolves the underlying signal
    // so it drops from every feed. If the condition is still truly
    // breaching, the next scheduler tick re-opens a fresh card, so an
    // ack can't permanently silence a live problem.
    async acknowledgeHealth(r) {
      if (r._busy || !r.signal_id) return;
      r._busy = true;
      const res = await window.pqlApi.fetch('/api/feed/signals/' + r.signal_id + '/ack', {
        method: 'POST',
      });
      r._busy = false;
      if (!res.ok) return;
      r._resolved = 'acked';
      window.pqlToast?.success?.('Acknowledged.');
    },

    // Retry a failed pipeline — POSTs the retry URL the signal payload
    // carries (e.g. re-run a job). Falls back to opening the source.
    async retryPipeline(r) {
      const retryUrl = r.payload && r.payload.retry_url;
      if (!retryUrl) {
        if (r.source_url) window.location.href = r.source_url;
        return;
      }
      if (r._busy) return;
      r._busy = true;
      const res = await window.pqlApi.fetch(retryUrl, { method: 'POST' });
      r._busy = false;
      if (!res.ok) return;
      r._resolved = 'retried';
      window.pqlToast?.success?.('Retry queued.');
    },

    async reload() {
      this.loaded = false;
      try {
        const params = new URLSearchParams({ filter: this.filter });
        if (this.searchDraft.trim()) params.set('q', this.searchDraft.trim());
        if (this.category && this.category !== 'all') params.set('category', this.category);
        // Multi-kind support: server still accepts a single ``kind`` param;
        // if multiple are selected we send a comma-joined list and let the
        // backend ignore the suffix until the route is widened.
        if (this.kindFilter.length > 0) {
          params.set('kind', this.kindFilter.join(','));
        }
        const res = await fetch('/api/feed?' + params.toString());
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.rows = data.rows || [];
        this.categoryCounts = data.category_counts || {};
        this.needsActionCount = data.needs_action_count || 0;
        this.unreadForYouCount = data.unread_for_you_count || 0;
        this.unseenCount = data.unseen_count || 0;
        this.caughtUp = !!data.caught_up;
        this.seenAt = data.seen_at || null;
        // Lazy-load reaction summaries for the social rows just rendered.
        this._loadReactionsFor(this.rows);
      } catch (e) {
        console.error('feed load failed', e);
        window.pqlToast?.error?.('Failed to load feed: ' + (e.message || 'unknown'));
      } finally {
        this.loaded = true;
      }
    },

    async toggleRead(r) {
      if (!r.id) {
        // Notifications carried via SSE haven't been round-tripped through
        // /api/feed yet; the id arrives on next reload.
        window.pqlToast?.error?.('Reload feed first to mark this read.');
        return;
      }
      try {
        const res = await fetch('/api/notifications/' + r.id + '/read', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        r.read_at = data.read ? new Date().toISOString() : null;
        window.pqlToast?.success?.(data.read ? 'Marked as read.' : 'Marked as unread.');
      } catch (e) {
        console.error('toggleRead failed', e);
        window.pqlToast?.error?.('Could not toggle read state.');
      }
    },

    async muteThread(r) {
      if (!r.entity_kind || !r.entity_ref) {
        window.pqlToast?.error?.('No thread to mute on this item.');
        return;
      }
      try {
        const res = await fetch('/api/feed/mute', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            entity_kind: r.entity_kind,
            entity_ref: r.entity_ref,
          }),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.rows = this.rows.filter(
          (x) => !(x.entity_kind === r.entity_kind && x.entity_ref === r.entity_ref)
        );
        window.pqlToast?.success?.(`Muted ${r.entity_ref}.`);
      } catch (e) {
        console.error('muteThread failed', e);
        window.pqlToast?.error?.('Could not mute thread.');
      }
    },

    async muteAuthor(r) {
      if (!r.actor_user_id) {
        window.pqlToast?.error?.('This item has no author.');
        return;
      }
      try {
        const res = await fetch('/api/feed/mute-author', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: r.actor_user_id }),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.rows = this.rows.filter((x) => x.actor_user_id !== r.actor_user_id);
        window.pqlToast?.success?.(`Muted ${r.actor_display_name || 'author'}.`);
      } catch (e) {
        console.error('muteAuthor failed', e);
        window.pqlToast?.error?.('Could not mute author.');
      }
    },

    async snooze(r, duration) {
      if (!r.entity_kind || !r.entity_ref) {
        window.pqlToast?.error?.('Nothing to snooze.');
        return;
      }
      try {
        const res = await fetch('/api/feed/snooze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            entity_kind: r.entity_kind,
            entity_ref: r.entity_ref,
            duration,
          }),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.rows = this.rows.filter(
          (x) => !(x.entity_kind === r.entity_kind && x.entity_ref === r.entity_ref)
        );
        const label = { '1h': '1 hour', '8h': '8 hours', '1d': '1 day' }[duration] || duration;
        window.pqlToast?.success?.(`Snoozed for ${label}.`);
      } catch (e) {
        console.error('snooze failed', e);
        window.pqlToast?.error?.('Could not snooze thread.');
      }
    },

    async copyItemLink(r) {
      try {
        const url = new URL(r.source_url || '#', window.location.origin).toString();
        await navigator.clipboard.writeText(url);
        window.pqlToast?.success?.('Link copied to clipboard.');
      } catch (e) {
        console.error('copy failed', e);
        window.pqlToast?.error?.('Could not copy link.');
      }
    },

    async copyText(text) {
      try {
        await navigator.clipboard.writeText(String(text || ''));
        window.pqlToast?.success?.('Copied to clipboard.');
      } catch (e) {
        console.error('copy failed', e);
        window.pqlToast?.error?.('Could not copy.');
      }
    },

    async markAllRead() {
      try {
        const res = await fetch('/api/notifications/mark-all-read', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        if (!res.ok && res.status !== 404) throw new Error('HTTP ' + res.status);
        // Clear the for-you inbox optimistically; this drains those rows
        // out of the "needs you" zone.  Ambient rows are left alone —
        // their newness is the seen-cursor's job, not a read flag.
        const now = new Date().toISOString();
        this.rows.forEach((r) => {
          if (r.attention === 'for_you' && !r.read_at) r.read_at = now;
        });
        this.unreadForYouCount = 0;
        window.pqlToast?.success?.('Inbox cleared.');
      } catch (e) {
        console.error('mark-all-read failed', e);
        window.pqlToast?.error?.('Could not mark all read.');
      }
    },

    drainBuffered() {
      if (this.bufferedRows.length === 0) {
        this.newCount = 0;
        return;
      }
      this.rows = this.bufferedRows.concat(this.rows);
      this.bufferedRows = [];
      this.newCount = 0;
      this._loadReactionsFor(this.rows);
      // Drained arrivals are unseen ambient activity until scrolled past
      // (Needs-you rows count via their own tiers, not the stream tally).
      this._recomputeUnseen();
      window.scrollTo({ top: 0, behavior: 'smooth' });
      // Drop the fresh-flag after the CSS animation completes (matches
      // the 1.4s ``pql-feed-item-fresh`` keyframe).
      window.setTimeout(() => {
        this.rows = this.rows.map((r) => {
          if (r._fresh) {
            const { _fresh, ...rest } = r;
            return rest;
          }
          return r;
        });
      }, 1500);
    },

    iconForKind(kind) {
      return KIND_ICONS[kind] || 'bi-circle';
    },
    kindLabel(kind) {
      return KIND_LABELS[kind] || kind;
    },

    // Item-level helpers.
    itemClasses(r) {
      const rk = r.render_kind || r.kind;
      return {
        'pql-feed-item--unread': r.kind === 'notification' && !r.read_at,
        'pql-feed-item--mention': rk === 'mention',
        'pql-feed-item--comment': rk === 'comment',
        'pql-feed-item--review': rk === 'review',
        'pql-feed-item--agent-run': rk === 'agent_run',
        'pql-feed-item--badge': rk === 'badge_award',
        'pql-feed-item--issue': rk === 'issue',
        'pql-feed-item--branch': rk === 'branch',
        'pql-feed-item--approval': rk === 'approval',
        'pql-feed-item--data-health': rk === 'data_health',
        'pql-feed-item--pipeline': rk === 'pipeline',
        'pql-feed-item--sev-warn': r.severity === 'warn',
        'pql-feed-item--sev-error': r.severity === 'error',
        'pql-feed-item--resolved': !!r._resolved,
        'pql-feed-item--fresh': !!r._fresh,
      };
    },

    // A row is "person-led" when a human/agent name owns the headline
    // (comments, reviews, mentions, branch promotions, agent runs, and
    // approvals once the principal resolves to a display name). System-led
    // rows (data-health, pipeline, badges, bare notifications) carry no
    // actor and render as a lane eyebrow + object instead of a fake name.
    isPersonLed(r) {
      return !!r.actor_display_name;
    },

    // Avatar descriptor for the header — a coloured-initials disc for
    // people, a lane-tinted glyph for system events. Consumed by the
    // template's ``rowAvatar`` binding.
    rowAvatar(r) {
      if (this.isPersonLed(r)) {
        return avatarFor({ name: r.actor_display_name, id: r.actor_user_id });
      }
      return avatarFor({
        kind: r.render_kind || r.kind,
        severity: r.severity,
        icon: this.avatarIcon(r),
      });
    },

    // Bootstrap icon for a system row's glyph avatar.
    avatarIcon(r) {
      const rk = r.render_kind || r.kind;
      if (rk === 'agent_run') return 'bi-robot';
      if (rk === 'approval') return 'bi-shield-check';
      if (rk === 'data_health') return 'bi-heart-pulse';
      if (rk === 'pipeline') return 'bi-diagram-2';
      if (rk === 'badge_award') return 'bi-award-fill';
      if (rk === 'issue') return 'bi-bug';
      if (rk === 'branch') return 'bi-bezier2';
      return this.iconForKind(r.entity_kind || r.kind);
    },

    // Short lane label shown before the object on system-led rows.
    laneEyebrow(r) {
      return LANE_EYEBROWS[r.render_kind || r.kind] || 'Update';
    },

    // Concise screen-reader label for the whole card — "who verb object".
    cardAria(r) {
      const who = r.actor_display_name || this.laneEyebrow(r);
      return [who, this.verbLabel(r), this.entityLinkLabel(r)].filter(Boolean).join(' ');
    },

    // Verb connecting a person to the object on person-led rows.
    verbLabel(r) {
      const rk = r.render_kind || r.kind;
      if (rk === 'comment') return 'commented on';
      if (rk === 'review') return 'reviewed';
      if (rk === 'mention') return 'mentioned you in';
      if (rk === 'agent_run') {
        return r.event_type && r.event_type.endsWith('.failed') ? 'failed on' : 'completed on';
      }
      if (rk === 'approval') return 'needs your approval on';
      if (rk === 'branch') return this.branchVerb(r.event_type).toLowerCase();
      if (rk === 'issue') return this.issueBadgeLabel(r.event_type).toLowerCase();
      if (rk === 'badge_award') return 'earned';
      if (rk === 'fact') return 'pinned';
      return '';
    },

    // Human-friendly object label — shortens opaque run UUIDs and hides
    // internal-id refs (user PK, review id) that mean nothing alone.
    entityLinkLabel(r) {
      const kind = r.entity_kind;
      const ref = r.entity_ref;
      if (kind && HIDE_ENTITY_REF_KINDS.has(kind)) return '';
      if (!ref) return kind ? this.kindLabel(kind) : '';
      if (kind === 'run') return 'run ' + String(ref).slice(0, 8);
      if (OPAQUE_REF_KINDS.has(kind)) return '';
      return String(ref);
    },

    // Whether to render the object link at all (suppressed for opaque
    // refs the friendly-label step blanks out).
    showObjectLink(r) {
      return !!this.entityLinkLabel(r);
    },

    // Inline-markdown → safe HTML for summary / body strings, so
    // ``**bold**`` and ``[links](…)`` render instead of showing markers.
    mdInline(s) {
      return renderInlineMd(s || '');
    },

    // Expand / collapse a clamped comment or review snippet.
    toggleSnippet(r) {
      r._expanded = !r._expanded;
    },

    // Icon for a severity-bearing status chip — paired with colour so
    // severity is glanceable, not communicated by colour alone.
    sevIcon(severity) {
      if (severity === 'error') return 'bi-x-octagon';
      if (severity === 'warn') return 'bi-exclamation-triangle';
      return 'bi-check-circle';
    },

    issueBadgeClass(eventType) {
      if (!eventType) return 'text-bg-secondary';
      if (eventType.endsWith('.opened')) return 'text-bg-success';
      if (eventType.endsWith('.closed')) return 'text-bg-secondary';
      if (eventType.endsWith('.resolved')) return 'text-bg-primary';
      return 'text-bg-secondary';
    },

    issueBadgeLabel(eventType) {
      if (!eventType) return 'Issue';
      if (eventType.endsWith('.opened')) return 'Opened';
      if (eventType.endsWith('.closed')) return 'Closed';
      if (eventType.endsWith('.resolved')) return 'Resolved';
      return 'Updated';
    },

    branchVerb(eventType) {
      if (!eventType) return 'Branch';
      if (eventType.endsWith('.created')) return 'Created';
      if (eventType.endsWith('.promoted')) return 'Promoted';
      if (eventType.endsWith('.discarded')) return 'Discarded';
      return 'Updated';
    },

    async loadTrending() {
      try {
        const res = await fetch('/api/feed/trending');
        if (!res.ok) return;
        const data = await res.json();
        this.trending = data.rows || [];
      } catch (e) {
        /* silent — the empty-state copy covers it */
      }
    },

    async loadPeople() {
      try {
        const res = await fetch('/api/feed/people');
        if (!res.ok) return;
        const data = await res.json();
        this.people = (data.rows || []).map((p) => ({ ...p, _following: false }));
      } catch (e) {
        /* silent */
      }
    },

    async followUser(p) {
      if (p._following) return;
      try {
        const res = await fetch('/api/users/' + p.id + '/follow', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        if (!res.ok && res.status !== 409) throw new Error('HTTP ' + res.status);
        p._following = true;
        window.pqlToast?.success?.('Following ' + p.display_name + '.');
      } catch (e) {
        console.error('followUser failed', e);
        window.pqlToast?.error?.('Could not follow user.');
      }
    },

    // Saved-searches: localStorage-backed bookmarked filter combos.
    _restoreSavedSearches() {
      try {
        const raw = window.localStorage?.getItem('pql.feed.savedSearches');
        if (raw) this.savedSearches = JSON.parse(raw) || [];
      } catch (e) {
        /* ignore */
      }
    },

    _persistSavedSearches() {
      try {
        window.localStorage?.setItem('pql.feed.savedSearches', JSON.stringify(this.savedSearches));
      } catch (e) {
        /* ignore */
      }
    },

    saveCurrentSearch() {
      const parts = [];
      if (this.filter && this.filter !== 'all') parts.push(this.filter);
      if (this.kindFilter.length > 0) parts.push(this.kindFilter.join('+'));
      if (this.searchDraft.trim()) parts.push('"' + this.searchDraft.trim() + '"');
      const label = parts.length === 0 ? 'All activity' : parts.join(' · ');
      const entry = {
        id: Date.now().toString(36),
        label,
        filter: this.filter,
        kindFilter: this.kindFilter.slice(),
        q: this.searchDraft.trim(),
      };
      this.savedSearches.push(entry);
      this._persistSavedSearches();
      window.pqlToast?.success?.('Saved search "' + label + '".');
    },

    applySavedSearch(s) {
      this.filter = s.filter || 'all';
      this.kindFilter = (s.kindFilter || []).slice();
      this.searchDraft = s.q || '';
      this.reload();
    },

    deleteSavedSearch(idx) {
      this.savedSearches.splice(idx, 1);
      this._persistSavedSearches();
    },

    // Keyboard navigation — j/k/o/e/m/r/?.
    _focusedIndex: -1,
    _hotkeysAttached: false,

    _installHotkeys() {
      if (this._hotkeysAttached) return;
      this._hotkeysAttached = true;
      window.addEventListener('keydown', (ev) => this._onHotkey(ev));
    },

    _onHotkey(ev) {
      // Don't hijack when the user is typing in a form field.
      const t = ev.target;
      const tag = t && t.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (t && t.isContentEditable)) {
        return;
      }
      // Don't hijack when a modifier is held — Cmd+R must reload.
      if (ev.ctrlKey || ev.metaKey || ev.altKey) return;

      const flat = this._flatRows();
      switch (ev.key) {
        case 'j':
          ev.preventDefault();
          this._focusedIndex = Math.min(flat.length - 1, this._focusedIndex + 1);
          this._highlightFocused();
          break;
        case 'k':
          ev.preventDefault();
          this._focusedIndex = Math.max(0, this._focusedIndex - 1);
          this._highlightFocused();
          break;
        case 'o':
        case 'Enter': {
          const row = flat[this._focusedIndex];
          if (row && row.source_url) {
            ev.preventDefault();
            window.location.href = row.source_url;
          }
          break;
        }
        case 'e': {
          const row = flat[this._focusedIndex];
          if (row && row.kind === 'notification') {
            ev.preventDefault();
            this.toggleRead(row);
          }
          break;
        }
        case 'm': {
          const row = flat[this._focusedIndex];
          if (row) {
            ev.preventDefault();
            this.muteThread(row);
          }
          break;
        }
        case 'r':
          ev.preventDefault();
          {
            const input = document.querySelector('.pql-feed-search');
            if (input) input.focus();
          }
          break;
        case '?':
          ev.preventDefault();
          if (window.bootstrap?.Modal) {
            const el = document.getElementById('pql-feed-help-modal');
            if (el) window.bootstrap.Modal.getOrCreateInstance(el).show();
          }
          break;
        default:
          break;
      }
    },

    _flatRows() {
      // Match rendered DOM order: the pinned "needs you" zone first,
      // then the day-grouped stream (hidden in focus mode).
      const out = [...this.needsYouRows];
      if (!this.focusMode) {
        for (const day of this.groupedDays) {
          for (const r of day.rows) out.push(r);
        }
      }
      return out;
    },

    _highlightFocused() {
      // Drop the focus class from every item, then apply to the n-th
      // rendered card. Card DOM order matches ``_flatRows`` because Alpine
      // renders ``groupedDays`` in the same order.
      const cards = document.querySelectorAll('.pql-feed-item');
      cards.forEach((el) => {
        el.classList.remove('pql-feed-item--focused');
      });
      const target = cards[this._focusedIndex];
      if (target) {
        target.classList.add('pql-feed-item--focused');
        target.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    },

    // Is this row part of the finite "needs you" inbox?  Unresolved
    // act work (approvals / open signals) always is; a for_you
    // notification is until it's read.  The resolved/read transition is
    // what drains the zone live.
    _inNeedsYou(r) {
      if (r._resolved) return false;
      if (r.attention === 'act') return true;
      return r.attention === 'for_you' && !r.read_at;
    },

    // The pinned inbox zone — act rows first (by severity), then
    // for_you (newest first).  A row appears here OR in the stream,
    // never both.
    get needsYouRows() {
      const sevRank = { error: 0, warn: 1, info: 2 };
      return this.rows
        .filter((r) => this._inNeedsYou(r))
        .slice()
        .sort((a, b) => {
          const aAct = a.attention === 'act' ? 0 : 1;
          const bAct = b.attention === 'act' ? 0 : 1;
          if (aAct !== bAct) return aAct - bAct;
          if (aAct === 0) {
            const sa = sevRank[a.severity] ?? 3;
            const sb = sevRank[b.severity] ?? 3;
            if (sa !== sb) return sa - sb;
          }
          return String(b.created_at).localeCompare(String(a.created_at));
        });
    },

    // The infinite ambient stream — everything not pinned into the
    // inbox zone above.
    get streamRows() {
      return this.rows.filter((r) => !this._inNeedsYou(r));
    },

    // Composite stream key, shared by the x-for :key and the caught-up
    // boundary lookup so the two never drift.
    _rowKey(r) {
      return (
        r.kind +
        ':' +
        r.created_at +
        ':' +
        r.event_type +
        ':' +
        (r.entity_ref || '') +
        ':' +
        (r.comment_id || '')
      );
    },

    // Key of the first already-seen stream row — where the "you're all
    // caught up" divider sits.  Null when every stream row is still new
    // (nothing seen yet to divide against).
    get _streamBoundaryKey() {
      const seen = this.streamRows.find((r) => !r.is_new);
      return seen ? this._rowKey(seen) : null;
    },

    // True for the single row the caught-up divider renders above.
    isCaughtUpBoundary(r) {
      const key = this._streamBoundaryKey;
      return key !== null && this._rowKey(r) === key;
    },

    // Re-derive the unseen tally from the current rows after a local
    // mutation (drain / scroll-advance), and refresh ``caughtUp``.
    _recomputeUnseen() {
      this.unseenCount = this.streamRows.filter((r) => !!r.is_new).length;
      this.caughtUp =
        this.unseenCount === 0 && this.needsActionCount === 0 && this.unreadForYouCount === 0;
    },

    // Scroll-driven seen-cursor: as the reader scrolls past new stream
    // rows they become "seen", so advance the cursor to the newest row
    // that has crossed the read line.  Reads the DOM fresh on each scan
    // so it survives Alpine re-renders, and only ever moves forward.
    _installSeenAutoAdvance() {
      if (this._seenAutoAttached) return;
      this._seenAutoAttached = true;
      window.addEventListener('scroll', () => this._scheduleSeenScan(), { passive: true });
    },

    _scheduleSeenScan() {
      if (this._seenScanPending) return;
      this._seenScanPending = true;
      window.setTimeout(() => {
        this._seenScanPending = false;
        this._scanSeen();
      }, 500);
    },

    _scanSeen() {
      if (!this.loaded || this.focusMode || this.unseenCount === 0) return;
      // Only count what the reader could actually have looked at.
      if (document.hidden || (document.hasFocus && !document.hasFocus())) return;
      const cards = document.querySelectorAll('.pql-feed-rows .pql-feed-item[data-feed-ts]');
      let maxTs = null;
      cards.forEach((el) => {
        // A card whose top has scrolled to/above the comfortable read
        // line counts as seen.
        if (el.getBoundingClientRect().top < 120) {
          const ts = el.getAttribute('data-feed-ts');
          if (ts && (maxTs === null || ts > maxTs)) maxTs = ts;
        }
      });
      if (maxTs) this._advanceSeenTo(maxTs);
    },

    async _advanceSeenTo(ts) {
      // Forward-only: a stale scan can never rewind the cursor.
      if (this.seenAt && String(ts) <= String(this.seenAt)) return;
      let changed = false;
      this.rows.forEach((r) => {
        if (r.is_new && String(r.created_at) <= String(ts)) {
          r.is_new = false;
          changed = true;
        }
      });
      if (!changed) return;
      this.seenAt = ts;
      this._recomputeUnseen();
      try {
        await fetch('/api/feed/seen', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ at: ts }),
        });
      } catch (e) {
        /* best-effort — the cursor re-syncs on the next reload */
      }
    },

    // Advance the seen-cursor to now and optimistically collapse the
    // stream to "caught up": every rendered row is marked seen and the
    // unseen tally zeroed, so the divider jumps to the top without a
    // reload.
    async markCaughtUp() {
      try {
        const res = await fetch('/api/feed/seen', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.seenAt = data.seen_at || this.seenAt;
      } catch (e) {
        console.error('markCaughtUp failed', e);
        window.pqlToast?.error?.('Could not update your place.');
        return;
      }
      this.rows.forEach((r) => {
        r.is_new = false;
      });
      this.unseenCount = 0;
      this.caughtUp = this.needsActionCount === 0 && this.unreadForYouCount === 0;
    },

    toggleFocusMode() {
      this.focusMode = !this.focusMode;
      try {
        window.localStorage?.setItem('pql.feed.focus', this.focusMode ? '1' : '0');
      } catch (e) {
        /* ignore */
      }
    },

    // Reflect the live "needs you" total in the browser-tab title so a
    // pending count is visible even when the feed is scrolled away or in
    // a background tab.  Driven by x-effect, so it tracks the zone
    // draining without a manual call.  htmx restores the plain title
    // from the next page's <title> on navigation.
    updateTitle() {
      const n = (this.needsActionCount || 0) + (this.unreadForYouCount || 0);
      const base = 'Home · PointlesSQL';
      try {
        document.title = n > 0 ? `(${n}) ${base}` : base;
      } catch (e) {
        /* ignore */
      }
    },

    get groupedDays() {
      const todayStart = _todayStart();
      const groups = new Map();
      for (const r of this.streamRows) {
        const rowDate = new Date(r.created_at);
        if (Number.isNaN(rowDate.getTime())) continue;
        const iso = _dayIso(rowDate, todayStart);
        if (!groups.has(iso)) {
          groups.set(iso, {
            iso,
            label: _dayLabel(rowDate, todayStart),
            rows: [],
          });
        }
        groups.get(iso).rows.push(r);
      }
      // Sort groups: "today" first, then iso desc, then "earlier" last.
      const ordered = Array.from(groups.values());
      ordered.sort((a, b) => {
        if (a.iso === 'earlier') return 1;
        if (b.iso === 'earlier') return -1;
        return a.iso < b.iso ? 1 : -1;
      });
      return ordered;
    },
  };

  // Mixin: emoji reactions + reply, wired to the polymorphic social API.
  installFeedSocial(obj);
  return obj;
}
