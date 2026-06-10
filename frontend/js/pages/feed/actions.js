/**
 * Feed page — User actions on feed rows (approve/deny/mute/snooze/read/reload).
 *
 * One slice of the ``feedPage`` Alpine factory.  ``installFeedActions`` mutates
 * the shared component object in place (the project's mixin-installer
 * pattern, mirroring ``installFeedSocial``); ``this`` resolves to the live
 * component at call time, so the method bodies are unchanged from the
 * original single-file factory.
 */

export function installFeedActions(state) {
  Object.assign(state, {
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
  });
}
