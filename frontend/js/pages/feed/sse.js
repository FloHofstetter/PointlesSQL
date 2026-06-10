/**
 * Feed page — SSE connection lifecycle + event classification for the feed.
 *
 * One slice of the ``feedPage`` Alpine factory.  ``installFeedSse`` mutates
 * the shared component object in place (the project's mixin-installer
 * pattern, mirroring ``installFeedSocial``); ``this`` resolves to the live
 * component at call time, so the method bodies are unchanged from the
 * original single-file factory.
 */

export function installFeedSse(state) {
  Object.assign(state, {
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
  });
}
